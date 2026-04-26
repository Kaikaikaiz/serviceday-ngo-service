import time
from django.core.cache import cache
from django.utils import timezone

NGO_EMPLOYEE_CACHE_KEY = 'ngo:employee_list'


def benchmark_ngo_cache():
    """
    Measures DB query time vs Redis cache hit time.

    Returns:
    {
        "db_query_ms":  15.2,
        "cache_hit_ms":  0.4,
        "speedup_x":    38.0,
        "improvement_percent": "97.4%",
        "db_queries_before": 1,
        "db_queries_after": 0,
        "record_count": 24,
        "cache_ttl_seconds": 300,
        "note": "Cache is ~38x faster than a DB query"
    }
    """
    from ngo.models import NGO

    now = timezone.now()

    def _base_queryset():
        return (
            NGO.objects
            .filter(is_active=True, cutoff_datetime__gt=now)
            .select_related('serviceType', 'organizer')
            .order_by('name')
            # ← removed .annotate(registered_count=Count('registration'))
            #   registration lives in a separate service
        )

    # ── BEFORE: cold DB query (cache cleared) ─────────────────
    cache.delete(NGO_EMPLOYEE_CACHE_KEY)

    t0   = time.perf_counter()
    data = list(_base_queryset())
    db_ms = round((time.perf_counter() - t0) * 1000, 3)

    # ── AFTER: warm the cache then measure retrieval ───────────
    cache.set(NGO_EMPLOYEE_CACHE_KEY, data, timeout=300)

    t1 = time.perf_counter()
    cache.get(NGO_EMPLOYEE_CACHE_KEY)
    cache_ms = round((time.perf_counter() - t1) * 1000, 3)

    # ── Summary ────────────────────────────────────────────────
    speedup     = round(db_ms / max(cache_ms, 0.001), 1)
    improvement = round(((db_ms - cache_ms) / max(db_ms, 0.001)) * 100, 1)

    return {
        'db_query_ms':         db_ms,
        'cache_hit_ms':        cache_ms,
        'time_saved_ms':       round(db_ms - cache_ms, 3),
        'speedup_x':           speedup,
        'improvement_percent': f'{improvement}%',
        'db_queries_before':   1,
        'db_queries_after':    0,
        'record_count':        len(data),
        'cache_ttl_seconds':   300,
        'note':                f'Cache is ~{speedup}x faster than a DB query',
    }