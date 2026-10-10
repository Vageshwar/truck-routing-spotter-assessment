"""Tiny wrapper around Django's cache for results from outside services.

The free routing and weather servers ask for fair use, and the same search is
often repeated (page reloads, the demo), so we keep answers for a while.
"""

import hashlib
import json
from collections.abc import Callable

from django.core.cache import cache


def cached[T](namespace: str, key_data: object, ttl_s: int, compute: Callable[[], T]) -> T:
    digest = hashlib.sha1(json.dumps(key_data, sort_keys=True, default=str).encode()).hexdigest()
    key = f"planner:{namespace}:{digest}"
    value = cache.get(key)
    if value is None:
        value = compute()
        cache.set(key, value, ttl_s)
    return value
