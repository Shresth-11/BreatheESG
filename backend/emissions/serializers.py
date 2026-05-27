from rest_framework import serializers
from .models import Tenant, IngestionBatch, EmissionRecord, AuditLog


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ['id', 'name', 'slug', 'created_at']


class IngestionBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestionBatch
        fields = ['id', 'tenant', 'source_type', 'filename', 'status',
                  'uploaded_at', 'row_count', 'error_count', 'notes']


class AuditLogSerializer(serializers.ModelSerializer):
    performed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = ['id', 'action', 'performed_by_name', 'note', 'timestamp']

    def get_performed_by_name(self, obj):
        return obj.performed_by.username if obj.performed_by else 'system'


class EmissionRecordSerializer(serializers.ModelSerializer):
    audit_logs = AuditLogSerializer(many=True, read_only=True)
    scope_display = serializers.CharField(source='get_scope_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    activity_display = serializers.CharField(source='get_activity_type_display', read_only=True)

    class Meta:
        model = EmissionRecord
        fields = [
            'id', 'tenant', 'batch', 'source_type', 'source_row_id',
            'scope', 'scope_display', 'activity_type', 'activity_display',
            'raw_value', 'raw_unit', 'raw_data',
            'emission_factor', 'emission_factor_source', 'co2e_kg',
            'activity_date', 'period_start', 'period_end',
            'facility_id', 'country',
            'status', 'status_display', 'flag_reason', 'analyst_note',
            'reviewed_by', 'reviewed_at', 'version',
            'created_at', 'updated_at',
            'audit_logs',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'audit_logs']


class EmissionRecordListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views — no raw_data or audit_logs"""
    scope_display = serializers.CharField(source='get_scope_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = EmissionRecord
        fields = [
            'id', 'source_type', 'scope', 'scope_display', 'activity_type',
            'raw_value', 'raw_unit', 'co2e_kg', 'activity_date',
            'facility_id', 'status', 'status_display', 'flag_reason',
        ]
