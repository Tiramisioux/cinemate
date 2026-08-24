# CODE MAP — cinemate (Python)

**Session:** S02 · **Snapshot:** `origin/dev` @ `02b5a39`
**Audience:** a competent Python developer who has never seen this repo.

Everything here is traced from source with `path:line` citations. No runtime claims —
there is no Pi in this review (KICKOFF §2.1).

---

## 1. The one-paragraph version

CineMate is a **single Python process** (`src/main.py`) that supervises an external C++
recorder (`cinepi-raw`) and paints an on-camera GUI. It does not capture frames itself.
It owns the *controls* and the *display*; cinepi-raw owns the *sensor and the writer*.
The two communicate exclusively through **Redis** — cinemate writes intent, cinepi-raw
writes actuals, and every UI surface is a view onto those keys. Boot is one long
straight-line function, `run_application()`, that constructs ~20 components in a fixed
order and then blocks forever on `signal.pause()`.

---

## 2. Entry and process shape

| Step | Where |
|---|---|
| `main()` | `main.py:1053` |
| run-lock acquisition (single-instance guard) | `main.py:84` `_acquire_run_lock()` |
| the whole application | `main.py:646` `run_application(args, log_queue)` |
| block forever | `main.py:1049-1050` `from signal import pause; pause()` |

There is exactly one live entry point. `src/stream.py` looks like a second one and is
dead — see F-013.

The process integrates with **systemd** as a notify-type service: `_systemd_notify`
(`main.py:138`), `systemd_ready` (`:160`), `mark_runtime_ready` (`:168`). Startup
failures are persisted and mirrored to the local console
(`persist_startup_failure` `:211`, `mirror_failure_to_local_console` `:302`) — this is
KICKOFF §9 principle 3 ("fail visible") implemented deliberately at the boot layer.

It also negotiates with **Plymouth** (the boot splash) for framebuffer ownership:
`plymouth_is_running()` `:336`, `wait_for_plymouth_to_quit()` `:358`. This matters for
ADR-001 — it is direct evidence that framebuffer ownership is already contended at boot
and is handled by *waiting for the other party to exit*, not by sharing.

---

## 3. Boot sequence — construction order

`run_application()` is ~400 lines of straight-line construction. Order is load-bearing;
later components take earlier ones as constructor arguments.

| # | Component | Line | Notes |
|---|---|---|---|
| 1 | `load_settings(SETTINGS_FILE)` | `:647` | `settings.jsonc` is read before anything else |
| 2 | splash (framebuffer or text) | `:670-679` | deferred if Plymouth is up |
| 3 | `get_raspberry_pi_model()` | `:684` | |
| 4 | `start_hotspot(settings)` | `:688` | |
| 5 | **`initialize_system()`** → 6 components | `:691` | see below |
| 6 | Redis seeding — ~10 `set_value` calls | `:698-731` | pi_model, anamorphic, audio gain, zoom, HDMI source, 4× HDR, recording_time |
| 7 | `ssd_monitor.refresh()` | `:735` | before cinepi-raw launches, so the storage profile is known |
| 8 | `CinePi(...)` + `.start_all()` | `:738-740` | launches the C++ recorder |
| 9 | `CinePiController(...)` | `:746` | the central controller; 11 constructor args |
| 10 | `StoragePreroll(...)` | `:758` | |
| 11 | `ComponentInitializer(...)` (GPIO) | `:777` | |
| 12 | `CommandExecutor(...)` + `.start()` | `:783-786` | the text-command dispatcher; CLI thread |
| 13 | `SerialHandler(...)` + `.start()` | `:789-795` | callback → `command_executor.handle_received_data` |
| 14 | `_relay_rec_over_serial` thread | `:806-807` | daemon; polls `is_recording` at 20 Hz |
| 15 | `StatusBroadcaster(...)` | `:816-822` | UDP :8888, optional |
| 16 | `usb_monitor.check_initial_devices()` | `:825` | |
| 17 | `AnalogControls(...)` | `:834` | pots |
| 18 | `cinepi_controller.mount()` | `:852` | |
| 19 | Plymouth handoff / splash teardown | `:854-889` | |
| 20 | `RedisListener(...)` | `:892` | the read side; 2084 LOC |
| 21 | `BatteryMonitor()` | `:900` | |
| 22 | `SimpleGUI(...)` | `:903` | 11 args; the HDMI GUI |
| 23 | `I2cOled` (optional) | `:918-920` | |
| 24 | `QuadRotaryController` (optional) | `:923-926` | |
| 25 | `create_app(...)` + socketio thread | `:931-936` | **only if `network_available()`** |
| 26 | `Mediator(...)` | `:938` | 8 args |
| 27 | `storage_preroll.mark_startup_ready()` | `:944` | |
| 28 | `mark_runtime_ready("Cinemate running")` | `:945` | systemd READY |

