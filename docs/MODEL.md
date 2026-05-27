# DATA MODEL — BreatheESG

## Overview

The schema is designed around three design goals:
1. **Multi-tenancy** — every row belongs to a `Tenant`; no cross-tenant data leakage is possible at the query level
2. **Full provenance** — every emission record knows where it came from, what the original value was, and what calculation produced the CO₂e figure
3. **Immutable audit trail** — once a record is locked, it cannot be changed; edits create new versions; all status transitions are logged

---

## Tables

### `Tenant`
One row per client company.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID (PK) | |
| name | varchar | "ACME Corporation" |
| slug | slug unique | "acme-corp" |
| created_at | timestamp | |

All other tables have a `tenant` FK. Queries always include `WHERE tenant_id = ?`. This is the simplest multi-tenancy model — shared schema, tenant-scoped data. It was chosen over schema-per-tenant because this is a prototype; schema-per-tenant adds deployment complexity (migrations must run per-tenant) that isn't warranted here. In production, row-level security in PostgreSQL would be the right upgrade path.

---

### `IngestionBatch`
One row per upload event. Groups all records that arrived together.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID (PK) | |
| tenant | FK → Tenant | |
| source_type | enum | `sap` / `utility` / `travel` |
| filename | varchar | Original filename |
| status | enum | `pending` / `processing` / `done` / `failed` |
| uploaded_by | FK → User | null if API pull |
| uploaded_at | timestamp | |
| row_count | int | Rows successfully parsed |
| error_count | int | Rows that failed |
| notes | text | Error message if failed |

The batch exists so analysts can see everything that came in together, understand parsing failures at a glance, and re-ingest if needed.

---

### `EmissionRecord`
The core table. One row = one activity event.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID (PK) | |
| tenant | FK → Tenant | |
| batch | FK → IngestionBatch | Which upload created this |
| source_type | enum | Denormalized from batch for query speed |
| source_row_id | varchar | Original row identifier from source (SAP doc number, meter ID, trip ID) |
| **scope** | int | 1 / 2 / 3 (GHG Protocol) |
| **activity_type** | enum | `fuel_diesel`, `electricity`, `travel_flight`, etc. |
| **raw_value** | decimal(20,6) | Exactly as parsed — never modified |
| **raw_unit** | varchar | Exactly as parsed — `L`, `kWh`, `M3`, `km`, `nights`, etc. |
| raw_data | JSON | Full original row as a dict — complete provenance |
| normalized_value_kwh | decimal(20,6) | For energy: value in kWh (null for travel) |
| **emission_factor** | decimal(20,8) | kg CO₂e per raw unit |
| emission_factor_source | varchar | "DEFRA 2023" — so factors can be updated and records recomputed |
| **co2e_kg** | decimal(20,6) | `raw_value × emission_factor` |
| activity_date | date | When the activity happened (not upload date) |
| period_start / period_end | date | For utility billing periods that don't align with calendar months |
| facility_id | varchar | SAP plant code, meter ID, or office — whatever the source provided |
| country | char(2) | ISO 3166-1 alpha-2 |
| **status** | enum | `pending` / `flagged` / `approved` / `locked` |
| flag_reason | text | Auto-generated or analyst-entered reason for flag |
| analyst_note | text | Free text from analyst during review |
| reviewed_by | FK → User | |
| reviewed_at | timestamp | |
| version | int | Starts at 1; increments on edit |
| superseded_by | FK → self | Points to the correction if this record was edited |

**Key design decisions:**

**Why `raw_value + raw_unit + raw_data` together?**
`raw_value` and `raw_unit` give us a machine-queryable original. `raw_data` is the full row dump for human auditors who want to see exactly what came in. If an auditor asks "what was the original SAP entry for this record?", `raw_data` answers that without having to go back to the source file.

**Why store `co2e_kg` instead of computing on read?**
Emission factors change (DEFRA publishes annually). Storing the computed value plus `emission_factor_source` means we know which version of the factors was used for each record. If we recompute on read, we'd silently change historical figures when factors are updated.

**Why `activity_date` separate from batch `uploaded_at`?**
A company might upload January data in March. Emissions are reported by activity period, not upload date.

**Why `period_start/period_end` for utility?**
Utility billing periods almost never align with calendar months. A billing period of Jan 3 → Feb 5 spans two months. Storing these separately lets us do correct period-based aggregation without assuming monthly alignment.

**Why `facility_id` as a varchar instead of a FK to a Facility table?**
SAP plant codes mean nothing without a lookup table; meter IDs are utility-specific. In a real deployment, a Facility master table would exist. For this prototype, we store the raw identifier and don't normalize it — this is noted in TRADEOFFS.md.

---

### `AuditLog`
Append-only log of every status change.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID (PK) | |
| record | FK → EmissionRecord | |
| action | enum | `created` / `flagged` / `approved` / `locked` / `edited` / `rejected` |
| performed_by | FK → User | null = system action |
| note | text | |
| snapshot | JSON | Full record state at time of action |
| timestamp | timestamp | |

`AuditLog` is append-only — no update or delete endpoints exist for it. The `snapshot` field captures the full record state so auditors can reconstruct exactly what was approved and when, even if the record is later edited.

---

## Scope Classification Logic

| Source | Activity | Scope | GHG Protocol Rationale |
|--------|----------|-------|------------------------|
| SAP | Fuel (diesel/petrol/gas/LPG) | **1** | Direct combustion in company-owned/controlled equipment |
| Utility | Purchased electricity | **2** | Indirect from energy production |
| Travel | Flights, hotels, ground transport | **3** | Indirect from employee activities not under company control |
| SAP | Procurement (non-fuel materials) | **3** | Upstream supply chain |

Scope is set at parse time based on `source_type + activity_type`. It is not editable by analysts — if the scope is wrong, the record should be rejected and re-ingested with the correct source type.

---

## Unit Normalization

All normalization is **one-way at ingest time**:

1. `raw_value` + `raw_unit` → preserved exactly
2. For energy: convert to kWh (stored in `normalized_value_kwh`)
3. `co2e_kg = raw_value_in_canonical_unit × emission_factor`

SAP unit codes mapped: `L/LTR/LT` → litres, `KL` → kilolitres (×1000), `GAL` → litres (×3.785), `M3/CF` → cubic metres. German unit codes (`KG`, `TO`) handled.

Emission factors are from **DEFRA 2023 UK Government GHG Conversion Factors** — the standard used by UK-based consultancies and acceptable for global reporting under GHG Protocol.

---

## Indexes

```
INDEX (tenant, status)    -- analyst review dashboard
INDEX (tenant, scope)     -- scope-based aggregation
INDEX (batch)             -- batch review page
INDEX (activity_date)     -- time-series queries
```
