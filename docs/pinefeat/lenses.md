# Lenses and calibration

CineMate keeps one entry per lens in a **lens database**. An entry holds what the adapter cannot tell CineMate by itself: a name, the aperture range, the last iris, the focus calibration, and what the lens can do.

## The lens database

One JSON file, `lenses.json`, in CineMate's `resources` folder. The setting `lens_control.database_file` can point elsewhere. CineMate writes the file, so it is not part of the repository and a software update never conflicts with it.

| Property | Behaviour |
|---|---|
| Missing file | Treated as an empty database. Created on the first save. |
| Writes | Atomic: written to a temporary file, then renamed. One write at a time. |
| Hand edits | Stop CineMate first. Fields CineMate does not know are kept when it rewrites the file. |
| Key | The entry's name as a slug. A clash gets `-2`. |

An entry, with example values:

```json
{
  "schema": 1,
  "lenses": {
    "canon-ef-50-f1-8-stm": {
      "name": "Canon EF 50 f/1.8 STM",
      "lens_id": 235,
      "last_used": "2026-10-04T12:00:00Z",
      "aperture": {"min": 1.8, "max": 22.0, "source": "manual"},
      "last_iris": 2.8,
      "capabilities": {"iris": true, "focus": true, "autofocus": null},
      "focus": {
        "calibrated_at": "2026-10-04T12:00:00Z",
        "position_min": 0,
        "position_max": 1069,
        "mfd_m": 0.28,
        "distance_encoder": false,
        "map": [0.0, 1037, 3.57, 0],
        "dioptre_min": 0.0,
        "dioptre_max": 3.57,
        "step_frames": 4
      }
    }
  }
}
```

| Field | Meaning |
|---|---|
| `name` | What you called the lens. The dropdown label. |
| `lens_id` | The number the adapter reads from the lens, 0 to 255. Not unique: two lenses can share one. |
| `last_used` | When the entry was last selected. Breaks ties between entries with the same `lens_id`. |
| `aperture` | `min` and `max` f-number, entered by you. `null` until entered. |
| `last_iris` | The last f-number sent. Re-applied when the lens is detected. |
| `capabilities` | `iris`, `focus`, `autofocus`: `true`, `false` or `null` (not tested). See [below](#capabilities). `autofocus` is reserved: autofocus is paused. |
| `focus` | The calibration result. `null` until calibrated. |
| `focus.position_min`, `position_max` | The focus motor's range |
| `focus.mfd_m` | Minimum focus distance in metres |
| `focus.distance_encoder` | Whether the lens reports distance while it moves |
| `focus.map` | Pairs of `dioptre, motor position`, dioptres rising. Calibration produces it; today CineMate only stores it. |
| `focus.dioptre_min`, `dioptre_max`, `step_frames` | Further calibration values, stored for later |

### Choosing the entry

When a lens is detected CineMate picks the entry for you.

| Entries with this `lens_id` | What happens |
|---|---|
| One | Selected automatically |
| Several | The one used last for that id is selected |
| None | State `unknown_lens`. Name the lens and save it. |

You can select any entry from the dropdown, or with `set lens`. Selecting an entry for a different lens than the mounted one is allowed and warned.

### Saving

Nothing is saved until you say so. CineMate keeps a **working lens**: a copy of the selected entry, or a blank one for an unknown lens. A calibration or an aperture-range edit changes the working lens and marks it unsaved.

| Action | Result |
|---|---|
| **Save as new** | Adds the working lens as a new entry under the name in the Name field. `save lens <name>`. |
| **Save over** | Replaces an existing entry. The settings editor asks you to confirm. |
| *(automatic)* | **`last_iris` only.** It is operating state, so it is written to the selected saved entry silently. |

## Aperture range

The adapter cannot read a lens's aperture range, and the lens silently ignores an iris command outside it. So you enter the range once per lens: the largest opening (`min`, for example 1.8) and the smallest (`max`, for example 22).

| Range | Iris steps offered |
|---|---|
| Entered | Third stops inside the range. The range's own ends are always included, for example f/22.6. |
| Not entered | The full table. CineMate notes "aperture range not set". Commands outside the lens's real range do nothing. |

The full table:

```text
1.0 1.1 1.2 1.4 1.6 1.8 2.0 2.2 2.5 2.8 3.2 3.5 4.0 4.5 5.0 5.6 6.3 7.1 8.0 9.0 10 11 13 14 16 18 20 22 25 29 32
```

The numbers are printed on the lens or in its datasheet. On a zoom lens the maximum opening can change with focal length; enter the value you will use.

## Calibration

Calibration teaches CineMate and the board the lens's focus range: how far the motor travels and how motor position relates to distance. An uncalibrated lens may refuse some focus moves.

**Set the lens's AF/MF switch to AF first.** On MF the lens may ignore focus commands.

### Two ways to start it

| Way | How |
|---|---|
| **Button** | **Calibrate** in the settings editor's [calibrator](panes.md#the-calibrator), or `calibrate lens`, or a button assigned to `calibrate_lens` |
| **Gesture on the lens** | Flip the AF/MF switch **three times within 15 seconds**. The board runs its self-test. CineMate sees it and calibrates when it ends. |

CineMate never calibrates by itself on boot or on a toggle.

!!! warning "The gesture leaves the switch on the other side"
    Three flips end on the opposite side from where you started. **Start on MF**, and the switch ends on **AF**. If you started on AF, it ends on MF and the calibration will not move the lens. Flip it back to AF and press **Calibrate**.

    The gesture is only seen if the board exposes its self-test to CineMate. If nothing happens, use the button.

### What it does

| Step | |
|---|---|
| 1 | Sends the board's calibrate command and samples position and distance while the lens sweeps |
| 2 | Checks that the lens actually moved. If not: "set the lens to AF and try again". |
| 3 | If distance changes along the sweep (the lens has a **distance encoder**), builds a multi-point map |
| 4 | If distance never changes, builds a two-point map from the position range and the minimum focus distance. The far end is at 97% of the range, clear of the end stop. |
| 5 | Puts the result in the working lens. **You save it.** |

A lens with no focus feedback at all (position always 0) fails step 2 in a way that retrying does not fix. CineMate then marks the lens's focus capability `false`. See below.

## Capabilities

Lenses differ. Some move the iris but report no focus position. Each entry records what works:

| Capability | `true` | `false` | `null` |
|---|---|---|---|
| `iris` | Iris commands engage | Iris commands do nothing | Not tested |
| `focus` | Focus moves and reports a position | The lens reports no position, so calibration cannot work | Not tested |
| `autofocus` | Reserved | Reserved | Not tested |

| Rule | |
|---|---|
| A failed calibration sets it | When calibration fails because the lens never reports a focus position, the working lens gets `focus: false`. You save it. |
| Unsupported means greyed | A control the lens cannot do is greyed or does nothing, and says why. It is never a silent failure. |

Edit the flags in the entry by hand if you know better. `null` means CineMate has not seen the lens fail.
