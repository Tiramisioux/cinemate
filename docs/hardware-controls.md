# Additional hardware

!!! note ""
    All hardware on this page is optional. Add what you need, when you need it.

Physical controls are mapped in [the settings file](settings-json.md). Type `editsettings` on the Pi to open it. Changes apply at the next CineMate start. Controls call the same commands as the CLI and web GUI, listed under [controller methods](controller-methods.md).

| Hardware | Connects to | Typical use | Extra parts needed |
| --- | --- | --- | --- |
| Push buttons | any free GPIO pin + GND | start/stop recording, change resolution | none |
| Two- and three-way switches | GPIO pins + GND | zoom, shutter sync mode, fps presets | none |
| Rotary encoders | two GPIO pins (+ optional button pin) | stepping ISO, shutter angle, fps, WB | none |
| [Grove Base HAT](https://wiki.seeedstudio.com/Grove_Base_Hat_for_Raspberry_Pi/) | GPIO header | dials for ISO, shutter angle, fps, WB | Potentiometers |
| Adafruit quad rotary encoder | I²C (STEMMA QT or SDA/SCL pins) | four dials + push buttons in one module | [Adafruit #5752](https://www.adafruit.com/product/5752) |
| [CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/) | PCIe (Raspberry Pi 5 only) | fast storage | CFexpress Type B card |

!!! info ""
    CineMate uses [BCM pin numbering](https://pinout.xyz)

## GPIO controls in the settings editor

Pins are configured on the **settings.jsonc** tab, in two sections of the left rail:

| Rail entry | Section heading | Holds |
| --- | --- | --- |
| **Buttons & switches** | **GPIO in** | Buttons, 2‑way and 3‑way switches, GPIO rotary encoders, the quad rotary i²c board |
| **Rec tally & GPIO out** | **GPIO out** | Tally and slate‑tone pins driven while recording |

Nothing is live until you click **Save changes**.

One row per physical control, in two halves:

| Half | Column heading | Contains |
| --- | --- | --- |
| Left | **GPIO** | The pin (or pins) the control is wired to |
| Right | **ACTION** + **COMMAND** | One line per gesture: what the operator does, what CineMate runs |

A row can carry several gesture lines: one button can record on **Press** and reboot the Pi on **Triple click**, same row, same pin. The heading strip renames per row type: quad rotary reads **Encoder | Action | Command**, GPIO out reads **Output | Trigger | Command**.

### Add a button and map it to record

![The add-control buttons at the foot of the GPIO in section](images/gui-add-control-row.png)

1. On the **settings.jsonc** tab, click **Buttons & switches** in the left rail.
2. Click **+ Add button**. A row appears at the bottom, GPIO **None**, one line: **Press** → **No action**.

    ![A button the moment it is added: no pin, PRESS, no action](images/gui-new-button-card.png)

3. Open the row's **GPIO** dropdown and pick **GPIO 26**, or any pin listed in black. The stock file holds 7, 9, 10, 11, 13, 18, 21, 22 and 24.
4. **Remap this control?** appears, reading "Move a button to GPIO 26?". Click **Remap**.
5. On the **Press** line, open **COMMAND** and pick **Start / stop recording**, under **Record**.
6. Click **Save changes**.

CineMate restarts and the button is live.

Commands are the set `cli_commands.py` dispatches, grouped as **Record**, **ISO**, **Shutter**, **Frame rate**, **White balance**, **ClearHDR**, **CineMate Log**, **Thumbnail**, **Zoom / anamorphic**, **Resolution / preview**, **Storage**, **Sensor**, **Locks**, **System**. Only legal arguments are offered. The pencil icon switches a line to free text (**Type it manually**); the list icon switches back.

### More gestures on the same button

| Gesture | Fires |
| --- | --- |
| **Press** | Immediately on press |
| **Single click** | One short click, 0.5 s after release |
| **Double click** | Two quick clicks |
| **Triple click** | Three or more quick clicks |
| **Hold** | Button held for 3 seconds |

**+ Add** in the row's command column lists the gestures that row does not use yet. Pick one and a line appears above **+ Add** with **No action**; set its command.

![One button carrying five gestures](images/gui-gpio-multi-action.png)

- The **ACTION** cell is a dropdown. Re‑key a configured line to another gesture without rebuilding it.
- Gestures already used by the row are greyed out in that row's dropdowns.
- **+ Add** disappears once all five gestures are configured.
- **×** at the end of a line removes that gesture.
- **Remove** deletes the whole control. Its confirm dialog is the generic one, titled **Remap this control?** with a **Remap** button; the body reads "Remove this button? This deletes it from the settings file on the next save."
- A press held longer than half a second stops counting as a click, so **Hold** never also fires **Single click**.

### The argument box

The box after the command is its argument. What a blank argument does depends on the command, and the box says which:

| Blank option | Means |
| --- | --- |
| **Cycle through the list** | Each trigger steps to the next value in **Value steps** |
| **Toggle on / off** | Each trigger inverts the current flag |
| **Needs a value —** | Nothing useful happens until you pick a value |

Pick a value instead and the control jumps straight to it every time. Cycling commands read **Set to 2×**, **Set to 800**; flag commands offer **0** and **1**. Number arguments carry the hint `— blank cycles` or `— required`.

A **Needs a value —** command left blank is drawn in red and fails the first time the button is pressed. `format_drive` is the sharp case: a blank argument formats the card as exFAT.

### 2-way and 3-way switches

Switches react to position, not to a click. At startup CineMate reads the current position and runs its line, so the camera always matches the switch.

**+ Add 2‑way switch** creates one pin and two lines:

| Line | Runs when |
| --- | --- |
| **On** | The pin reads closed |
| **Off** | The pin reads open |

**+ Add 3‑way switch** creates three pin dropdowns, **pin 1**, **pin 2**, **pin 3**, and three lines:

| Line | Runs when |
| --- | --- |
| **Position 1** | pin 1 is the active input |
| **Position 2** | pin 2 is the active input |
| **Position 3** | pin 3 is the active input |

All three pins must be set. With no input active, no line runs.

Typical 2‑way pairing: **Set preview zoom** at **Set to 2×** on **On**, **Set to 1×** on **Off**.

### Rotary encoders

**+ Add rotary encoder** creates three pin dropdowns, **CLK**, **DT** and **BTN**.

| Pin | Required |
| --- | --- |
| **CLK** | Yes |
| **DT** | Yes |
| **BTN** | No; leave **None** if the encoder has no push button |

The row starts with a single **Button press** line; **+ Add** offers the rest.

![A single control row: pin, gesture, command](images/gui-gpio-control-row.png)

| Line | Fires |
| --- | --- |
| **Button press** | Press of the encoder's push button |
| **Button hold** | Push button held |
| **Rotate CW** | One step clockwise |
| **Rotate CCW** | One step counter‑clockwise |

Usual pattern: **ISO up one stop** on **Rotate CW**, **ISO down one stop** on **Rotate CCW**, **Toggle ISO lock** on **Button press**. The `inc_`/`dec_` commands step through the tables under **Value steps**.

### The quad rotary i²c board

**Quad rotary — the 4‑encoder i²c board** sits below the GPIO in list with its own **+ Add encoder**. Its rows address the board's four encoders, not GPIO pins, so the left column offers **None** and **Encoder 0** through **Encoder 3**.

![One dial of the quad rotary board](images/gui-quad-rotary-row.png)

**+ Add encoder** claims the lowest free encoder index. Set the **Turn** line, what rotating the dial cycles, then add button gestures with **+ Add** as on a GPIO button.

**Turn** offers **Nothing**, **ISO**, **Shutter angle**, **Frame rate**, **White balance**, **Resolution**, **Preview zoom**, **Nominal shutter angle**, **HDR threshold low**, **HDR threshold high**, **HDR blend**, **HDR gain adder**.

The push button below **Turn** takes the full button grammar.

With all four configured, **+ Add encoder** reports "All four encoders are already configured". The stock file ships all four in use.

### GPIO out: tally and slate tone

![The GPIO out section](images/gui-gpio-out.png)

1. Click **Rec tally & GPIO out** in the left rail.
2. Click **+ Add pin**. A row appears with **Output** on **None** and a **While rec** line set to **REC tally**.
3. Pick the pin from **Output** and confirm the remap.
4. For a sync tone instead of a lamp, change **While rec** to **REC tone**.

**REC tone** reveals an **at … Hz** field in the row and three cards below the list:

| Card | Sets |
| --- | --- |
| **Slate tone frequency** | Pitch in hertz |
| **Slate tone duty cycle** | Pulse width in percent |
| **Mute the tone on a dropped frame** | Cuts the tone for about one frame when the camera drops one |

One frequency serves every tone pin: the in‑row field and the card edit the same value. The cards are hidden while no pin is set to **REC tone**. Add as many tally and tone rows as you are wired for.

### Pin conflicts

Every pin dropdown lists **None** plus GPIO 2–13 and 16–27.

- A pin held by another row is greyed out, reading **GPIO 9 — in use (a rotary encoder (CLK pin))**. The bracket names the row holding it.
- **GPIO 18 — in use (the slate tone)** is greyed out in every picker except one already set to it, reserved whether or not a tone pin is configured.
- Changing a pin always opens **Remap this control?**. **Remap** applies it and frees the old pin; **Cancel** puts the dropdown back.
- Setting a pin back to **None** asks "It stops responding until you give it a pin again", then dims the row's lines.

A row left on **None** is dropped at save. Same for a 3‑way switch missing a pin, an encoder missing CLK or DT, a GPIO out row with no pin, and a quad rotary row on **None**.

### Saving

Editing a control shows the **N unsaved** pill and enables **Save changes**. Every edit across both sections collapses into one entry in that count.

!!! warning "Moving a pin on its own does not arm Save"
    Changing the **GPIO** dropdown on a row already in the file updates the raw preview but not the unsaved counter, so **Save changes** can stay greyed out. Change a command on one of the row's lines, or add and delete a spare gesture, to arm it.

**Save changes** on this tab:

1. Backs up `settings.jsonc` to `.settings-backups/` alongside it (timestamped, last 10 kept).
2. Writes your changes.
3. Restarts CineMate, toast "Saved. Restarting Cinemate…". Recording stops if one is in progress.

Adding or removing a row resizes an array, which the surgical writer cannot express: that save rewrites the whole file and loses the comments in `settings.jsonc`. The backup from step 1 still has them. Editing a row in place keeps them.

`pull_up` and `debounce_time` have no widget here. Button rows round‑trip what the file held; **+ Add button** writes `pull_up: true`, `debounce_time: 0.1`. Encoder rows never round‑trip: every save rewrites `enabled: true`, `pull_up: true`, `debounce_time: 0.05`. Switch rows carry neither. `combined_actions` passes through unchanged.

The top bar's **settings.jsonc** button opens a drawer with the exact text the next save would write.

## Wiring

| Device | Wiring |
| --- | --- |
| Push button | One leg to a GPIO pin, the other to ground. No resistor; the Pi's internal pull-up is used. |
| Two-way switch | One GPIO pin plus ground. |
| Three-way switch | Three GPIO pins, one per position, plus ground. |
| Rotary encoder | Two pins (`clk` and `dt`), plus a third if it has a push button. KY-040 modules work directly. |
| Grove Base HAT pot | Stacks on the GPIO header; plug a Grove rotary angle sensor, or any 10 kΩ linear pot, into an analog port. The Pi has no analog input of its own. |
| Adafruit quad rotary | I²C: a STEMMA QT cable, or four wires to 3V3, GND, SDA (GPIO 2) and SCL (GPIO 3). |
| Tally LED | Series resistor of roughly 220–330 Ω between the pin and GND. |

!!! info ""
    Some push buttons are wired closed = 1 and open = 0. At startup CineMate detects buttons that
    read as pressed and reverses them, so both types work with no configuration.

!!! info ""
    Only assign pot channels that have a potentiometer connected. Unconnected analog inputs pick
    up noise and can trigger false readings.

### What ships mapped

The prebuilt image ships these mapped:

| Control | Pin(s) | Does |
| --- | --- | --- |
| Button | 7 | press: start/stop recording |
| Button | 10 | press: start/stop recording |
| Button | 13 | single click: change resolution · double: restart CineMate · triple: reboot · hold: mount/unmount |
| 2-way switch | 24 | on: digital zoom 2× · off: zoom 1× |
| 2-way switch | 22 | on: shutter-angle sync mode · off: off |
| Rotary encoder | 9 / 11 / 10 | turn: ISO up/down · press: ISO lock |
| Quad rotary dial 0 | i²c | turn: ISO · press: zoom · hold: safe shutdown |
| Quad rotary dial 1 | i²c | turn: shutter angle · press: shutter sync mode |
| Quad rotary dial 2 | i²c | turn: fps · press: double fps |
| Quad rotary dial 3 | i²c | turn: white balance · single click: change resolution · double: restart · triple: reboot · hold: mount/unmount |
| Tally out | 21 | high while recording |
| Slate tone | 18 | 1 kHz tone while recording |

## CFE Hat

The [CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/) by Will Whang adds a CFexpress Type B card slot to the Raspberry Pi 5 over PCIe.

No configuration needed. CineMate detects the hat at startup and shows **CFE** as the media type. Format the card `exFAT` and label it `RAW`, like any recording drive: the RAW files pane has a format button, `format exfat` does the same in the CLI.

## Outputs and displays

- **Rec light (tally LED)** – `hardware_outputs.rec_out_pin` (GPIO 21 stock) goes high while recording.
- **Rec sync tone** – `hardware_outputs.rec_tone.pin` (GPIO 18 stock) outputs a 1 kHz tone while recording.
- **I²C OLED display** – an SSD1306-style status screen showing values you choose (ISO, timecode, write speed, disk space…). Enable it in `output_peripherals.oled`.

Reference: [hardware_outputs](settings-json.md#hardware_outputs), [output_peripherals](settings-json.md#output_peripherals), [settings.jsonc](settings-json.md), [controller methods](controller-methods.md), [CineMate terminal commands](cli-commands.md).
