from django.urls import path
from .views import (
    NGOListCreateView,
    NGODetailView,
    NGOToggleActiveView,
    NGODashboardView,
    ServiceTypeListCreateView,
    ServiceTypeDetailView,
    OrganizerListCreateView,
    OrganizerDetailView,
)

# mounted at /api/v1/ in ngo_service/urls.py
urlpatterns = [
    # ── Dashboard ──────────────────────────────────────
    path("ngos/dashboard/",                  NGODashboardView.as_view(),          name="api-ngo-dashboard"),

    # ── NGO CRUD ───────────────────────────────────────
    path("ngos/",                            NGOListCreateView.as_view(),         name="api-ngo-list-create"),
    path("ngos/<int:ngo_id>/",               NGODetailView.as_view(),             name="api-ngo-detail"),
    path("ngos/<int:ngo_id>/toggle-active/", NGOToggleActiveView.as_view(),       name="api-ngo-toggle-active"),

    # ── Service Types ──────────────────────────────────
    path("service-types/",                   ServiceTypeListCreateView.as_view(), name="api-service-type-list"),
    path("service-types/<int:pk>/",          ServiceTypeDetailView.as_view(),     name="api-service-type-detail"),

    # ── Organizers ─────────────────────────────────────
    path("organizers/",                      OrganizerListCreateView.as_view(),   name="api-organizer-list"),
    path("organizers/<int:pk>/",             OrganizerDetailView.as_view(),       name="api-organizer-detail"),
]