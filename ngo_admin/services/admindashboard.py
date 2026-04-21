"""
ngo_admin/services/admindashboard.py
Topic 9.2a — Redis cache for admin NGO listing.
Copied from monolithic and adapted for microservice.
"""

from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.cache import cache
from datetime import datetime
import time
import logging

from ngo.models import NGO, ServiceType, Organizer
from django.shortcuts import get_object_or_404

logger = logging.getLogger(__name__)

NGO_ADMIN_CACHE_KEY     = 'ngo:admin_list'
NGO_ADMIN_CACHE_TIMEOUT = 60 * 5   # 5 minutes


# ── Cache ─────────────────────────────────────────────────────

def invalidate_ngo_cache():
    cache.delete(NGO_ADMIN_CACHE_KEY)
    cache.delete('ngo:employee_list')


# ── READ ──────────────────────────────────────────────────────

def get_all_ngos(search="", status_filter=""):
    cached_ngos = cache.get(NGO_ADMIN_CACHE_KEY)

    if cached_ngos is None:
        t_start     = time.perf_counter()
        cached_ngos = list(
            NGO.objects
            .select_related("serviceType", "organizer")
            .order_by("service_date", "start_time")
        )
        t_end  = time.perf_counter()
        db_ms  = round((t_end - t_start) * 1000, 2)
        cache.set(NGO_ADMIN_CACHE_KEY, cached_ngos, NGO_ADMIN_CACHE_TIMEOUT)
        logger.info(f"[CACHE MISS] Admin NGO list — DB took {db_ms}ms, saved to Redis")
    else:
        logger.info("[CACHE HIT] Admin NGO list — served from Redis")

    ngos = cached_ngos

    if search:
        search_lower = search.lower()
        ngos = [n for n in ngos if search_lower in n.name.lower() or search_lower in n.location.lower()]

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

    return ngos


def get_dashboard_stats():
    all_ngos = list(NGO.objects.all())

    total_ngos          = len(all_ngos)
    open_count          = sum(1 for n in all_ngos if not n.is_full and not n.is_closed and n.is_active)
    total_registrations = sum(n.slots_taken for n in all_ngos)
    total_max           = sum(n.max_slots for n in all_ngos)
    fill_pct            = round(total_registrations / total_max * 100, 1) if total_max > 0 else 0.0

    return {
        "total_ngos":          total_ngos,
        "open_count":          open_count,
        "total_registrations": total_registrations,
        "fill_pct":            fill_pct,
    }


def get_ngo_or_404(ngo_id):
    return get_object_or_404(
        NGO.objects.select_related("serviceType", "organizer"),
        pk=ngo_id
    )


def get_all_service_types():
    return list(ServiceType.objects.all().order_by("name"))


# ── CREATE ────────────────────────────────────────────────────

def create_ngo(data):
    cleaned      = _parse_form_data(data)
    _validate_ngo_data(cleaned)
    service_type = _get_service_type(cleaned["serviceType_id"])

    organizer = None
    if cleaned["organizer_id"]:
        try:
            organizer = Organizer.objects.get(pk=cleaned["organizer_id"])
        except Organizer.DoesNotExist:
            pass

    ngo = NGO(
        name            = cleaned["name"],
        description     = cleaned["description"],
        serviceType     = service_type,
        organizer       = organizer,
        location        = cleaned["location"],
        service_date    = cleaned["service_date"],
        start_time      = cleaned["start_time"],
        end_time        = cleaned["end_time"],
        max_slots       = cleaned["max_slots"],
        cutoff_datetime = cleaned["cutoff_datetime"],
        is_active       = cleaned["is_active"],
    )
    ngo.full_clean()
    ngo.save()
    invalidate_ngo_cache()
    return ngo


def create_service_type(name):
    name = name.strip()
    if not name:
        raise ValidationError("Service type name cannot be empty.")
    if ServiceType.objects.filter(name__iexact=name).exists():
        raise ValidationError(f'"{name}" already exists.')
    return ServiceType.objects.create(name=name)


# ── UPDATE ────────────────────────────────────────────────────

def update_ngo(ngo_id, data):
    ngo     = get_ngo_or_404(ngo_id)
    cleaned = _parse_form_data(data)
    _validate_ngo_data(cleaned)

    organizer = None
    if cleaned["organizer_id"]:
        try:
            organizer = Organizer.objects.get(pk=cleaned["organizer_id"])
        except Organizer.DoesNotExist:
            pass

    if cleaned["max_slots"] < ngo.slots_taken:
        raise ValidationError(
            f"Cannot reduce max slots to {cleaned['max_slots']}: "
            f"{ngo.slots_taken} employee(s) are already registered."
        )

    service_type        = _get_service_type(cleaned["serviceType_id"])
    ngo.name            = cleaned["name"]
    ngo.description     = cleaned["description"]
    ngo.serviceType     = service_type
    ngo.organizer       = organizer
    ngo.location        = cleaned["location"]
    ngo.service_date    = cleaned["service_date"]
    ngo.start_time      = cleaned["start_time"]
    ngo.end_time        = cleaned["end_time"]
    ngo.max_slots       = cleaned["max_slots"]
    ngo.cutoff_datetime = cleaned["cutoff_datetime"]
    ngo.is_active       = cleaned["is_active"]

    ngo.full_clean()
    ngo.save()
    invalidate_ngo_cache()
    return ngo


