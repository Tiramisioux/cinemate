"""The HDMI GUI's Pinefeat lens surface: the IRIS top-row group and the SYS EF
and CAL boxes (PLAN D10). Same dict feeds the web GUI, so the field decisions
tested here are the web GUI's too.

States under test, for the IRIS group: hidden (no adapter), grey (found, but
lens control is off / no lens / iris capability false), normal (effective).
"""
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image, ImageDraw  # noqa: E402

from test_simple_gui_no_camera import FakeFramebuffer, make_gui  # noqa: E402

from module.design_tokens import DESIGN_TOKENS  # noqa: E402
from module.redis_controller import ParameterKey  # noqa: E402
from module.simple_gui import _format_iris  # noqa: E402


class FakeLens:
    """The slice of LensController the GUI touches."""

    def __init__(self, capabilities=None, entries=None):
        self._capabilities = capabilities or {"iris": True, "focus": True, "autofocus": None}
        self._entries = entries or {}

    def working_entry(self):
        return {"capabilities": dict(self._capabilities), "key": None}

    def entries(self):
        return dict(self._entries)


def lens_gui(*, found=True, enabled=True, state="ready", iris="2.8", capabilities=None,
             entries=None, steps=(2.8, 4.0, 5.6)):
    gui = make_gui()
    r = gui.redis_controller.values
    r[ParameterKey.LENS_DETECTED.value] = "1" if found else "0"
    r[ParameterKey.LENS_CONTROL.value] = "1" if enabled else "0"
    r[ParameterKey.LENS_STATE.value] = state
    r[ParameterKey.IRIS.value] = iris
    r[ParameterKey.LENS_KEY.value] = "sigma"
    r[ParameterKey.LENS_NAME.value] = "Sigma 18-35"
    r[ParameterKey.LENS_ID.value] = "235"
    r[ParameterKey.LENS_MESSAGE.value] = "Sigma ready"
    gui.cinepi_controller.lens_controller = FakeLens(capabilities, entries)
    gui.cinepi_controller.iris_steps = lambda: list(steps)
    return gui


class FormatIrisTests(unittest.TestCase):
    def test_f_number_style(self):
        self.assertEqual(_format_iris("2.8"), "F2.8")
        self.assertEqual(_format_iris("22"), "F22")
        self.assertEqual(_format_iris("22.0"), "F22")
        self.assertEqual(_format_iris(8.0), "F8")

    def test_unknown_is_dashes(self):
        for value in ("", None, "abc", "0", "-1"):
            self.assertEqual(_format_iris(value), "F--", value)


