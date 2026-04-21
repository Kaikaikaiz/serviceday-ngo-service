"""
ngo_admin/views.py
Topic 8 — RESTful API for NGO Management (Admin).
Microservice version — API views only, no templates.

Endpoints:
    GET/POST        /api/v1/ngos/
    GET/PUT/PATCH/DELETE /api/v1/ngos/<id>/
    PATCH           /api/v1/ngos/<id>/toggle-active/
    GET             /api/v1/ngos/dashboard/
    GET/POST        /api/v1/service-types/
    GET/PUT/DELETE  /api/v1/service-types/<id>/
    GET/POST        /api/v1/organizers/
    GET/PUT/PATCH/DELETE /api/v1/organizers/<id>/
"""

from rest_framework          import status
from rest_framework.views    import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from rest_framework.pagination import PageNumberPagination
from django.db.models        import Q, Count

from ngo.models import NGO, ServiceType, Organizer
from .serializers import (
    NGOListSerializer, NGODetailSerializer, NGOWriteSerializer,
    ServiceTypeSerializer, ServiceTypeWriteSerializer,
    OrganizerSerializer, OrganizerWriteSerializer,
)


# ── Pagination ────────────────────────────────────────────────

class NGOPagination(PageNumberPagination):
    page_size             = 10
    page_size_query_param = "page_size"
    max_page_size         = 100


# ── Helpers ───────────────────────────────────────────────────

def _ngo_queryset():
    return (
        NGO.objects
        .select_related("serviceType", "organizer")
        .order_by("service_date", "start_time")
    )


def _success(data=None, message="", status_code=status.HTTP_200_OK):
    body = {"success": True}
    if message:
        body["message"] = message
    if data is not None:
        body["data"] = data
    return Response(body, status=status_code)


