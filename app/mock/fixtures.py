MOCK_FIXTURES = {
    "refer": {
        "id": "s_mock_refer",
        "participant_code": "EE-261019-001",
        "created_at": "2026-10-19T09:41:00+08:00",
        "site": "RHU Sumilao",
        "consent_age": True,
        "consent_signed": True,
        "client_time": "2026-10-19T09:41:00+08:00",
        "status": "complete",
        "referral": True,
        "referral_eyes": ["OD", "OS"],
        "eyes": {
            "OD": {
                "status": "ok",
                "sphere_D": -1.50,
                "cylinder_D": -0.50,
                "se_D": -1.75,
                "label": "myopia_mild",
                "frames_used": 10,
                "frames_total": 118,
                "distance_cm": {"min": 12.1, "max": 13.4},
                "thumbnail_url": "/media/OD_sample.jpg",
                "ground_truth": None
            },
            "OS": {
                "status": "ok",
                "sphere_D": -1.25,
                "cylinder_D": -0.24,
                "se_D": -1.37,
                "label": "myopia_mild",
                "frames_used": 10,
                "frames_total": 120,
                "distance_cm": {"min": 11.8, "max": 13.0},
                "thumbnail_url": "/media/OS_sample.jpg",
                "ground_truth": None
            }
        }
    },
    "no_refer": {
        "id": "s_mock_norefer",
        "participant_code": "EE-261019-002",
        "created_at": "2026-10-19T10:15:00+08:00",
        "site": "RHU Sumilao",
        "consent_age": True,
        "consent_signed": True,
        "client_time": "2026-10-19T10:15:00+08:00",
        "status": "complete",
        "referral": False,
        "referral_eyes": [],
        "eyes": {
            "OD": {
                "status": "ok",
                "sphere_D": 0.25,
                "cylinder_D": -0.50,
                "se_D": 0.00,
                "label": "emmetropia",
                "frames_used": 10,
                "frames_total": 115,
                "distance_cm": {"min": 12.0, "max": 13.5},
                "thumbnail_url": "/media/OD_sample.jpg",
                "ground_truth": None
            },
            "OS": {
                "status": "ok",
                "sphere_D": 0.50,
                "cylinder_D": -0.50,
                "se_D": 0.25,
                "label": "emmetropia",
                "frames_used": 10,
                "frames_total": 112,
                "distance_cm": {"min": 12.3, "max": 13.1},
                "thumbnail_url": "/media/OS_sample.jpg",
                "ground_truth": None
            }
        }
    },
    "retake": {
        "id": "s_mock_retake",
        "participant_code": "EE-261019-003",
        "created_at": "2026-10-19T11:00:00+08:00",
        "site": "RHU Sumilao",
        "consent_age": True,
        "consent_signed": True,
        "client_time": "2026-10-19T11:00:00+08:00",
        "status": "retake_needed",
        "referral": None,
        "referral_eyes": [],
        "eyes": {
            "OD": {
                "status": "ok",
                "sphere_D": -0.75,
                "cylinder_D": -0.50,
                "se_D": -1.00,
                "label": "myopia_mild",
                "frames_used": 10,
                "frames_total": 110,
                "distance_cm": {"min": 12.2, "max": 13.0},
                "thumbnail_url": "/media/OD_sample.jpg",
                "ground_truth": None
            },
            "OS": {
                "status": "retake_needed",
                "frames_used": 6,
                "frames_total": 108,
                "error_reason": "Not enough clear frames (6/10 valid). Check for blinking or distance drift."
            }
        }
    }
}

def seed_fixtures_if_empty(store):
    sessions = store.list_sessions()
    if not sessions:
        for fixture in MOCK_FIXTURES.values():
            store.create_session(fixture)
