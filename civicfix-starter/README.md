# CivicFix — starter project

A small, beginner-friendly civic issue reporting prototype for a student innovation event. It uses HTML/CSS/JavaScript, Python Flask, and SQLite. AI image-and-text suggestions are optional and run server-side if a Gemini API key is configured. Without a key, the app uses transparent keyword rules and labels them as demo rules—not AI.

## 1. What works in this starter

- Submit an issue with category, description, location, severity, and optional photo.
- View reports and filter by status or search by text.
- See transparent rule-based priority scores (0–100).
- Find a likely duplicate when the same category and location are reported again; this increases the existing report's count.
- Toggle local demo authority mode to change issue status.
- View sample records by selecting “Load demo examples”. Sample reports are labelled.
- Ask for an issue category/severity suggestion. Configure Gemini to use image-aware AI; otherwise the fallback uses text keywords only.
- Status change events are saved to a history table.

## 2. Run locally (Windows)

Install Python 3.10 or newer. Open this folder in VS Code, then open Terminal → New Terminal and run:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

If PowerShell blocks activation, open Command Prompt and use:

```bat
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000` in your browser. The SQLite database is created automatically as `civicfix.db`.

## 3. Turn on actual AI image + text suggestions (optional)

1. Get an API key in Google's Gemini API developer console.
2. Copy `.env.example` to a file named `.env` in this folder.
3. Add your key to `.env`:

```env
GEMINI_API_KEY=put_your_key_here
GEMINI_MODEL=gemini-3.8-flash
```

4. Restart `python app.py`.

The browser never receives the key; calls happen from Flask. Keep `.env` private and never commit or share it. API/model availability and costs/limits depend on your provider account and current terms. The model only suggests a category/severity; the user should review it. An AI suggestion is not proof of an issue or an official emergency assessment.

## 4. Suggested team split (3 people)

- **Member 1 — Frontend:** form UX, responsive CSS, issue cards, search/filter, user testing, accessibility.
- **Member 2 — Backend/data:** Flask endpoints, database schema, validation, duplicate detection, status-history and deployment notes.
- **Member 3 — AI/demo/QA:** optional Gemini setup, prompt testing, rule fallback, test cases, demo script, slides and evidence screenshots.

Pair-review each other's work before merging. Use Git branches such as `frontend`, `backend`, and `ai-demo`.

## 5. Implementation roadmap

### Phase 1 — MVP (do not skip)
- Run locally on all team laptops.
- Create, read, update status for reports.
- Validate inputs and upload images safely.
- Add basic search, filters, and visible status.

### Phase 2 — Differentiators
- Add/verify AI-assisted category suggestion with both image and description.
- Improve duplicate detection by comparing nearby coordinates and visual similarity (rather than relying only on the exact location text).
- Add an audit trail and evidence after resolution.

### Phase 3 — Competition polish
- Add map pins (Leaflet/OpenStreetMap), a clear demo dataset, performance metrics, error states, phone-sized layout testing, and a 2–3 minute live demo.
- Compare actual duplicate-detection results on a small manually labelled test set. Report measured results; don't invent accuracy numbers.

## 6. Database schema

### `reports`

| Field | Meaning |
|---|---|
| `id` | Primary key / report ID |
| `title` | Short generated title |
| `category` | One of six permitted categories |
| `description` | Citizen-provided description |
| `location` | Landmark or location text |
| `severity` | Low, Medium, High (initially citizen assessed) |
| `priority_score` | Transparent rule-based score, 0–100 |
| `status` | Submitted, Verified, In Progress, Resolved |
| `image_filename` | Stored image filename, if provided |
| `report_count` | Number of similar submissions associated with this record |
| `is_demo` | Marks seeded sample data |
| `created_at`, `updated_at` | ISO timestamps |

### `status_history`

Stores `report_id`, `old_status`, `new_status`, a short note, and `changed_at` every time the issue status changes. This supports an audit timeline.

## 7. API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Health and AI mode |
| GET | `/api/reports` | List reports |
| POST | `/api/reports` | Submit report (multipart form) |
| POST | `/api/analyze` | Suggest category/severity from text + optional image |
| PATCH | `/api/reports/<id>/status` | Update status |
| GET | `/api/reports/<id>/history` | Retrieve status history |
| POST | `/api/demo-seed` | Add sample records |

## 8. Important limitations before any public deployment

This is a hackathon prototype, not a production government platform. The authority-mode update endpoint is intentionally unauthenticated for local demonstration; **do not expose it publicly**. Before deployment add proper staff authentication/authorization, rate limiting, CSRF protection where applicable, stronger image validation and scanning, privacy/retention policies, secure hosting, location privacy protections, and backups. Public user submissions should be reviewed before being treated as verified. Don't show personal addresses or private details on a public map.