def _error(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    body = {"success": False, "message": message}
    if errors:
        body["errors"] = errors
    return Response(body, status=status_code)


# ── NGO CRUD ──────────────────────────────────────────────────

class NGOListCreateView(APIView):
    """
    GET  /api/v1/ngos/  → list all NGOs (paginated, filterable)
    POST /api/v1/ngos/  → create a new NGO
    Topic 7.3b — Admin only
    Topic 9.2a — Uses Redis cache for unfiltered GET
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        # use cache for unfiltered requests
        search        = request.query_params.get("search", "").strip()
        status_filter = request.query_params.get("status", "").strip()
        date_from     = request.query_params.get("date_from", "").strip()
        date_to       = request.query_params.get("date_to", "").strip()
        location      = request.query_params.get("location", "").strip()
        service_type  = request.query_params.get("service_type", "").strip()

        has_filters = any([search, status_filter, date_from, date_to, location, service_type])

        if not has_filters:
            from ngo_admin.services.admindashboard import get_all_ngos
            ngos = get_all_ngos()
        else:
            qs = _ngo_queryset()
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

        # status filter in Python (uses model properties)
        if status_filter == "open":
            ngos = [n for n in ngos if not n.is_full and not n.is_closed and n.is_active]
        elif status_filter == "full":
            ngos = [n for n in ngos if n.is_full]
        elif status_filter == "almost":
            ngos = [n for n in ngos if not n.is_full and n.available_slots <= n.max_slots * 0.5 and n.is_active]
        elif status_filter == "closed":
            ngos = [n for n in ngos if n.is_closed]
        elif status_filter == "inactive":
            ngos = [n for n in ngos if not n.is_active]

        paginator  = NGOPagination()
        page       = paginator.paginate_queryset(ngos, request)
        serializer = NGOListSerializer(page, many=True)

        return Response({
            "success": True,
            "data": {
                "count":    paginator.page.paginator.count,
                "next":     paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "results":  serializer.data,
            }
        })

    def post(self, request):
        serializer = NGOWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return _error("Validation failed.", errors=serializer.errors,
                          status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        ngo = serializer.save()
        # invalidate cache after create
        from ngo_admin.services.admindashboard import invalidate_ngo_cache
        invalidate_ngo_cache()
        return _success(
            data=NGODetailSerializer(ngo).data,
            message="NGO created successfully.",
            status_code=status.HTTP_201_CREATED,
        )


class NGODetailView(APIView):
    """
    GET/PUT/PATCH/DELETE /api/v1/ngos/<id>/
    Topic 7.3b — Admin only
    """
    permission_classes = [IsAdminUser]

    def _get_ngo(self, ngo_id):
        try:
            return _ngo_queryset().get(pk=ngo_id)
        except NGO.DoesNotExist:
            return None

    def get(self, request, ngo_id):
        ngo = self._get_ngo(ngo_id)
        if not ngo:
            return _error("NGO not found.", status_code=status.HTTP_404_NOT_FOUND)
        return _success(data=NGODetailSerializer(ngo).data)

    def put(self, request, ngo_id):
        ngo = self._get_ngo(ngo_id)
        if not ngo:
            return _error("NGO not found.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = NGOWriteSerializer(ngo, data=request.data)
        if not serializer.is_valid():
            return _error("Validation failed.", errors=serializer.errors,
                          status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        updated = serializer.save()
        from ngo_admin.services.admindashboard import invalidate_ngo_cache
        invalidate_ngo_cache()
        return _success(data=NGODetailSerializer(updated).data, message="NGO updated successfully.")

    def patch(self, request, ngo_id):
        ngo = self._get_ngo(ngo_id)
        if not ngo:
            return _error("NGO not found.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = NGOWriteSerializer(ngo, data=request.data, partial=True)
        if not serializer.is_valid():
            return _error("Validation failed.", errors=serializer.errors,
                          status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        updated = serializer.save()
        from ngo_admin.services.admindashboard import invalidate_ngo_cache
        invalidate_ngo_cache()
        return _success(data=NGODetailSerializer(updated).data, message="NGO updated successfully.")

    def delete(self, request, ngo_id):
        ngo = self._get_ngo(ngo_id)
        if not ngo:
            return _error("NGO not found.", status_code=status.HTTP_404_NOT_FOUND)
        ngo.delete()
        from ngo_admin.services.admindashboard import invalidate_ngo_cache
        invalidate_ngo_cache()
        return _success(message="NGO deleted successfully.")


class NGOToggleActiveView(APIView):
    """PATCH /api/v1/ngos/<id>/toggle-active/"""
    permission_classes = [IsAdminUser]

    def patch(self, request, ngo_id):
        try:
            ngo = _ngo_queryset().get(pk=ngo_id)
        except NGO.DoesNotExist:
            return _error("NGO not found.", status_code=status.HTTP_404_NOT_FOUND)

        ngo.is_active = not ngo.is_active
        ngo.save(update_fields=["is_active"])
        from ngo_admin.services.admindashboard import invalidate_ngo_cache
        invalidate_ngo_cache()
        state = "activated" if ngo.is_active else "deactivated"
        return _success(
            data={"id": ngo.id, "is_active": ngo.is_active},
            message=f"NGO {state} successfully.",
        )


class NGODashboardView(APIView):
    """GET /api/v1/ngos/dashboard/"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from ngo_admin.services.admindashboard import get_dashboard_stats
        return _success(data=get_dashboard_stats())


# ── ServiceType CRUD ──────────────────────────────────────────

class ServiceTypeListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        types = ServiceType.objects.all().order_by("name")
        return _success(data=ServiceTypeSerializer(types, many=True).data)

    def post(self, request):
        serializer = ServiceTypeWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return _error("Validation failed.", errors=serializer.errors,
                          status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        st = serializer.save()
        return _success(data=ServiceTypeSerializer(st).data, message="Service type created.",
                        status_code=status.HTTP_201_CREATED)


class ServiceTypeDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get(self, pk):
        try:
            return ServiceType.objects.get(pk=pk)
        except ServiceType.DoesNotExist:
            return None

    def get(self, request, pk):
        st = self._get(pk)
        if not st:
            return _error("Service type not found.", status_code=status.HTTP_404_NOT_FOUND)
        return _success(data=ServiceTypeSerializer(st).data)

    def put(self, request, pk):
        st = self._get(pk)
        if not st:
            return _error("Service type not found.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = ServiceTypeWriteSerializer(st, data=request.data)
        if not serializer.is_valid():
            return _error("Validation failed.", errors=serializer.errors,
                          status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        updated = serializer.save()
        return _success(data=ServiceTypeSerializer(updated).data, message="Service type updated.")

    def delete(self, request, pk):
        st = self._get(pk)
        if not st:
            return _error("Service type not found.", status_code=status.HTTP_404_NOT_FOUND)
        if st.ngo_set.exists():
            return _error(f'Cannot delete "{st.name}" — it is used by existing NGOs.',
                          status_code=status.HTTP_409_CONFLICT)
        st.delete()
        return _success(message="Service type deleted.")


# ── Organizer CRUD ────────────────────────────────────────────

class OrganizerListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        organizers = Organizer.objects.all().order_by("company_name")
        return _success(data=OrganizerSerializer(organizers, many=True).data)

    def post(self, request):
        serializer = OrganizerWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return _error("Validation failed.", errors=serializer.errors,
                          status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        org = serializer.save()
        return _success(data=OrganizerSerializer(org).data, message="Organizer created.",
                        status_code=status.HTTP_201_CREATED)


class OrganizerDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get(self, pk):
        try:
            return Organizer.objects.get(pk=pk)
        except Organizer.DoesNotExist:
            return None

    def get(self, request, pk):
        org = self._get(pk)
        if not org:
            return _error("Organizer not found.", status_code=status.HTTP_404_NOT_FOUND)
        return _success(data=OrganizerSerializer(org).data)

    def put(self, request, pk):
        org = self._get(pk)
        if not org:
            return _error("Organizer not found.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = OrganizerWriteSerializer(org, data=request.data)
        if not serializer.is_valid():
            return _error("Validation failed.", errors=serializer.errors,
                          status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        updated = serializer.save()
        return _success(data=OrganizerSerializer(updated).data, message="Organizer updated.")

    def patch(self, request, pk):
        org = self._get(pk)
        if not org:
            return _error("Organizer not found.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = OrganizerWriteSerializer(org, data=request.data, partial=True)
        if not serializer.is_valid():
            return _error("Validation failed.", errors=serializer.errors,
                          status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        updated = serializer.save()
        return _success(data=OrganizerSerializer(updated).data, message="Organizer updated.")

    def delete(self, request, pk):
        org = self._get(pk)
        if not org:
            return _error("Organizer not found.", status_code=status.HTTP_404_NOT_FOUND)
        org.delete()
        return _success(message="Organizer deleted.")