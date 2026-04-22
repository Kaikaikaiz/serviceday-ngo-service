from django.db import models
from django.utils import timezone


class ServiceType(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Organizer(models.Model):
    company_name = models.CharField(max_length=100)
    description  = models.TextField()

    def __str__(self):
        return self.company_name


class NGO(models.Model):
    name            = models.CharField(max_length=100)
    description     = models.TextField()
    serviceType     = models.ForeignKey(ServiceType, on_delete=models.CASCADE)
    organizer       = models.ForeignKey(
        Organizer,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='ngos'
    )
    location        = models.CharField(max_length=100)
    service_date    = models.DateField()
    start_time      = models.TimeField()
    end_time        = models.TimeField()
    max_slots       = models.IntegerField()
    cutoff_datetime = models.DateTimeField()
    is_active       = models.BooleanField(default=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def slots_taken(self):
        return getattr(self, 'registered_count', 0)

    @property
    def available_slots(self):
        return max(self.max_slots - self.slots_taken, 0)

    @property
    def is_full(self):
        return self.available_slots == 0

    @property
    def is_closed(self):
        return timezone.now() > self.cutoff_datetime

    @property
    def slots_taken_percent(self):
        if self.max_slots == 0:
            return 0
        taken = self.max_slots - self.available_slots
        return round((taken / self.max_slots) * 100)

    @property
    def is_ended(self):
        now       = timezone.now()
        event_end = timezone.datetime.combine(
            self.service_date,
            self.end_time,
            tzinfo=now.tzinfo
        )
        return now >= event_end