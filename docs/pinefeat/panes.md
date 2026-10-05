# Panes and controls

How each CineMate surface shows and uses the adapter. The rules are the same everywhere:

| Rule | Meaning |
|---|---|
| **One switch** | `lens control` is one on/off setting, saved across restarts. |
| **Only when found** | It can be switched on only while the adapter is found. Otherwise it refuses and says why. |
| **Effective = on and found** | Everything below follows that. |
| **Controls never disappear** | Buttons, dials and commands stay assignable. When lens control is not active they do nothing and say why. |

## States

The adapter's state is one word. Every pane shows the same one.

| State | Meaning | What to do |
|---|---|---|
| `absent` | No adapter found on the camera's I²C bus | Check the cable and port: [Compatibility](compatibility.md#troubleshooting) |
| `no_lens` | Adapter found, no lens detected | Mount a lens |
| `unknown_lens` | A lens the database does not know | Name it and save it: [Lenses](lenses.md#saving) |
| `uncalibrated` | Lens known, focus range not calibrated | [Calibrate](lenses.md#calibration) |
| `ready` | Lens known and calibrated | Use it |
| `selftest` | The lens's own self-test is running (AF/MF switch flipped three times) | Wait for it to finish |
| `calibrating` | CineMate is calibrating | Wait. It takes seconds. |
| `error` | The last command failed | Read the message line |

## HDMI GUI

The simple GUI on the camera's HDMI monitor.

The top row reads `FPS  SHUTTER  EXP  IRIS  EI  WB  RES`. The `IRIS` group is a label and a value, like the others, for example `IRIS F2.8`. With the adapter fitted the seven groups are spaced evenly across the row, so the other groups sit slightly closer together than on a camera without it. Without the adapter the row is the six groups it always was.

| Where | Shows | When |
|---|---|---|
| Top row, **`IRIS`** group, between `EXP` and `EI` | The commanded f-number, `F2.8` style. `F--` until an f-number has been sent. | See the table below |
| SYS column, **`EF`** box | Adapter present | Always while the adapter is found. See the look below. |
| SYS column, **`CAL`** box | Calibration running | Only while calibrating, under the `EF` box |

States of the `IRIS` group:

| Look | When |
|---|---|
| Hidden, takes no room | No adapter found |
| Grey label and value | Adapter found, but lens control is off, no lens is mounted, the adapter reports an error, or the saved entry for the lens says its iris does nothing |
| Normal | Lens control active |

States of the `EF` box:

| Look | When |
|---|---|
| Grey box | Lens control on |
| Dim box | Lens control off |
| Grey box with a diagonal strike | Adapter found but no lens mounted, or the adapter is in the `error` state |

An unknown or uncalibrated lens is not marked on the monitor. The box cannot say which of the two it is, and the iris works for both. The [settings editor pane](#settings-editor-lens-pinefeat) shows those states.

A control the mounted lens cannot do is greyed with a reason, not hidden: see [per-lens capabilities](lenses.md#capabilities).

!!! note ""
    The lens cannot report its real aperture. The group shows the f-number CineMate last sent. After a lens swap CineMate re-applies the last iris saved for that lens.

## Web GUI

Same top row, same three states for the `IRIS` group, and the same `EF` and `CAL` boxes in the left column. The web page draws exactly what the HDMI GUI decided, so the two never disagree.

| Control | What it does |
|---|---|
| **`IRIS`** value | Click it to open a picker of the mounted lens's own f-numbers (clamped to its [aperture range](lenses.md#aperture-range)). Picking one sends `set iris`. |
| `IRIS` value while grey | The picker still opens, but choosing a value only shows the reason (for example "Lens control is off") and sends nothing. |
| **Lens dropdown**, in the button row beside `EXPERIMENT` | Lists the lenses in the database and selects one with `set lens <key>`. Shown only while the adapter is found. Choosing an entry for a different lens than the mounted one is allowed and warned. |

The web page has no autofocus controls.

## Settings editor: Lens / Pinefeat

The **Lens** tab, between *i2c* and *settings.jsonc*. It is the pane for everything that needs typing or a decision. It reads the running camera live, once a second while the tab is open, and it has no Save button of its own: each action takes effect at once, and the lens list is saved only by **Save as new** and **Save over**.

The tab works with no camera running. It then shows a "camera is not running" note, still lists the saved lenses from the [lens database](lenses.md#the-lens-database) file, and lets you delete one. Every other action is refused with that same note.

From top to bottom the tab has four panes: *Pinefeat CEF168 adapter*, *Lens*, *Calibration*, *Saved lenses*.

| Element | What it does |
|---|---|
| **Adapter** card | A `found` or `not found` chip, then where it was found (`cam0`, the bus and how the bus was worked out) and the provenance in words: *the cef168 driver is bound* or *raw read on the camera bus, no driver*. When not found it says why. |
| **Lens control** toggle | On/off. Disabled until the adapter is found, and while the camera is not running. |
| **Mounted lens** card | The lens id the adapter reads, a state chip (the words in [States](#states)) and the current message line |
| **Lens in use** dropdown | The saved entries, plus **Unknown lens (not saved)**, which is the state when no entry is selected. Choosing an entry selects it, and discards unsaved changes to the previous one. Disabled while no lens is mounted. |
| **Unsaved changes** marker | Shown beside the dropdown while the working lens has changes that are not saved |
| **Name** field | The name of the working lens. This is the dropdown label. It fills in the selected entry's name until you type. |
| **Save as new** | Adds the working lens to the database under the name in the field |
| **Save over** | Replaces the selected entry (and renames it to the name in the field). Asks you to confirm first. Disabled when no entry is selected. |
| **Aperture range** | Two f-number fields, **Apply** and **Clear**. [Why](lenses.md#aperture-range). An edit marks the working lens unsaved. |
| **What this lens can do** | Three chips, see below |
| **Saved lenses** list | One row per entry: name, id, aperture range, calibrated or iris only, last used. An **in use** chip marks the selected one. **Delete** asks you to confirm first. |

The pane never overwrites a name or an f-number you are typing. The fields follow the selected entry until you touch them, and again after you save or choose another entry.

### Capabilities

The **What this lens can do** card shows what CineMate has found out about the selected lens: `Iris`, `Focus` and `Autofocus`.

| Chip | Values |
|---|---|
| `Iris` | `yes`, `no` or `untested` |
| `Focus` | `yes`, `no` or `untested` |
| `Autofocus` | Always `reserved`. Autofocus is not available. |

If `Focus` is `no`, the card adds a line: **Iris only: this lens never reported a focus position when it was calibrated, so focus controls are off for it.** The lens still works for iris. The same lens shows **iris only** in the saved list. This is set by a calibration that found no focus position, and it is kept only when you save the lens. [Per-lens capabilities](lenses.md#capabilities).

### The calibrator

The **Calibrate** card in the *Calibration* pane.

| Element | What it does |
|---|---|
| **Calibrate** button | Starts a calibration. Same as the `calibrate lens` command. |
| **MFD** field | Optional minimum focus distance in metres. Fill it only if the lens does not report one. |
| Progress | A bar and a line, live while the lens sweeps: the position out of the range, the elapsed seconds and the number of samples |
| Refusal | If the calibration is refused (recording, lens control off, no lens) the card says **Not started:** and the reason, and keeps saying it |
| **Last calibration** card | After a sweep: the number of map points, the minimum focus distance, whether the lens has a distance encoder (otherwise a 2-point fallback map is used), the focus range and how long it took. It ends with **Not saved yet** while the working lens is unsaved. |
| Failure | In red, with the reason. If the lens never reported a focus position, the reason says so and that the lens is now marked iris only. |

A calibration changes the **working lens** only. Nothing reaches the database until you save. [Lenses](lenses.md#saving).

## The i²c pane

The settings editor's i²c pane has a **Pinefeat CEF168 lens adapter** row: found or not, where, and which way it was reached. The adapter is on the camera's own I²C bus, never on the Raspberry Pi's user bus 1, and the row reads it without writing anything.

| Shown | Meaning |
|---|---|
| `raw I²C` (provenance `i2c-raw`) | CineMate read the board directly on the camera bus. No driver in use. The normal case. |
| `kernel driver` (provenance `v4l2-subdev`) | The optional `cef168` driver is bound and CineMate goes through it. |
| Reported by the running lens controller | The usual source while CineMate runs: the row reuses the lens thread's own answer and sends nothing on the bus. |
| Probed | With no camera running, one read-only attempt on the camera bus. A bus that turns out to be bus 1 is refused. |

When the adapter is not found the row says why.

## Commands

The commands are listed with their arguments in the [commands reference](../cli-commands.md). Names:

| Group | Commands |
|---|---|
| Iris | `set iris`, `inc iris`, `dec iris` |
| Focus | `set focus`, `inc focus`, `dec focus` |
| Lens | `set lens`, `save lens`, `calibrate lens`, `set lens control`, `set lens aperture` |

With lens control off, a command does nothing and prints why.

| Command | Direction and details |
|---|---|
| `inc iris` / `dec iris` | `inc` goes towards a higher f-number (stop down, darker). One third of a stop, along the mounted lens's own table. |
| `inc focus` / `dec focus` | `inc` goes towards infinity. One detent is 1 % of the motor range. Focus never wraps. |
| `save lens <name>` | Saves the working lens as a new entry. With no name, saves over the selected entry. |
| `set lens aperture 1.8 22` | Enters the aperture range. Unsaved until `save lens`. |

## Buttons, dials and pots

Everything is assigned the usual way: [Additional hardware](../hardware-controls.md). The lens controls are always on the list.

| Hardware | How to assign | Methods and names |
|---|---|---|
| GPIO button or switch | Pick the command on a gesture line | `inc_iris`, `dec_iris`, `inc_focus`, `dec_focus`, `calibrate_lens`, `set_lens` |
| Rotary encoder | **Rotate CW** and **Rotate CCW** lines | `inc_iris` and `dec_iris`, or `inc_focus` and `dec_focus` |
| Quad rotary board | The dial's **Turn** line: `setting_name` | `"iris"` or `"focus"` |
| Grove potentiometer | A pot channel in `input_peripherals.pots` | `{ "channel": 2, "setting": "iris" }` ([settings](../settings-json.md#lens_control)) |

In the settings editor's **Command** dropdown the lens commands sit together under the heading **Lens (Pinefeat)**. When lens control is not active, those entries are dimmed and the heading carries the reason, for example **Lens (Pinefeat) — greyed: Lens control is off**. They stay selectable, so you can set up a layout before the adapter arrives. A press or turn does nothing until lens control is on. They stay in your saved layout, so switching lens control on brings them back with no reconfiguration.
