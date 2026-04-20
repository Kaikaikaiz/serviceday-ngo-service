from django.urls import path
from . import views

# mounted at /api/v1/ in ngo_service/urls.py
urlpatterns = [
    path('activities/',            views.activity_list,    name='api-activity-list'),
    path('activities/benchmark/',  views.cache_benchmark,  name='api-cache-benchmark'),
    path('activities/<int:pk>/',   views.activity_detail,  name='api-activity-detail'),
]