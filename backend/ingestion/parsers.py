"""
Ingestion parsers for each of the three data sources.

Each parser:
  1. Accepts a file-like object
  2. Returns a list of dicts with normalized fields
  3. Raises ParseError with row info on bad data (continues on non-fatal errors)
  4. Preserves the original row in raw_data for full auditability

EMISSION FACTORS (DEFRA 2023, UK Government GHG Conversion Factors):
  Diesel:        2.68676 kg CO2e/L
  Petrol:        2.31480 kg CO2e/L
  Natural Gas:   2.02258 kg CO2e/m³
  LPG:           1.55540 kg CO2e/L
  Electricity UK: 0.20707 kg CO2e/kWh (2023 grid average)
  Flight short:  0.25500 kg CO2e/km/passenger (economy, <3700km)
  Flight long:   0.19500 kg CO2e/km/passenger (economy, >3700km)
  Hotel:         0.06700 kg CO2e/night (average)
  Ground taxi:   0.14900 kg CO2e/km

Airport distance pairs are computed via haversine when only IATA codes given.
"""

import csv
import io
import re
from decimal import Decimal
from datetime import datetime, date
from math import radians, sin, cos, sqrt, atan2

# ── Emission factors (kg CO2e per raw unit) ──────────────────────────────────
EMISSION_FACTORS = {
    'diesel_L':       Decimal('2.68676'),
    'petrol_L':       Decimal('2.31480'),
    'natural_gas_m3': Decimal('2.02258'),
    'lpg_L':          Decimal('1.55540'),
    'electricity_kWh': Decimal('0.20707'),
    'flight_short_km': Decimal('0.25500'),
    'flight_long_km':  Decimal('0.19500'),
    'hotel_night':     Decimal('0.06700'),
    'taxi_km':         Decimal('0.14900'),
    'bus_km':          Decimal('0.08900'),
}

# IATA airport coords (lat, lon) — subset for realistic sample data
AIRPORT_COORDS = {
    'LHR': (51.477500, -0.461389),
    'JFK': (40.639722, -73.778889),
    'BOM': (19.088700, 72.868100),
    'DEL': (28.556500, 77.100900),
    'SIN': (1.359167, 103.989444),
    'DXB': (25.252778, 55.364444),
    'CDG': (49.012779, 2.550000),
    'FRA': (50.033333, 8.570556),
    'ORD': (41.978611, -87.904722),
    'SFO': (37.618889, -122.375),
    'BLR': (13.198889, 77.705556),
    'HYD': (17.240000, 78.429722),
    'BBI': (20.244400, 85.817800),
    'CCU': (22.654722, 88.446667),
    'MAA': (12.990005, 80.169296),
}


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))


def airport_distance_km(orig, dest):
    orig = orig.strip().upper()
    dest = dest.strip().upper()
    if orig in AIRPORT_COORDS and dest in AIRPORT_COORDS:
        lat1, lon1 = AIRPORT_COORDS[orig]
        lat2, lon2 = AIRPORT_COORDS[dest]
        return haversine_km(lat1, lon1, lat2, lon2)
    return None


# ── SAP unit normalization ────────────────────────────────────────────────────
SAP_UNIT_MAP = {
    # SAP UOM code → (canonical_unit, conversion_factor_to_L_or_m3)
    'L':   ('L', 1.0), 'LTR': ('L', 1.0), 'LT': ('L', 1.0),
    'KL':  ('L', 1000.0), 'ML': ('L', 0.001),
    'GAL': ('L', 3.78541), 'GL': ('L', 3.78541),
    'KG':  ('kg', 1.0), 'G': ('kg', 0.001), 'TO': ('kg', 1000.0),
    'M3':  ('m3', 1.0), 'CF': ('m3', 0.0283168),
}

