# Building control units

Build a wireless camera controller — a record button, a tally light, an ISO knob, a full remote — out of an ESP32, an M5Stack, a Raspberry Pi Pico W, or another Pi. The device joins the camera's Wi-Fi hotspot and sends the same commands you would type into the Cinemate CLI.

You need three things on the device, and nothing else:

1. Join the hotspot
2. `POST` a command string
3. Listen for the UDP status line

## What you need

| | |
|---|---|
| Camera | Cinemate with `system.wifi_hotspot.enabled` set to `true` |
| Controller | Any Wi-Fi microcontroller — ESP32, ESP8266, M5Stack, Pico W, or a Pi |
| Network | The camera's own hotspot. No router, no internet. |
| Camera address | `10.42.0.1`, port `5000` for commands, `8888/udp` for status |

No library is required beyond the board's own Wi-Fi and HTTP support. There is no SDK to install and no JSON parser to link.

## Before you write firmware

Prove the camera answers, from a laptop joined to the `CinePi` hotspot:

```bash
curl http://10.42.0.1:5000/api/v1/hello
curl -d "rec" http://10.42.0.1:5000/api/v1/cmd
nc -ul 8888
```

If those three work, every example below will work. If they do not, fix that first — see [Troubleshooting](#troubleshooting).

## ESP32 — record button and tally light

The complete controller. One momentary button to GND, one LED.

```cpp
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiUdp.h>

const char* SSID = "CinePi";
const char* PASS = "11111111";
const char* CAM  = "http://10.42.0.1:5000";

const int PIN_BUTTON = 0;    // momentary to GND
const int PIN_TALLY  = 2;    // LED to GND through a resistor

WiFiUDP udp;

void sendCmd(const char* line) {
  HTTPClient http;
  http.begin(String(CAM) + "/api/v1/cmd");
  http.addHeader("Content-Type", "text/plain");
  http.setTimeout(1500);
  int code = http.POST(line);
  Serial.printf("%s -> %d %s\n", line, code, http.getString().c_str());
  http.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  pinMode(PIN_TALLY, OUTPUT);

  WiFi.begin(SSID, PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(250); Serial.print("."); }
  Serial.println(WiFi.localIP());

  udp.begin(8888);                       // status broadcast
}

void loop() {
  // button → toggle record
  static bool last = HIGH;
  static uint32_t lastEdge = 0;
  bool now = digitalRead(PIN_BUTTON);
  if (now != last && millis() - lastEdge > 50) {      // 50 ms debounce
    lastEdge = millis();
    if (now == LOW) sendCmd("rec");
    last = now;
  }

  // broadcast → tally
  if (udp.parsePacket() > 0) {
    char buf[512];
    int len = udp.read(buf, sizeof(buf) - 1);
    buf[len] = 0;
    char* p = strstr(buf, "rec=");
    if (p) digitalWrite(PIN_TALLY, p[4] == '1' ? HIGH : LOW);
  }
}
```

That is the whole thing. `sendCmd` accepts any [Cinemate command](cli-commands.md): `"set iso 800"`, `"inc fps"`, `"set wb 5600"`, `"rec f 48"`.

The tally reads the broadcast rather than polling. It costs the camera nothing extra whether you build one tally light or ten.

## M5StickC — button, display, tally

The M5StickC has a button, a screen and an LED already, so it makes a good handheld remote with no wiring at all.

```cpp
#include <M5StickCPlus.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiUdp.h>

const char* SSID = "CinePi";
const char* PASS = "11111111";
const char* CAM  = "http://10.42.0.1:5000";

WiFiUDP udp;
String iso = "-", fps = "-", tc = "--:--:--:--";
bool recording = false;

void sendCmd(const char* line) {
  HTTPClient http;
  http.begin(String(CAM) + "/api/v1/cmd");
  http.addHeader("Content-Type", "text/plain");
  http.setTimeout(1500);
  http.POST(line);
  http.end();
}

// pull one "key=value" out of the broadcast line
String field(const char* buf, const char* key) {
  const char* p = strstr(buf, key);
  if (!p) return "-";
  p += strlen(key);
  const char* e = strchr(p, ' ');
  return e ? String(p).substring(0, e - p) : String(p);
}

void draw() {
  M5.Lcd.fillScreen(recording ? RED : BLACK);
  M5.Lcd.setCursor(6, 10);  M5.Lcd.setTextSize(3);
  M5.Lcd.print(recording ? "REC" : "---");
  M5.Lcd.setTextSize(2);
  M5.Lcd.setCursor(6, 50);  M5.Lcd.print("ISO " + iso);
  M5.Lcd.setCursor(6, 75);  M5.Lcd.print(fps + " fps");
  M5.Lcd.setCursor(6, 100); M5.Lcd.print(tc);
}

void setup() {
  M5.begin();
  M5.Lcd.setRotation(3);
  WiFi.begin(SSID, PASS);
  while (WiFi.status() != WL_CONNECTED) delay(250);
  udp.begin(8888);
  draw();
}

void loop() {
  M5.update();
  if (M5.BtnA.wasPressed()) sendCmd("rec");
  if (M5.BtnB.wasPressed()) sendCmd("inc iso");

  if (udp.parsePacket() > 0) {
    char buf[512];
    int len = udp.read(buf, sizeof(buf) - 1);
    buf[len] = 0;
    recording = field(buf, "rec=") == "1";
    iso = field(buf, "iso=");
    fps = field(buf, "fps=");
    tc  = field(buf, "tc=");
    draw();
  }
}
```

## Raspberry Pi Pico W — MicroPython

No external libraries. Raw sockets only, so it works on any build.

```python
import network, socket, time
from machine import Pin

SSID, PASS = "CinePi", "11111111"
HOST, PORT = "10.42.0.1", 5000

button = Pin(15, Pin.IN, Pin.PULL_UP)
tally  = Pin("LED", Pin.OUT)

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(SSID, PASS)
while not wlan.isconnected():
    time.sleep(0.5)
print("ip", wlan.ifconfig()[0])

def cmd(line):
    body = line.encode()
    s = socket.socket()
    try:
        s.connect((HOST, PORT))
        s.send(b"POST /api/v1/cmd HTTP/1.1\r\nHost: " + HOST.encode() +
               b"\r\nContent-Type: text/plain\r\nContent-Length: " +
               str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
        return s.recv(128)
    finally:
        s.close()

udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp.bind(("0.0.0.0", 8888))
udp.setblocking(False)

last = 1
while True:
    now = button.value()
    if last == 1 and now == 0:
        cmd("rec")
        time.sleep_ms(50)
    last = now

    try:
        data, _ = udp.recvfrom(512)
        tally.value(1 if b"rec=1" in data else 0)
    except OSError:
        pass

    time.sleep_ms(10)
```

If your build ships `requests`, the command function collapses to one line:

```python
import requests
requests.post("http://10.42.0.1:5000/api/v1/cmd", data="rec").close()
```

## Another Raspberry Pi, or any computer

```python
import requests, socket

CAM = "http://10.42.0.1:5000/api/v1"

def cmd(line):
    return requests.post(f"{CAM}/cmd", data=line, timeout=2).text

cmd("set iso 800")
cmd("set fps 24")
cmd("rec")

# status broadcast, parsed into a dict
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("", 8888))
while True:
    line = s.recvfrom(512)[0].decode()
    print(dict(kv.split("=", 1) for kv in line.split()))
```

## Control patterns

| Control | Send | Note |
|---|---|---|
| Momentary REC button | `rec` | Toggles. Debounce 50 ms on the device. |
| Timed take button | `rec f 48` | Records exactly 48 frame slots, then stops itself |
| Rotary encoder | `inc iso` / `dec iso` | **Rate-limit on the device.** See below. |
| Latching switch | `set fps lock 1` / `set fps lock 0` | Send the explicit `0`/`1`, not the bare toggle, so switch and camera cannot drift apart |
| Preset button | `set iso 800`, then `set fps 24`, then `set shutter a 180` | Three requests. Leave ~20 ms between them. |
| Menu on a display | `GET /api/v1/commands` | Build the menu from the camera's live command list instead of hardcoding it |
| Tally light | UDP `rec=` | Use the broadcast, not polling |
| Storage warning | UDP `space=` | Megabytes remaining |
| Dropped-frame alarm | UDP `drops=` | Non-zero means the last take dropped frames |

### Rate-limit encoders on the device

A rotary encoder can emit fifty steps per second. The camera rejects anything over `max_commands_per_sec` (default 20) with `429`, and you lose steps.

Accumulate on the device and send at most one command every 50 ms:

```cpp
// in the encoder ISR: detents += direction;
static uint32_t lastSend = 0;
if (detents != 0 && millis() - lastSend > 50) {
  sendCmd(detents > 0 ? "inc iso" : "dec iso");
  detents += (detents > 0) ? -1 : 1;
  lastSend = millis();
}
```

### Handle a camera that is not there yet

The camera may reboot, or be switched on after the controller. Never block forever on a request.

- Set an HTTP timeout of 1–2 seconds. Do not use the default.
- Treat any failure as "camera absent" and show it — a dim tally, a dash on the display.
- Re-check with `GET /api/v1/hello` every few seconds until it answers.
- The UDP broadcast needs no reconnect. Packets simply resume.

### Confirm state after a restart command

`set resolution` and `set log` restart the camera. The `200 ok` arrives before the restart finishes. Do not assume the value took. Read it back:

```
GET /api/v1/get/sensor_mode
```

## Design rules

- **Send the command string, not a parameter.** `POST "set iso 800"` — there is no `/iso` endpoint, by design. The command vocabulary is the API, so your firmware keeps working as commands are added.
- **Prefer the UDP broadcast over polling.** One packet feeds every device. Polling multiplies load by the number of controllers.
- **Use `/api/v1/get/<key>` when you need one value on demand.** It returns bare text, so no JSON parser and no heap allocation.
- **Use `?keys=` on `/status`.** A full snapshot is several kilobytes and will strain a Pico.
- **Do not hold an SSE connection unless you need every change.** Each one occupies a thread on the camera, and there are only four.

## Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| Device joins Wi-Fi, all requests time out | Web server never started — it only starts if the interface had an IP when Cinemate booted | Restart Cinemate after the hotspot is up. See [Wi-Fi hotspot](hotspot-logic.md). |
| `curl` works from a laptop, fails from the ESP32 | URL encoding | Use `POST` with a plain body, not `GET` with spaces in the query |
| `400 err unknown command` | Typo, or a command that does not exist in this version | `GET /api/v1/commands` lists exactly what this camera accepts |
| `403 err blocked` | `format`, `erase`, `reboot` or `shutdown` with `allow_destructive` false | Intentional. See the [Web API](web-api.md) settings table. |
| `429 err rate limited` | Encoder flooding | Rate-limit on the device |
| `503 err too many clients` | More than four SSE connections | Switch those devices to the UDP broadcast |
| No UDP packets | Broadcast disabled, or the device is not on the hotspot subnet | Confirm with `nc -ul 8888` from a laptop on `CinePi` |
| Commands land but nothing happens | The command was accepted and ignored — e.g. `set iso` while ISO is locked | Check the lock state: `GET /api/v1/get/iso` before and after |
| Tally lags by a second | Polling instead of the broadcast | Switch to UDP |

## See also

- [Web API](web-api.md) — the full endpoint reference
- [Cinemate terminal commands](cli-commands.md) — every command you can send
- [Redis Key reference](redis-keys.md) — every key you can read
- [Configuring the Wi-Fi hotspot](hotspot-logic.md)
- [Additional hardware](hardware-controls.md) — for wired buttons and encoders on the Pi's own GPIO
