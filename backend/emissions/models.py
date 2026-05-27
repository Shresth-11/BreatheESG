"""
Core data models for BreatheESG.

Design principles:
- Multi-tenancy via Tenant (one per client company)
- Every EmissionRecord knows its source (SAP/utility/travel), ingestion batch,
  original raw value + unit, and normalized value in kg CO2e
- Scope 1/2/3 is set at ingestion time based on source + activity type
- Audit trail: status transitions are logged in AuditLog
- EmissionRecord is immutable once status=LOCKED; edits create a new version
"""
from django.db import models
from django.contrib.auth.models import User
import uuid


class Tenant(models.Model):
    """One row per client company. All data is scoped to a tenant."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class IngestionBatch(models.Model):
    """
    Represents one upload/pull event for a specific source type.
    Groups all records that came in together so analysts can review by batch.
    """
    SOURCE_SAP = 'sap'
    SOURCE_UTILITY = 'utility'
    SOURCE_TRAVEL = 'travel'
    SOURCE_CHOICES = [
        (SOURCE_SAP, 'SAP Fuel & Procurement'),
        (SOURCE_UTILITY, 'Utility / Electricity'),
        (SOURCE_TRAVEL, 'Corporate Travel'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_DONE, 'Done'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='batches')
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    filename = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    row_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.tenant} | {self.source_type} | {self.uploaded_at:%Y-%m-%d}"


class EmissionRecord(models.Model):
    """
    Normalized emission record. One row = one activity event.

    SCOPE DEFINITIONS (GHG Protocol):
      Scope 1: Direct emissions — fuel combustion, company vehicles
      Scope 2: Indirect from purchased electricity/heat/cooling
      Scope 3: All other indirect — business travel, supply chain

    UNIT NORMALIZATION:
      raw_value + raw_unit preserved for audit.
      normalized_value is always in kg CO2e.
      emission_factor records what multiplier was used and from which source.

    STATUS FLOW:
      pending → flagged (if suspicious) or approved → locked (for audit)
      Any edit while pending/flagged creates a new version; original is kept.
    """
    SCOPE_1 = 1
    SCOPE_2 = 2
    SCOPE_3 = 3
    SCOPE_CHOICES = [(1, 'Scope 1'), (2, 'Scope 2'), (3, 'Scope 3')]

    STATUS_PENDING = 'pending'
    STATUS_FLAGGED = 'flagged'
    STATUS_APPROVED = 'approved'
    STATUS_LOCKED = 'locked'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Review'),
        (STATUS_FLAGGED, 'Flagged / Suspicious'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_LOCKED, 'Locked for Audit'),
    ]

    ACTIVITY_CHOICES = [
        # Scope 1
        ('fuel_diesel', 'Diesel Fuel'),
        ('fuel_petrol', 'Petrol / Gasoline'),
        ('fuel_natural_gas', 'Natural Gas'),
        ('fuel_lpg', 'LPG'),
        # Scope 2
        ('electricity', 'Purchased Electricity'),
        # Scope 3
        ('travel_flight', 'Flight'),
        ('travel_hotel', 'Hotel Stay'),
        ('travel_ground', 'Ground Transport'),
        ('procurement', 'Procurement / Supply Chain'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='records')
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name='records')

    # Provenance
    source_type = models.CharField(max_length=20, choices=IngestionBatch.SOURCE_CHOICES)
    source_row_id = models.CharField(max_length=255, blank=True,
        help_text="Original row identifier from source (SAP doc number, meter ID, trip ID)")

    # Classification
    scope = models.IntegerField(choices=SCOPE_CHOICES)
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_CHOICES)

    # Raw values (preserved exactly as ingested)
    raw_value = models.DecimalField(max_digits=20, decimal_places=6)
    raw_unit = models.CharField(max_length=50,
        help_text="Original unit: L, kg, kWh, MWh, km, nights, etc.")
    raw_data = models.JSONField(default=dict,
        help_text="Full original row as parsed — for full audit trail")

    # Normalized values
    normalized_value_kwh = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True,
        help_text="Energy in kWh (for fuel/electricity; null for travel)")
    emission_factor = models.DecimalField(max_digits=20, decimal_places=8,
        help_text="kg CO2e per raw unit, from DEFRA/EPA/IPCC")
    emission_factor_source = models.CharField(max_length=255, default='DEFRA 2023',
        help_text="Which emission factor database was used")
    co2e_kg = models.DecimalField(max_digits=20, decimal_places=6,
        help_text="Final emission in kg CO2e = raw_value * emission_factor")

    # Temporal
    activity_date = models.DateField(help_text="Date the activity occurred (not upload date)")
    period_start = models.DateField(null=True, blank=True,
        help_text="For billing-period data (utility); start of period")
    period_end = models.DateField(null=True, blank=True,
        help_text="For billing-period data; end of period")

    # Location / facility
    facility_id = models.CharField(max_length=255, blank=True,
        help_text="SAP plant code, meter ID, or office name")
    country = models.CharField(max_length=2, blank=True,
        help_text="ISO 3166-1 alpha-2")

    # Review status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    flag_reason = models.TextField(blank=True,
        help_text="Auto-generated reason if record was auto-flagged as suspicious")
    analyst_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reviewed_records')
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # Versioning (if analyst edits a record, original stays; edited creates new)
    version = models.IntegerField(default=1)
    superseded_by = models.ForeignKey('self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='supersedes')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-activity_date']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'scope']),
            models.Index(fields=['batch']),
            models.Index(fields=['activity_date']),
        ]

    def __str__(self):
        return f"{self.tenant} | {self.activity_type} | {self.co2e_kg} kg CO2e"


class AuditLog(models.Model):
    """
    Immutable log of every status change on an EmissionRecord.
    Written by signals — never edited directly.
    """
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('flagged', 'Auto-flagged'),
        ('approved', 'Approved'),
        ('locked', 'Locked'),
        ('edited', 'Edited'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(EmissionRecord, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    note = models.TextField(blank=True)
    snapshot = models.JSONField(default=dict,
        help_text="Full record state at time of action")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']
