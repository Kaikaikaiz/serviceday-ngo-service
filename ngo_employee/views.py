"""
Employee activity listing using @api_view decorator style.

Endpoints:
    GET /api/v1/activities/            — list all active activities (employee only)
    GET /api/v1/activities/<id>/       — single activity detail (employee only)
    GET /api/v1/activities/benchmark/  — cache before vs after (admin only, Topic 9.3)
"""

from time import time

from django.db import connection, reset_queries
from django_redis import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from django.db.models import Count

from ngo.models import NGO, Organizer, ServiceType
from .serializers import NGOEmployeeListSerializer, NGOEmployeeDetailSerializer, OrganizerSerializer, ServiceTypeSerializer
import requests
from django.conf import settings
# ── Permission: Admin only  ────────────────────

class IsAdminUser(BasePermission):
  
    def has_permission(self, request, view):
        # AnonymousUser is not a dict, so guard against it first
        if not isinstance(request.user, dict):
            return False
        groups = request.user.get('groups', [])
        return 'Administrator' in groups

# ── Permission: Employee only ────────────────────

class IsEmployee(BasePermission):
    def has_permission(self, request, view):
        print(f"DEBUG request.user = {request.user}") 
        if not request.user or not isinstance(request.user, dict):
            return False
        groups = request.user.get('groups', [])
        if 'Administrator' in groups:
            return False
        return 'Employee' in groups


# ── Helper ────────────────────────────────────────────────────

def _get_active_ngos():
    return (
        NGO.objects
        .filter(is_active=True)
        .select_related('serviceType', 'organizer')
        .order_by('service_date')
    )


# ── GET /api/v1/activities/ ───────────────────────────────────

@api_view(['GET'])
@permission_classes([IsEmployee])
def activity_list(request):

    service_date = request.query_params.get('service_date')
    date_from = request.query_params.get('date_from')
    date_to   = request.query_params.get('date_to')
    location  = request.query_params.get('location')
    name      = request.query_params.get('name')
    has_filters = any([service_date, date_from, date_to, location, name])

    if not has_filters:
        from .services.ngo_service import NGOService
        ngos = NGOService.get_all_ngo_list_active()
    else:
        qs = _get_active_ngos()
        if service_date:    qs = qs.filter(service_date=service_date)
        if date_from:       qs = qs.filter(service_date__gte=date_from)
        if date_to:         qs = qs.filter(service_date__lte=date_to)
        if location:        qs = qs.filter(location__icontains=location)
        if name:            qs = qs.filter(name__icontains=name)
        ngos = list(qs)

    # ← fetch registration counts from registration-service
    counts = {}
    try:
        ngo_ids = ','.join([str(n.id) for n in ngos])
        reg_resp = requests.get(
            settings.REGISTRATION_SERVICE_URL + '/api/v1/registrations/counts/',
            headers={'Authorization': request.headers.get('Authorization', '')},
            params={'ngo_ids': ngo_ids},
            timeout=3
        )
        if reg_resp.status_code == 200:
            counts = reg_resp.json()
    except Exception:
        pass

    # ← pass counts in context
    context = {'registration_counts': counts}

    if not has_filters:
        serializer = NGOEmployeeListSerializer(ngos, many=True, context=context)
        return Response({
            'count':      len(ngos),
            'from_cache': True,
            'results':    serializer.data,
        })

    paginator = PageNumberPagination()
    paginator.page_size = 10
    page = paginator.paginate_queryset(ngos, request)
    serializer = NGOEmployeeListSerializer(page, many=True, context=context)
    return paginator.get_paginated_response(serializer.data)


# ── GET /api/v1/activities/<id>/ ──────────────────────────────

@api_view(['GET'])
@permission_classes([IsEmployee])
def activity_detail(request, pk):
    try:
        ngo = _get_active_ngos().get(pk=pk)
    except NGO.DoesNotExist:
        return Response(
            {'error': 'Activity not found.'},
            status=status.HTTP_404_NOT_FOUND
        )

    # ← fetch registration count for this single NGO
    counts = {}
    try:
        reg_resp = requests.get(
            settings.REGISTRATION_SERVICE_URL + '/api/v1/registrations/counts/',
            headers={'Authorization': request.headers.get('Authorization', '')},
            params={'ngo_ids': str(ngo.id)},
            timeout=3
        )
        if reg_resp.status_code == 200:
            counts = reg_resp.json()
    except Exception:
        pass

    serializer = NGOEmployeeDetailSerializer(ngo, context={'registration_counts': counts})
    return Response(serializer.data)


# ── Employee-accessible endpoints ─────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsEmployee])
def service_type_list(request):
    """
    GET /api/v1/service-types/
    Employee can read service types for filter panel.
    """
    types = ServiceType.objects.all().order_by('name')
    return Response({
        'success': True,
        'data': ServiceTypeSerializer(types, many=True).data
    })


@api_view(['GET'])
@permission_classes([IsEmployee])
def organizer_list(request):
    """
    GET /api/v1/organizers/
    Employee can read organizers for filter panel.
    """
    organizers = Organizer.objects.all().order_by('company_name')
    return Response({
        'success': True,
        'data': OrganizerSerializer(organizers, many=True).data
    })


# ── GET /api/v1/activities/benchmark/ ────────────────────────

@api_view(['GET'])
@permission_classes([IsAdminUser])
def cache_benchmark(request):
    """
    Topic 9.3 — Before vs After cache performance comparison.
    Delegates all measurement logic to benchmark_ngo_cache().
    """
    from .services.cache_benchmark import benchmark_ngo_cache
    result = benchmark_ngo_cache()
    return Response(result)