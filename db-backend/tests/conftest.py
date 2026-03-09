import pytest

from app.algorithms.cfkg.inference import clear_model_cache
from app.algorithms.cfkg.reranker import clear_reranker_cache
from app.recommendation_cache import clear_all_recommendation_caches


@pytest.fixture(autouse=True)
def clear_recommendation_state():
    clear_all_recommendation_caches()
    clear_model_cache()
    clear_reranker_cache()
    yield
    clear_all_recommendation_caches()
    clear_model_cache()
    clear_reranker_cache()
