"""
Employee activity listing using @api_view decorator style.

Endpoints:
    GET /api/v1/activities/            — list all active activities (employee only)
    GET /api/v1/activities/<id>/       — single activity detail (employee only)
    GET /api/v1/activities/benchmark/  — cache before vs after (admin only, Topic 9.3)
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from django.db.models import Count

from ngo.models import NGO
from .serializers import NGOEmployeeListSerializer, NGOEmployeeDetailSerializer


# ── Permission: Employee only (Topic 7.3c) ────────────────────

class IsEmployee(IsAuthenticated):
    """
    Blocks admins from accessing employee endpoints.
    Admins use /api/v1/ngos/ instead.
    """
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.user.groups.filter(name='Administrator').exists():
            return False
        return request.user.groups.filter(name='Employee').exists()


# ── Helper ────────────────────────────────────────────────────

def _get_active_ngos():
    return (
        NGO.objects
        .filter(is_active=True)
        .select_related('serviceType', 'organizer')
        .annotate(registered_count=Count('registration'))
        .order_by('service_date')
    )


# ── GET /api/v1/activities/ ───────────────────────────────────

@api_view(['GET'])
@permission_classes([IsEmployee])
def activity_list(request):

    # ── Filtering ──────────────────────────────────
    date_from = request.query_params.get('date_from')
    date_to   = request.query_params.get('date_to')
    location  = request.query_params.get('location')
    name      = request.query_params.get('name')
    has_filters = any([date_from, date_to, location, name])

    if not has_filters:
        # ──  Redis cache ───────────────────────
        from .services.ngo_service import NGOService
        ngos       = NGOService.get_all_ngo_list_active()
        serializer = NGOEmployeeListSerializer(ngos, many=True)
        return Response({
            'count':      len(ngos),
            'from_cache': True,
            'results':    serializer.data,
        })

    # ── filtered: bypass cache, hit DB directly ───────────────
    qs = _get_active_ngos()

    if date_from:
        qs = qs.filter(service_date__gte=date_from)
    if date_to:
        qs = qs.filter(service_date__lte=date_to)
    if location:
        qs = qs.filter(location__icontains=location)
    if name:
        qs = qs.filter(name__icontains=name)

    # ── Pagination ─────────────────────────────────
    paginator            = PageNumberPagination()
    paginator.page_size  = 10
    page       = paginator.paginate_queryset(list(qs), request)
    serializer = NGOEmployeeListSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


# ── GET /api/v1/activities/<id>/ ──────────────────────────────

@api_view(['GET'])
@permission_classes([IsEmployee])
def activity_detail(request, pk):
    """UC2 — Full detail for a single activity."""
    try:
        ngo = _get_active_ngos().get(pk=pk)
    except NGO.DoesNotExist:
        return Response(
            {'error': 'Activity not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    serializer = NGOEmployeeDetailSerializer(ngo)
    return Response(serializer.data)


# ── GET /api/v1/activities/benchmark/ ────────────────────────

@api_view(['GET'])
@permission_classes([IsAdminUser])
def cache_benchmark(request):
    """
    Returns:
    {
        "db_query_ms":  15.2,
        "cache_hit_ms":  0.4,
        "speedup_x":    38.0,
        "note": "Cache is ~38x faster than a DB query"
    }
    """
    from .services.cache_benchmark import benchmark_ngo_cache
    return Response(benchmark_ngo_cache())