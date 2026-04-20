"""
Shows all info employees need to choose an activity.
"""

from rest_framework import serializers
from django.utils import timezone
from ngo.models import NGO, ServiceType, Organizer


class ServiceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ServiceType
        fields = ['id', 'name']


class OrganizerSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Organizer
        fields = ['id', 'company_name', 'description']


class NGOEmployeeListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for activity list.
    Shows: name, location, date, time, slots, status.
    """
    serviceType     = ServiceTypeSerializer(read_only=True)
    organizer       = OrganizerSerializer(read_only=True)
    available_slots = serializers.IntegerField(read_only=True)
    status          = serializers.SerializerMethodField()

    class Meta:
        model  = NGO
        fields = [
            'id', 'name', 'description', 'serviceType', 'organizer',
            'location', 'service_date', 'start_time', 'end_time',
            'max_slots', 'available_slots',
            'cutoff_datetime', 'status', 'is_active',
        ]

    def get_status(self, obj):
        if timezone.now() > obj.cutoff_datetime:
            return 'closed'
        if obj.is_full:
            return 'full'
        if obj.available_slots <= obj.max_slots * 0.5:
            return 'almost_full'
        return 'open'


class NGOEmployeeDetailSerializer(NGOEmployeeListSerializer):
    """Full detail for single activity view."""
    class Meta(NGOEmployeeListSerializer.Meta):
        pass