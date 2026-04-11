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
    client._genai_client = None
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


def _make_generate_response(text: str):
    """Build a mock generate_content response with a single text part."""
    part = MagicMock()
    part.text = text
    candidate = MagicMock()
    candidate.content.parts = [part]
    response = MagicMock()
    response.candidates = [candidate]
    return response


def test_generate_calls_model_and_returns_text():
    """generate() must call GenerativeModel.generate_content and return text."""
    client = _make_client()
    fake_genai = MagicMock()
    fake_genai.models.generate_content.return_value = MagicMock(text="Pit on lap 30.")
    client._genai_client = fake_genai
    client._initialized = True

    with patch.object(client, "_ensure_initialized"):
        result = client.generate("Should Verstappen pit?")

    assert result == "Pit on lap 30."
    fake_genai.models.generate_content.assert_called_once()


def test_generate_passes_structured_inputs_to_prompt():
    """generate() with structured_inputs must produce a prompt with Race Context."""
    client = _make_client()
    fake_genai = MagicMock()
    client._genai_client = fake_genai
    client._initialized = True

    captured_prompts = []

    def capture_call(model, contents, config):
        captured_prompts.append(contents)
        return MagicMock(text="Stay out.")

    fake_genai.models.generate_content.side_effect = capture_call

    with patch.object(client, "_ensure_initialized"):
        client.generate(
            "Pit?", structured_inputs={"driver": "Norris", "circuit": "Spa"}
        )

    assert len(captured_prompts) == 1
    assert "Norris" in captured_prompts[0]


# ── generate_with_tools ──────────────────────────────────────────────────────


def _make_text_part(text: str):
    part = MagicMock()
    part.function_call = None
    part.text = text
    return part


def _make_fn_call_part(name: str, args: dict):
    fc = MagicMock()
    fc.name = name
    fc.args = args
    part = MagicMock()
    part.function_call = fc
    return part


def test_generate_with_tools_no_tool_call_returns_text():
    """generate_with_tools returns model text for a non-simulation question (no eager tool call)."""
    client = _make_client()

    text_part = _make_text_part("The safety car plays a huge role in Monaco strategy.")
    response = MagicMock()
    response.candidates = [MagicMock(content=MagicMock(parts=[text_part]))]

    fake_chat = MagicMock()
    fake_chat.send_message.return_value = response

    fake_model = MagicMock()
    fake_model.start_chat.return_value = fake_chat

    executor = MagicMock(return_value={})

    fake_genai = MagicMock()
    fake_genai.chats.create.return_value = fake_chat
    fake_genai.models.generate_content.return_value = MagicMock(
        text="Hamilton would excel in Monaco's tight layout."
    )
    client._genai_client = fake_genai
    client._initialized = True

    with patch.object(client, "_ensure_initialized"):
        result = client.generate_with_tools("Who won Monaco in 1984?", executor)

    assert result == "The safety car plays a huge role in Monaco strategy."
    executor.assert_not_called()


def test_generate_with_tools_simulation_question_calls_executor_eagerly():
    """generate_with_tools eagerly calls tool_executor for what-if/simulation questions."""
    client = _make_client()

    text_part = _make_text_part("Hamilton would excel in Monaco's tight layout.")
    response = MagicMock()
    response.candidates = [MagicMock(content=MagicMock(parts=[text_part]))]

    fake_chat = MagicMock()
    fake_chat.send_message.return_value = response

    fake_model = MagicMock()
    fake_model.start_chat.return_value = fake_chat

    executor = MagicMock(return_value={"avg_lap_time_s": 73.2})

    fake_genai = MagicMock()
    fake_genai.chats.create.return_value = fake_chat
    fake_genai.models.generate_content.return_value = MagicMock(
        text="Hamilton would excel in Monaco's tight layout."
    )
    client._genai_client = fake_genai
    client._initialized = True

    with patch.object(client, "_ensure_initialized"):
        result = client.generate_with_tools(
            "What if Hamilton was at McLaren?", executor
        )

    assert result == "Hamilton would excel in Monaco's tight layout."
    executor.assert_called_once()