class IrisStateTests(unittest.TestCase):
    def values(self, **kw):
        return lens_gui(**kw).populate_values()

    def test_hidden_when_the_adapter_is_not_found(self):
        v = self.values(found=False)
        self.assertEqual(v["iris_state"], "hidden")
        self.assertEqual(v["lens_ef_state"], "")
        self.assertEqual(v["lens_options"], [])
        self.assertEqual(v["iris_steps"], [])

    def test_hidden_with_no_lens_block_at_all(self):
        # a controller built without the lens: no keys in Redis, no attribute
        v = make_gui().populate_values()
        self.assertEqual(v["iris_state"], "hidden")

    def test_normal_when_effective(self):
        v = self.values()
        self.assertEqual(v["iris_state"], "normal")
        self.assertEqual(v["iris"], "F2.8")
        self.assertEqual(v["iris_label"], "IRIS")
        self.assertEqual(v["iris_grey_reason"], "")
        self.assertEqual(v["iris_steps"], [2.8, 4.0, 5.6])
        self.assertEqual(v["lens_ef_state"], "on")
        self.assertEqual(v["lens_key"], "sigma")

    def test_grey_when_lens_control_is_off(self):
        v = self.values(enabled=False)
        self.assertEqual(v["iris_state"], "grey")
        self.assertEqual(v["iris_grey_reason"], "Lens control is off")
        self.assertEqual(v["lens_ef_state"], "off")
        # the value still shows what was last commanded
        self.assertEqual(v["iris"], "F2.8")

    def test_grey_when_no_lens_is_mounted(self):
        v = self.values(state="no_lens", iris="")
        self.assertEqual(v["iris_state"], "grey")
        self.assertEqual(v["iris"], "F--")
        self.assertEqual(v["lens_ef_state"], "no_lens")

    def test_grey_when_the_entry_says_the_iris_does_nothing(self):
        v = self.values(capabilities={"iris": False, "focus": True, "autofocus": None})
        self.assertEqual(v["iris_state"], "grey")
        self.assertIn("iris", v["iris_grey_reason"].lower())

    def test_untested_iris_capability_is_not_grey(self):
        v = self.values(capabilities={"iris": None, "focus": None, "autofocus": None})
        self.assertEqual(v["iris_state"], "normal")

    def test_unknown_and_uncalibrated_lenses_stay_normal(self):
        # iris works for both; only focus needs the calibration
        for state in ("unknown_lens", "uncalibrated"):
            v = self.values(state=state)
            self.assertEqual(v["iris_state"], "normal", state)
            self.assertEqual(v["lens_ef_state"], "on", state)

    def test_calibrating_sets_the_cal_flag(self):
        self.assertTrue(self.values(state="calibrating")["lens_calibrating"])
        self.assertFalse(self.values(state="ready")["lens_calibrating"])
        self.assertFalse(self.values(found=False, state="calibrating")["lens_calibrating"])

    def test_error_state_is_grey_and_crossed(self):
        v = self.values(state="error")
        self.assertEqual(v["iris_state"], "grey")
        self.assertEqual(v["lens_ef_state"], "error")

    def test_lens_options_come_from_the_database_sorted_by_name(self):
        entries = {
            "b": {"name": "Zeiss 50", "lens_id": 3},
            "a": {"name": "canon 24", "lens_id": 9},
        }
        v = self.values(entries=entries)
        self.assertEqual([o["key"] for o in v["lens_options"]], ["a", "b"])
        self.assertEqual(v["lens_options"][0], {"key": "a", "name": "canon 24", "lens_id": 9})

    def test_colours_follow_the_state(self):
        gui = lens_gui(enabled=False)
        gui.populate_values()
        self.assertEqual(gui.colors["iris"]["normal"], DESIGN_TOKENS["dim"])
        self.assertEqual(gui.colors["iris_label"]["normal"], DESIGN_TOKENS["dim"])
        gui = lens_gui()
        gui.populate_values()
        self.assertEqual(gui.colors["iris"]["normal"], DESIGN_TOKENS["value"])
        self.assertEqual(gui.colors["iris_label"]["normal"], DESIGN_TOKENS["label"])
        self.assertEqual(gui.colors["iris"]["inverse"], "black")


def measured_layout(values, width=1920, height=1080):
    gui = lens_gui()
    image = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(image)
    return gui, gui._top_row_layout(draw, values, width / 1920, height / 1080, None)[0]


