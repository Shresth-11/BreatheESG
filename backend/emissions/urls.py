from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TenantViewSet, IngestionBatchViewSet, EmissionRecordViewSet

router = DefaultRouter()
router.register('tenants', TenantViewSet)
router.register('batches', IngestionBatchViewSet)
router.register('records', EmissionRecordViewSet)

urlpatterns = [path('', include(router.urls))]
