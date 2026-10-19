import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import unittest
from app import store

class TestStore(unittest.TestCase):
    def setUp(self):
        store.init_db()
        store.delete_all_sessions()

    def test_create_and_get_session(self):
        session_data = {
            "id": "test_s1",
            "participant_code": "EE-261019-999",
            "site": "Test Site",
            "consent_age": True,
            "consent_signed": True,
            "status": "created",
            "referral": False,
            "referral_eyes": [],
            "eyes": {
                "OD": {"status": "ok", "se_D": 0.25},
                "OS": {"status": "ok", "se_D": 0.00}
            }
        }
        created = store.create_session(session_data)
        self.assertEqual(created["id"], "test_s1")
        self.assertEqual(created["participant_code"], "EE-261019-999")
        self.assertFalse(created["referral"])
        
        fetched = store.get_session("test_s1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["site"], "Test Site")

    def test_update_and_delete_session(self):
        session_data = {
            "id": "test_s2",
            "participant_code": "EE-261019-888",
            "consent_age": True,
            "consent_signed": True,
            "status": "created"
        }
        store.create_session(session_data)
        updated = store.update_session("test_s2", status="complete", referral=True, referral_eyes=["OD"])
        self.assertTrue(updated["referral"])
        self.assertEqual(updated["status"], "complete")
        
        ok = store.delete_session("test_s2")
        self.assertTrue(ok)
        self.assertIsNone(store.get_session("test_s2"))

    def test_settings(self):
        store.set_setting("lang", "fil")
        self.assertEqual(store.get_setting("lang"), "fil")
        store.set_setting("lang", "en")
        self.assertEqual(store.get_setting("lang"), "en")

if __name__ == "__main__":
    unittest.main()
