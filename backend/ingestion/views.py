import io
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from emissions.models import Tenant, IngestionBatch, EmissionRecord, AuditLog
from .parsers import parse_sap_csv, parse_utility_csv, parse_travel_csv

PARSER_MAP = {
    'sap': parse_sap_csv,
    'utility': parse_utility_csv,
    'travel': parse_travel_csv,
}


class IngestView(APIView):
    """
    POST /api/ingest/
    Accepts a multipart form with:
      - file: the CSV upload
      - source_type: sap | utility | travel
      - tenant_id: UUID of the tenant

    Creates an IngestionBatch, runs the appropriate parser,
    bulk-creates EmissionRecord rows, logs auto-flags.
    Returns batch summary.
    """

    def post(self, request):
        source_type = request.data.get('source_type')
        tenant_id = request.data.get('tenant_id')
        file_obj = request.FILES.get('file')

        if not all([source_type, tenant_id, file_obj]):
            return Response(
                {'error': 'source_type, tenant_id, and file are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if source_type not in PARSER_MAP:
            return Response(
                {'error': f'source_type must be one of: {list(PARSER_MAP.keys())}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        tenant = get_object_or_404(Tenant, id=tenant_id)
        parser = PARSER_MAP[source_type]

        batch = IngestionBatch.objects.create(
            tenant=tenant,
            source_type=source_type,
            filename=file_obj.name,
            status=IngestionBatch.STATUS_PROCESSING,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )

        try:
            records_data, errors = parser(file_obj)
        except Exception as e:
            batch.status = IngestionBatch.STATUS_FAILED
            batch.notes = str(e)
            batch.save()
            return Response({'error': f'Parse failed: {e}', 'batch_id': str(batch.id)}, status=500)

        created = []
        for r in records_data:
            auto_flag = r.pop('auto_flag', False)
            flag_reason = r.pop('flag_reason', '')
            rec = EmissionRecord(
                tenant=tenant,
                batch=batch,
                status=EmissionRecord.STATUS_FLAGGED if auto_flag else EmissionRecord.STATUS_PENDING,
                flag_reason=flag_reason,
                **r
            )
            created.append(rec)

        EmissionRecord.objects.bulk_create(created)

        # Audit log for each created record
        audit_entries = []
        for rec in EmissionRecord.objects.filter(batch=batch):
            audit_entries.append(AuditLog(
                record=rec,
                action='created',
                performed_by=None,
                note=f'Ingested from {source_type} file: {file_obj.name}',
                snapshot={'status': rec.status, 'co2e_kg': str(rec.co2e_kg)}
            ))
        AuditLog.objects.bulk_create(audit_entries)

        batch.row_count = len(created)
        batch.error_count = len(errors)
        batch.status = IngestionBatch.STATUS_DONE
        batch.save()

        return Response({
            'batch_id': str(batch.id),
            'source_type': source_type,
            'rows_ingested': len(created),
            'rows_failed': len(errors),
            'errors': errors[:10],  # Return first 10 errors
            'flagged': sum(1 for r in EmissionRecord.objects.filter(batch=batch)
                          if r.status == EmissionRecord.STATUS_FLAGGED),
        })
