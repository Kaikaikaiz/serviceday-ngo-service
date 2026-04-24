"""
ngo_admin/views.py
Topic 8 — RESTful API for NGO Management (Admin).
Using @api_view decorator style (consistent with lecturer's approach).
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from django.db.models import Q
import requests
from django.conf import settings


from ngo.models import NGO, ServiceType, Organizer
from .serializers import (
    NGOListSerializer, NGODetailSerializer, NGOWriteSerializer,
    ServiceTypeSerializer, ServiceTypeWriteSerializer,
    OrganizerSerializer, OrganizerWriteSerializer,
)

class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user:
            return False
        # StatelessJWTAuthentication returns a dict payload
        if isinstance(user, dict):
            return 'Administrator' in user.get('groups', [])
        # fallback for SessionAuthentication
        return user.is_authenticated and (
            user.is_staff or
            user.groups.filter(name='Administrator').exists()
        )


def _get_ngo(ngo_id):
    try:
        return NGO.objects.select_related('serviceType', 'organizer').get(pk=ngo_id)
    except NGO.DoesNotExist:
        return None


def _paginate(queryset, request):
    paginator           = PageNumberPagination()
    paginator.page_size = 10
    page                = paginator.paginate_queryset(queryset, request)
    return page, paginator

def _get_registration_counts(ngo_ids, auth_header):
    try:
        resp = requests.get(
            settings.REGISTRATION_SERVICE_URL + '/api/v1/registrations/counts/',
            headers={'Authorization': auth_header},
            params={'ngo_ids': ','.join([str(i) for i in ngo_ids])},
            timeout=3
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}

@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def ngo_list_create(request):
    if request.method == 'GET':
        search        = request.query_params.get('search', '').strip()
        status_filter = request.query_params.get('status', '').strip()
        date_from     = request.query_params.get('date_from', '').strip()
        date_to       = request.query_params.get('date_to', '').strip()
        location      = request.query_params.get('location', '').strip()
        service_type  = request.query_params.get('service_type', '').strip()

        has_filters = any([search, status_filter, date_from, date_to, location, service_type])

        if not has_filters:
            from ngo_admin.services.admindashboard import get_all_ngos
            ngos = get_all_ngos()
        else:
            qs = NGO.objects.select_related('serviceType', 'organizer').order_by('service_date')
            if search:
                qs = qs.filter(Q(name__icontains=search) | Q(location__icontains=search))
            if location:
                qs = qs.filter(location__icontains=location)
            if date_from:
                qs = qs.filter(service_date__gte=date_from)
            if date_to:
                qs = qs.filter(service_date__lte=date_to)
            if service_type:
                qs = qs.filter(serviceType__id=service_type)
            ngos = list(qs)

        if status_filter == 'open':
            ngos = [n for n in ngos if not n.is_full and not n.is_closed and n.is_active]
        elif status_filter == 'full':
            ngos = [n for n in ngos if n.is_full]
        elif status_filter == 'almost':
            ngos = [n for n in ngos if not n.is_full and n.available_slots <= n.max_slots * 0.5 and n.is_active]
        elif status_filter == 'closed':
            ngos = [n for n in ngos if n.is_closed]
        elif status_filter == 'inactive':
            ngos = [n for n in ngos if not n.is_active]

        page, paginator = _paginate(ngos, request)
        auth_header = request.headers.get('Authorization', '')
        counts      = _get_registration_counts([n.id for n in page], auth_header)
        serializer = NGOListSerializer(page, many=True, context={'registration_counts': counts})

        return Response({
            'success': True,
            'data': {
                'count':    paginator.page.paginator.count,
                'next':     paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results':  serializer.data,
            }
        })

    elif request.method == 'POST':
        serializer = NGOWriteSerializer(data=request.data)
        if serializer.is_valid():
            ngo = serializer.save()
            from ngo_admin.services.admindashboard import invalidate_ngo_cache
            invalidate_ngo_cache()
            return Response(
                {'success': True, 'message': 'NGO created successfully.', 'data': NGODetailSerializer(ngo).data},
                status=status.HTTP_201_CREATED
            )
        return Response(
            {'success': False, 'message': 'Validation failed.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAdminUser])
def ngo_detail(request, ngo_id):
    ngo = _get_ngo(ngo_id)
    if not ngo:
        return Response({'success': False, 'message': 'NGO not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        auth_header = request.headers.get('Authorization', '')
        counts      = _get_registration_counts([ngo.id], auth_header)
        print(f"COUNTS: {counts}")
        return Response({'success': True, 'data': NGODetailSerializer(ngo, context={'registration_counts': counts}).data})

    elif request.method in ['PUT', 'PATCH']:
        partial    = request.method == 'PATCH'
        serializer = NGOWriteSerializer(ngo, data=request.data, partial=partial)
        if serializer.is_valid():
            updated = serializer.save()
            from ngo_admin.services.admindashboard import invalidate_ngo_cache
            invalidate_ngo_cache()
            return Response({'success': True, 'message': 'NGO updated successfully.', 'data': NGODetailSerializer(updated).data})
        return Response(
            {'success': False, 'message': 'Validation failed.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    elif request.method == 'DELETE':
        ngo.delete()
        from ngo_admin.services.admindashboard import invalidate_ngo_cache
        invalidate_ngo_cache()
        return Response({'success': True, 'message': 'NGO deleted successfully.'})


@api_view(['PATCH'])
@permission_classes([IsAdminUser])
def ngo_toggle_active(request, ngo_id):
    ngo = _get_ngo(ngo_id)
    if not ngo:
        return Response({'success': False, 'message': 'NGO not found.'}, status=status.HTTP_404_NOT_FOUND)
    ngo.is_active = not ngo.is_active
    ngo.save(update_fields=['is_active'])
    from ngo_admin.services.admindashboard import invalidate_ngo_cache
    invalidate_ngo_cache()
    state = 'activated' if ngo.is_active else 'deactivated'
    return Response({'success': True, 'message': f'NGO {state} successfully.', 'data': {'id': ngo.id, 'is_active': ngo.is_active}})


@api_view(['GET'])
@permission_classes([IsAdminUser])
def ngo_dashboard(request):
    from ngo_admin.services.admindashboard import get_dashboard_stats
    return Response({'success': True, 'data': get_dashboard_stats()})


@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def service_type_list_create(request):
    if request.method == 'GET':
        types = ServiceType.objects.all().order_by('name')
        return Response({'success': True, 'data': ServiceTypeSerializer(types, many=True).data})

    elif request.method == 'POST':
        serializer = ServiceTypeWriteSerializer(data=request.data)
        if serializer.is_valid():
            st = serializer.save()
            return Response(
                {'success': True, 'message': 'Service type created.', 'data': ServiceTypeSerializer(st).data},
                status=status.HTTP_201_CREATED
            )
        return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAdminUser])
def service_type_detail(request, pk):
    try:
        st = ServiceType.objects.get(pk=pk)
    except ServiceType.DoesNotExist:
        return Response({'success': False, 'message': 'Service type not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response({'success': True, 'data': ServiceTypeSerializer(st).data})

    elif request.method == 'PUT':
        serializer = ServiceTypeWriteSerializer(st, data=request.data)
        if serializer.is_valid():
            updated = serializer.save()
            return Response({'success': True, 'data': ServiceTypeSerializer(updated).data})
        return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        if st.ngo_set.exists():
            return Response(
                {'success': False, 'message': f'Cannot delete "{st.name}" — it is used by existing NGOs.'},
                status=status.HTTP_409_CONFLICT
            )
        st.delete()
        return Response({'success': True, 'message': 'Service type deleted.'})


@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def organizer_list_create(request):
    if request.method == 'GET':
        organizers = Organizer.objects.all().order_by('company_name')
        return Response({'success': True, 'data': OrganizerSerializer(organizers, many=True).data})

    elif request.method == 'POST':
        serializer = OrganizerWriteSerializer(data=request.data)
        if serializer.is_valid():
            org = serializer.save()
            return Response(
                {'success': True, 'message': 'Organizer created.', 'data': OrganizerSerializer(org).data},
                status=status.HTTP_201_CREATED
            )
        return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAdminUser])
def organizer_detail(request, pk):
    try:
        org = Organizer.objects.get(pk=pk)
    except Organizer.DoesNotExist:
        return Response({'success': False, 'message': 'Organizer not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response({'success': True, 'data': OrganizerSerializer(org).data})

    elif request.method in ['PUT', 'PATCH']:
        partial    = request.method == 'PATCH'
        serializer = OrganizerWriteSerializer(org, data=request.data, partial=partial)
        if serializer.is_valid():
            updated = serializer.save()
            return Response({'success': True, 'data': OrganizerSerializer(updated).data})
        return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        org.delete()
        return Response({'success': True, 'message': 'Organizer deleted.'})