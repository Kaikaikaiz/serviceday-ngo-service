from django.urls import path
from . import views

urlpatterns = [
    path('ngos/dashboard/',                  views.ngo_dashboard,            name='api-ngo-dashboard'),
    path('ngos/',                            views.ngo_list_create,          name='api-ngo-list-create'),
    path('ngos/<int:ngo_id>/',               views.ngo_detail,               name='api-ngo-detail'),
    path('ngos/<int:ngo_id>/toggle-active/', views.ngo_toggle_active,        name='api-ngo-toggle-active'),
    path('service-types/',                   views.service_type_list_create, name='api-service-type-list'),
    path('service-types/<int:pk>/',          views.service_type_detail,      name='api-service-type-detail'),
    path('organizers/',                      views.organizer_list_create,    name='api-organizer-list'),
    path('organizers/<int:pk>/',             views.organizer_detail,         name='api-organizer-detail'),
]