# SAP German → English header mapping (common in EU deployments)
SAP_HEADER_MAP = {
    'Buchungsdatum': 'posting_date',
    'Menge': 'quantity',
    'Mengeneinheit': 'unit',
    'Werk': 'plant',
    'Material': 'material',
    'Lieferant': 'vendor',
    'Belegnummer': 'document_number',
    'Kostenstelle': 'cost_center',
    'Materialkurztext': 'material_description',
    # English variants
    'Posting Date': 'posting_date',
    'Quantity': 'quantity',
    'Unit': 'unit',
    'Plant': 'plant',
    'Material': 'material',
    'Vendor': 'vendor',
    'Document Number': 'document_number',
    'Cost Center': 'cost_center',
    'Material Description': 'material_description',
}

# Material → activity type mapping (simplified; real would use material master)
MATERIAL_ACTIVITY_MAP = {
    'diesel': ('fuel_diesel', 'L'),
    'petrol': ('fuel_petrol', 'L'),
    'benzin': ('fuel_petrol', 'L'),  # German
    'kraftstoff': ('fuel_diesel', 'L'),  # German for fuel
    'natural gas': ('fuel_natural_gas', 'm3'),
    'erdgas': ('fuel_natural_gas', 'm3'),
    'lpg': ('fuel_lpg', 'L'),
    'flüssiggas': ('fuel_lpg', 'L'),
}


class ParseError(Exception):
    def __init__(self, message, row=None):
        super().__init__(message)
        self.row = row