def test_generate_with_tools_passes_history_to_start_chat():
    """generate_with_tools converts history dicts to Content objects and passes them to start_chat."""
    client = _make_client()

    text_part = _make_text_part("He would be on hard tyres.")
    response = MagicMock()
    response.candidates = [MagicMock(content=MagicMock(parts=[text_part]))]

    fake_chat = MagicMock()
    fake_chat.send_message.return_value = response

    fake_model = MagicMock()
    fake_model.start_chat.return_value = fake_chat

    executor = MagicMock(return_value={})
    history = [
        {"role": "user", "content": "Put Hamilton in Piastri's car at Monaco 2025"},
        {"role": "assistant", "content": "Hamilton would start on mediums."},
    ]

    fake_genai = MagicMock()
    fake_genai.chats.create.return_value = fake_chat
    fake_genai.models.generate_content.return_value = MagicMock(
        text="He would be on hard tyres."
    )
    client._genai_client = fake_genai
    client._initialized = True

    with patch.object(client, "_ensure_initialized"):
        result = client.generate_with_tools(
            "So what would happen on lap 30?", executor, history=history
        )

    assert result == "He would be on hard tyres."


def test_generate_with_tools_executes_tool_and_returns_final_text():
    """generate_with_tools calls tool_executor and returns text from second response."""
    client = _make_client()

    fn_part = _make_fn_call_part(
        "get_strategy_recommendation",
        {
            "race_id": "2025_monaco",
            "driver_id": "hamilton",
            "current_lap": 40,
            "current_compound": "MEDIUM",
            "fuel_level": 0.5,
            "track_temp": 44.0,
            "air_temp": 26.0,
        },
    )
    first_response = MagicMock()
    first_response.candidates = [MagicMock(content=MagicMock(parts=[fn_part]))]

    text_part = _make_text_part("Hamilton should pit on lap 41 for HARD tyres.")
    second_response = MagicMock()
    second_response.candidates = [MagicMock(content=MagicMock(parts=[text_part]))]

    fake_chat = MagicMock()
    fake_chat.send_message.side_effect = [first_response, second_response]

    fake_model = MagicMock()
    fake_model.start_chat.return_value = fake_chat

    tool_result = {
        "recommended_action": "PIT_SOON",
        "pit_window_start": 41,
        "target_compound": "HARD",
    }
    executor = MagicMock(return_value=tool_result)

    fake_genai = MagicMock()
    fake_genai.chats.create.return_value = fake_chat
    fake_genai.models.generate_content.return_value = MagicMock(
        text="Hamilton should pit on lap 41 for HARD tyres."
    )
    client._genai_client = fake_genai
    client._initialized = True

    with patch.object(client, "_ensure_initialized"):
        result = client.generate_with_tools("Simulate Monaco with Hamilton", executor)

    assert result == "Hamilton should pit on lap 41 for HARD tyres."
    # executor is called at least once (eager pre-call + optional Gemini fn call)
    assert executor.call_count >= 1
    assert executor.call_args_list[-1][0][0] == "get_strategy_recommendation"


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
    r = client.post("/users/login", data={"username": "admin", "password": "admin"})
    assert r.status_code == 200
    return r.json()["access_token"]


def test_llm_chat_happy_path():
    """POST /llm/chat returns 200 with answer, latency_ms, model fields."""
    from fastapi.testclient import TestClient
    from src.api.main import app
    from src.llm import gemini_client as mod

    fake_client = MagicMock()
    fake_client.generate_with_tools.return_value = "Pit on lap 30 for hard tyres."
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
    """POST /llm/chat with race_inputs passes structured dict to generate_with_tools()."""
    from fastapi.testclient import TestClient
    from src.api.main import app
    from src.llm import gemini_client as mod

    fake_client = MagicMock()
    fake_client.generate_with_tools.return_value = "Stay out two more laps."
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
        call_kwargs = fake_client.generate_with_tools.call_args[1]
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