`initialize_system()` (`main.py:605-632`) builds the six lowest-level components in this
order: `RedisController` → `SensorDetect` → `SSDMonitor` → `USBMonitor` → `GPIOOutput` →
`DmesgMonitor` (started immediately at `:629`).

### The seam that matters most

**`RedisController` is constructed first and injected into almost everything.** It is the
widest fan-in in the repo — 10 importing modules (CENSUS.md §4). If you are changing how
state moves, you are changing this object or its callers.

---

## 4. Thread inventory and lifecycle

| Thread | Started | Daemon | Stopped in `cleanup()` | Joined |
|---|---|---|---|---|
| `RedisController._listen` (pub/sub) | in `__init__`, `redis_controller.py:188` | — | **no** (F-022) | no |
| `DmesgMonitor` | `main.py:629` | — | yes `:984` | yes `:999` |
| `CommandExecutor` (CLI) | `main.py:786` | — | yes `:986` | yes `:1000` |
| `SerialHandler` | `main.py:795` | — | yes `:1005` | yes `:1008` |
| `_relay_rec_over_serial` | `main.py:807` | **yes** | no — infinite `while True`, no stop flag | no |
| `StatusBroadcaster` | `main.py:822` | — | yes `:988` | yes `:1001` |
| `SimpleGUI` | internal | — | yes `:991` | via its own `join_timeout` |
| `I2cOled` | `main.py:920` | — | yes `:1010-1013` | yes |
| `QuadRotaryController` | `main.py:926` | — | yes `:1014-1017` | yes |
| socketio / Flask (`stream`) | `main.py:936` | **no** (F-024) | **no** | no |
| splash `_animate` | `main.py:467` | yes | yes `:1022-1024` | yes |
| `RedisListener` internals | via constructor | — | **no `stop()` exists** (F-023) | no |
| `USBMonitor` / `SSDMonitor` internals | via constructors | — | **`stop()` exists, never called** (F-023) | no |

Classes that subclass `threading.Thread`: `DmesgMonitor`, `SerialHandler`,
`StatusBroadcaster`, `CommandExecutor`, `SimpleGUI`, `CinePiProcess`. Everything else
manages threads internally or not at all.

### Shutdown path

`cleanup()` (`main.py:954`) is registered with `atexit` (`:1035`) **and** called from
`handle_exit` on SIGINT/SIGTERM (`:1037-1042`), guarded by a `cleanup_called` flag.
`handle_exit` restores the default handler then re-raises via `os.kill(os.getpid(), sig)`.

Two behaviours worth knowing:

- It branches on `system_shutdown_in_progress()` (`:960`). On a real power-down it uses a
  2.0 s join timeout and skips the console handoff; otherwise 0.25 s.
- It writes three Redis keys on the way out (`:974-979`): `is_recording=0`, `is_writing=0`,
  and `fps_last = fps`. That is the only state deliberately persisted across a restart.

**The gaps are F-022, F-023 and F-024** — four components with live threads are never
told to stop. The `os.kill` in `handle_exit` masks the consequence, so this is a
correctness/tidiness issue rather than an observed hang; the hang claim is `unverified`
without a Pi.

---

## 5. Control surfaces → dispatcher → controller

This is the part most worth internalising. **There are two independent paths to
`CinePiController`, and only one of them is serialised.**

