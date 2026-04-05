import pytest


@pytest.fixture(autouse=True)
def reset_embedder_model_cache():
    """Clear the module-level model cache before each test for isolation."""
    try:
        import rag.embedder as embedder_mod
        embedder_mod._model_cache.clear()
    except Exception:
        pass
    yield
