import os
import json
import unittest

class TestI18n(unittest.TestCase):
    def setUp(self):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "static", "i18n"))
        with open(os.path.join(base_dir, "en.json"), "r", encoding="utf-8") as f:
            self.en = json.load(f)
        with open(os.path.join(base_dir, "fil.json"), "r", encoding="utf-8") as f:
            self.fil = json.load(f)

    def test_identical_keys(self):
        en_keys = set(self.en.keys())
        fil_keys = set(self.fil.keys())

        missing_in_fil = en_keys - fil_keys
        extra_in_fil = fil_keys - en_keys

        self.assertEqual(missing_in_fil, set(), f"Keys in en.json missing in fil.json: {missing_in_fil}")
        self.assertEqual(extra_in_fil, set(), f"Extra keys in fil.json not in en.json: {extra_in_fil}")

    def test_non_empty_values(self):
        for k, v in self.en.items():
            self.assertTrue(len(v.strip()) > 0, f"Empty value in en.json for key '{k}'")
        for k, v in self.fil.items():
            self.assertTrue(len(v.strip()) > 0, f"Empty value in fil.json for key '{k}'")

if __name__ == "__main__":
    unittest.main()
