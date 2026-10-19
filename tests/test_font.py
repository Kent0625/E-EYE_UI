import os
import unittest
from fontTools.ttLib import TTFont

class TestInterFont(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.font_path = os.path.join(self.base_dir, "app", "static", "fonts", "inter-latin-variable.woff2")
        self.license_path = os.path.join(self.base_dir, "app", "static", "fonts", "LICENSE.txt")
        self.ofl_path = os.path.join(self.base_dir, "app", "static", "fonts", "OFL.txt")

    def test_font_file_exists(self):
        self.assertTrue(os.path.exists(self.font_path), f"Font file missing at {self.font_path}")

    def test_font_family_name_is_inter(self):
        """Asserts the TrueType/OpenType name table declares font family 'Inter'."""
        font = TTFont(self.font_path)
        name_table = font["name"]
        
        # NameID 1 = Font Family name, NameID 16 = Typographic Family name
        family_names = [n.toStr() for n in name_table.names if n.nameID in (1, 16)]
        self.assertTrue(len(family_names) > 0, "No family name found in font name table")
        self.assertIn("Inter", family_names, f"Expected 'Inter' in family names, got: {family_names}")

    def test_sil_ofl_license_exists(self):
        """Asserts SIL Open Font License is preserved alongside the font file."""
        self.assertTrue(os.path.exists(self.license_path), "LICENSE.txt missing in fonts directory")
        self.assertTrue(os.path.exists(self.ofl_path), "OFL.txt missing in fonts directory")
        with open(self.license_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("SIL OPEN FONT LICENSE", content)

if __name__ == "__main__":
    unittest.main()
