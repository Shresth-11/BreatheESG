from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Sum, Count, Q
from .models import Tenant, IngestionBatch, EmissionRecord, AuditLog
from .serializers import (TenantSerializer, IngestionBatchSerializer,
                           EmissionRecordSerializer, EmissionRecordListSerializer)


class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer


class IngestionBatchViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = IngestionBatch.objects.select_related('tenant', 'uploaded_by').all()
    serializer_class = IngestionBatchSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        tenant_id = self.request.query_params.get('tenant')
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        return qs


class EmissionRecordViewSet(viewsets.ModelViewSet):
    queryset = EmissionRecord.objects.select_related('tenant', 'batch', 'reviewed_by').all()

    def get_serializer_class(self):
        if self.action == 'list':
            return EmissionRecordListSerializer
        return EmissionRecordSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('tenant'):
            qs = qs.filter(tenant_id=params['tenant'])
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        if params.get('scope'):
            qs = qs.filter(scope=params['scope'])
        if params.get('source_type'):
            qs = qs.filter(source_type=params['source_type'])
        if params.get('batch'):
            qs = qs.filter(batch_id=params['batch'])
        return qs

    def _log(self, record, action, user, note=''):
        import json
        from decimal import Decimal

        def default(o):
            if isinstance(o, Decimal):
                return str(o)
            raise TypeError

        AuditLog.objects.create(
            record=record,
            action=action,
            performed_by=user if user.is_authenticated else None,
            note=note,
            snapshot=json.loads(json.dumps({
                'status': record.status,
                'co2e_kg': str(record.co2e_kg),
                'analyst_note': record.analyst_note,
            }, default=default))
        )

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        record = self.get_object()
        if record.status == EmissionRecord.STATUS_LOCKED:
            return Response({'error': 'Record is locked and cannot be changed.'}, status=400)
        record.status = EmissionRecord.STATUS_APPROVED
        record.reviewed_by = request.user if request.user.is_authenticated else None
        record.reviewed_at = timezone.now()
        record.analyst_note = request.data.get('note', '')
        record.save()
        self._log(record, 'approved', request.user, request.data.get('note', ''))
        return Response({'status': 'approved'})

    @action(detail=True, methods=['post'])
    def flag(self, request, pk=None):
        record = self.get_object()
        if record.status == EmissionRecord.STATUS_LOCKED:
            return Response({'error': 'Record is locked.'}, status=400)
        record.status = EmissionRecord.STATUS_FLAGGED
        record.flag_reason = request.data.get('reason', 'Manually flagged by analyst')
        record.save()
        self._log(record, 'flagged', request.user, record.flag_reason)
        return Response({'status': 'flagged'})

    @action(detail=True, methods=['post'])
    def lock(self, request, pk=None):
        record = self.get_object()
        if record.status != EmissionRecord.STATUS_APPROVED:
            return Response({'error': 'Only approved records can be locked.'}, status=400)
        record.status = EmissionRecord.STATUS_LOCKED
        record.save()
        self._log(record, 'locked', request.user)
        return Response({'status': 'locked'})

    @action(detail=False, methods=['get'])
    def summary(self, request):
        qs = self.get_queryset()
        data = {
            'total_co2e_kg': qs.aggregate(t=Sum('co2e_kg'))['t'] or 0,
            'by_scope': {
                str(s): qs.filter(scope=s).aggregate(t=Sum('co2e_kg'))['t'] or 0
                for s in [1, 2, 3]
            },
            'by_source': {
                src: qs.filter(source_type=src).aggregate(t=Sum('co2e_kg'))['t'] or 0
                for src in ['sap', 'utility', 'travel']
            },
            'by_status': {
                st: qs.filter(status=st).count()
                for st in ['pending', 'flagged', 'approved', 'locked']
            },
            'total_records': qs.count(),
        }
        return Response(data)