```
 PATH A — text commands, serialised under CommandExecutor._dispatch_lock
 ┌─────────────┐
 │ CLI (stdin) │──┐
 └─────────────┘  │
 ┌─────────────┐  │   ┌──────────────────────────────┐
 │ Serial (UART)│──┼──▶│ CommandExecutor              │──▶ CinePiController
 └─────────────┘  │   │ handle_received_data()       │
 ┌─────────────┐  │   │  _dispatch_lock, 2 s timeout │
 │ Web API/HTTP│──┘   └──────────────────────────────┘
 └─────────────┘

 PATH B — direct method calls, NOT serialised
 ┌──────────────────┐
 │ GPIO buttons/sw. │──┐
 ├──────────────────┤  │
 │ Analog pots      │──┼──────────────────────────────▶ CinePiController
 ├──────────────────┤  │        (direct .method() calls)
 │ Quad rotary (I²C)│──┤
 ├──────────────────┤  │
 │ Keyboard  (DEAD) │──┘   ← class never instantiated, F-031
 └──────────────────┘
```

**Path A** — `CommandExecutor` (`cli_commands.py:10`, a `Thread`) owns a command table
(`:24`) and `handle_received_data()` (`:186`). It acquires `_dispatch_lock` with a 2 s
timeout at `:218` and releases at `:257`; on timeout the command is **dropped with a
warning** (`:219`). Its own comment (`:17-20`) states the intent: give HTTP callers the
ordering guarantee CLI and serial had by construction.

- CLI: `CommandExecutor.run()` reads stdin, `:317`/`:362`
- Serial: `SerialHandler(callback=command_executor.handle_received_data)`, `main.py:790`,
  invoked at `serial_handler.py:175`
- Web: `command_executor` is passed into `create_app(...)`, `main.py:932`

**Path B** — hardware surfaces hold a `cinepi_controller` reference and call methods on it
directly. **Three are live** (GPIO, analog pots, quad rotary); the fourth, `keyboard.py`,
is dead — class `Keyboard` is never instantiated and `module.keyboard` is never imported
(F-031, found in S03). An earlier revision of this map listed it as live; that was wrong. None of them touches `_dispatch_lock` (grep confirms the lock appears
only in `cli_commands.py`). So a GPIO button press and an HTTP request can enter the
controller concurrently, with only the latter serialised. Whether that is actually
harmful depends on controller-internal locking — **not established in S02, and it needs
a Pi to observe.** Recorded as F-025 with the consequence marked `probable`. **S11a
(desk-only) then found the internal locking directly (F-268/F-269): 3 serialised paths, 6
bypassing modules, 9 lock sites guarding 3 narrow concerns, no general fallback. PI-007/F-285
confirmed the consequence on hardware: a live analog pot 100% starves explicit CLI commands
on the same key, not an occasional race. F-025 is now `confirmed`, `high`, not `probable`,
`medium`.**

### The reflective-dispatch contract (important)

Both GPIO and the quad rotary resolve controller methods **by name, from strings in
`settings.jsonc`**:

```
quad_rotary_controller.py:114
    method = getattr(self.cinepi_controller, method_name, None)
    if method: method(*action.get("args", []))
    else:      self.logger.error("method %s not found", method_name)
```

`gpio_input.py:38-49,74-75` does the same via `extract_action_method()`.

The names live in the user-editable config:

```
settings.jsonc:256   "press_action":        { "method": "rec" }
settings.jsonc:269   "single_click_action": { "method": "set_resolution" }
settings.jsonc:270   "double_click_action": { "method": "restart_cinemate" }
settings.jsonc:271   "triple_click_action": { "method": "reboot" }
settings.jsonc:272   "hold_action":         { "method": "toggle_mount" }
settings.jsonc:278   "state_on_action":     { "method": "set_zoom", "args": [2] }
```

**Consequences a newcomer must know:**

1. `CinePiController`'s public method names are a **user-facing API**. Renaming one
   silently breaks every camera whose `settings.jsonc` references it. This is a large
   part of why that file is 2626 LOC and 94 methods — and why refactoring it is riskier
   than its size alone suggests.
2. The failure mode is a **log line**, not a visible error (`logger.error("method %s not
   found")`). A typo in `settings.jsonc` yields a button that silently does nothing —
   a violation of KICKOFF §9 principle 3. Recorded as F-026.
3. This explains `_test/test_quad_rotary_controller_setting_names.py` — it exists to
   guard exactly this contract, and it is one of the 27 tests that never run (F-006).

---

## 6. State ownership — who writes what

