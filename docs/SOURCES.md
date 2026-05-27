# SOURCES — BreatheESG

For each of the three data sources: what format I researched, what I learned, what my sample data looks like, and what would break in a real deployment.

---

## 1. SAP — Fuel & Procurement

### What format I researched
SAP has several data export mechanisms:
- **IDoc (Intermediate Document)**: SAP's native EDI format for system-to-system exchange. Control segment (EDI_DC40) + data segments. Used in WE02/WE19 transactions. Designed for automated inter-system pipelines.
- **OData**: SAP Gateway REST API, exposed via transaction SEGW. Used by SAP Fiori apps. Requires SAP Basis team setup.
- **Flat file / SE16 export**: Running a transaction (MB51 for material documents, ME2M for purchase orders), hitting "export to spreadsheet." Produces a tab-delimited or semicolon-delimited file directly from SAP ALV grid.

### What I learned
The flat-file export is the de facto format for sustainability reporting at mid-to-large enterprises. IT teams don't expose OData APIs to sustainability leads; they get read access to SE16 and export manually. Key pain points:
- **German headers**: European SAP configurations use German column names (`Buchungsdatum` = Posting Date, `Werk` = Plant, `Menge` = Quantity, `Mengeneinheit` = Unit, `Materialkurztext` = Material Description). A Swiss or German plant's export will have all-German headers.
- **SAP UOM codes**: Units are SAP-internal codes, not standard SI. `L` = litre, `KL` = kilolitre, `M3` = cubic metre, `CF` = cubic foot, `GAL` = US gallon, `KG` = kilogram, `TO` = metric tonne. The same liquid may be reported in `L` at one plant and `KL` at another.
- **Dates**: Always `YYYYMMDD` in flat files, never ISO 8601.
- **Material classification**: The material number alone doesn't tell you what it is — you need the material description or the material group from the material master (MARA table) to classify it as diesel, natural gas, etc.
- **Plant codes**: Arbitrary 4-character codes (e.g., `DE01`, `IN03`). Mean nothing without a lookup table that maps them to physical locations and countries.

### What my sample data looks like
`SAP_MB51_2024_Q1.csv` — semicolon-delimited, German headers, mix of `L`/`KL`/`M3`/`GAL` units, dates in `YYYYMMDD`, materials including `Diesel Kraftstoff`, `Erdgas`, `Benzin`, `LPG Flüssiggas`, one record with a suspiciously large quantity (98,000 L) to demonstrate auto-flagging.

### What would break in a real deployment
- **Material master dependency**: My keyword matching on `Materialkurztext` is a heuristic. A real deployment needs a mapping table from SAP material group to emission activity type, maintained alongside the client's SAP config.
- **Plant-to-country mapping**: Without this, we can't select the right grid factor for Scope 2, or determine whether a plant's fuel use is Scope 1 or Scope 3 (company-owned vs. contractor vehicle).
- **Volume**: An enterprise client might have 50,000+ SAP documents per quarter. Bulk insert (already implemented with `bulk_create`) handles this, but parsing needs to be async.
- **Character encoding**: SAP exports can be Windows-1252 or ISO-8859-1, not UTF-8, especially for German text. The parser handles BOM (`utf-8-sig`) and replaces unknown chars, but a malformed German Umlaut could corrupt material descriptions.

---

## 2. Utility / Electricity

### What format I researched
- **PDF bills**: Standard for most utilities. Every utility has a different layout. Brittle to parse. Not scalable.
- **Utility portal CSV**: Most major utilities (PG&E, National Grid, ComEd, AGL) offer a "Download My Data" or "Green Button" export. The US DOE Green Button standard (ESPI schema) defines a CSV format with columns: TYPE, START DATE, END DATE, USAGE, UNITS, COST.
- **Utility APIs**: Some utilities offer REST APIs (Arcadia, Bayou Energy aggregate these). Requires data access agreements and per-utility integration.

