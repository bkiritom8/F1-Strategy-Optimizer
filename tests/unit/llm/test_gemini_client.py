import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("vertexai")


def _make_client():
    """Return a GeminiClient with a mock RagConfig — bypasses Vertex AI init."""
    from src.llm.gemini_client import GeminiClient

    mock_config = MagicMock()
    mock_config.PROJECT_ID = "f1optimizer"
    mock_config.REGION = "us-central1"
    mock_config.LLM_MODEL = "gemini-2.5-flash"
    mock_config.LLM_TEMPERATURE = 0.2
    mock_config.MAX_OUTPUT_TOKENS = 1024

    client = GeminiClient.__new__(GeminiClient)
    client._config = mock_config
    client._model = None
    client._initialized = False
    return client


# ── build_prompt ────────────────────────────────────────────────────────────

def test_build_prompt_free_form_has_no_race_context():
    """build_prompt with no structured_inputs must not include 'Race Context'."""
    client = _make_client()
    prompt = client.build_prompt("Who should pit first?")
    assert "Race Context" not in prompt
    assert "Who should pit first?" in prompt


def test_build_prompt_with_structured_inputs_includes_race_context():
    """build_prompt with structured_inputs must include labelled race context."""
    client = _make_client()
    inputs = {
        "driver": "Verstappen",
        "circuit": "Monaco",
        "current_lap": 28,
        "total_laps": 78,
        "tire_compound": "MEDIUM",
        "tire_age_laps": 18,
    }
    prompt = client.build_prompt("Should he pit?", structured_inputs=inputs)
    assert "Race Context" in prompt
    assert "Verstappen" in prompt
    assert "Monaco" in prompt
    assert "28" in prompt
    assert "MEDIUM" in prompt


def test_build_prompt_empty_structured_inputs_treated_as_none():
    """build_prompt with empty dict must not include 'Race Context' block."""
    client = _make_client()
    prompt = client.build_prompt("General question", structured_inputs={})
    assert "Race Context" not in prompt


def test_build_prompt_none_values_in_inputs_excluded():
    """build_prompt must skip keys whose values are None."""
    client = _make_client()
    inputs = {"driver": "Hamilton", "circuit": None, "current_lap": None}
    prompt = client.build_prompt("Q?", structured_inputs=inputs)
    assert "Hamilton" in prompt
    assert "None" not in prompt


def test_build_prompt_with_context_docs_includes_context_block():
    """build_prompt with context_docs must include a Context block with doc content."""
    pytest.importorskip("langchain_core")
    from langchain_core.documents import Document

    client = _make_client()
    docs = [Document(page_content="Hamilton won Monaco 2019", metadata={})]
    prompt = client.build_prompt("Who won Monaco?", context_docs=docs)
    assert "Context" in prompt
    assert "Hamilton won Monaco 2019" in prompt


def test_build_prompt_empty_context_docs_no_context_block():
    """build_prompt with empty context_docs must not include Context block."""
    client = _make_client()
    prompt = client.build_prompt("Q?", context_docs=[])
    assert "---" not in prompt


# ── generate ────────────────────────────────────────────────────────────────

def test_generate_calls_model_and_returns_text():
    """generate() must call GenerativeModel.generate_content and return .text."""
    client = _make_client()
    fake_model = MagicMock()
    fake_model.generate_content.return_value.text = "Pit on lap 30."
    client._model = fake_model
    client._initialized = True

    with patch.object(client, "_ensure_initialized"):
        result = client.generate("Should Verstappen pit?")

    assert result == "Pit on lap 30."
    fake_model.generate_content.assert_called_once()


def test_generate_passes_structured_inputs_to_prompt():
    """generate() with structured_inputs must produce a prompt with Race Context."""
    client = _make_client()
    fake_model = MagicMock()
    fake_model.generate_content.return_value.text = "Stay out."
    client._model = fake_model
    client._initialized = True

    captured_prompts = []

    def capture_call(prompt, **kwargs):
        captured_prompts.append(prompt)
        return fake_model.generate_content.return_value

    fake_model.generate_content.side_effect = capture_call

    with patch.object(client, "_ensure_initialized"):
        client.generate("Pit?", structured_inputs={"driver": "Norris", "circuit": "Spa"})

    assert len(captured_prompts) == 1
    assert "Norris" in captured_prompts[0]


# ── get_client singleton ─────────────────────────────────────────────────────

def test_get_client_returns_same_instance():
    """get_client() must return the same GeminiClient singleton on repeated calls."""
    import src.llm.gemini_client as mod

    original = mod._client
    mod._client = None
    try:
        from src.llm.gemini_client import get_client
        c1 = get_client()
        c2 = get_client()
        assert c1 is c2
    finally:
        mod._client = original


# ── /llm/chat endpoint ───────────────────────────────────────────────────────

def _get_token(client):
    r = client.post("/token", data={"username": "admin", "password": "admin"})
    assert r.status_code == 200
    return r.json()["access_token"]


def test_llm_chat_happy_path():
    """POST /llm/chat returns 200 with answer, latency_ms, model fields."""
    from fastapi.testclient import TestClient
    from src.api.main import app
    from src.llm import gemini_client as mod

    fake_client = MagicMock()
    fake_client.generate.return_value = "Pit on lap 30 for hard tyres."
    original = mod._client
    mod._client = fake_client

    try:
        with TestClient(app) as tc:
            token = _get_token(tc)
            r = tc.post(
                "/llm/chat",
                json={"question": "Should Verstappen pit?"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert r.status_code == 200
        data = r.json()
        assert data["answer"] == "Pit on lap 30 for hard tyres."
        assert "latency_ms" in data
        assert "model" in data
    finally:
        mod._client = original


def test_llm_chat_with_race_inputs():
    """POST /llm/chat with race_inputs passes structured dict to generate()."""
    from fastapi.testclient import TestClient
    from src.api.main import app
    from src.llm import gemini_client as mod

    fake_client = MagicMock()
    fake_client.generate.return_value = "Stay out two more laps."
    original = mod._client
    mod._client = fake_client

    try:
        with TestClient(app) as tc:
            token = _get_token(tc)
            r = tc.post(
                "/llm/chat",
                json={
                    "question": "Pit or stay out?",
                    "race_inputs": {
                        "driver": "Norris",
                        "circuit": "Silverstone",
                        "current_lap": 40,
                        "tire_compound": "SOFT",
                    },
                },
                headers={"Authorization": f"Bearer {token}"},
            )
        assert r.status_code == 200
        call_kwargs = fake_client.generate.call_args[1]
        assert call_kwargs["structured_inputs"]["driver"] == "Norris"
    finally:
        mod._client = original


def test_llm_chat_no_auth_returns_401():
    """POST /llm/chat without token returns 401."""
    from fastapi.testclient import TestClient
    from src.api.main import app

    with TestClient(app) as tc:
        r = tc.post("/llm/chat", json={"question": "test"})
    assert r.status_code == 401


def test_llm_chat_empty_question_returns_422():
    """POST /llm/chat with empty string question returns 422."""
    from fastapi.testclient import TestClient
    from src.api.main import app

    with TestClient(app) as tc:
        token = _get_token(tc)
        r = tc.post(
            "/llm/chat",
            json={"question": ""},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 422
