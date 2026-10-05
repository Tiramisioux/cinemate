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

**[placeholder - WP4: HDMI GUI top row with the IRIS group, and the SYS column with EF and CAL]**

| Where | Shows | When |
|---|---|---|
| Top row, **`IRIS`** group, between `EXP` and `EI` | The commanded f-number | See the table below |
| SYS column, **`EF`** box | Adapter present | Dim while lens control is off |
| SYS column, **`CAL`** box | Calibration running | Only while calibrating |

States of the `IRIS` group:

| Look | When |
|---|---|
| Hidden | No adapter found |
| Grey | Adapter found, but lens control is off or no lens is mounted |
| Normal | Lens control active |

A control the mounted lens cannot do is greyed with a reason, not hidden: see [per-lens capabilities](lenses.md#capabilities).

!!! note ""
    The lens cannot report its real aperture. The group shows the f-number CineMate last sent. After a lens swap CineMate re-applies the last iris saved for that lens.

## Web GUI

Same top row, same three states for the `IRIS` group. The lens dropdown lists the lenses in the database and selects one.

**[placeholder - WP4: web GUI top row with the IRIS group and the lens dropdown]**

| Control | What it does |
|---|---|
| Lens dropdown | Selects a database entry. Choosing an entry for a different lens than the mounted one is allowed and warned. |

## Settings editor: Lens / Pinefeat

The pane for everything that needs typing or a decision.

**[placeholder - WP4: screenshot of the Lens / Pinefeat pane]**

| Element | What it does |
|---|---|
| **Adapter** line | Found or not, and how: **raw I²C** or **kernel driver** |
| **Lens control** toggle | On/off. Disabled until the adapter is found. |
| **Lens** dropdown | The database entries. Selects one. |
| **Name** field | The name of the working lens. This is the dropdown label. |
| **Save as new** | Adds the working lens to the database under the name in the field |
| **Save over** | Replaces an existing entry. Asks you to confirm first. |
| Unsaved marker | Shows while the working lens has changes that are not saved |
| **Aperture range** | Smallest and largest f-number of this lens. [Why](lenses.md#aperture-range) |
| **Delete entry** | Removes the selected entry from the database |

**[placeholder - WP4: how the pane shows and edits per-lens capabilities]**

### The calibrator

A small panel in the same pane.

**[placeholder - WP4: screenshot of the calibrator mid-sweep and after a result]**

| Element | What it does |
|---|---|
| **Calibrate** button | Starts a calibration. Same as the `calibrate lens` command. |
| Progress | Live. Position and distance while the lens sweeps. |
| Result | The focus map, the minimum focus distance, and whether the lens has a distance encoder |
| Message | If the lens did not move: "set the lens to AF and try again" |

A calibration changes the **working lens** only. Nothing reaches the database until you save. [Lenses](lenses.md#saving).

## The i²c pane

The settings editor's i²c pane has an adapter row: found or not, and which way it was reached.

| Shown | Meaning |
|---|---|
| `raw I²C` | CineMate read the board directly. No driver in use. The normal case. |
| `kernel driver` | The optional `cef168` driver owns the board and CineMate goes through it. |

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

**[placeholder - WP4: how the lens commands are grouped in the Command dropdown]**

When lens control is not active, the settings editor greys these entries and a press or turn does nothing. They stay in your saved layout, so switching lens control on brings them back with no reconfiguration.
