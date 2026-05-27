# DECISIONS — BreatheESG

Every ambiguity I resolved, what I chose, why, and what I'd ask the PM.

---

## SAP: Format Choice — Flat File CSV, not IDoc or OData

**What I considered:**
- **IDoc**: SAP's native EDI format. Used for system-to-system data exchange (WE02/WE19 transaction). Structured with EDI_DC40 control record and data segments. Realistic for automated pipelines between SAP and external systems.
- **OData**: SAP Gateway API, modern, RESTful, used in SAP Fiori apps. Requires middleware setup (transaction SEGW) and is rarely available to sustainability teams without IT involvement.
- **Flat file / CSV**: MB51 (material documents) or ME2M (purchase orders) transaction exports via SE16. The actual way sustainability analysts pull data — they run a transaction, click "Export to spreadsheet", get a tab or semicolon-delimited file.

**What I chose:** Flat file CSV via SE16/MB51 export.

**Why:** Real sustainability teams don't have SAP developer access. The person asking for carbon data is the sustainability lead, not the SAP Basis team. The flat-file export is the format that actually lands in their inbox. IDoc is correct for automated pipelines between SAP systems but wrong for the "facilities team pulls data" scenario the PM described.

**What the file looks like:** Semicolon-delimited, sometimes tab-delimited depending on locale. German headers in EU deployments (`Buchungsdatum` = Posting Date, `Werk` = Plant, `Menge` = Quantity, `Mengeneinheit` = Unit of Measure). Dates in `YYYYMMDD` format. Units in SAP UOM codes (`L`, `KL`, `M3`, `KG`, `GAL`, `CF`).

**What I'd ask the PM:** "Does the client have an SAP Basis team who can set up an automated extract, or will the sustainability lead be manually exporting? That changes whether we should plan for IDoc or flat file long-term."

---

## Utility: Format Choice — Green Button CSV, not PDF parsing

**What I considered:**
- **PDF bill parsing**: Most utilities send PDF bills. Parsing is brittle — every utility has a different layout, table structures vary, text extraction from PDFs is error-prone. Not scalable.
- **Utility API**: Some large utilities (PG&E, National Grid) offer REST APIs. Requires per-utility integration, OAuth setup, and data access agreements. Not realistic for a prototype covering a generic "facilities team".
- **Green Button CSV**: The US DOE standard for utility data export. Supported by PG&E, National Grid, ComEd, and many others. Available via "Download My Data" on utility portals. Columns: TYPE, START DATE, END DATE, USAGE, UNITS, COST.

**What I chose:** Green Button CSV format.

**Why:** It's the only standardized format available across utilities without API agreements. Sustainability teams can download it from their utility's customer portal in under a minute. The format is well-documented (Green Button Alliance spec). It also honestly represents what billing periods look like — they don't align to calendar months, readings can be estimated (shown as zero or flagged), and units vary (kWh, MWh, therms).

**What I'd ask the PM:** "Which country is the client in? US utilities mostly support Green Button; UK utilities use a different export format (some via smart meter APIs). If they're in the EU, we may need PDF parsing after all."

---

## Travel: Format Choice — CSV export, not API integration

**What I considered:**
- **Navan API**: Navan (formerly TripActions) does have an API. However, API access requires admin-level credential creation, is poorly documented publicly, and requires a direct partnership or enterprise plan. The Airbyte connector for Navan only supports hotels and flights (not all travel types).
- **Concur API**: SAP Concur has a REST API. Requires OAuth2 setup per-tenant and IT involvement from the client. Not something a sustainability lead can self-serve.
- **CSV export**: Both Navan and Concur offer "Export to CSV" from their reports section. This is what sustainability teams actually use — they run a date-range report and download it.

**What I chose:** CSV export format based on Navan's report columns.

**Why:** Same reasoning as SAP — the PM said "business travel data from a corporate travel platform." They didn't say "build an API integration." The CSV export is the self-serve path. API integration is a later phase once the data model is validated.

**Ambiguity I resolved: distances.** Flight data often only includes origin/destination airport codes (IATA), not distances. I implemented a haversine calculation over a lookup table of ~15 IATA airport coordinates. Records where distance was computed (rather than provided) are auto-flagged so the analyst knows the emission figure is estimated. I use DEFRA's short/long-haul boundary (3,700km) to pick the right emission factor.

**What I'd ask the PM:** "Does the client actually use Navan or Concur? The column names in my CSV format assume Navan's export. Concur has different column names. And do they capture hotel nights in the same system, or is that tracked separately?"

---

## Scope assignment: at parse time, not at review time

Scope (1/2/3) is assigned by the parser based on `source_type + activity_type`. Analysts cannot change the scope — they can only approve, flag, or lock records.

**Why:** If scope assignment is user-editable, you lose the ability to guarantee GHG Protocol compliance. An analyst shouldn't be reclassifying diesel fuel as Scope 2 because they made an error. If the scope is wrong, the record should be re-ingested with the correct source type. This is enforced at the data layer, not just the UI.

---

## Emission factors: DEFRA 2023, stored per-record

I chose DEFRA (UK Government GHG Conversion Factors, 2023) rather than EPA (US) or IPCC.

**Why:** DEFRA is the most commonly used factor set for international corporate carbon reporting. The PM didn't specify the client's location; DEFRA is a safe default for a UK-based consultancy. The `emission_factor_source` field on every record means we can filter by factor set and recompute if the client uses EPA or IEA factors instead.

---

## Auto-flagging rules

Records are auto-flagged (not rejected) when:
- SAP: quantity ≤ 0, or CO₂e > 50 tonnes (likely a data entry error or KL/L confusion)
- Utility: zero kWh usage (possible estimated read), billing period > 35 days (estimated meter read)
- Travel: distance computed from IATA codes rather than provided, unknown IATA pair

**Why auto-flag rather than reject?** An estimated read or a very large diesel purchase might be legitimate. The analyst should make the call, not the system. Auto-rejecting data would silently drop real emissions from the audit.

---

## Multi-tenancy: shared schema, tenant-scoped rows

All data lives in one PostgreSQL database with a `tenant_id` column on every table. All queries filter by `tenant_id`.

**Why not schema-per-tenant?** Schema-per-tenant isolates data at the database level, which is stronger. But it means running migrations across N schemas every deployment, and managing N database connections. For a 4-day prototype with one demo tenant, shared schema is correct. In production, PostgreSQL row-level security policies would be the right upgrade.
