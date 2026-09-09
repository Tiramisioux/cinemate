# Building CineMate microcontroller control units

You can use ESP32, an M5Stack, a Raspberry Pi Pico W or other type of microcontroller to build wireless camera controllers — a record button, a tally light, an ISO knob or a full handheld remote with a display. The device joins the camera's Wi-Fi hotspot and sends the same commands you would type into the [CineMate CLI](cli-commands.md).

| Wi-Fi network (SSID)     | `CinePi`                        |
| ------------------------ | ------------------------------- |
| Password                 | `11111111`                      |
| Camera IP on the hotspot | `10.42.0.1`                     |
| Commands                 | port `5000`, `POST /api/v1/cmd` |
| Status broadcast         | port `8888/udp`                 |

### Simple test:

For using numeric address, try:

```bash
curl http://10.42.0.1:5000/api/v1/hello
curl -d "rec" http://10.42.0.1:5000/api/v1/cmd
nc -ul 8888
```

You can also try the `cinepi.local`address

```bash
curl http://cinepi.local:5000/api/v1/hello
curl -d "rec" http://cinepi.local:5000/api/v1/cmd
```

## Example projects

### ESP32 — record button and tally light

```cpp
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiUdp.h>

const char* SSID = "CinePi";
const char* PASS = "11111111";
const char* CAM  = "http://10.42.0.1:5000";

const int PIN_BUTTON = 32;   // momentary to GND — not a strapping pin
const int PIN_TALLY  = 33;   // LED to GND through a resistor

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
    const char* KEY = "is_recording=";
    char* p = strstr(buf, KEY);
    if (p) digitalWrite(PIN_TALLY, p[strlen(KEY)] == '1' ? HIGH : LOW);
  }
}
```

`sendCmd` accepts any [CineMate command](cli-commands.md): `"set iso 800"`, `"inc fps"`, `"set wb 5600"`, `"rec f 48"`.

### M5StickC — button, display, tally

The M5StickC has a button, a screen and an LED already, so it makes a good handheld remote.

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
    recording = field(buf, "is_recording=") == "1";
    iso = field(buf, "iso=");
    fps = field(buf, "fps=");
    tc  = field(buf, "recording_time_tod=");
    draw();
  }
}
```

### Raspberry Pi Pico W — MicroPython

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
        tally.value(1 if b"is_recording=1" in data else 0)
    except OSError:
        pass

    time.sleep_ms(10)
```

If your build ships `requests`, the command function collapses to one line:

```python
import requests
requests.post("http://10.42.0.1:5000/api/v1/cmd", data="rec").close()
```

### Another Raspberry Pi, or any computer

```python
import requests, socket

CAM = "http://cinepi.local:5000/api/v1"

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

## Serial control

A controller can also talk to the camera down a wire. Use **115200 baud, 8N1, one command per line.** The line is handed to the CineMate CLI , so comamnds are the same as in the [commands reference](cli-commands.md):

```text
rec
set iso 800
set shutter a 172.8
```

CineMate sends back `rec` when a recording starts and `stop` when it ends. This can be useful for controlling a tally light on the serial device. 

For serial input you can use USB or Rx/Tx pins (14/15) on the Pi
## Design rules

See [CineMate commands](cli-commands.md) for a complete list of available commands. We are using the same syntax as for the CineMate CLI.

- **Send the command as plain text.** `POST "set iso 800"`, exactly what you would type. There is no `/iso` endpoint and there never will be. Because the commands themselves are the API, firmware
  you write today still works when new commands are added.
- **Listen to the status broadcast instead of asking over and over.** The camera sends one packet to everyone five times a second, so ten controllers cost it the same as one. Asking in a loop costs it once per device.
- **To read one value, use `/api/v1/get/<key>`.** It replies with just the value as text, so there
  is nothing to parse and nothing to allocate.
- **To read several, add `?keys=` to `/status`.** Without it you get every value, a few kilobytes,
  which is a lot to hand a Pico.
- **Only open an SSE stream if you need every change the instant it happens.** The camera holds four at most, and each one occupies a connection for as long as it is open.

## Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| Device joins Wi-Fi, all requests time out | Web server never started — it only starts if the interface had an IP when CineMate booted | Restart CineMate after the hotspot is up. See [Wi-Fi hotspot](hotspot-logic.md). |
| `curl` works from a laptop, fails from the ESP32 | URL encoding | Use `POST` with a plain body, not `GET` with spaces in the query |
| `400 err unknown command` | Typo, or a command that does not exist in this version | `GET /api/v1/commands` lists exactly what this camera accepts |
| `401 err unauthorized` | A token is set in `system.web_api.token` | Send it in the `X-Cinemate-Token` header |
| `403 err blocked` | `format`, `erase`, `reboot` or `shutdown` with `allow_destructive` false | Intentional. See the [Web API](web-api.md) settings table. |
| `429 err rate limited` | Encoder flooding | Rate-limit on the device |
| `503 err too many clients` | More than four SSE connections | Switch those devices to the UDP broadcast |
| No UDP packets | Broadcast disabled, or the device is not on the hotspot subnet | Confirm with `nc -ul 8888` from a laptop on `CinePi` |
| Commands land but nothing happens | The command was accepted and ignored — e.g. `set iso` while ISO is locked | Check the lock state: `GET /api/v1/get/iso` before and after |
| Tally lags by a second | Polling instead of the broadcast | Switch to UDP |

## See also

- [Web API](web-api.md) — the full endpoint reference
- [CineMate terminal commands](cli-commands.md) — every command you can send
- [Redis Key reference](redis-keys.md) — every key you can read
- [Configuring the Wi-Fi hotspot](hotspot-logic.md)
- [Additional hardware](hardware-controls.md) — for wired buttons and encoders on the Pi's own GPIO
