# Web API

The camera answers HTTP on port `5000`. Any [CineMate CLI](cli-commands.md) command line can be sent over HTTP instead. Replies are plain text, so a microcontroller needs no JSON parser.

```bash
curl -d "rec" http://cinepi.local:5000/api/v1/cmd
```

## Address

| | |
|---|---|
| Hotspot SSID / password | `CinePi` / `11111111` (set in [`settings.jsonc`](settings-json.md) under `system.wifi_hotspot`) |
| Camera address | `cinepi.local`, or `10.42.0.1` on the camera's own hotspot |
| API port | `5000` |
| Status broadcast port | `8888/udp` |
| Base URL | `http://cinepi.local:5000/api/v1/` |

!!! note "Which address to use"

    Use `cinepi.local` from a laptop or phone. The installer enables `avahi-daemon`, so it
    resolves on a joined network and on the hotspot, and it keeps working when the camera's
    IP changes.

    Hard-code `10.42.0.1` in microcontroller firmware. On the camera's own hotspot that
    address never changes, so a name lookup buys nothing, and resolving a `.local` name needs
    an mDNS resolver an ESP32 or Pico W build may not have. See
    [Building control units](building-control-units.md).

    `system.https.enabled` moves the whole web server, API included, to `https://` on the
    same port `5000` with a self-signed certificate. Leave it off for microcontroller clients.

## Send a command

One endpoint: `/api/v1/cmd`. Send the command line exactly as you would type it in the CLI.

```bash
curl -d "set iso 800" http://cinepi.local:5000/api/v1/cmd
curl -d "set fps 48" http://cinepi.local:5000/api/v1/cmd
```

| Method | Use it from | Shape |
|---|---|---|
| POST | Microcontrollers, scripts | Body is the command line verbatim, no URL encoding and no JSON. `Content-Type` is not checked (the `curl -d` lines above send `application/x-www-form-urlencoded` and work); send `text/plain` when you can |
| GET | Browsers, quick tests | `/api/v1/cmd?c=inc+iso` — spaces may be `+` or `%20` |

### Replies

| HTTP | Body | Meaning |
|---|---|---|
| 200 | `ok` | Command matched and was dispatched |
| 200 | `ok requested <x>, live value is <y>` | Dispatched, but the value read back had not stuck. Usually a pot or a lock writing the same parameter |
| 400 | `err unknown command` | No command matched (an empty body counts as this) |
| 400 | `err bad argument` | Matched, but the argument was the wrong type |
| 400 | `err missing argument` | Command requires an argument |
| 401 | `err unauthorized` | A token is configured and yours was wrong or absent |
| 403 | `err blocked` | Destructive command, blocked by settings |
| 429 | `err rate limited` | Too many commands per second |
| 503 | `err busy` | Another command still held the dispatcher after 2 seconds |

Add `?json=1` for `{"ok":true,"cmd":"set iso 800","message":""}` instead.

!!! warning "200 means dispatched, not applied"

    `set log` restarts the camera when idle, and defers to the end of the take while
    recording. `set resolution` restarts it only when the new mode changes the aspect ratio;
    a same-aspect change is seamless. The reply arrives before any restart finishes. Read the
    new state back with `/api/v1/get/<key>`.

## Read a value

```
GET /api/v1/get/is_recording   →   1
```

Returns the raw value as text. This is the endpoint for a tally light. Unknown keys return `404` and `err unknown key`. Key names are the [Redis keys](redis-keys.md).

### Many values at once

| Request | Result |
|---|---|
| `GET /api/v1/status` | JSON object of every key |
| `GET /api/v1/status?keys=is_recording,iso,fps` | JSON object of only those keys |
| `GET /api/v1/status?keys=iso,fps&fmt=text` | `key=value` lines instead of JSON |

Use `?keys=` on memory-constrained devices; a full snapshot is all 88 keys, a couple of kilobytes of JSON. Unknown keys in `?keys=` are skipped silently rather than erroring, so one firmware build works across CineMate versions.

### `/commands` and `/hello`

`GET /api/v1/commands` returns every command the camera accepts, as JSON `[{"name":"set iso","arg":"int"}, ...]`, or one name per line with `?fmt=text`. It is built live from the running command table.

