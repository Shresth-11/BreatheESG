"""
Seed command: creates a demo tenant, admin user, and sample data for all 3 sources.
Run: python manage.py seed
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from emissions.models import Tenant, IngestionBatch, EmissionRecord, AuditLog
from decimal import Decimal
from datetime import date


class Command(BaseCommand):
    help = 'Seed demo data for BreatheESG'

    def handle(self, *args, **kwargs):
        # Create admin user
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@breatheesg.com', 'admin123')
            self.stdout.write('Created admin user (admin/admin123)')

        # Create analyst user
        if not User.objects.filter(username='analyst').exists():
            User.objects.create_user('analyst', 'analyst@breatheesg.com', 'analyst123')
            self.stdout.write('Created analyst user (analyst/analyst123)')

        user = User.objects.get(username='admin')

        # Create demo tenant
        tenant, _ = Tenant.objects.get_or_create(
            slug='acme-corp',
            defaults={'name': 'ACME Corporation'}
        )
        self.stdout.write(f'Tenant: {tenant.name}')

        # SAP batch
        sap_batch = IngestionBatch.objects.create(
            tenant=tenant, source_type='sap',
            filename='SAP_MB51_2024_Q1.csv',
            status='done', uploaded_by=user,
            row_count=6, error_count=0,
        )
        sap_records = [
            dict(scope=1, activity_type='fuel_diesel', raw_value=Decimal('1500'),
                 raw_unit='L', emission_factor=Decimal('2.68676'),
                 emission_factor_source='DEFRA 2023',
                 co2e_kg=Decimal('4030.14'), activity_date=date(2024,1,15),
                 facility_id='PLANT_DE01', country='DE',
                 source_row_id='5000012345',
                 raw_data={'document_number':'5000012345','plant':'PLANT_DE01',
                           'material_description':'Diesel','quantity':'1500','unit':'L',
                           'posting_date':'20240115','vendor':'Aral GmbH'}),
            dict(scope=1, activity_type='fuel_petrol', raw_value=Decimal('800'),
                 raw_unit='L', emission_factor=Decimal('2.31480'),
                 emission_factor_source='DEFRA 2023',
                 co2e_kg=Decimal('1851.84'), activity_date=date(2024,2,3),
                 facility_id='PLANT_UK01', country='GB',
                 source_row_id='5000012398',
                 raw_data={'document_number':'5000012398','plant':'PLANT_UK01',
                           'material_description':'Petrol','quantity':'800','unit':'L',
                           'posting_date':'20240203','vendor':'BP UK Ltd'}),
            dict(scope=1, activity_type='fuel_natural_gas', raw_value=Decimal('2200'),
                 raw_unit='M3', emission_factor=Decimal('2.02258'),
                 emission_factor_source='DEFRA 2023',
                 co2e_kg=Decimal('4449.68'), activity_date=date(2024,3,22),
                 facility_id='PLANT_DE01', country='DE',
                 source_row_id='5000012501',
                 raw_data={'document_number':'5000012501','plant':'PLANT_DE01',
                           'material_description':'Erdgas','quantity':'2200','unit':'M3',
                           'posting_date':'20240322','vendor':'E.ON Energie'}),
            dict(scope=1, activity_type='fuel_diesel',
                 raw_value=Decimal('98000'),  # intentionally suspicious
                 raw_unit='L', emission_factor=Decimal('2.68676'),
                 emission_factor_source='DEFRA 2023',
                 co2e_kg=Decimal('263102.48'), activity_date=date(2024,3,31),
                 facility_id='PLANT_IN01', country='IN',
                 source_row_id='5000012610',
                 status='flagged',
                 flag_reason='unusually high CO2e (>50t)',
                 raw_data={'document_number':'5000012610','plant':'PLANT_IN01',
                           'material_description':'Diesel','quantity':'98000','unit':'L',
                           'posting_date':'20240331','vendor':'Indian Oil Corp'}),
        ]
        for r in sap_records:
            status_val = r.pop('status', 'pending')
            flag_reason = r.pop('flag_reason', '')
            rec = EmissionRecord.objects.create(
                tenant=tenant, batch=sap_batch,
                source_type='sap', status=status_val, flag_reason=flag_reason, **r)
            AuditLog.objects.create(record=rec, action='created', performed_by=user,
                note='Seeded demo SAP data', snapshot={'status': status_val})

        # Utility batch
        util_batch = IngestionBatch.objects.create(
            tenant=tenant, source_type='utility',
            filename='GreenButton_2024_Q1.csv',
            status='done', uploaded_by=user,
            row_count=3, error_count=0,
        )
        util_records = [
            dict(scope=2, activity_type='electricity', raw_value=Decimal('12450'),
                 raw_unit='kWh', normalized_value_kwh=Decimal('12450'),
                 emission_factor=Decimal('0.20707'), emission_factor_source='DEFRA 2023',
                 co2e_kg=Decimal('2578.02'), activity_date=date(2024,1,1),
                 period_start=date(2024,1,1), period_end=date(2024,1,31),
                 facility_id='METER_LDN_001', country='GB',
                 source_row_id='utility_row_2',
                 raw_data={'TYPE':'Electric','START DATE':'2024-01-01','END DATE':'2024-01-31',
                           'USAGE':'12450','UNITS':'kWh','COST':'1867.50'}),
            dict(scope=2, activity_type='electricity', raw_value=Decimal('11900'),
                 raw_unit='kWh', normalized_value_kwh=Decimal('11900'),
                 emission_factor=Decimal('0.20707'), emission_factor_source='DEFRA 2023',
                 co2e_kg=Decimal('2464.13'), activity_date=date(2024,2,1),
                 period_start=date(2024,2,1), period_end=date(2024,2,29),
                 facility_id='METER_LDN_001', country='GB',
                 source_row_id='utility_row_3',
                 raw_data={'TYPE':'Electric','START DATE':'2024-02-01','END DATE':'2024-02-29',
                           'USAGE':'11900','UNITS':'kWh','COST':'1785.00'}),
            dict(scope=2, activity_type='electricity', raw_value=Decimal('0'),
                 raw_unit='kWh', normalized_value_kwh=Decimal('0'),
                 emission_factor=Decimal('0.20707'), emission_factor_source='DEFRA 2023',
                 co2e_kg=Decimal('0'), activity_date=date(2024,3,1),
                 period_start=date(2024,3,1), period_end=date(2024,4,8),
                 facility_id='METER_LDN_001', country='GB',
                 source_row_id='utility_row_4',
                 status='flagged',
                 flag_reason='zero usage — possible estimated read; billing period > 35 days — likely estimated',
                 raw_data={'TYPE':'Electric','START DATE':'2024-03-01','END DATE':'2024-04-08',
                           'USAGE':'0','UNITS':'kWh','COST':'0.00'}),
        ]
        for r in util_records:
            status_val = r.pop('status', 'pending')
            flag_reason = r.pop('flag_reason', '')
            rec = EmissionRecord.objects.create(
                tenant=tenant, batch=util_batch,
                source_type='utility', status=status_val, flag_reason=flag_reason, **r)
            AuditLog.objects.create(record=rec, action='created', performed_by=user,
                note='Seeded demo utility data', snapshot={'status': status_val})

        # Travel batch
        travel_batch = IngestionBatch.objects.create(
            tenant=tenant, source_type='travel',
            filename='Navan_Export_2024_Q1.csv',
            status='done', uploaded_by=user,
            row_count=5, error_count=0,
        )
        travel_records = [
            dict(scope=3, activity_type='travel_flight', raw_value=Decimal('6730'),
                 raw_unit='km', emission_factor=Decimal('0.19500'),
                 emission_factor_source='DEFRA 2023',
                 co2e_kg=Decimal('1312.35'), activity_date=date(2024,1,8),
                 source_row_id='TRP-2024-001',
                 raw_data={'trip_id':'TRP-2024-001','traveler_name':'Sarah Chen',
                           'trip_type':'flight','origin':'LHR','destination':'JFK',
                           'departure_date':'2024-01-08','distance_km':'6730',
                           'cost_usd':'1240.00'}),
            dict(scope=3, activity_type='travel_hotel', raw_value=Decimal('3'),
                 raw_unit='nights', emission_factor=Decimal('0.06700'),
                 emission_factor_source='DEFRA 2023',
                 co2e_kg=Decimal('0.201'), activity_date=date(2024,1,8),
                 source_row_id='TRP-2024-001-H',
                 raw_data={'trip_id':'TRP-2024-001-H','traveler_name':'Sarah Chen',
                           'trip_type':'hotel','origin':'New York','destination':'New York',
                           'departure_date':'2024-01-08','nights':'3','cost_usd':'680.00'}),
            dict(scope=3, activity_type='travel_flight', raw_value=Decimal('1174'),
                 raw_unit='km', emission_factor=Decimal('0.25500'),
                 emission_factor_source='DEFRA 2023',
                 co2e_kg=Decimal('299.37'), activity_date=date(2024,2,14),
                 source_row_id='TRP-2024-002',
                 status='flagged',
                 flag_reason='distance estimated from IATA codes (LHR→CDG)',
                 raw_data={'trip_id':'TRP-2024-002','traveler_name':'Raj Patel',
                           'trip_type':'flight','origin':'LHR','destination':'CDG',
                           'departure_date':'2024-02-14','distance_km':'',
                           'cost_usd':'320.00'}),
            dict(scope=3, activity_type='travel_ground', raw_value=Decimal('45'),
                 raw_unit='km', emission_factor=Decimal('0.14900'),
                 emission_factor_source='DEFRA 2023',
                 co2e_kg=Decimal('6.705'), activity_date=date(2024,3,5),
                 source_row_id='TRP-2024-003',
                 raw_data={'trip_id':'TRP-2024-003','traveler_name':'Priya Sharma',
                           'trip_type':'ground','transport_mode':'taxi',
                           'origin':'Heathrow','destination':'London City',
                           'departure_date':'2024-03-05','distance_km':'45',
                           'cost_usd':'85.00'}),
        ]
        for r in travel_records:
            status_val = r.pop('status', 'pending')
            flag_reason = r.pop('flag_reason', '')
            rec = EmissionRecord.objects.create(
                tenant=tenant, batch=travel_batch,
                source_type='travel', status=status_val, flag_reason=flag_reason, **r)
            AuditLog.objects.create(record=rec, action='created', performed_by=user,
                note='Seeded demo travel data', snapshot={'status': status_val})

        self.stdout.write(self.style.SUCCESS('Seed complete! Login: admin / admin123'))