class TopRowLayoutTests(unittest.TestCase):
    BASE = {
        "fps_label": "FPS", "fps": 24,
        "shutter_label": "SHUTTER", "shutter_speed": "180.0°",
        "exposure_label": "EXP", "exposure_time": "1/48",
        "iris_label": "IRIS", "iris": "F2.8",
        "iso_label": "EI", "iso": 800,
        "wb_label": "WB", "color_temp": "5600 K",
        "res_label": "RES", "res": "4056×3040 :12b",
    }

    def test_six_groups_without_the_adapter(self):
        values = dict(self.BASE, iris_state="hidden")
        _, x = measured_layout(values)
        self.assertNotIn("iris", x)
        self.assertNotIn("iris_label", x)
        self.assertEqual(len([k for k in x if k.endswith("_label")]), 6)

    def test_a_frame_without_iris_state_is_the_old_six_group_row(self):
        values = dict(self.BASE)
        _, x = measured_layout(values)
        self.assertNotIn("iris", x)

    def test_iris_sits_between_exp_and_iso(self):
        for state in ("normal", "grey"):
            values = dict(self.BASE, iris_state=state)
            _, x = measured_layout(values)
            self.assertLess(x["exposure_time"], x["iris_label"], state)
            self.assertLess(x["iris_label"], x["iris"], state)
            self.assertLess(x["iris"], x["iso_label"], state)

    def test_the_other_groups_make_room_rather_than_overlap(self):
        gui = lens_gui()
        draw = ImageDraw.Draw(Image.new("RGBA", (1920, 1080)))
        wide = dict(self.BASE, iris_state="normal", iris="F22")
        narrow = dict(self.BASE, iris_state="hidden")
        x_wide = gui._top_row_layout(draw, wide, 1.0, 1.0, None)[0]
        x_narrow = gui._top_row_layout(draw, narrow, 1.0, 1.0, None)[0]
        # the row is justified between fixed ends, so adding a group pulls the
        # earlier groups' neighbours closer together rather than pushing RES out
        self.assertLess(x_wide["shutter_label"], x_narrow["shutter_label"])
        self.assertLess(x_wide["exposure_label"], x_narrow["exposure_label"])

    def worst_case(self):
        # the longest string each group can show, plus both badges' room
        return dict(
            self.BASE,
            iris_state="normal", iris="F32",
            fps=120, shutter_speed="359.9°", exposure_time="1/1000",
            iso=12800, color_temp="10000 K", res="3840×2160 :16b",
        )

    def test_all_seven_groups_fit_at_the_configured_widths(self):
        from module import simple_gui as sg

        badge = {"width": 70}    # a ClearHDR sensor's SDR/HDR pill, the widest tail
        for width, height in ((1920, 1080), (1280, 720), (1024, 600), (800, 480), (3840, 2160)):
            gui = lens_gui()
            draw = ImageDraw.Draw(Image.new("RGBA", (width, height)))
            shrink_x, shrink_y = width / 1920, height / 1080
            values = self.worst_case()
            x, badge_x = gui._top_row_layout(draw, values, shrink_x, shrink_y,
                                             dict(badge, width=badge["width"] * shrink_x))
            order = [k for g in gui._active_top_row_groups(values) for k in g]
            xs = [x[k] for k in order]
            self.assertEqual(xs, sorted(xs), f"{width}x{height}: groups out of order")
            self.assertEqual(len(order), 14)
            # every value ends before the next label starts (positive gap)
            for (label_key, value_key), (next_label, _) in zip(
                    gui._active_top_row_groups(values), gui._active_top_row_groups(values)[1:]):
                value_w = gui._measure_layout_text(draw, value_key, values, shrink_x, shrink_y)
                self.assertGreater(x[next_label], x[value_key] + value_w,
                                   f"{width}x{height}: {value_key} runs into {next_label}")
            # and the badge ends on the anchor, not past it
            res_w = gui._measure_layout_text(draw, "res", values, shrink_x, shrink_y)
            self.assertLessEqual(badge_x + badge["width"] * shrink_x,
                                 sg.RES_RIGHT_ANCHOR * shrink_x + 1,
                                 f"{width}x{height}: RES badge past the anchor")
            self.assertGreater(res_w, 0)


