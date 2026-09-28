"""One loader for resources/aspect_ratios.json -- the canonical ratio table.

ASPECT-RATIOS.md, "What CineMate does with this", step 2/5: id, exact value,
common name, in one file both the Python side (SensorDetect's per-sensor
availability derivation and the ratio matcher) and, from WP-CM-7, the
settings page read. A second copy in JavaScript is the mistake
resources/sensors.json's own loader (module.sensor_database) already exists
to avoid -- this module mirrors that one's shape deliberately.

Stdlib only, and no import of anything under module/ that pulls in redis:
the settings editor blueprint has to read this with no camera attached and
no Redis running, exactly like the sensor database.

resources/aspect_ratios.json is strict JSON (no comments), same convention
as resources/sensors.json -- a stray `//` would take the whole file down.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

DEFAULT_ASPECT_RATIO_TABLE_FILE = "resources/aspect_ratios.json"

# The two ratios a camera nobody has chosen anything for starts out selected
# on, when it actually offers them, plus its own full frame. SensorDetect.
# _default_ratio_ids applies the rule; see its own docstring.
#
# Operator instruction, 2026-09-28, superseding 2026-09-26's "1.78 or
# closest": "with no [per-sensor] file, the stock rule applies: ratios --
# 1.33:1 if the sensor offers it, 1.78:1 if it offers it, plus its full
# frame; modes -- 1x1 modes on, every mode when the driver does not report
# binning." "Offers" now means literally offered -- a member of
# SensorDetect.available_aspect_ratios(camera), i.e. some mode's own home
# ratio -- never a stand-in found by searching the camera's shapes for the
# nearest thing to a preference.
#
# That is the whole reason this rule replaced 2026-09-26's: "or closest" was
# built to give imx477 something in the 1.78 slot despite having no true
# 16:9 mode (its widest, 2028x1080, is 1.878, home ratio 1.89:1) by treating
# 1.89:1 as a stand-in for 1.78:1 -- but the operator report that produced
# this file (D2 in PLAN.md, 2026-09-28) traced a swapped-sensor bug to
# exactly that kind of inference surviving as a saved choice across a sensor
# swap. The rule is deliberately more literal now: a camera whose delivery
# shape does not exist gets no delivery-slot toggle, full stop, and
# 1.33:1/1.78:1 are never present unless a mode's own aspect actually lands
# on them within ASPECT_RATIO_TOLERANCE.
#
# Worked through, with each camera's real fixture modes (see
# _test/test_aspect_ratio_selection.py for the exact numbers):
#   imx477  (no crop reported -> full frame unknown)     -> 1.33:1 offered, 1.78:1 not (its
#           nearest is 1.89:1, a DIFFERENT id) -> stock = ["1.33:1"] alone.
#   imx585  (cinemate-7modes driver: 1920x1080/3840x2160/1920x1100/3840x2200,
#           all ~16:9, no 4:3 mode)                       -> stock = ["1.78:1"] alone.
#   imx283  (crop-annotated: full frame 5472x3648 = 1.50, off-table)
#                                                           -> stock = [FULL_FRAME_RATIO_ID, "1.78:1"]
#           when it also has a ~16:9 mode; ["1.78:1"] alone for a fixture with
#           no crop annotation at all (full frame then unknown, same as imx477).
# Never empty for a camera that offers ANY ratio: _default_ratio_ids falls
# back to every offered id when neither preference nor the full frame apply.
#
# Operator addendum, 2026-09-28: "imx477 should also open with 2028x1080 --
# not the 4K mode." resources/sensors.json can name an optional per-sensor
# `"stock_selection": {"extra_modes": [{"width": ..., "height": ...}]}`
# block (module.sensor_database), matched against the driver's own mode
# table by width x height (optionally narrowed by bit_depth/hdr) -- never a
# hardcoded camera name in Python. SensorDetect._default_ratio_ids() unions
# in the home ratio id of every entry that matches a real mode; the rest of
# the rule above (three membership checks, "never empty") is otherwise
# unchanged. Worked example, imx477: 2028x1080's home is "1.89:1" (its
# widest 16:9-ish shape, same id 4056x2160 also comes home to) -> stock
# becomes ["1.33:1", "1.89:1"], but SensorDetect._stock_mode_selected()
# only stock-selects an extras-only ratio's modes when they are themselves
# one of the matched extra_modes rows -- so 1.89:1 is ON and 2028x1080 is
# selected, while its sibling 4056x2160 stays offered but unticked (that
# camera's toggle covers both; the extras contract does not).
#
# An id, not a value: the table is the one place a ratio's number lives (that
# is this module's whole job), so this is looked up in it, and a ratio missing
# from the table simply cannot be preferred.
PREFERRED_DELIVERY_RATIO_ID = "1.78:1"

# Checked first, same "only if actually offered" rule as
# PREFERRED_DELIVERY_RATIO_ID above -- see that constant's comment for the
# worked examples. Named "shape" (a 4:3-ish frame) rather than "delivery"
# because it is the slot a camera's OWN full frame most often also fills
# (imx477's 4056x3040 full frame is exactly 1.33:1), not because it behaves
# differently from the delivery slot in the rule itself; both are plain
# membership tests against available_aspect_ratios(camera), tried in the
# same order every time: 1.33:1, then 1.78:1, then the full frame.
PREFERRED_SHAPE_RATIO_ID = "1.33:1"

# The id of the synthetic "whole sensor" toggle, which is NOT in
# resources/aspect_ratios.json and deliberately so: it does not name a shape,
# it names "whatever this sensor reads when it reads everything". Its value,
# label and very existence are per-camera, so it cannot live in a table shared
# by every camera.
#
# Operator instruction, 2026-09-22: "among the aspect ratios, also add the full
# option (last). then i get the full frame options for the sensor regardless of
# aspect ratio. unless the full frame actually _is_ one of the aspect ratios.
# then this option should read: 1.33:1 (full)".
#
# So there are two shapes this takes, decided per camera in
# SensorDetect.full_frame_ratio():
#
#   - the sensor's full frame IS one of the table's ratios (within
#     ASPECT_RATIO_TOLERANCE) -- imx585's 3840x2160 is 1.78, imx477's 4056x3040
#     is 1.33 -- and then NO extra toggle appears. The existing one carries
#     `is_full: true` so the pane/default know it also covers the whole
#     sensor, but its label is unchanged: "1.78:1", not "1.78:1 (full)" (the
#     operator dropped the suffix on 2026-09-22, revising their own earlier
#     request for one -- see available_aspect_ratios()'s own comment).
#   - the sensor's full frame is a shape the table does not carry -- the
#     imx283 is a 3:2 sensor at 1.50, and 1.50 is not one of the fourteen --
#     and then this id appears as its own toggle, placed by value among the
#     table's ratios (not merely appended last), labelled with the real
#     aspect and no suffix either: "1.50:1".
#
# Why it is not simply a fifteenth row in the table: 1.50 is the imx283's
# native shape and nothing at all on an imx585, and a table entry would offer
# it on every camera. The toggle has to be derived from the sensor in front of
# you, which is the same reason available_aspect_ratios() is derived and never
# stored.
FULL_FRAME_RATIO_ID = "full"

# Prefix for a mode whose own real aspect is neither within
# ASPECT_RATIO_TOLERANCE of any canonical ratio nor this camera's full frame:
# "no closest" (operator, 2026-09-28 -- PLAN.md, superseding the near-tie/
# tolerance-union matching this rule replaced) means such a mode still needs
# its OWN reachable toggle rather than being folded into whichever canonical
# ratio happens to be nearest. SensorDetect.home_ratio_id() builds the full id
# as f"{NATIVE_RATIO_PREFIX}{aspect:.2f}", e.g. "native:1.50" -- always two
# decimal places, matching _mode_aspect()'s own rounding, so the same real
# shape always produces the same id. Never a member of the loaded table
# (load_aspect_ratio_table() only ever returns resources/aspect_ratios.json's
# fourteen rows) and never equal to FULL_FRAME_RATIO_ID, which is reserved for
# a mode that reads the WHOLE sensor -- home_ratio_id() folds a non-full mode
# that happens to share the off-table full frame's rounded aspect into
# FULL_FRAME_RATIO_ID instead of minting a native id here, specifically so the
# two toggles a camera could otherwise show for the same real shape collapse
# into one.
NATIVE_RATIO_PREFIX = "native:"

logger = logging.getLogger(__name__)

_EMPTY: list[dict[str, Any]] = []


def repo_root() -> Path:
    # src/module/aspect_ratios.py -> repo root
    return Path(__file__).resolve().parents[2]


def resolve_aspect_ratio_table_path(path_value: str | None = None) -> Path:
    path = Path(path_value or DEFAULT_ASPECT_RATIO_TABLE_FILE)
    return path if path.is_absolute() else repo_root() / path


def load_aspect_ratio_table(path_value: str | None = None) -> list[dict[str, Any]]:
    """Parse the canonical ratio table, or return an empty one after warning.

    A missing/broken table must not stop CineMate from booting -- it falls
    back to no ratios matching, which _finalize_modes's existing "never leave
    a camera without modes" fallback already covers -- but it has to be
    loud: silently running with no ratio table looks like "no ratio is
    offered", not like a broken file.
    """
    path = resolve_aspect_ratio_table_path(path_value)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        logger.warning("Aspect ratio table unavailable (%s): %s", path, exc)
        return list(_EMPTY)
    except json.JSONDecodeError as exc:
        logger.warning("Aspect ratio table is invalid JSON (%s): %s", path, exc)
        return list(_EMPTY)

    ratios = data.get("ratios") if isinstance(data, dict) else None
    if not isinstance(ratios, list):
        logger.warning("Aspect ratio table %s has no ratios array", path)
        return list(_EMPTY)

    out: list[dict[str, Any]] = []
    for entry in ratios:
        if not isinstance(entry, dict):
            continue
        rid = entry.get("id")
        value = entry.get("value")
        if rid is None or value is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        out.append({
            "id": str(rid),
            "value": value,
            "name": entry.get("name", str(rid)),
        })
    return out
