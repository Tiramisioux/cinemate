# Cinemate Web API — implementation plan

**Status:** implemented on `feature/web-api` (phases 1–5, code-complete). Phase 0 hardware verification did not run this session — the Pi was unreachable (see section 10) — so the gateway IP, the hotspot/`network_available()` startup ordering, and every `curl`/`nc` hardware gate in section 8 are still unconfirmed against real hardware. Unit tests cover the dispatcher, argument coercion, destructive-command gating, token/rate-limit gating, `?keys=` filtering, SSE lifecycle and UDP payload assembly — run `python3 -m unittest discover -s _test -p "test_*.py"` from the `cinemate` repo root.
**Owning repo:** `cinemate` only. `cinepi-raw` and `libcamera` are untouched.
**Target branch:** `feature/web-api`, cut from `cinemate` `dev`.
**Source of truth:** this file. User-facing contract lives in [`docs/web-api.md`](../../docs/web-api.md); operator manual in [`docs/building-control-units.md`](../../docs/building-control-units.md). If any of the three disagree, this file wins for internals, `docs/web-api.md` wins for the wire format.

---

## 1. Goal

Let ESP32, Raspberry Pi Pico W, other Pis, and phones send **the same commands as the CineMate CLI** over the Pi's Wi-Fi hotspot, and receive live camera status back. Optimise for how little code the *client* needs, not for REST purity.

Non-goal: replacing the browser GUI. Non-goal: a new command vocabulary.

---

## 2. Verified starting state

All facts below were read from `cinemate` `dev` @ `07d3186d`. Do not re-derive them; do re-verify any line number that has moved.

| # | Fact | Evidence |
|---|---|---|
| F1 | A single string→action dispatcher already exists | `CommandExecutor.handle_received_data(line)` — `src/module/cli_commands.py:169` |
| F2 | CLI **and** serial already share that one dispatcher | `src/main.py:761-773` — `SerialHandler(callback=command_executor.handle_received_data)` |
| F3 | ~55 commands in one dict, longest-prefix match, typed args | table `src/module/cli_commands.py:33-127`; matcher `:182-187`; type coercion `:200-221` |
| F4 | `rec` is special-cased before generic dispatch | `src/module/cli_commands.py:195-196` → `handle_rec_command` `:238` |
| F5 | Flask + SocketIO already bind `0.0.0.0:5000` | `src/main.py:888-890` |
| F6 | The web server only starts if `wlan0` or `eth0` already has an IP | `src/main.py:887`, `network_available()` `:548` |
| F7 | The existing web UI **bypasses** the command table | `src/module/app/main/events.py` hand-writes `change_iso`, `change_fps`, `container_tap`→`rec()` |
| F8 | No JSON/REST endpoint exists today; `/` returns HTML only | `src/module/app/main/routes.py` |
| F9 | A change-push event already exists | `RedisController.redis_parameter_changed` (`Event` class) — `src/module/redis_controller.py:146,165,207,294` |
| F10 | Serial's outbound status is **only** `rec`/`stop` | `_relay_rec_over_serial`, `src/main.py:775-785` |
| F11 | `handle_received_data` returns `None`; both callers ignore the return | `src/module/cli_commands.py:169-221` |
| F12 | Hotspot is nmcli shared mode on `wlan0`, SSID/pw from settings | `src/module/wifi_hotspot.py:230-235`; `settings.json → system.wifi_hotspot` |
| F13 | **No eventlet/gevent installed** → Flask-SocketIO runs `threading` async mode on the Werkzeug dev server | `requirements.txt`; `allow_unsafe_werkzeug=True` at `src/main.py:889` |
| F14 | `command_executor` is constructed at `src/main.py:761`, well before `create_app` at `:888` | ordering for dependency injection already works |
| F15 | Serial input is debounced 100 ms per port; HTTP would have no such guard | `src/module/serial_handler.py:132-141` |

### Consequences

- **F1/F2/F11** — the feature is an adapter, not a new subsystem. The only change to the dispatcher is giving it a return value.
- **F13** — every open SSE connection holds a Werkzeug thread. SSE must be capped; a UDP broadcaster is the scalable push path.
- **F15** — HTTP needs its own rate limit. A rotary encoder on an ESP32 will emit 50+ `inc iso`/s.
- **F3/F4** — dispatch, arg coercion and the `rec` special case must **not** be reimplemented in the API layer. Call `handle_received_data` and nothing else.