| State | Owner | Mechanism |
|---|---|---|
| Live camera state (fps, iso, shutter, wb, resolution, rec…) | **Redis** | `RedisController`, 84 `ParameterKey` members |
| Intent (what the operator asked for) | cinemate → Redis | `set_value` from controller/surfaces |
| Actuals (what the sensor/writer did) | cinepi-raw → Redis | read by `RedisListener` |
| User configuration | `settings.jsonc` | `config_loader.py`, read at boot |
| Per-surface view state | each UI | e.g. `SimpleGUI` layout constants |

`RedisController` (`redis_controller.py:160`) is more than a client:

- keeps a **local cache** primed at `_prime_cache()` (`:181`); `get_value()` (`:214`)
  reads the cache, **not Redis**, under `self.lock`
- runs a pub/sub listener thread `_listen()` (`:188`) to keep the cache fresh
- `set_value()` (`:229`) writes Redis, publishes on channel `cp_controls`, updates the
  cache, and short-circuits if the value is unchanged (`:238-239`)
- owns the recording timer (`_run_recording_timer` `:361`) and timecode formatting
  (`nanoseconds_to_timecode` `:303`)

**Four distinct Redis access patterns exist**, which is one of the review's clearer
consistency problems:

1. `set_value(ParameterKey.X.value, …)` — the intended path
2. `set_value("raw_string", …)` — accepted, because `set_value` does
   `key.value if isinstance(key, ParameterKey) else str(key)` (`:235`). F-015.
3. module-level string constants — `REDIS_KEY_FSCK_STATUS` (`ssd_monitor.py:44`),
   `CAPTURE_GAIN_REDIS_KEY` (`usb_monitor.py:14`), `RECORDER_VU_REDIS_KEY`
   (`simple_gui.py:21`)
4. **reaching past the controller** to the raw client — `self.redis_controller.r`
   (`simple_gui.py:1166-1172`), which bypasses the cache entirely. F-020.

`usb_monitor.py` additionally constructs its own `StrictRedis` at four separate call
sites (`:141,439,458,581`) instead of using the injected controller.

---

## 7. The seams — where changes are supposed to be made

| I want to change… | Go to | Also update |
|---|---|---|
| a camera parameter's behaviour | `cinepi_controller.py` (94 methods) | `settings.jsonc` if the method name changes — it is a public contract (§5) |
| a new piece of live state | `ParameterKey` (`redis_controller.py:18`) | `docs/redis-keys.md` (F-014), and the C++ side if cinepi-raw writes it |
| what the HDMI GUI shows | `simple_gui.py` | `template.html` CSS vars if it is a colour (F-007) |
| what the web GUI shows | `app/templates/template.html` + `app/main/routes.py` | `simple_gui.py` for parity |
| a new CLI/serial/HTTP command | `CommandExecutor`'s table (`cli_commands.py:24`) | `docs/cli-commands.md` |
| a new GPIO button/switch | `settings.jsonc` `hardware_controls` | nothing in code, if the method already exists |
| boot order / a new component | `run_application()` (`main.py:646`) | `cleanup()` (`:954`) — easy to forget, see F-023 |
| a new user-facing setting | `settings.jsonc` + `settings.schema.json` | `config_loader.py` defaults, `docs/settings-json.md` |

**The most common mistake this layout invites:** adding a component to
`run_application()` and forgetting `cleanup()`. Four components already have that bug
(F-023). The two functions are 300 lines apart in the same file with no structural link
between them.

---

## 8. What S02 did not establish

- ~~`CinePiController` internals. 2626 LOC, 94 methods, only its API surface was
  mapped. Whether it locks internally — which determines how serious F-025 is — is open.~~
  **Settled: S11a traced it (F-268/F-269, no hardware), PI-007/F-285 confirmed the
  consequence on hardware. See CINEMATE-PHILOSOPHY.md.**
- **`RedisListener` internals.** 2084 LOC, the entire read side, untraced.
- **`cinepi_multi.py` / `CinePi` process supervision.** How the C++ child is launched,
  monitored, and restarted is S03's boundary but partly lives here.
- **The web layer.** `create_app` wiring was confirmed (6 args) but routes, events and
  the API surface belong to S07.
- **Anything runtime.** Thread timing, lock contention, and shutdown behaviour are all
  `unverified` — see `PI-VERIFICATION-QUEUE.md`.
