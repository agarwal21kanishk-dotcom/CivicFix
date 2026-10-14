"""CivicFix: beginner-friendly Flask + SQLite prototype.

For local demonstration only. Add authentication and authorization before deployment.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = Path(os.getenv("CIVICFIX_DB", str(BASE_DIR / "civicfix.db")))

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB per request
app.config["JSON_SORT_KEYS"] = False

CATEGORIES = [
    "Pothole / Road Damage",
    "Garbage / Waste",
    "Water Leakage",
    "Streetlight / Electrical",
    "Drainage / Flooding",
    "Other",
]
SEVERITIES = {"Low", "Medium", "High"}
STATUSES = {"Submitted", "Verified", "In Progress", "Resolved"}
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MIME_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT NOT NULL,
            severity TEXT NOT NULL CHECK (severity IN ('Low', 'Medium', 'High')),
            priority_score INTEGER NOT NULL DEFAULT 50,
            status TEXT NOT NULL DEFAULT 'Submitted'
                CHECK (status IN ('Submitted', 'Verified', 'In Progress', 'Resolved')),
            image_filename TEXT,
            report_count INTEGER NOT NULL DEFAULT 1,
            is_demo INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);
        CREATE INDEX IF NOT EXISTS idx_reports_category_location ON reports(category, location);
        CREATE TABLE IF NOT EXISTS status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            old_status TEXT NOT NULL,
            new_status TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            changed_at TEXT NOT NULL,
            FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
        );
        """)