---

## 3. Architecture

```
stdin ─────┐
serial ────┼──► CommandExecutor.handle_received_data(line) ──► CinePiController ──► Redis
HTTP ──────┘            (one threading.Lock)

RedisController.redis_parameter_changed ──┬──► SSE  /api/v1/events   (few clients)
                                          └──► UDP broadcast :8888   (many clients)
```

One dispatcher, three inbound transports, two outbound transports.

---

## 4. Wire format

Plain text by default. A microcontroller should never need a JSON parser for the common path.

### 4.1 `POST /api/v1/cmd` — primary IoT path

| | |
|---|---|
| Content-Type | `text/plain` |
| Body | the CLI line verbatim, e.g. `set iso 800` |
| Why POST | no URL encoding on the device: `http.POST("set iso 800")` |

### 4.2 `GET /api/v1/cmd?c=<urlencoded>` — browser / curl path

Accepts `+` or `%20` for spaces. Same semantics as POST.

### 4.3 Responses (both forms)

`Content-Type: text/plain`, no trailing newline required by clients.

| HTTP | Body | Meaning |
|---|---|---|
| 200 | `ok` | matched and dispatched |
| 200 | `ok <message>` | dispatched, handler returned a message |
| 400 | `err unknown command` | no prefix matched the table |
| 400 | `err bad argument` | matched, argument failed type coercion |
| 400 | `err missing argument` | command requires an arg, none given |
| 401 | `err unauthorized` | token configured and wrong/absent |
| 403 | `err blocked` | destructive command, `allow_destructive` is false |
| 429 | `err rate limited` | over `max_commands_per_sec` |
| 503 | `err busy` | dispatch lock not acquired within timeout |

Add `?json=1` for `{"ok":true,"cmd":"set iso 800","message":""}`.

**200 means "dispatched", not "the camera reached that state."** Commands that restart the camera (`set resolution`, `set log`, `set hdr profile`) return before the restart completes. Clients confirm via `/api/v1/get/<key>` or the push channel.

### 4.4 `GET /api/v1/get/<key>` — parser-free single value

Returns the raw Redis value as text. `GET /api/v1/get/is_recording` → `1`.
`404` + `err unknown key` if the key is not a `ParameterKey` member.
This is the tally-light endpoint. No JSON, no allocation.

### 4.5 `GET /api/v1/status`

| Query | Result |
|---|---|
| *(none)* | JSON object of every `ParameterKey` and its value |
| `?keys=is_recording,iso,fps` | JSON object of only those keys |
| `?fmt=text` | `key=value` lines instead of JSON |

Unknown keys in `?keys=` are omitted silently, not an error — lets one firmware talk to several Cinemate versions.

### 4.6 `GET /api/v1/commands`

JSON array `[{"name":"set iso","arg":"int"},{"name":"rec","arg":null}, ...]`, built live from `CommandExecutor.commands`. `?fmt=text` → one name per line.
Lets an M5Stack build its own menu instead of hardcoding one.

### 4.7 `GET /api/v1/hello`

Text: `cinemate <version> api=1 sensor=<model> cams=<n> rec=<0|1>`.
Cheap identity/liveness check so a device can tell "wrong IP" from "Cinemate not started".

### 4.8 `GET /api/v1/events` — SSE

- `Content-Type: text/event-stream`
- One `data: key=value\n\n` per changed key
- `: ping\n\n` heartbeat every 15 s so devices detect dead links
- Over `max_sse_clients` → `503` + `err too many clients`

### 4.9 UDP status broadcast

| | |
|---|---|
| Port | `8888` (configurable) |
| Destination | subnet broadcast of `wlan0`, plus `255.255.255.255` |
| Payload | one line, space-separated `key=value`, **under 500 bytes** so it never fragments |
| Default keys | `rec iso fps shutter tc space drops mounted` |
| Cadence | on change, coalesced to max 10 Hz, plus heartbeat at `hz` (default 5) |

