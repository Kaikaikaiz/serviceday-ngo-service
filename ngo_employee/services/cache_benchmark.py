import time
from django.core.cache import cache

NGO_EMPLOYEE_CACHE_KEY = 'ngo:employee_list'


def benchmark_ngo_cache():
    """
    Measures DB query time vs Redis cache hit time.

    Example result:
    {
        "db_query_ms":  15.2,
        "cache_hit_ms":  0.4,
        "speedup_x":    38.0,
        "note": "Cache is ~38x faster than a DB query"
    }
    """
    from ngo.models import NGO
    from django.db.models import Count
    from django.utils import timezone

    now = timezone.now()

    # ── BEFORE: cold DB query (no cache) ─────────────────────
    cache.delete(NGO_EMPLOYEE_CACHE_KEY)
    t0 = time.perf_counter()
    list(
        NGO.objects
        .filter(is_active=True, cutoff_datetime__gt=now)
        .select_related('serviceType', 'organizer')
        .annotate(registered_count=Count('registration'))
        .order_by('name')
    )
    db_ms = round((time.perf_counter() - t0) * 1000, 3)

    # ── AFTER: warm cache hit ─────────────────────────────────
    cached = list(
        NGO.objects
        .filter(is_active=True, cutoff_datetime__gt=now)
        .select_related('serviceType', 'organizer')
        .annotate(registered_count=Count('registration'))
        .order_by('name')
    )
    cache.set(NGO_EMPLOYEE_CACHE_KEY, cached, 300)

    t1       = time.perf_counter()
    cache.get(NGO_EMPLOYEE_CACHE_KEY)
    cache_ms = round((time.perf_counter() - t1) * 1000, 3)

    speedup = round(db_ms / max(cache_ms, 0.001), 1)

    return {
        'db_query_ms':  db_ms,
        'cache_hit_ms': cache_ms,
        'speedup_x':    speedup,
        'note':         f'Cache is ~{speedup}x faster than a DB query',
    }