# Additional hardware

!!! note ""
    All hardware on this page is optional. Add what you need, when you need it.

Physical controls are mapped in [the settings file](settings-json.md). On the Pi, type `editsettings` in the terminal to open it. Changes take effect the next time Cinemate starts. Buttons, switches, pots and encoders simply call the same commands that the CLI and the web GUI use. See [controller methods](controller-methods.md) for the full list of available commands.


| Hardware | Connects to | Typical use | Extra parts needed |
| --- | --- | --- | --- |
| Push buttons | any free GPIO pin + GND | start/stop recording, change resolution | none |
| Two- and three-way switches | GPIO pins + GND | zoom, shutter sync mode, fps presets | none |
| Rotary encoders | two GPIO pins (+ optional button pin) | stepping through ISO, shutter angle, fps, WB | none |
| [Grove Base HAT](https://wiki.seeedstudio.com/Grove_Base_Hat_for_Raspberry_Pi/) | GPIO header | dials for ISO, shutter angle, fps, WB | Potentiometers |
| Adafruit quad rotary encoder | I²C (STEMMA QT or SDA/SCL pins) | four dials + push buttons in one module | [Adafruit #5752](https://www.adafruit.com/product/5752) |
| [CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/) | PCIe (Raspberry Pi 5 only) | for fast storage| CFexpress Type B card |

!!! info ""
    Cinemate uses [BCM pin numbering](https://pinout.xyz)

## Push buttons

Any momentary push button works. Wire one leg to a GPIO pin and the other leg to ground — no resistor needed, the Pi's internal pull-up is used.

One button can trigger several different actions:

| Gesture | Fires when |
| --- | --- |
| `press_action` | immediately on press |
| `single_click_action` | one short click |
| `double_click_action` | two quick clicks |
| `triple_click_action` | three quick clicks |
| `hold_action` | button held for 3 seconds |

The prebuilt image ships with this mapping:

| GPIO | Action |
| --- | --- |
| 7 | press: start/stop recording |
| 10 | press: start/stop recording |
| 13 | single click: change resolution · double click: restart Cinemate · triple click: reboot the Pi · hold: mount/unmount drive |

A minimal button entry in `settings.json` looks like this:

```json
"buttons": [
  {
    "pin": 7,
    "pull_up": true,
    "debounce_time": 0.1,
    "press_action": {"method": "rec"}
  }
]
```

!!! info ""
    Some push buttons are wired closed = 1 and open = 0. At startup Cinemate detects buttons that read as pressed and reverses them automatically, so both button types work without any configuration.

One button can also act as a modifier for another (hold one, press the other) via the `combined_actions` section — see [settings.json](settings-json.md#combined_actions).

## Switches

Latching switches work like buttons, but Cinemate reacts to the *state* instead of a click. When the switch changes position, the matching action runs. At startup, Cinemate reads the current position and applies it, so the camera always matches the physical switch.

**Two-way switches** use one GPIO pin. The prebuilt image maps:

| GPIO | ON | OFF |
| --- | --- | --- |
| 24 | digital zoom 2× | zoom 1× |
| 22 | shutter angle sync mode on | sync mode off |

```json
"two_way_switches": [
  {
    "pin": 24,
    "state_on_action":  {"method": "set_zoom", "args": [2]},
    "state_off_action": {"method": "set_zoom", "args": [1]}
  }
]
```

**Three-way switches** use three GPIO pins, one per position — handy for fixed fps presets:

```json
"three_way_switches": [
  {
    "pins": [5, 6, 13],
    "state_0_action": {"method": "set_fps", "args": [24]},
    "state_1_action": {"method": "set_fps", "args": [25]},
    "state_2_action": {"method": "set_fps", "args": [50]}
  }
]
```

## Rotary encoders

Standard rotary encoders (for example KY-040, for example) connect straight to the GPIO header. Each encoder uses two pins (`clk_pin` and `dt_pin`), plus an optional third pin if the encoder has a built-in push button. The push button uses the same action grammar as the [buttons](#push-buttons) section.

No encoders are enabled in the stock settings file. A typical entry — turning the dial steps through ISO, pressing it locks the value:

```json
"rotary_encoders": [
  {
    "enabled": true,
    "clk_pin": 9,
    "dt_pin": 11,
    "button_pin": 10,
    "encoder_actions": {
      "rotate_clockwise":        {"method": "inc_iso"},
      "rotate_counterclockwise": {"method": "dec_iso"}
    },
    "button_actions": {
      "press_action": {"method": "set_iso_lock"}
    }
  }
]
```

The `inc_`/`dec_` commands step through the value arrays defined in `settings.json` — see [arrays](settings-json.md#arrays) and [free mode](settings-json.md#free_mode).

## Grove Base HAT

The Pi has no analog inputs, so potentiometers need an analog-to-digital converter. Cinemate supports the [Grove Base HAT](https://wiki.seeedstudio.com/Grove_Base_Hat_for_Raspberry_Pi/), which stacks on the GPIO header and adds analog ports. Plug in Grove rotary angle sensors (or wire any 10 kΩ linear pot to a Grove analog port) and map the channels in `settings.json`:

```json
"analog_controls": {
  "iso_pot": 0,
  "shutter_a_pot": 2,
  "fps_pot": 4,
  "wb_pot": "None"
}
```

The HAT is detected automatically at startup; if it is not present, the section is simply ignored. Pot positions snap to the step arrays (or to the full range in [free mode](settings-json.md#free_mode)), and readings are smoothed with dead zones so values don't flicker between steps.

!!! info ""
    Only map channels that actually have a potentiometer connected. Unconnected analog inputs pick up noise and can trigger false readings.

## Adafruit quad rotary encoder

The [Adafruit I2C Quad Rotary Encoder breakout](https://www.adafruit.com/product/5752) packs four rotary encoders — each with a push button and an RGB LED — into one small board. It connects over I²C: either with a STEMMA QT cable or four wires to the Pi header (3V3, GND, SDA on GPIO 2, SCL on GPIO 3).

Support is built in but disabled in the stock settings file. Set `"enabled": true` in the `quad_rotary_controller` section when the board is connected. The stock mapping:

| Dial | Turning | Push button |
| --- | --- | --- |
| 0 | white balance | single click: change resolution · double click: restart Cinemate · triple click: reboot · hold: mount/unmount drive |
| 1 | fps | press: toggle fps double |
| 2 | shutter angle | press: toggle shutter sync mode |
| 3 | ISO | press: toggle zoom · hold: safe shutdown |

Each dial steps through the same value arrays as the CLI and GPIO encoders. The buttons use the same press/click/hold grammar as the [buttons](#push-buttons) section, so every dial can be remapped freely — see [quad_rotary_controller](settings-json.md#quad_rotary_controller).

The board is hot-pluggable: if it is not found (or gets disconnected), Cinemate retries every few seconds, so you can attach it while the camera is running. The LEDs light up while a button is pressed.

## CFE Hat

The [CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/) by Will Whang adds a CFexpress Type B card slot to the Raspberry Pi 5 over PCIe.

No configuration is needed. Cinemate detects the hat automatically at startup and shows **CFE** as the media type in the GUI. The card follows the same rules as any other recording drive: format it as `exFAT` and label it `RAW` (the web GUI has a format button that does this for you).

The [dynamic resolution](settings-json.md#dynamic_resolution) profiles include measured sustainable frame rates for CFE media, so fps limits adjust automatically to what the card can sustain.

## Outputs and displays

Cinemate can also drive hardware in the other direction:

- **Rec light (tally LED)** – pins listed in `gpio_output.rec_out_pin` (GPIO 21 in the stock file) go high while recording. Wire an LED with a series resistor (roughly 220–330 Ω) between the pin and GND.
- **Rec sync tone** – `gpio_output.rec_tone_pin` (GPIO 18 in the stock file) outputs a 1 kHz tone while recording, useful for feeding a sync signal to an external recorder.
- **I²C OLED display** – a small SSD1306-style status screen showing values you choose (ISO, timecode, write speed, disk space…). Enable it in the `i2c_oled` section.

All three are configured in `settings.json` — see [gpio_output](settings-json.md#gpio_output) and [i2c_oled](settings-json.md#i2c_oled).

## Going further

- [settings.json reference](settings-json.md) – every option for the sections shown above.
- [Controller methods](controller-methods.md) – all commands you can bind to buttons, switches and dials.
- [Cinemate terminal commands](cli-commands.md) – try a command in the CLI first, then map it to hardware.