Example payload:

```
rec=1 iso=800 fps=24.0 shutter=180.0 tc=01:02:03:04 space=412 drops=0 mounted=1
```

No parser needed, no connection state, one packet serves every device on the hotspot. This is the recommended default for tally and status displays.

---

## 5. Settings

New block in `src/settings.json` and `src/settings.schema.json`:

```json
"system": {
  "web_api": {
    "enabled": true,
    "token": "",
    "allow_destructive": false,
    "max_commands_per_sec": 20,
    "max_sse_clients": 4,
    "broadcast": {
      "enabled": true,
      "port": 8888,
      "hz": 5,
      "keys": ["is_recording", "iso", "fps", "shutter_a_actual",
               "recording_tc_tod", "space_left", "drop_frame_count", "is_mounted"]
    }
  }
}
```

Defaults must be safe on a stock unit: hotspot password ships as `11111111`, so `allow_destructive` defaults to **false**.

`allow_destructive: false` blocks exactly: `reboot`, `shutdown`, `erase`, `format`. `unmount` stays allowed — it is routine and reversible.

Missing `web_api` block must behave as the defaults above. Do not require users to edit `settings.json` to get a working API.

---

## 6. File-by-file changes

| File | Change | Risk |
|---|---|---|
| `src/module/cli_commands.py` | `handle_received_data` returns `(ok: bool, msg: str)`. Add `self._dispatch_lock = threading.Lock()`, held across the handler call. Every current `logging.info("... not found")`-style branch also produces a return value. | **Low** — F11: both existing callers ignore returns |
| `src/module/app/api.py` | **new**. Flask blueprint `api_v1`, url_prefix `/api/v1`. Holds §4.1–4.8. | new file |
| `src/module/app/__init__.py` | `create_app(redis_controller, cinepi_controller, simple_gui, sensor_detect, command_executor, settings)`; register `api_v1` | Low |
| `src/main.py` | pass `command_executor` and `settings` into `create_app` (F14: ordering already correct); start `StatusBroadcaster` | Low |
| `src/module/status_broadcast.py` | **new**. Thread; subscribes to `redis_parameter_changed`; coalesces; sends UDP. | new file |
| `src/settings.json`, `src/settings.schema.json` | `system.web_api` block | Low |
| `docs/web-api.md`, `docs/building-control-units.md`, `mkdocs.yml` | already written — remove the "not implemented" banners when Phase 5 lands | Docs |
| `src/module/web_api_settings.py` | **new, not in the original plan.** `DEFAULT_WEB_API_SETTINGS` + `web_api_settings()` factored out of `api.py` so `status_broadcast.py` and `main.py` don't have to import `module.app` (which imports `flask_socketio`) just to read one settings block. Both `api.py` and `status_broadcast.py` import from here. | Low, additive |
| `src/module/redis_controller.py` | **new, not in the original plan.** Added `Event.unsubscribe()` (the class only had `subscribe`/`emit`). Required for `/api/v1/events`: without it, every SSE client that disconnects leaves its callback permanently subscribed — a real memory/CPU leak on a device meant to run for days. `emit()` now iterates `list(self._handlers)` so unsubscribing during emit is safe. No existing caller unsubscribes today, so this is purely additive. | Low, additive |

### Explicitly do not

- Do **not** add per-parameter endpoints (`/api/v1/iso`). The command string is the API.
- Do **not** reimplement parsing, coercion, or the `rec` special case in `api.py`.
- Do **not** migrate `events.py` onto the new API in this branch. It is a bigger change and belongs in a follow-up.
- Do **not** add eventlet or gevent. That changes how the whole server runs and is out of scope.
- Do **not** touch `SerialHandler` or `_relay_rec_over_serial`.

---

## 7. Concurrency

Serial is single-threaded, so commands are naturally serialised today. HTTP invites concurrent calls.

Use a **single `threading.Lock` around dispatch**, not a queue:

- preserves today's ordering guarantee
- still allows a synchronous return value (a queue would force async responses)
- contention is negligible at these rates
- acquire with `timeout=2.0`; on timeout return `503 err busy`

The lock lives in `CommandExecutor` so the CLI and serial paths get the same protection for free.

