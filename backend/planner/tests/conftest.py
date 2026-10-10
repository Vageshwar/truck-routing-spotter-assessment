import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_cache():
    # routing and weather results are cached; keep tests independent
    cache.clear()
    yield
    cache.clear()
