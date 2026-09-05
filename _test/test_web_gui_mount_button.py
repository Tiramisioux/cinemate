"""The mount button needs the mount flag, and it was never sent one.

It only ever said UNMOUNT and only ever sent unmount, so an unmounted drive
could not be remounted from the shooting screen. Reading is_mounted fixed the
first half and not the second: populate_values() -- the dict the page is
seeded and updated with -- carried storage_type but not is_mounted, so the
flag was undefined in the browser. undefined reads as not-mounted, which is
why the button said MOUNT over a mounted drive and then sent mount at it,
which does nothing.

storage_type is not a substitute: it names the device, not whether it is
mounted.
"""

import re
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "template.html"
SIMPLE_GUI = ROOT / "src" / "module" / "simple_gui.py"


class MountButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")
        cls.gui = SIMPLE_GUI.read_text(encoding="utf-8")

    def test_the_page_is_actually_sent_the_flag_it_reads(self):
        self.assertIn('"is_mounted":', self.gui)
        self.assertIn("ParameterKey.IS_MOUNTED.value", self.gui)

    def test_the_button_reads_that_flag_rather_than_the_device_name(self):
        self.assertIn("truthy(V.is_mounted)", self.html)

    def test_the_label_says_which_way_it_goes(self):
        self.assertIn("mountBtn.textContent = mounted ? 'UNMOUNT' : 'MOUNT';", self.html)

    def test_the_click_sends_the_matching_command(self):
        handler = re.search(r"\$\('btn-unmount'\)\.addEventListener\('click'.*?\}\);",
                            self.html, re.S).group(0)
        self.assertIn("truthy(V.is_mounted) ? 'unmount' : 'mount'", handler)

    def test_the_state_is_read_at_click_time(self):
        # bound once, it would keep sending whatever was true at page load
        handler = re.search(r"\$\('btn-unmount'\)\.addEventListener\('click'.*?\}\);",
                            self.html, re.S).group(0)
        self.assertIn("V.is_mounted", handler)

    def test_truthy_accepts_the_string_redis_actually_stores(self):
        # redis hands back "1"/"0" as strings, not booleans
        helper = re.search(r"const truthy = .*?;", self.html, re.S).group(0)
        self.assertIn("'1'", helper)


if __name__ == "__main__":
    unittest.main()