def normalize_location(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def priority_score(category: str, severity: str, description: str) -> int:
    """Transparent rule-based score; not a trained predictive model."""
    score = {"Low": 25, "Medium": 55, "High": 78}.get(severity, 45)
    if category in {"Drainage / Flooding", "Streetlight / Electrical", "Pothole / Road Damage"}:
        score += 8
    safety_words = ("accident", "injury", "danger", "blocked road", "school", "hospital", "flood")
    if any(word in description.lower() for word in safety_words):
        score += 8
    return min(score, 100)


def is_allowed_image(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_image(file_storage) -> str | None:
    if not file_storage or not file_storage.filename:
        return None
    if not is_allowed_image(file_storage.filename):
        raise ValueError("Upload an image in PNG, JPG, JPEG, or WEBP format.")
    extension = file_storage.filename.rsplit(".", 1)[1].lower()
    safe_original = secure_filename(file_storage.filename)
    if not safe_original:
        safe_original = f"image.{extension}"
    new_name = f"{uuid.uuid4().hex}.{extension}"
    file_storage.save(UPLOAD_DIR / new_name)
    return new_name


def rules_based_suggestion(description: str) -> dict[str, str]:
    """Fallback that works without an API key. It is explicitly not called AI."""
    text = description.lower()
    rules = [
        ("Pothole / Road Damage", ["pothole", "road", "crack", "crater", "asphalt"]),
        ("Garbage / Waste", ["garbage", "trash", "waste", "rubbish", "dump", "litter"]),
        ("Water Leakage", ["leak", "pipe", "water", "burst", "tap"]),
        ("Streetlight / Electrical", ["streetlight", "street light", "lamp", "light pole", "wire", "electric"]),
        ("Drainage / Flooding", ["drain", "sewer", "flood", "waterlogging", "blocked manhole"]),
    ]
    category = "Other"
    for candidate, keywords in rules:
        if any(word in text for word in keywords):
            category = candidate
            break
    high_words = ["accident", "injury", "danger", "flood", "exposed wire", "electric shock", "hospital", "school"]
    low_words = ["minor", "small amount", "slight"]
    severity = "High" if any(w in text for w in high_words) else ("Low" if any(w in text for w in low_words) else "Medium")
    return {
        "category": category,
        "severity": severity,
        "rationale": "Suggested from description keywords only. This is a demo rule, not an AI image analysis.",
    }


def gemini_suggestion(description: str, image_bytes: bytes | None, mime_type: str | None) -> dict[str, str] | None:
    """Optional real AI analysis using the Gemini REST API; requires GEMINI_API_KEY."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    parts: list[dict[str, Any]] = [{
        "text": (
            "You assist with preliminary civic issue triage. Analyse the description and, if provided, the image. "
            "Return JSON only with keys category, severity, rationale. category must be exactly one of: "
            + ", ".join(CATEGORIES)
            + ". severity must be Low, Medium, or High. Be cautious: do not claim that a location or image is verified; "
            "do not infer emergency facts unsupported by the input. rationale should be one short sentence.\nDescription: "
            + (description[:1200] or "No description provided.")
        )
    }]
    if image_bytes and mime_type:
        parts.append({"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode("ascii")}})

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    try:
        response = requests.post(
            url,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": parts}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
        category = result.get("category")
        severity = result.get("severity")
        if category not in CATEGORIES or severity not in SEVERITIES:
            return None
        return {
            "category": category,
            "severity": severity,
            "rationale": str(result.get("rationale", "AI-generated suggestion; check before submitting."))[:300],
        }
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError, json.JSONDecodeError):
        app.logger.exception("Gemini analysis failed; using demo rules instead")
        return None


def as_report(row: sqlite3.Row) -> dict[str, Any]:
    report = dict(row)
    report["image_url"] = f"/uploads/{report['image_filename']}" if report.get("image_filename") else None
    return report


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "ai_mode": "Gemini API" if os.getenv("GEMINI_API_KEY") else "Demo rules (no API key)"})


@app.get("/api/reports")
def list_reports():
    status = request.args.get("status")
    with get_connection() as conn:
        if status in STATUSES:
            rows = conn.execute("SELECT * FROM reports WHERE status = ? ORDER BY priority_score DESC, created_at DESC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM reports ORDER BY priority_score DESC, created_at DESC").fetchall()
    return jsonify([as_report(row) for row in rows])


@app.post("/api/analyze")
def analyze():
    description = request.form.get("description", "").strip()
    image = request.files.get("image")
    image_bytes = None
    mime_type = None
    if image and image.filename:
        if not is_allowed_image(image.filename):
            return jsonify({"error": "Upload PNG, JPG, JPEG, or WEBP only."}), 400
        image_bytes = image.read()
        ext = image.filename.rsplit(".", 1)[1].lower()
        mime_type = MIME_TYPES[ext]
    if not description and not image_bytes:
        return jsonify({"error": "Add a short description or image before asking for a suggestion."}), 400

    api_configured = bool(os.getenv("GEMINI_API_KEY", "").strip())
    suggestion = gemini_suggestion(description, image_bytes, mime_type)
    mode = "Gemini AI" if suggestion else ("Demo rules fallback (AI unavailable)" if api_configured else "Demo rules (no API key)")
    if suggestion is None:
        suggestion = rules_based_suggestion(description)
        if api_configured:
            suggestion["rationale"] += " The Gemini API could not be reached, so this fallback used text keywords only."
        else:
            suggestion["rationale"] += " Add GEMINI_API_KEY in .env to enable image-aware AI suggestions."
    return jsonify({**suggestion, "mode": mode})


@app.post("/api/reports")
def create_report():
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    location = request.form.get("location", "").strip()
    severity = request.form.get("severity", "Medium").strip()
    image = request.files.get("image")

    if category not in CATEGORIES:
        return jsonify({"error": "Choose a valid issue category."}), 400
    if not description or len(description) < 8:
        return jsonify({"error": "Please write a description of at least 8 characters."}), 400
    if not location or len(location) < 3:
        return jsonify({"error": "Please enter a useful location."}), 400
    if severity not in SEVERITIES:
        return jsonify({"error": "Choose Low, Medium, or High severity."}), 400

    try:
        image_filename = save_image(image)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    now = utc_now()
    title = f"{category} near {location[:70]}"
    score = priority_score(category, severity, description)
    normalized_location = normalize_location(location)
    try:
        with get_connection() as conn:
            existing = conn.execute(
                """SELECT * FROM reports
                   WHERE category = ? AND lower(trim(location)) = ? AND status != 'Resolved' AND is_demo = 0
                   ORDER BY created_at DESC LIMIT 1""",
                (category, normalized_location),
            ).fetchone()
            if existing:
                conn.execute("UPDATE reports SET report_count = report_count + 1, updated_at = ? WHERE id = ?", (now, existing["id"]))
                updated = conn.execute("SELECT * FROM reports WHERE id = ?", (existing["id"],)).fetchone()
                if image_filename:
                    try:
                        (UPLOAD_DIR / image_filename).unlink(missing_ok=True)
                    except OSError:
                        pass
                return jsonify({"duplicate": True, "message": "A similar unresolved report already exists at this location. Its report count has been increased.", "report": as_report(updated)}), 200

            cursor = conn.execute(
                """INSERT INTO reports
                   (title, category, description, location, severity, priority_score, status, image_filename, report_count, is_demo, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'Submitted', ?, 1, 0, ?, ?)""",
                (title, category, description, location, severity, score, image_filename, now, now),
            )
            report_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO status_history (report_id, old_status, new_status, note, changed_at) VALUES (?, ?, ?, ?, ?)",
                (report_id, "None", "Submitted", "Report created by citizen", now),
            )
            row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    except sqlite3.Error:
        app.logger.exception("Could not save report")
        if image_filename:
            (UPLOAD_DIR / image_filename).unlink(missing_ok=True)
        return jsonify({"error": "Could not save the report. Please try again."}), 500
    return jsonify({"duplicate": False, "message": "Report submitted.", "report": as_report(row)}), 201


@app.patch("/api/reports/<int:report_id>/status")
def update_status(report_id: int):
    """Local demo endpoint only: add authentication before any real deployment."""
    data = request.get_json(silent=True) or {}
    new_status = str(data.get("status", "")).strip()
    note = str(data.get("note", "")).strip()[:250]
    if new_status not in STATUSES:
        return jsonify({"error": "Choose a valid status."}), 400
    now = utc_now()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not row:
            return jsonify({"error": "Report not found."}), 404
        old_status = row["status"]
        conn.execute("UPDATE reports SET status = ?, updated_at = ? WHERE id = ?", (new_status, now, report_id))
        conn.execute(
            "INSERT INTO status_history (report_id, old_status, new_status, note, changed_at) VALUES (?, ?, ?, ?, ?)",
            (report_id, old_status, new_status, note or "Status updated in demo authority mode", now),
        )
        updated = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    return jsonify({"message": "Status updated.", "report": as_report(updated)})


@app.get("/api/reports/<int:report_id>/history")
def report_history(report_id: int):
    with get_connection() as conn:
        exists = conn.execute("SELECT id FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not exists:
            return jsonify({"error": "Report not found."}), 404
        rows = conn.execute("SELECT old_status, new_status, note, changed_at FROM status_history WHERE report_id = ? ORDER BY changed_at ASC", (report_id,)).fetchall()
    return jsonify([dict(row) for row in rows])


@app.post("/api/demo-seed")
def seed_demo():
    examples = [
        ("Pothole / Road Damage", "A deep pothole is creating a hazard for two-wheelers near the main crossing.", "Main crossing near Block A", "High"),
        ("Garbage / Waste", "Garbage has accumulated beside the public bin and needs collection.", "Community park entrance", "Medium"),
        ("Streetlight / Electrical", "The streetlight near the pedestrian path is not working after dark.", "Library pedestrian path", "Medium"),
    ]
    now = utc_now()
    with get_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) AS count FROM reports WHERE is_demo = 1").fetchone()["count"]
        if existing:
            return jsonify({"message": "Demo examples are already loaded."}), 200
        for category, description, location, severity in examples:
            score = priority_score(category, severity, description)
            cursor = conn.execute(
                """INSERT INTO reports (title, category, description, location, severity, priority_score, status, report_count, is_demo, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'Submitted', 2, 1, ?, ?)""",
                (f"{category} near {location}", category, description, location, severity, score, now, now),
            )
            conn.execute(
                "INSERT INTO status_history (report_id, old_status, new_status, note, changed_at) VALUES (?, ?, ?, ?, ?)",
                (cursor.lastrowid, "None", "Submitted", "Preloaded sample only — not a real public complaint", now),
            )
    return jsonify({"message": "Three sample reports added. They are clearly marked as demo data."}), 201


@app.get("/uploads/<path:filename>")
def uploaded_file(filename: str):
    return send_from_directory(UPLOAD_DIR, filename)


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "The image is too large. Maximum upload size is 5 MB."}), 413


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv("PORT", "5000")))