### What I learned
Green Button is the closest thing to a standard. Oracle's utility billing software (used by many US and UK utilities) exports this exact format. Key pain points:
- **Billing periods ≠ calendar months**: A billing period might be Jan 3 → Feb 5 (33 days) or Jan 1 → Apr 8 (98 days for an estimated read). You cannot assume monthly data and aggregate by month naively.
- **Estimated reads**: When a meter reader doesn't access the meter, the utility estimates usage. These show up as zero or as an anomalously long billing period. Green Button sometimes marks these with an asterisk in the NOTES column.
- **Units vary**: kWh is most common, but some industrial meters report MWh. Gas meters report in therms or CCF. The UNITS column is the source of truth.
- **Multi-site accounts**: A facilities team might have 20 meters across a building. Each meter is a separate row or a separate file download. Meter IDs are utility-specific strings.
- **Tariff information**: Green Button doesn't include tariff structure (time-of-use rates, demand charges). If you need to verify the bill, you need the tariff separately.

### What my sample data looks like
`GreenButton_2024_Q1.csv` — standard Green Button columns, two meters, one record with zero usage and a 38-day billing period (auto-flagged as likely estimated read), units all kWh.

### What would break in a real deployment
- **Non-electricity sources**: Green Button also covers gas and water. The parser currently skips non-electric rows. A client with gas boilers would need gas handling (therms → kg CO₂e via natural gas emission factor).
- **Country-specific grid factors**: UK electricity is 0.207 kg CO₂e/kWh (DEFRA 2023). India is 0.708. France is 0.056. The parser uses UK factors universally. A multi-country client would overstate or understate massively.
- **Market-based vs. location-based accounting**: GHG Protocol Scope 2 guidance requires both location-based (grid average) and market-based (renewable energy contracts) reporting. The current model only supports location-based.
- **Missing meter-to-facility mapping**: The parser stores the row number as the source_row_id since Green Button doesn't include meter IDs in the standard columns. A real deployment needs a meter→facility→tenant mapping table.

---

## 3. Corporate Travel

### What format I researched
- **Concur API**: SAP Concur has a REST API (v3.0). Requires OAuth2 per-tenant, IT involvement, and enterprise plan access. Well-documented but not self-service.
- **Navan API**: Navan (formerly TripActions) offers API credentials (Client ID + Client Secret) created by admins. The Airbyte connector confirms it supports hotels and flights. However, documentation is behind a login wall and API access is plan-gated.
- **CSV exports**: Both platforms offer report-based CSV exports from their web UI. Navan's "Expense Report" export includes trip segments by category. Concur's "Travel Itinerary" export has similar structure.

### What I learned
Sustainability teams almost always use CSV exports rather than APIs — API access requires IT involvement and legal data-sharing agreements. The self-service path is: run a date-range report in Navan/Concur → export CSV → upload to BreatheESG.

Key pain points:
- **Distances often not provided**: Flight records frequently include only origin/destination airport codes (IATA). Distances are not always in the export. You have to compute them from IATA lat/lon coordinates via haversine — and flag these records as estimated.
- **Category inconsistency**: A "ground transport" row might be a taxi, a train, a rental car, or a bus. Emission factors differ by mode. The `transport_mode` field exists in some exports but not all.
- **Currency**: Costs are in whatever currency the booking was made in. Not relevant for emission calculation but complicates spend reporting.
- **Connecting flights**: A LHR→FRA→JFK trip might appear as two rows (LHR→FRA, FRA→JFK) or one row (LHR→JFK). Two rows is more accurate; one row assumes a direct flight that doesn't exist.
- **Radiative forcing**: The IPCC recommends applying a multiplier (typically ×1.9–3.0) to flight emissions to account for high-altitude radiative forcing effects (contrails, NOx). DEFRA 2023 does not include this multiplier by default. I did not include it — this should be a configuration option noted in DECISIONS.md.

### What my sample data looks like
`Navan_Export_2024_Q1.csv` — flights with and without distances (one computed via IATA haversine, flagged), hotel nights, ground transport with transport_mode, realistic traveler names, realistic costs.

### What would break in a real deployment
- **IATA code coverage**: My haversine lookup table covers 15 airports. A real deployment would need all ~10,000 IATA codes and their coordinates (available from OpenFlights.org dataset).
- **Radiative forcing**: Not included. Would need to be a tenant-level configuration (some reporting frameworks require it, others don't).
- **Hotel emission factors by country**: Hotel emission factors vary by country's grid mix. The current factor (0.067 kg/night) is a global average. UK hotels should use UK grid factor × kWh/night.
- **Rental cars**: Not handled. Would need vehicle type (electric vs. ICE) and fuel type to apply correct factor.
