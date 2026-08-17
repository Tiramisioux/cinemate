# Web API

The web API exposes **the same commands as the [Cinemate terminal commands](cli-commands.md)** over the Wi-Fi hotspot. Anything you can type into the Cinemate CLI, or send over serial, you can send over HTTP.

It is designed so a microcontroller needs as little code as possible. Responses are plain text by default — no JSON parser required for the common path.

For a step-by-step guide to building a physical controller, see [Building control units](building-control-units.md).

## Address

| | |
|---|---|
| Hotspot SSID / password | `CinePi` / `11111111` (set in [`settings.jsonc`](settings-json.md) under `system.wifi_hotspot`) |
| Camera address on the hotspot | `10.42.0.1` (NetworkManager shared-mode default — not yet confirmed against a running hotspot; see `dev_projects/web-api/IMPLEMENTATION-PLAN.md` section 10) |
| API port | `5000` |
| Status broadcast port | `8888/udp` |
| Base URL | `http://10.42.0.1:5000/api/v1/` |

!!! note ""

    On a wired or joined network the camera is also reachable as `cinepi.local:5000`.
    Use the numeric hotspot address on microcontrollers — mDNS resolution is an extra
    dependency and is not reliable on every ESP32 build.

## Sending commands

### POST — the path for devices

Send the command line verbatim as the request body. No URL encoding.

```
POST /api/v1/cmd
Content-Type: text/plain

set iso 800
```

### GET — the path for browsers and curl

```
GET /api/v1/cmd?c=set+iso+800
```

Spaces may be `+` or `%20`.

```bash
curl -d "rec" http://10.42.0.1:5000/api/v1/cmd
curl -d "set fps 48" http://10.42.0.1:5000/api/v1/cmd
curl "http://10.42.0.1:5000/api/v1/cmd?c=inc+iso"
```

### Responses

| HTTP | Body | Meaning |
|---|---|---|
| 200 | `ok` | Command matched and was dispatched |
| 200 | `ok <message>` | Dispatched, with a message from the handler |
| 400 | `err unknown command` | No command matched |
| 400 | `err bad argument` | Matched, but the argument was the wrong type |
| 400 | `err missing argument` | Command requires an argument |
| 401 | `err unauthorized` | A token is configured and yours was wrong or absent |
| 403 | `err blocked` | Destructive command, blocked by settings |
| 429 | `err rate limited` | Too many commands per second |
| 503 | `err busy` | Another command was still running |

Add `?json=1` to get `{"ok":true,"cmd":"set iso 800","message":""}` instead.

!!! warning "200 means dispatched, not applied"

    `set resolution` and `set log` restart the camera. The response
    returns before the restart finishes. Confirm the new state by reading it back with
    `/api/v1/get/<key>` or by watching the status broadcast.

## Reading status

### Single value — no parser needed

```
GET /api/v1/get/is_recording   →   1
```

Returns the raw value as text. This is the endpoint to use for a tally light. Returns `404` and `err unknown key` for an unknown key.

Key names are the [Redis keys](redis-keys.md).

### Snapshot

| Request | Result |
|---|---|
| `GET /api/v1/status` | JSON object of every key |
| `GET /api/v1/status?keys=is_recording,iso,fps` | JSON object of only those keys |
| `GET /api/v1/status?keys=iso,fps&fmt=text` | `key=value` lines instead of JSON |

Use `?keys=` on memory-constrained devices. A full snapshot is several kilobytes.

Unknown keys in `?keys=` are skipped silently rather than erroring, so one firmware build can talk to several Cinemate versions.

### Command list

```
GET /api/v1/commands
```

Returns every command the camera accepts, as JSON `[{"name":"set iso","arg":"int"}, ...]`, or one name per line with `?fmt=text`. Built live from the running command table — a controller can generate its own menu instead of hardcoding one.

### Identity

```
GET /api/v1/hello   →   cinemate 3.3.2 api=1 sensor=imx585 cams=1 rec=0
```

Cheap check that you are talking to a Cinemate camera, and that it has finished starting.

## Live updates

Three ways to keep a device in sync. Pick by device class.

| Method | Best for | Cost on the device | Cost on the camera |
|---|---|---|---|
| **UDP broadcast** | Tally lights, displays, many devices | ~10 lines, no connection state | One packet serves every device |
| **SSE** | One to four devices needing every change | Open socket, read lines | One server thread per client |
| **Polling `/get/<key>`** | Anything; always works | Trivial | One short request per poll |

### UDP broadcast — recommended default

The camera broadcasts a single plain-text line to port `8888` on the hotspot subnet, at 5 Hz plus immediately on change.

```
rec=1 iso=800 fps=24.0 shutter=180.0 tc=01:02:03:04 space=412 drops=0 mounted=1
```

One packet, under 500 bytes, no parser, no connection to maintain, and it scales to as many devices as you like. Configure which keys are included in [`settings.jsonc`](settings-json.md).

### Server-sent events

```
GET /api/v1/events
```

`text/event-stream`. One `data: key=value` per changed key, with a `: ping` heartbeat every 15 seconds so devices can detect a dead link.

!!! warning "Limited number of clients"

    Cinemate's web server holds one thread per open connection, so SSE is capped
    (`max_sse_clients`, default 4). Beyond the cap the server returns `503`. For more than
    a handful of devices, use the UDP broadcast.

## Settings

Add to [`settings.jsonc`](settings-json.md) under `system`. Every field is optional — the defaults below apply when the block is absent.

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

| Field | Default | Effect |
|---|---|---|
| `enabled` | `true` | Turns the API off entirely |
| `token` | `""` | When set, requests must carry `X-Cinemate-Token` |
| `allow_destructive` | `false` | When false, blocks `reboot`, `shutdown`, `erase`, `format` |
| `max_commands_per_sec` | `20` | Per-client rate limit |
| `max_sse_clients` | `4` | Concurrent `/events` connections |
| `broadcast.keys` | see above | Which keys appear in the UDP line |

!!! danger "The hotspot password is public knowledge"

    Cinemate ships with the hotspot password `11111111`. Anyone within Wi-Fi range can
    reach the API. `allow_destructive` therefore defaults to **false**, so `format` and
    `erase` cannot be triggered remotely on a stock unit. Change the hotspot password in
    `system.wifi_hotspot` before enabling destructive commands, and set a `token` if the
    camera will be used somewhere crowded.

## Relationship to the other control paths

| Path | Transport | Same commands? |
|---|---|---|
| Cinemate CLI | `cinemate` in a terminal | — |
| Serial | Tx/Rx pins or USB, 9600 baud | Yes |
| **Web API** | HTTP on port 5000 | **Yes** |
| Web GUI | Browser on port 5000, posts to `/api/v1/cmd` | Yes |
| GPIO / rotary / I²C | [`settings.jsonc`](settings-json.md) mappings | Yes |

All command-based paths go through one dispatcher, so behaviour cannot drift between them. The
browser control page (`docs/web-gui.md`) is itself a `/api/v1/cmd` client — its ISO/shutter/FPS/WB/
resolution selectors, REC tap, LOG toggle and Unmount button all post CLI command lines. Socket.IO
carries only the push side: the live preview data feeding the on-screen readout.