def _parse_sap_date(s):
    """SAP dates come as YYYYMMDD or DD.MM.YYYY or MM/DD/YYYY"""
    s = str(s).strip()
    for fmt in ('%Y%m%d', '%d.%m.%Y', '%m/%d/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ParseError(f"Cannot parse SAP date: {s!r}")


def parse_sap_csv(file_obj):
    """
    Parses a SAP flat-file export (semicolon or tab-delimited CSV).
    Handles German headers, inconsistent units, and plant codes.

    Expected columns (after header normalization):
      document_number, posting_date, plant, material, material_description,
      quantity, unit, vendor, cost_center
    """
    content = file_obj.read()
    if isinstance(content, bytes):
        content = content.decode('utf-8-sig', errors='replace')  # handle BOM

    # Detect delimiter
    first_line = content.split('\n')[0]
    delimiter = ';' if first_line.count(';') > first_line.count('\t') else '\t'

    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    raw_headers = reader.fieldnames or []

    # Normalize headers (German → English)
    header_map = {}
    for h in raw_headers:
        normalized = SAP_HEADER_MAP.get(h.strip(), h.strip().lower().replace(' ', '_'))
        header_map[h] = normalized

    records = []
    errors = []
    for i, row in enumerate(reader, start=2):
        row = {header_map.get(k, k): v for k, v in row.items()}
        try:
            mat_desc = (row.get('material_description') or row.get('material') or '').lower()
            activity_type = 'fuel_diesel'
            expected_unit = 'L'
            for keyword, (atype, eunit) in MATERIAL_ACTIVITY_MAP.items():
                if keyword in mat_desc:
                    activity_type = atype
                    expected_unit = eunit
                    break

            raw_qty = float(str(row.get('quantity', '0')).replace(',', '.').strip())
            raw_unit_code = str(row.get('unit', 'L')).strip().upper()
            unit_info = SAP_UNIT_MAP.get(raw_unit_code, ('L', 1.0))
            canonical_unit, factor = unit_info
            qty_normalized = raw_qty * factor

            # Map to emission factor
            ef_key = f"{activity_type.replace('fuel_', '')}_{canonical_unit}"
            ef = EMISSION_FACTORS.get(ef_key) or EMISSION_FACTORS.get('diesel_L')
            co2e = Decimal(str(qty_normalized)) * ef

            activity_date = _parse_sap_date(row.get('posting_date', ''))
            plant = str(row.get('plant', '')).strip()

            flags = []
            if raw_qty <= 0:
                flags.append('zero or negative quantity')
            if co2e > Decimal('50000'):
                flags.append('unusually high CO2e (>50t)')

            records.append({
                'source_type': 'sap',
                'source_row_id': str(row.get('document_number', f'row_{i}')),
                'scope': 1,
                'activity_type': activity_type,
                'raw_value': Decimal(str(raw_qty)),
                'raw_unit': raw_unit_code,
                'raw_data': dict(row),
                'emission_factor': ef,
                'emission_factor_source': 'DEFRA 2023',
                'co2e_kg': co2e,
                'activity_date': activity_date,
                'facility_id': plant,
                'flag_reason': '; '.join(flags) if flags else '',
                'auto_flag': bool(flags),
            })
        except Exception as e:
            errors.append({'row': i, 'error': str(e), 'data': dict(row)})

    return records, errors


def parse_utility_csv(file_obj):
    """
    Parses Green Button Download My Data CSV format (Oracle/PG&E/National Grid).

    Expected columns: TYPE, START DATE, END DATE, USAGE, UNITS, COST
    UNITS is typically 'kWh' but may be 'MWh', 'Wh', 'therms'.
    Billing periods don't align with calendar months — we store period_start/end.
    """
    content = file_obj.read()
    if isinstance(content, bytes):
        content = content.decode('utf-8-sig', errors='replace')

    reader = csv.DictReader(io.StringIO(content))
    records = []
    errors = []

    # Unit → kWh conversion
    unit_to_kwh = {
        'kwh': Decimal('1'), 'kWh': Decimal('1'),
        'mwh': Decimal('1000'), 'MWh': Decimal('1000'),
        'wh': Decimal('0.001'), 'Wh': Decimal('0.001'),
        'therms': Decimal('29.3001'),  # 1 therm = 29.3 kWh
    }

    for i, row in enumerate(reader, start=2):
        try:
            # Skip non-electricity rows (gas, water)
            row_type = str(row.get('TYPE', 'Electric')).strip().lower()
            if 'gas' in row_type or 'water' in row_type:
                continue

            usage_str = str(row.get('USAGE', '0')).strip()
            if not usage_str or usage_str == '':
                continue
            usage = Decimal(usage_str.replace(',', ''))
            unit = str(row.get('UNITS', 'kWh')).strip()
            kwh_factor = unit_to_kwh.get(unit, Decimal('1'))
            kwh = usage * kwh_factor

            ef = EMISSION_FACTORS['electricity_kWh']
            co2e = kwh * ef

            def parse_date(s):
                s = str(s).strip()
                for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y'):
                    try:
                        return datetime.strptime(s, fmt).date()
                    except ValueError:
                        continue
                raise ParseError(f"Cannot parse date: {s!r}")

            period_start = parse_date(row.get('START DATE', ''))
            period_end = parse_date(row.get('END DATE', ''))

            # Suspicious: zero usage, or period > 35 days (estimated reads)
            flags = []
            if kwh == 0:
                flags.append('zero usage — possible estimated read')
            if (period_end - period_start).days > 35:
                flags.append('billing period > 35 days — likely estimated')
            if co2e > Decimal('100000'):
                flags.append('unusually high electricity (>100 MWh)')

            records.append({
                'source_type': 'utility',
                'source_row_id': f"utility_row_{i}",
                'scope': 2,
                'activity_type': 'electricity',
                'raw_value': usage,
                'raw_unit': unit,
                'raw_data': dict(row),
                'normalized_value_kwh': kwh,
                'emission_factor': ef,
                'emission_factor_source': 'DEFRA 2023',
                'co2e_kg': co2e,
                'activity_date': period_start,
                'period_start': period_start,
                'period_end': period_end,
                'flag_reason': '; '.join(flags) if flags else '',
                'auto_flag': bool(flags),
            })
        except Exception as e:
            errors.append({'row': i, 'error': str(e), 'data': dict(row)})

    return records, errors


def parse_travel_csv(file_obj):
    """
    Parses Navan/Concur CSV export format.

    Expected columns:
      trip_id, traveler_name, trip_type (flight/hotel/ground),
      origin, destination, departure_date, return_date,
      distance_km (optional), nights (for hotel),
      transport_mode (for ground: taxi/bus/train), cost_usd

    Distances computed from IATA codes via haversine when not provided.
    Scope 3 for all travel.
    """
    content = file_obj.read()
    if isinstance(content, bytes):
        content = content.decode('utf-8-sig', errors='replace')

    reader = csv.DictReader(io.StringIO(content))
    records = []
    errors = []

    for i, row in enumerate(reader, start=2):
        try:
            trip_type = str(row.get('trip_type', '')).strip().lower()
            departure_date_str = str(row.get('departure_date', '')).strip()
            try:
                activity_date = datetime.strptime(departure_date_str, '%Y-%m-%d').date()
            except ValueError:
                activity_date = datetime.strptime(departure_date_str, '%m/%d/%Y').date()

            flags = []

            if trip_type == 'flight':
                origin = str(row.get('origin', '')).strip().upper()
                dest = str(row.get('destination', '')).strip().upper()
                dist_raw = row.get('distance_km', '').strip()

                if dist_raw:
                    dist_km = Decimal(dist_raw)
                else:
                    computed = airport_distance_km(origin, dest)
                    if computed:
                        dist_km = Decimal(str(computed))
                        flags.append(f'distance estimated from IATA codes ({origin}→{dest})')
                    else:
                        flags.append(f'unknown IATA pair {origin}→{dest}, distance set to 0')
                        dist_km = Decimal('0')

                # Short-haul <3700km, long-haul >=3700km (DEFRA threshold)
                ef_key = 'flight_long_km' if dist_km >= 3700 else 'flight_short_km'
                ef = EMISSION_FACTORS[ef_key]
                co2e = dist_km * ef

                records.append({
                    'source_type': 'travel',
                    'source_row_id': str(row.get('trip_id', f'row_{i}')),
                    'scope': 3,
                    'activity_type': 'travel_flight',
                    'raw_value': dist_km,
                    'raw_unit': 'km',
                    'raw_data': dict(row),
                    'emission_factor': ef,
                    'emission_factor_source': 'DEFRA 2023',
                    'co2e_kg': co2e,
                    'activity_date': activity_date,
                    'flag_reason': '; '.join(flags) if flags else '',
                    'auto_flag': bool(flags),
                })

            elif trip_type == 'hotel':
                nights = Decimal(str(row.get('nights', '1')).strip() or '1')
                ef = EMISSION_FACTORS['hotel_night']
                co2e = nights * ef
                records.append({
                    'source_type': 'travel',
                    'source_row_id': str(row.get('trip_id', f'row_{i}')),
                    'scope': 3,
                    'activity_type': 'travel_hotel',
                    'raw_value': nights,
                    'raw_unit': 'nights',
                    'raw_data': dict(row),
                    'emission_factor': ef,
                    'emission_factor_source': 'DEFRA 2023',
                    'co2e_kg': co2e,
                    'activity_date': activity_date,
                    'flag_reason': '',
                    'auto_flag': False,
                })

            elif trip_type in ('ground', 'taxi', 'bus', 'train'):
                mode = str(row.get('transport_mode', 'taxi')).strip().lower()
                dist_km = Decimal(str(row.get('distance_km', '10') or '10'))
                ef_key = 'bus_km' if mode == 'bus' else 'taxi_km'
                ef = EMISSION_FACTORS[ef_key]
                co2e = dist_km * ef
                records.append({
                    'source_type': 'travel',
                    'source_row_id': str(row.get('trip_id', f'row_{i}')),
                    'scope': 3,
                    'activity_type': 'travel_ground',
                    'raw_value': dist_km,
                    'raw_unit': 'km',
                    'raw_data': dict(row),
                    'emission_factor': ef,
                    'emission_factor_source': 'DEFRA 2023',
                    'co2e_kg': co2e,
                    'activity_date': activity_date,
                    'flag_reason': '',
                    'auto_flag': False,
                })

        except Exception as e:
            errors.append({'row': i, 'error': str(e), 'data': dict(row)})

    return records, errors
