import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.dynamic_resolution import (
    choose_resolution,
    dynamic_resolution_indicator_active,
    load_profile_rows,
    max_fps_for_context,
)


IMX585_MODES = {
    0: {"width": 1928, "height": 1090, "bit_depth": 12, "fps_max": 87},
    1: {"width": 3840, "height": 2160, "bit_depth": 12, "fps_max": 40},
}

IMX585_DETECTED_ORDER_MODES = {
    0: {"width": 3856, "height": 2180, "bit_depth": 12, "fps_max": 43},
    1: {"width": 1928, "height": 1090, "bit_depth": 12, "fps_max": 50},
}

IMX585_TABLE = [
    {
        "sensor": "imx585",
        "storage_type": "cfe",
        "filesystem": "ext4",
        "width": 1928,
        "height": 1090,
        "bit_depth": 12,
        "sustainable_fps": 50,
    },
    {
        "sensor": "imx585",
        "storage_type": "cfe",
        "filesystem": "ext4",
        "width": 3856,
        "height": 2180,
        "bit_depth": 12,
        "max_fps": 40,
    },
]


class DynamicResolutionTests(unittest.TestCase):
    def test_resolution_indicator_only_when_current_mode_differs_from_desired_mode(self):
        self.assertFalse(
            dynamic_resolution_indicator_active(
                enabled=True,
                active=True,
                current_mode=0,
                desired_mode=0,
            )
        )
        self.assertTrue(
            dynamic_resolution_indicator_active(
                enabled=True,
                active=True,
                current_mode=1,
                desired_mode=0,
            )
        )
        self.assertTrue(
            dynamic_resolution_indicator_active(
                enabled=True,
                active=False,
                current_mode=1,
                desired_mode=0,
            )
        )
        self.assertFalse(
            dynamic_resolution_indicator_active(
                enabled=False,
                active=True,
                current_mode=1,
                desired_mode=0,
            )
        )

    def test_switches_down_when_requested_fps_exceeds_desired_mode(self):
        choice = choose_resolution(
            sensor_modes=IMX585_MODES,
            desired_mode=1,
            requested_fps=41,
            sensor="imx585",
            storage_type="cfe",
            filesystem="ext4",
            performance_table=IMX585_TABLE,
            tolerance_px=32,
        )

        self.assertIsNotNone(choice)
        self.assertEqual(choice.mode, 0)
        self.assertTrue(choice.dynamic_active)

    def test_keeps_desired_mode_at_or_below_observed_limit(self):
        choice = choose_resolution(
            sensor_modes=IMX585_MODES,
            desired_mode=1,
            requested_fps=40,
            sensor="imx585",
            storage_type="cfe",
            filesystem="ext4",
            performance_table=IMX585_TABLE,
            tolerance_px=32,
        )

        self.assertIsNotNone(choice)
        self.assertEqual(choice.mode, 1)
        self.assertFalse(choice.dynamic_active)

    def test_returns_none_when_storage_filesystem_has_no_data(self):
        choice = choose_resolution(
            sensor_modes=IMX585_MODES,
            desired_mode=1,
            requested_fps=41,
            sensor="imx585",
            storage_type="cfe",
            filesystem="exfat",
            performance_table=IMX585_TABLE,
            tolerance_px=32,
        )

        self.assertIsNone(choice)

    def test_mono_sensor_uses_base_sensor_table(self):
        choice = choose_resolution(
            sensor_modes=IMX585_MODES,
            desired_mode=1,
            requested_fps=41,
            sensor="imx585_mono",
            storage_type="cfe",
            filesystem="ext4",
            performance_table=IMX585_TABLE,
            tolerance_px=32,
        )

        self.assertIsNotNone(choice)
        self.assertEqual(choice.mode, 0)

    def test_dynamic_max_fps_uses_measured_context_when_desired_mode_has_data(self):
        fps_max = max_fps_for_context(
            sensor_modes=IMX585_MODES,
            desired_mode=1,
            sensor="imx585",
            storage_type="cfe",
            filesystem="ext4",
            performance_table=IMX585_TABLE,
            tolerance_px=32,
        )

        self.assertEqual(fps_max, 50)

    def test_stock_profile_exposes_ssd_exfat_lower_mode_max(self):
        rows = load_profile_rows(
            {
                "profiles_file": "resources/dynamic_resolution_profiles.json",
                "profile": "default",
            },
            settings_file=ROOT / "src" / "settings.json",
        )

        fps_max = max_fps_for_context(
            sensor_modes=IMX585_MODES,
            desired_mode=1,
            sensor="imx585_mono",
            storage_type="SSD",
            filesystem="exFAT",
            performance_table=rows,
            tolerance_px=32,
        )
        choice = choose_resolution(
            sensor_modes=IMX585_MODES,
            desired_mode=1,
            requested_fps=26,
            sensor="imx585_mono",
            storage_type="USB SSD",
            filesystem="exfat",
            performance_table=rows,
            tolerance_px=32,
        )
        restored_choice = choose_resolution(
            sensor_modes=IMX585_MODES,
            desired_mode=1,
            requested_fps=25,
            sensor="imx585_mono",
            storage_type="ssd",
            filesystem="exfat",
            performance_table=rows,
            tolerance_px=32,
        )

        self.assertEqual(fps_max, 50)
        self.assertIsNotNone(choice)
        self.assertEqual(choice.mode, 0)
        self.assertTrue(choice.dynamic_active)
        self.assertEqual(choice.desired_row.max_fps, 25)
        self.assertIsNotNone(restored_choice)
        self.assertEqual(restored_choice.mode, 1)
        self.assertFalse(restored_choice.dynamic_active)

    def test_stock_profile_handles_live_imx585_detected_mode_order(self):
        rows = load_profile_rows(
            {
                "profiles_file": "resources/dynamic_resolution_profiles.json",
                "profile": "default",
            },
            settings_file=ROOT / "src" / "settings.json",
        )

        fps_max = max_fps_for_context(
            sensor_modes=IMX585_DETECTED_ORDER_MODES,
            desired_mode=0,
            sensor="imx585",
            storage_type="ssd",
            filesystem="exfat",
            performance_table=rows,
            tolerance_px=32,
        )
        high_fps_choice = choose_resolution(
            sensor_modes=IMX585_DETECTED_ORDER_MODES,
            desired_mode=0,
            requested_fps=43,
            sensor="imx585",
            storage_type="ssd",
            filesystem="exfat",
            performance_table=rows,
            tolerance_px=32,
        )
        restored_choice = choose_resolution(
            sensor_modes=IMX585_DETECTED_ORDER_MODES,
            desired_mode=0,
            requested_fps=25,
            sensor="imx585",
            storage_type="ssd",
            filesystem="exfat",
            performance_table=rows,
            tolerance_px=32,
        )

        self.assertEqual(fps_max, 50)
        self.assertIsNotNone(high_fps_choice)
        self.assertEqual(high_fps_choice.mode, 1)
        self.assertTrue(high_fps_choice.dynamic_active)
        self.assertIsNotNone(restored_choice)
        self.assertEqual(restored_choice.mode, 0)
        self.assertFalse(restored_choice.dynamic_active)

    def test_dynamic_max_fps_stays_unset_when_desired_mode_has_no_data(self):
        table_without_4k = [IMX585_TABLE[0]]
        fps_max = max_fps_for_context(
            sensor_modes=IMX585_MODES,
            desired_mode=1,
            sensor="imx585",
            storage_type="cfe",
            filesystem="ext4",
            performance_table=table_without_4k,
            tolerance_px=32,
        )

        self.assertIsNone(fps_max)

    def test_stock_profile_uses_excel_imx585_values(self):
        rows = load_profile_rows(
            {
                "profiles_file": "resources/dynamic_resolution_profiles.json",
                "profile": "default",
            },
            settings_file=ROOT / "src" / "settings.json",
        )

        imx585_rows = [
            row for row in rows
            if row.get("sensor") == "imx585"
            and row.get("width") == 3856
            and row.get("height") == 2180
        ]
        values = {
            (
                tuple(row["storage_type"])
                if isinstance(row["storage_type"], list)
                else row["storage_type"],
                row["filesystem"],
            ): row["sustainable_fps"]
            for row in imx585_rows
        }

        self.assertEqual(values[(("cfe", "nvme"), "ext4")], 40)
        self.assertEqual(values[(("cfe", "nvme"), "exfat")], 38)
        self.assertEqual(values[("ssd", "ext4")], 25)
        self.assertEqual(values[("ssd", "exfat")], 25)


if __name__ == "__main__":
    unittest.main()
