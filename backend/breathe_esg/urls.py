from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def health(request):
    return JsonResponse({"status": "ok", "service": "BreatheESG API"})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health),
    path('api/', include('ingestion.urls')),
    path('api/', include('emissions.urls')),
]