def toggle_ngo_active(ngo_id):
    ngo           = get_ngo_or_404(ngo_id)
    ngo.is_active = not ngo.is_active
    ngo.save(update_fields=["is_active"])
    invalidate_ngo_cache()
    return ngo


# ── DELETE ────────────────────────────────────────────────────

def delete_ngo(ngo_id):
    ngo = get_ngo_or_404(ngo_id)
    ngo.delete()
    invalidate_ngo_cache()


def delete_service_type(pk):
    st = get_object_or_404(ServiceType, pk=pk)
    if st.ngo_set.exists():
        raise ValidationError(f'Cannot delete "{st.name}" — it is used by existing NGOs.')
    st.delete()
    return st


# ── TEMPLATE HELPERS ──────────────────────────────────────────

def get_ngo_status(ngo):
    if not ngo.is_active:
        return "Inactive"
    if ngo.is_closed:
        return "Closed"
    if ngo.is_full:
        return "Full"
    if ngo.available_slots <= ngo.max_slots * 0.5:
        return "Almost Full"
    return "Open"


def get_slots_fill_pct(ngo):
    if ngo.max_slots == 0:
        return 0
    return min(100, round(ngo.slots_taken / ngo.max_slots * 100))


# ── PRIVATE HELPERS ───────────────────────────────────────────

def _parse_form_data(data):
    cutoff_date_str = data.get("cutoff_date", "").strip()
    cutoff_time_str = data.get("cutoff_time", "").strip()

    cutoff_datetime = None
    if cutoff_date_str and cutoff_time_str:
        try:
            naive           = datetime.strptime(f"{cutoff_date_str} {cutoff_time_str}", "%Y-%m-%d %H:%M")
            cutoff_datetime = timezone.make_aware(naive)
        except ValueError:
            pass

    return {
        "name":            data.get("name", "").strip(),
        "description":     data.get("description", "").strip(),
        "serviceType_id":  data.get("serviceType", "").strip(),
        "organizer_id":    data.get("organizer", "").strip(),
        "location":        data.get("location", "").strip(),
        "service_date":    data.get("service_date", "").strip(),
        "start_time":      data.get("start_time", "").strip(),
        "end_time":        data.get("end_time", "").strip(),
        "max_slots":       data.get("max_slots", "").strip(),
        "cutoff_datetime": cutoff_datetime,
        "is_active":       data.get("is_active") == "1",
    }


def _get_service_type(service_type_id):
    try:
        return ServiceType.objects.get(pk=service_type_id)
    except (ServiceType.DoesNotExist, ValueError):
        raise ValidationError("Selected service type does not exist.")


def _validate_ngo_data(cleaned):
    required = {
        "name":            "NGO name",
        "serviceType_id":  "Service type",
        "location":        "Location",
        "service_date":    "Service date",
        "start_time":      "Start time",
        "end_time":        "End time",
        "max_slots":       "Max slots",
        "cutoff_datetime": "Registration cutoff date and time",
    }
    for field, label in required.items():
        if not cleaned.get(field):
            raise ValidationError(f"{label} is required.")

    try:
        max_slots = int(cleaned["max_slots"])
    except (ValueError, TypeError):
        raise ValidationError("Max slots must be a whole number.")
    if max_slots < 1:
        raise ValidationError("Max slots must be at least 1.")

    cleaned["max_slots"] = max_slots

    if cleaned["start_time"] >= cleaned["end_time"]:
        raise ValidationError("End time must be later than start time.")

    if cleaned["service_date"] < timezone.now().date().isoformat():
        raise ValidationError("Service date cannot be in the past.")

    cutoff      = cleaned["cutoff_datetime"]
    service_str = cleaned["service_date"] if isinstance(cleaned["service_date"], str) \
                  else cleaned["service_date"].isoformat()

    if cutoff.date().isoformat() >= service_str[:10]:
        raise ValidationError("Registration cut-off must be before the service date.")


# ── ORGANIZER ─────────────────────────────────────────────────

def get_all_organizers():
    return list(Organizer.objects.all().order_by('company_name'))


def get_organizer_or_404(organizer_id):
    return get_object_or_404(Organizer, pk=organizer_id)


def create_organizer(data):
    company_name = data.get('company_name', '').strip()
    description  = data.get('description', '').strip()

    if not company_name:
        raise ValidationError("Company name is required.")
    if Organizer.objects.filter(company_name__iexact=company_name).exists():
        raise ValidationError(f'"{company_name}" already exists.')

    return Organizer.objects.create(
        company_name=company_name,
        description=description,
    )


def update_organizer(organizer_id, data):
    organizer    = get_organizer_or_404(organizer_id)
    company_name = data.get('company_name', '').strip()
    description  = data.get('description', '').strip()

    if not company_name:
        raise ValidationError("Company name is required.")

    organizer.company_name = company_name
    organizer.description  = description
    organizer.save()
    return organizer


def delete_organizer(organizer_id):
    organizer = get_organizer_or_404(organizer_id)
    organizer.delete()