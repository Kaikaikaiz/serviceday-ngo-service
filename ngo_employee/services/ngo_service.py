"""
Topic 9.2a — Cache employee NGO listing using Redis.
"""

import time
import logging
from django.core.cache import cache
from django.db.models import Count

logger = logging.getLogger(__name__)

NGO_EMPLOYEE_CACHE_KEY     = 'ngo:employee_list'
NGO_EMPLOYEE_CACHE_TIMEOUT = 60 * 5   # 5 minutes


class NGOService:

    @staticmethod
    def get_all_ngo_list_active():
        """
        Topic 9.2a — Returns Redis-cached NGO list for employee dashboard.
        Cache key: ngo:employee_list (5 minute TTL)
        Falls back to DB on cache miss.
        """
        from django.utils import timezone
        from ngo.models import NGO

        cached_ngos = cache.get(NGO_EMPLOYEE_CACHE_KEY)

        if cached_ngos is None:
            # cache miss — query DB and save to Redis
            t_start     = time.perf_counter()
            now         = timezone.now()
            cached_ngos = list(
                NGO.objects
                .filter(is_active=True, cutoff_datetime__gt=now)
                .select_related('serviceType', 'organizer')
                .annotate(registered_count=Count('registration'))
                .order_by('name')
            )
            t_end  = time.perf_counter()
            db_ms  = round((t_end - t_start) * 1000, 2)
            cache.set(NGO_EMPLOYEE_CACHE_KEY, cached_ngos, NGO_EMPLOYEE_CACHE_TIMEOUT)
            logger.info(f"[CACHE MISS] Employee NGO list — DB took {db_ms}ms, saved to Redis")
        else:
            logger.info("[CACHE HIT] Employee NGO list — served from Redis")

        return cached_ngos

    @staticmethod
    def invalidate_cache():
        """Call this when NGO data changes."""
        cache.delete(NGO_EMPLOYEE_CACHE_KEY)