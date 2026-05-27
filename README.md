# BreatheESG — Carbon Data Ingestion & Review Platform

A Django REST + React prototype for ingesting, normalizing, and reviewing emissions data from three enterprise source types: SAP fuel/procurement exports, utility portal CSVs, and corporate travel platform exports.

**Live demo:** `[your-render-url]`  
**Credentials:** `admin / admin123` (admin), `analyst / analyst123` (analyst)

---

## Architecture

```
breathe-esg/
├── backend/              # Django 4.2 + DRF
│   ├── emissions/        # Core models: Tenant, IngestionBatch, EmissionRecord, AuditLog
│   ├── ingestion/        # CSV parsers + upload API endpoint
│   └── breathe_esg/      # Settings, URLs, WSGI
├── frontend/             # React 18 + Recharts
├── sample_data/          # Realistic CSV files for all 3 sources
├── docs/
│   ├── MODEL.md          # Data model design and rationale (35% of grade)
│   ├── DECISIONS.md      # Every ambiguity resolved and why
│   ├── TRADEOFFS.md      # What was deliberately not built
│   └── SOURCES.md        # Source format research and findings
└── render.yaml           # Render deployment config
```

---

## Local Setup

### Backend
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed          # Creates admin/analyst users + demo data
python manage.py runserver
```
API runs at `http://localhost:8000/api/`

### Frontend
```bash
cd frontend
npm install
# Create .env.local:
echo "REACT_APP_API_URL=http://localhost:8000/api" > .env.local
npm start
```
UI runs at `http://localhost:3000`

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tenants/` | List tenants |
| GET | `/api/records/?tenant=&status=&scope=&source_type=` | List records with filters |
| GET | `/api/records/{id}/` | Record detail with audit log |
| GET | `/api/records/summary/?tenant=` | Dashboard summary stats |
| POST | `/api/records/{id}/approve/` | Approve a record |
| POST | `/api/records/{id}/flag/` | Flag a record as suspicious |
| POST | `/api/records/{id}/lock/` | Lock approved record for audit |
| POST | `/api/ingest/` | Upload CSV (multipart: file, source_type, tenant_id) |

---

## Sample Data Files

| File | Source | Notes |
|------|--------|-------|
| `sample_data/SAP_MB51_2024_Q1.csv` | SAP | Semicolon-delimited, German headers, mixed units, one suspicious row |
| `sample_data/GreenButton_2024_Q1.csv` | Utility | Green Button format, one estimated read (zero kWh, 38-day period) |
| `sample_data/Navan_Export_2024_Q1.csv` | Travel | Mix of flights (one missing distance), hotels, ground transport |

---

## Deployment on Render

1. Push to GitHub
2. Create new Render Blueprint from `render.yaml`
3. Render will provision: PostgreSQL (free tier) + Django web service + React static site
4. Backend `build.sh` runs migrations and seeds demo data automatically

Grant repo access to: `saurav@breatheesg.com`, `rahul@breatheesg.com`, `shivang@breatheesg.com`

---

## Key Design Decisions

See `docs/DECISIONS.md` for full rationale. Summary:
- **SAP**: Flat-file CSV (SE16 export) — not IDoc. Reason: sustainability leads don't have SAP Basis access.
- **Utility**: Green Button CSV — not PDF parsing. Reason: industry standard, available from all major utility portals.
- **Travel**: Navan CSV export — not API. Reason: API requires admin credentials and IT involvement; CSV is self-service.
- **Scope**: Set at parse time, not editable. Reason: GHG Protocol compliance.
- **Emission factors**: DEFRA 2023, stored per-record. Reason: factors change annually; records must remember which version was used.