---

## 8. Phases and gates

Each phase must pass its gate before the next starts.

| Phase | Deliverable | Gate |
|---|---|---|
| **0** | Verify runtime assumptions on the Pi | `ip addr show wlan0` while the hotspot is up records the real gateway IP; `ss -tlnp \| grep 5000` shows the bind; a phone on `CinePi` can load `:5000` |
| **1** | Return values + dispatch lock + `POST/GET /api/v1/cmd` | `curl -d "rec" http://<pi>:5000/api/v1/cmd` → `ok`, camera records; `curl -d "set iso 800"` → `ok`, `iso` changes; `curl -d "nonsense"` → 400 `err unknown command`; **CLI and serial still work unchanged** |
| **2** | `/get/<key>`, `/status`, `/commands`, `/hello` | `curl .../get/is_recording` → `0` or `1`; `/status?keys=iso,fps` returns only those two; `/commands` lists every entry in the table |
| **3** | UDP broadcaster | `nc -ul 8888` on a laptop joined to `CinePi` prints a line ≥5×/s and reacts to `rec` within 200 ms |
| **4** | Settings gating, token, rate limit | `format` → 403 with default settings; 100 rapid commands → some 429; wrong token → 401 |
| **5** | SSE, docs banner removal, changelog | ESP32 on the bench toggles REC and lights a tally LED |

Phases 1–2 alone are a complete, useful wireless control surface. Phase 3 is what makes tally trivial.

---

## 9. Test notes

- Unit-testable without hardware: the dispatcher return values, arg coercion, the destructive-command allowlist, the `?keys=` filter, and UDP payload assembly. Prefer these over end-to-end tests.
- `handle_received_data` needs a fake controller; the command table is built from bound methods at `__init__`, so construct `CommandExecutor` with a mock `cinepi_controller`/`cinepi_app`.
- Regression that must not break: `SerialHandler`'s callback signature and the CLI thread in `CommandExecutor.run()`.

---

## 10. Open questions

1. **Hotspot gateway IP is still unverified.** Phase 0 did not run this session — the Pi at `pi@cinepi.local` was unreachable (Mac on ethernet, not joined to the `CinePi` hotspot, mDNS not resolving, no other route to the device). `docs/web-api.md` and `docs/building-control-units.md` still document `10.42.0.1` as the NetworkManager shared-mode default, flagged inline as unconfirmed. **Whoever runs Phase 0 on real hardware must confirm `ip addr show wlan0` while the hotspot is up and correct both doc pages if it differs.**
2. **F6 / hotspot-vs-web-server startup ordering — inspected, not hardware-verified.** `start_hotspot(settings)` runs at `src/main.py:678`; `network_available()` gates `create_app`/`socketio.run` at `src/main.py:903` (post-implementation line numbers on `feature/web-api`). `WiFiHotspotManager.create_hotspot()` shells out to `nmcli d wifi hotspot ...` via a plain (blocking) `subprocess.run`, which by default does not return until NetworkManager reports the connection activated — so by inspection, `wlan0` should already be addressed well before the `network_available()` check runs, given the further ~200 lines of `initialize_system()`/controller/GPIO setup in between. This reads as already-correct, not a bug, but it is **not confirmed on hardware** — Phase 0's `ip addr show wlan0` + `ss -tlnp | grep 5000` check is still the thing that proves it either way.
3. Should `/api/v1/cmd` accept several newline-separated commands in one body? Useful for a preset button ("set iso 800\nset fps 24\nset shutter a 180"). Not implemented — deferred, as originally planned, unless asked for.
4. **New, from implementation:** the UDP broadcaster (`src/module/status_broadcast.py`) runs independently of the `network_available()` gate — it is started unconditionally (subject only to `system.web_api.broadcast.enabled`) right after the serial relay thread in `src/main.py`, and it re-resolves the hotspot subnet's broadcast address on every send rather than caching it once at thread start. So even if question 2 above ever turns out to be a real ordering bug that blocks the HTTP server, the UDP tally/status broadcast should still self-heal once `wlan0` gets an address. This is also unverified on hardware — Phase 3's `nc -ul 8888` check is the proof.
