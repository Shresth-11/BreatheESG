# TRADEOFFS — BreatheESG

Three things I deliberately did not build, and why.

---

## 1. Authentication and role-based access control

**What I didn't build:** Proper JWT authentication, per-tenant user management, analyst vs. approver vs. admin roles with separate permissions.

**What exists instead:** Django's session authentication with hardcoded admin/analyst demo users. The REST API accepts all requests without tenant-scoped auth.

**Why I skipped it:** Implementing auth correctly for a multi-tenant app requires:
- JWT with tenant claim embedded in token
- Per-tenant user–role mapping
- Middleware that reads tenant from JWT and scopes every query
- Token refresh, logout, password reset flows
- UI login/logout state management

This is 1–2 days of work that produces no signal about the actual problem: can we ingest heterogeneous carbon data and surface it meaningfully? Auth is a solved problem (dj-rest-auth + SimpleJWT). The data model and ingestion logic are the interesting parts.

**What this breaks in production:** Every tenant can see every other tenant's data. The upload endpoint accepts any tenant_id. This is obviously not acceptable in production and would be the first thing I'd build next.

---

## 2. Facility and material master data

**What I didn't build:** A Facility table (SAP plant code → address → country → grid emission factor), a Material master (SAP material number → activity type → correct unit), a User/Tenant membership table.

**What exists instead:** `facility_id` is stored as a raw varchar. Material classification is done by keyword matching on `material_description` (a heuristic). Country is manually set per-record.

**Why I skipped it:** In a real SAP deployment, the material master (`MARA`/`MARC` tables) contains the definitive mapping from material number to material group, which maps to emission category. SAP plant codes map to physical locations, which determine:
- Country (for grid emission factors)
- Ownership type (for Scope 1 vs. Scope 2 determination)
- Reporting entity for consolidated reporting

Building these lookup tables properly requires data from the client — you can't fabricate them. And the ingestion logic that uses them (lookup plant code → get country → get correct electricity grid factor) adds two or three database joins per row.

**What this breaks in production:** Electricity emission factors vary significantly by country grid (UK: 0.207 kg/kWh; India: 0.708 kg/kWh; France: 0.056 kg/kWh, heavily nuclear). Without facility-to-country mapping, all electricity defaults to UK DEFRA factors, which would significantly misstate emissions for a multi-country client.

---

## 3. Automated data pulls and scheduling

**What I didn't build:** Scheduled ingestion jobs (Celery + Redis), API connectors to Navan or utility APIs, SAP OData or RFC pull mechanisms, email/Slack notifications when new data is ingested or records need review.

**What exists instead:** Manual file upload via drag-and-drop UI. All ingestion is synchronous in the request-response cycle.

**Why I skipped it:** Automated pulls require:
- A task queue (Celery, Dramatiq, or similar)
- A scheduler (Celery Beat or cron)
- Per-integration credentials stored securely (not in the database as plaintext)
- Error handling for rate limits, downtime, partial pulls, and duplicate detection
- Infrastructure to run workers separately from the web process on Render

This is infrastructure work, not product work. The assignment asks us to "ingest data from three source types" — demonstrating that we understand what those source types look like and can parse them correctly is the signal. Whether the trigger is a human clicking "upload" or a cron job hitting an API is a deployment detail.

**What this breaks in production:** Manual upload is not viable for a real enterprise client whose utility sends a bill every month and whose SAP team exports weekly. Automation is the difference between a prototype and a product.
