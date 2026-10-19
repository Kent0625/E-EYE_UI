import sqlite3
import json
import os
from datetime import datetime
from app.config import DATABASE_PATH

def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                participant_code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                site TEXT,
                consent_age INTEGER NOT NULL,
                consent_signed INTEGER NOT NULL,
                client_time TEXT,
                status TEXT NOT NULL,
                referral INTEGER,
                referral_eyes TEXT,
                eyes_data TEXT
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        conn.commit()

def create_session(session_dict):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sessions (
                id, participant_code, created_at, site,
                consent_age, consent_signed, client_time,
                status, referral, referral_eyes, eyes_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_dict["id"],
            session_dict["participant_code"],
            session_dict.get("created_at", datetime.now().isoformat()),
            session_dict.get("site", ""),
            1 if session_dict.get("consent_age") else 0,
            1 if session_dict.get("consent_signed") else 0,
            session_dict.get("client_time", ""),
            session_dict.get("status", "created"),
            1 if session_dict.get("referral") is True else (0 if session_dict.get("referral") is False else None),
            json.dumps(session_dict.get("referral_eyes", [])),
            json.dumps(session_dict.get("eyes", {}))
        ))
        conn.commit()
    return get_session(session_dict["id"])

def get_session(session_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return _row_to_session(row)

def update_session(session_id, **kwargs):
    updates = []
    values = []
    for k, v in kwargs.items():
        if k == "referral":
            updates.append("referral = ?")
            values.append(1 if v is True else (0 if v is False else None))
        elif k == "referral_eyes":
            updates.append("referral_eyes = ?")
            values.append(json.dumps(v))
        elif k == "eyes":
            updates.append("eyes_data = ?")
            values.append(json.dumps(v))
        elif k in ("status", "site", "client_time"):
            updates.append(f"{k} = ?")
            values.append(v)
    if not updates:
        return get_session(session_id)
    values.append(session_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?", tuple(values))
        conn.commit()
    return get_session(session_id)

def list_sessions(q="", filter_type="all"):
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM sessions WHERE 1=1"
        params = []
        if q:
            query += " AND participant_code LIKE ?"
            params.append(f"%{q}%")
        if filter_type == "referral":
            query += " AND referral = 1"
        elif filter_type == "no_referral":
            query += " AND referral = 0"
        query += " ORDER BY created_at DESC"
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        sessions = [_row_to_session(r) for r in rows]
        if filter_type in ("myopia", "hyperopia"):
            filtered = []
            for s in sessions:
                eyes = s.get("eyes", {})
                labels = [v.get("label", "") for v in eyes.values() if isinstance(v, dict)]
                if filter_type == "myopia" and any("myopia" in lbl for lbl in labels):
                    filtered.append(s)
                elif filter_type == "hyperopia" and any("hyperopia" in lbl for lbl in labels):
                    filtered.append(s)
            return filtered
        return sessions

def delete_session(session_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        return cursor.rowcount > 0

def delete_all_sessions():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions")
        conn.commit()
        return True

def get_setting(key, default=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default

def set_setting(key, value):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()

def _row_to_session(row):
    return {
        "id": row["id"],
        "participant_code": row["participant_code"],
        "created_at": row["created_at"],
        "site": row["site"],
        "consent_age": bool(row["consent_age"]),
        "consent_signed": bool(row["consent_signed"]),
        "client_time": row["client_time"],
        "status": row["status"],
        "referral": True if row["referral"] == 1 else (False if row["referral"] == 0 else None),
        "referral_eyes": json.loads(row["referral_eyes"] or "[]"),
        "eyes": json.loads(row["eyes_data"] or "{}")
    }
