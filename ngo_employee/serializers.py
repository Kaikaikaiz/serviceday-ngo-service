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
    serviceType         = ServiceTypeSerializer(read_only=True)
    organizer           = OrganizerSerializer(read_only=True)
    slots_taken         = serializers.SerializerMethodField()    # ← add
    available_slots     = serializers.SerializerMethodField()    # ← change
    slots_taken_percent = serializers.SerializerMethodField()    # ← add
    status              = serializers.SerializerMethodField()
    is_full             = serializers.SerializerMethodField()    # ← add
    is_closed           = serializers.SerializerMethodField()    # ← add

    class Meta:
        model  = NGO
        fields = [
            'id', 'name', 'description', 'serviceType', 'organizer',
            'location', 'service_date', 'start_time', 'end_time',
            'max_slots', 'slots_taken', 'available_slots',
            'slots_taken_percent', 'cutoff_datetime',
            'status', 'is_active', 'is_full', 'is_closed',
        ]

    def _get_taken(self, obj):
        counts = self.context.get('registration_counts', {})
        return counts.get(str(obj.id), counts.get(obj.id, 0))

    def get_slots_taken(self, obj):
        return self._get_taken(obj)

    def get_available_slots(self, obj):
        taken = self._get_taken(obj)
        return max(obj.max_slots - taken, 0)

    def get_slots_taken_percent(self, obj):
        taken = self._get_taken(obj)
        if obj.max_slots == 0:
            return 0
        return round((taken / obj.max_slots) * 100)

    def get_is_full(self, obj):
        taken = self._get_taken(obj)
        return taken >= obj.max_slots

    def get_is_closed(self, obj):
        return timezone.now() > obj.cutoff_datetime

    def get_status(self, obj):
        taken = self._get_taken(obj)
        available = max(obj.max_slots - taken, 0)

        if timezone.now() > obj.cutoff_datetime:
            return 'closed'
        if taken >= obj.max_slots:
            return 'full'
        if available <= obj.max_slots * 0.5:
            return 'almost_full'
        return 'open'


class NGOEmployeeDetailSerializer(NGOEmployeeListSerializer):
    """Full detail for single activity view."""
    class Meta(NGOEmployeeListSerializer.Meta):
        pass