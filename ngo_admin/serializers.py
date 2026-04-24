"""
ngo_admin/serializers.py
Copied from monolithic ngo/api/serializers.py — admin serializers only.
"""

from rest_framework import serializers
from django.utils import timezone
from ngo.models import NGO, ServiceType, Organizer


class ServiceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ServiceType
        fields = ["id", "name"]


class OrganizerSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Organizer
        fields = ["id", "company_name", "description"]


class NGOListSerializer(serializers.ModelSerializer):
    serviceType         = ServiceTypeSerializer(read_only=True)
    organizer           = OrganizerSerializer(read_only=True)
    slots_taken         = serializers.SerializerMethodField()
    available_slots     = serializers.SerializerMethodField()
    slots_taken_percent = serializers.SerializerMethodField()
    is_full             = serializers.SerializerMethodField()
    is_closed           = serializers.SerializerMethodField()
    status              = serializers.SerializerMethodField()

    class Meta:
        model  = NGO
        fields = [
            "id", "name", "location", "description", "service_date",
            "start_time", "end_time", "max_slots", "slots_taken",
            "available_slots", "slots_taken_percent", "is_full", "is_closed",
            "is_active", "cutoff_datetime", "serviceType", "organizer",
            "created_at", "status",
        ]

    def _get_taken(self, obj):
        counts = self.context.get('registration_counts', {})
        return counts.get(str(obj.id), counts.get(obj.id, 0))

    def get_slots_taken(self, obj):
        return self._get_taken(obj)

    def get_available_slots(self, obj):
        return max(obj.max_slots - self._get_taken(obj), 0)

    def get_slots_taken_percent(self, obj):
        taken = self._get_taken(obj)
        if obj.max_slots == 0:
            return 0
        return round((taken / obj.max_slots) * 100)

    def get_is_full(self, obj):
        return self._get_taken(obj) >= obj.max_slots

    def get_is_closed(self, obj):
        return timezone.now() > obj.cutoff_datetime

    def get_status(self, obj):
        taken     = self._get_taken(obj)
        available = max(obj.max_slots - taken, 0)
        if not obj.is_active:
            return "inactive"
        if timezone.now() > obj.cutoff_datetime:
            return "closed"
        if taken >= obj.max_slots:
            return "full"
        if available <= obj.max_slots * 0.5:
            return "almost_full"
        return "open"


class NGODetailSerializer(NGOListSerializer):
    class Meta(NGOListSerializer.Meta):
        fields = NGOListSerializer.Meta.fields + ["description"]


class NGOWriteSerializer(serializers.ModelSerializer):
    serviceType  = serializers.PrimaryKeyRelatedField(queryset=ServiceType.objects.all())
    organizer    = serializers.PrimaryKeyRelatedField(
        queryset=Organizer.objects.all(), required=False, allow_null=True
    )
    cutoff_date  = serializers.DateField(write_only=True)
    cutoff_time  = serializers.TimeField(write_only=True, format="%H:%M")

    class Meta:
        model  = NGO
        fields = [
            "name", "description", "serviceType", "organizer",
            "location", "service_date", "start_time", "end_time",
            "max_slots", "cutoff_date", "cutoff_time", "is_active",
        ]

    def validate_max_slots(self, value):
        if value < 1:
            raise serializers.ValidationError("Max slots must be at least 1.")
        return value

    def validate_service_date(self, value):
        if value < timezone.now().date():
            raise serializers.ValidationError("Service date cannot be in the past.")
        return value

    def validate(self, data):
        start = data.get("start_time")
        end   = data.get("end_time")
        if start and end and start >= end:
            raise serializers.ValidationError({"end_time": "End time must be later than start time."})

        cutoff_date  = data.get("cutoff_date")
        cutoff_time  = data.get("cutoff_time")
        service_date = data.get("service_date")

        if cutoff_date and cutoff_time:
            from datetime import datetime as dt
            naive_cutoff        = dt.combine(cutoff_date, cutoff_time)
            cutoff_aware        = timezone.make_aware(naive_cutoff)
            data["cutoff_datetime"] = cutoff_aware

            if service_date and cutoff_date >= service_date:
                raise serializers.ValidationError(
                    {"cutoff_date": "Registration cut-off must be before the service date."}
                )

        instance = self.instance
        if instance and "max_slots" in data:
            if data["max_slots"] < instance.slots_taken:
                raise serializers.ValidationError(
                    {"max_slots": (
                        f"Cannot reduce max slots to {data['max_slots']}: "
                        f"{instance.slots_taken} employee(s) are already registered."
                    )}
                )
        return data

    def create(self, validated_data):
        validated_data.pop("cutoff_date", None)
        validated_data.pop("cutoff_time", None)
        return NGO.objects.create(**validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("cutoff_date", None)
        validated_data.pop("cutoff_time", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.full_clean()
        instance.save()
        return instance


class ServiceTypeWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ServiceType
        fields = ["name"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Service type name cannot be empty.")
        qs = ServiceType.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f'"{value}" already exists.')
        return value


class OrganizerWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Organizer
        fields = ["company_name", "description"]

    def validate_company_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Company name is required.")
        qs = Organizer.objects.filter(company_name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f'"{value}" already exists.')
        return value