class DrawingTests(unittest.TestCase):
    def draw_frame(self, gui):
        gui.fb = FakeFramebuffer()
        gui.disp_width, gui.disp_height = 1920, 1080
        values = gui.populate_values()
        captured = {}
        gui.fb.show = lambda image: captured.setdefault("image", image)
        gui.draw_gui(values)
        return values, captured["image"]

    def region_brightness(self, image, box):
        crop = image.crop(box).convert("L")
        return crop.getextrema()[1]

    def test_draw_gui_renders_all_states_without_raising(self):
        for kwargs in ({}, {"enabled": False}, {"found": False}, {"state": "no_lens", "iris": ""},
                       {"state": "calibrating"}):
            self.draw_frame(lens_gui(**kwargs))

    def iris_box(self, gui, values, image):
        """A crop around where the IRIS group was laid out (top row)."""
        draw = ImageDraw.Draw(image)
        x, _ = gui._top_row_layout(draw, values, 1.0, 1.0, None)
        left = x["iris_label"]
        right = x["iris"] + gui._measure_layout_text(draw, "iris", values, 1.0, 1.0)
        # y 0-45: the preview guide's white outline starts at y 50
        return (int(left), 0, int(right) + 1, 45)

    def test_normal_iris_value_is_drawn_bright_and_grey_is_dimmer(self):
        gui = lens_gui()
        values, image = self.draw_frame(gui)
        bright = self.region_brightness(image, self.iris_box(gui, values, image))
        self.assertGreater(bright, 200)

        gui = lens_gui(enabled=False)
        values, image = self.draw_frame(gui)
        dim = self.region_brightness(image, self.iris_box(gui, values, image))
        self.assertLessEqual(dim, DESIGN_TOKENS["dim"][0] + 2)
        self.assertGreater(dim, 40)      # drawn, not absent

    def test_a_hidden_iris_group_paints_nothing_where_it_would_be(self):
        # with the adapter absent the row is the six old groups; the strip the
        # IRIS group would occupy is whatever the neighbours put there
        gui = lens_gui(found=False)
        values, image = self.draw_frame(gui)
        draw = ImageDraw.Draw(image)
        x, _ = gui._top_row_layout(draw, values, 1.0, 1.0, None)
        self.assertNotIn("iris", x)

    def sys_boxes(self, gui):
        drawn = []
        original = gui._draw_status_box

        def record(draw, box, text, fill, font, text_color, *, crossed=False):
            drawn.append((text, fill, crossed))
            return original(draw, box, text, fill, font, text_color, crossed=crossed)

        gui._draw_status_box = record
        values = gui.populate_values()
        gui.draw_left_sections(ImageDraw.Draw(Image.new("RGBA", (1920, 1080))), values)
        return drawn

    def test_ef_box_when_found_and_on(self):
        drawn = self.sys_boxes(lens_gui())
        self.assertIn(("EF", DESIGN_TOKENS["box"], False), drawn)
        self.assertNotIn("CAL", [d[0] for d in drawn])

    def test_ef_box_is_dim_when_lens_control_is_off(self):
        drawn = self.sys_boxes(lens_gui(enabled=False))
        self.assertIn(("EF", DESIGN_TOKENS["dim"], False), drawn)

    def test_ef_box_is_crossed_with_no_lens(self):
        drawn = self.sys_boxes(lens_gui(state="no_lens"))
        self.assertIn(("EF", DESIGN_TOKENS["box"], True), drawn)

    def test_unknown_lens_is_not_marked(self):
        drawn = self.sys_boxes(lens_gui(state="unknown_lens"))
        self.assertIn(("EF", DESIGN_TOKENS["box"], False), drawn)

    def test_cal_box_while_calibrating(self):
        drawn = self.sys_boxes(lens_gui(state="calibrating"))
        self.assertIn("CAL", [d[0] for d in drawn])
        self.assertLess([d[0] for d in drawn].index("EF"), [d[0] for d in drawn].index("CAL"))

    def test_no_ef_box_without_the_adapter(self):
        drawn = self.sys_boxes(lens_gui(found=False))
        self.assertNotIn("EF", [d[0] for d in drawn])

    def test_sys_header_appears_for_the_adapter_alone(self):
        # nothing else in SYS (no serial, mic, keyboard, storage): the EF box
        # must still bring its heading with it
        gui = lens_gui()
        gui.serial_handler = types.SimpleNamespace(serial_connected=False)
        labels = []
        draw = ImageDraw.Draw(Image.new("RGBA", (1920, 1080)))
        original_text = draw.text
        draw.text = lambda xy, text, **kw: (labels.append(text), original_text(xy, text, **kw))[1]
        gui.draw_left_sections(draw, gui.populate_values())
        self.assertIn("SYS", labels)


if __name__ == "__main__":
    unittest.main()