`GET /api/v1/hello` returns `cinemate 3.4.0 api=1 sensor=imx585 cams=1 rec=0`. A configured `token` guards it, like every other `/api/v1/` route.

## Keep a device in sync

| Method | Best for | Cost on the device | Cost on the camera |
|---|---|---|---|
| **UDP broadcast** | Tally lights, displays, many devices | ~10 lines, no connection state | One send serves every device |
| **SSE** | One to four devices needing every change | Open socket, read lines | One server thread per client |
| **Polling `/get/<key>`** | Anything; always works | Trivial | One short request per poll |

**Use the UDP broadcast unless you have a reason not to.** One plain-text line goes to port `8888`, at both the `wlan0` subnet broadcast address and `255.255.255.255`, at 5 Hz plus immediately on change (coalesced to at most 10 Hz):

```
is_recording=1 iso=800 fps=24.0 shutter_angle_actual=180.0 recording_time_tod=01:02:03:04 space_left=412 drop_frame_count=0 is_mounted=1
```

The keys are the [Redis keys](redis-keys.md), unabbreviated, truncated at 500 bytes. That line is the default set; pick your own in [`settings.jsonc`](settings-json.md).

### Server-sent events

`GET /api/v1/events` returns `text/event-stream`: one `data: key=value` per changed key, with a `: ping` heartbeat every 15 seconds. One thread is held per open connection, so SSE is capped (`max_sse_clients`, default 4). Beyond the cap the server returns `503` and `err too many clients`.

## Settings

The stock [`settings.jsonc`](settings-json.md) already carries a full `system.web_api` block under `system`, with exactly the values below — edit it there. The same values are also hard-coded in `src/module/web_api_settings.py`, and they apply if you delete the block or fill it in only partly, so every field is optional.

| Field | Default | Effect |
|---|---|---|
| `enabled` | `true` | `false` unregisters `/api/v1` entirely, which also breaks the [Web GUI](web-gui.md)'s controls, since they post to it. The UDP broadcast has its own switch |
| `token` | `""` | When set, every `/api/v1/` request must carry `X-Cinemate-Token` |
| `allow_destructive` | `false` | When false, blocks `reboot`, `shutdown`, `erase`, `format`, matched on the first word of the command line |
| `max_commands_per_sec` | `20` | Per-client (per source IP) limit on `/api/v1/cmd`, over a sliding one-second window |
| `max_sse_clients` | `4` | Concurrent `/events` connections |
| `broadcast.enabled` | `true` | The UDP status broadcast, switched independently of `enabled` |
| `broadcast.port` | `8888` | UDP destination port |
| `broadcast.hz` | `5` | Heartbeat rate when nothing is changing |
| `broadcast.keys` | see below | Which keys appear in the UDP line |

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
      "keys": ["is_recording", "iso", "fps", "shutter_angle_actual",
               "recording_time_tod", "space_left", "drop_frame_count", "is_mounted"]
    }
  }
}
```

!!! danger "The hotspot password is public knowledge"

    CineMate ships with the hotspot password `11111111`, so anyone within Wi-Fi range can
    reach the API. `allow_destructive` therefore defaults to **false**: `format` and `erase`
    cannot be triggered remotely on a stock unit. Change the hotspot password in
    `system.wifi_hotspot` before enabling destructive commands, and set a `token` if the
    camera will be used somewhere crowded.

## Other control paths

| Path | Transport | Same command lines? |
|---|---|---|
| CineMate CLI | `cinemate` in a terminal | Yes |
| Serial | Tx/Rx pins or USB, 9600 baud | Yes |
| **Web API** | HTTP on port 5000 | **Yes** |
| Web GUI | Browser on port 5000, posts to `/api/v1/cmd` | Yes |
| GPIO / rotary / I²C | [`settings.jsonc`](settings-json.md) mappings | No — see below |

The CLI, serial, the Web API and the [Web GUI](web-gui.md) funnel into one dispatcher. GPIO buttons, rotary encoders and the I²C quad encoder are wired up differently: `settings.jsonc` names a controller method (`{"method": "set_zoom"}`), called directly rather than as a command line, so a command name is not a valid value there.

**Next step:** [Building control units](building-control-units.md) — wiring and firmware for a physical controller.
