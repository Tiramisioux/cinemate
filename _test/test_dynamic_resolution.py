import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.dynamic_resolution import (
    choose_resolution,
    load_profile_rows,
    max_fps_for_context,
    update_observed_profile,
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

    def test_observed_profile_is_only_loaded_when_user_opts_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            settings_file = tmp_path / "src" / "settings.json"
            settings_file.parent.mkdir()
            profiles_file = tmp_path / "resources" / "profiles.json"
            observed_file = tmp_path / "src" / "observed.json"
            profiles_file.parent.mkdir()
            profiles_file.write_text(
                json.dumps({"profiles": {"default": [IMX585_TABLE[1]]}}),
                encoding="utf-8",
            )
            observed_file.write_text(
                json.dumps(
                    {
                        "profiles": {
                            "observed": [
                                {
                                    **IMX585_TABLE[1],
                                    "max_fps_no_buffer": 42,
                                    "confidence": "observed",
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            config = {
                "profiles_file": "resources/profiles.json",
                "observed_profiles_file": "observed.json",
                "profile": "default",
                "observed_profile": "observed",
            }

            standard_rows = load_profile_rows(config, settings_file=settings_file)
            observed_rows = load_profile_rows(
                {**config, "use_observed_profile": True},
                settings_file=settings_file,
            )

            self.assertEqual(standard_rows[0]["max_fps"], 40)
            self.assertEqual(observed_rows[0]["max_fps_no_buffer"], 42)

    def test_observed_alias_overrides_standard_sensor_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            settings_file = tmp_path / "src" / "settings.json"
            settings_file.parent.mkdir()
            profiles_file = tmp_path / "resources" / "profiles.json"
            observed_file = tmp_path / "src" / "observed.json"
            profiles_file.parent.mkdir()
            profiles_file.write_text(
                json.dumps(
                    {
                        "profiles": {
                            "default": [
                                {
                                    **IMX585_TABLE[1],
                                    "sensor_aliases": ["imx585_mono"],
                                    "max_fps_no_buffer": 40,
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            observed_file.write_text(
                json.dumps(
                    {
                        "profiles": {
                            "observed": [
                                {
                                    **IMX585_TABLE[1],
                                    "sensor": "imx585_mono",
                                    "max_fps_no_buffer": 38,
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            rows = load_profile_rows(
                {
                    "profiles_file": "resources/profiles.json",
                    "observed_profiles_file": "observed.json",
                    "profile": "default",
                    "observed_profile": "observed",
                    "use_observed_profile": True,
                },
                settings_file=settings_file,
            )

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["sensor"], "imx585_mono")
            self.assertEqual(rows[0]["max_fps_no_buffer"], 38)

    def test_observed_profile_only_replaces_matching_storage_from_grouped_row(self):
        standard_rows = [
            {
                **IMX585_TABLE[1],
                "storage_type": ["cfe", "nvme"],
                "sustainable_fps": 40,
            }
        ]
        observed_rows = [
            {
                **IMX585_TABLE[1],
                "storage_type": "cfe",
                "sustainable_fps": 38,
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            settings_file = tmp_path / "src" / "settings.json"
            settings_file.parent.mkdir()
            profiles_file = tmp_path / "resources" / "profiles.json"
            observed_file = tmp_path / "src" / "observed.json"
            profiles_file.parent.mkdir()
            profiles_file.write_text(
                json.dumps({"profiles": {"default": standard_rows}}),
                encoding="utf-8",
            )
            observed_file.write_text(
                json.dumps({"profiles": {"observed": observed_rows}}),
                encoding="utf-8",
            )

            merged = load_profile_rows(
                {
                    "profiles_file": "resources/profiles.json",
                    "observed_profiles_file": "observed.json",
                    "profile": "default",
                    "observed_profile": "observed",
                    "use_observed_profile": True,
                },
                settings_file=settings_file,
            )

        values = {
            row["storage_type"]: row["sustainable_fps"]
            for row in merged
        }
        self.assertEqual(values["cfe"], 38)
        self.assertEqual(values["nvme"], 40)

    def test_update_observed_profile_writes_local_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "src" / "settings.json"
            settings_file.parent.mkdir()
            config = {
                "observed_profiles_file": "observed.json",
                "observed_profile": "observed",
            }
            observation = {
                "sensor": "imx585",
                "storage_type": "cfe",
                "filesystem": "ext4",
                "width": 3856,
                "height": 2180,
                "bit_depth": 12,
                "observed_fps": 41,
                "max_fps_no_buffer": 40,
                "duration_seconds": 30,
                "buffer_peak_frames": 2,
                "drop_frames": 0,
                "result": "buffer_or_drop",
                "observed_at": "2026-05-23T00:00:00+0000",
            }

            self.assertTrue(
                update_observed_profile(config, observation, settings_file=settings_file)
            )
            data = json.loads((settings_file.parent / "observed.json").read_text())
            row = data["profiles"]["observed"][0]

            self.assertEqual(row["sustainable_fps"], 40)
            self.assertEqual(row["max_fps_no_buffer"], 40)
            self.assertEqual(row["failure_count"], 1)
            self.assertEqual(row["last_result"], "buffer_or_drop")

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
