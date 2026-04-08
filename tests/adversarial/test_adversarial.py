"""Adversarial prompt integration tests against the real Gemini 2.5 Flash endpoint.

Run with:
    pytest tests/adversarial/ -v --tb=short

Requires ambient GCP credentials (ADC) with Vertex AI access.
Each test calls the real Gemini API. A JSON report is uploaded to
gs://f1optimizer-training/adversarial-reports/<run_id>.json at session end.
"""

from __future__ import annotations

import pytest

from tests.adversarial.prompts import PROMPTS, AdversarialPrompt
from tests.adversarial.scorer import score


def _prompt_id(p: AdversarialPrompt) -> str:
    """Stable pytest node ID: category::first-40-chars-of-prompt."""
    slug = p.prompt[:40].replace(" ", "_").replace("'", "").replace(".", "")
    return f"{p.category}::{slug}"


@pytest.mark.adversarial
@pytest.mark.parametrize(
    "adv_prompt",
    PROMPTS,
    ids=[_prompt_id(p) for p in PROMPTS],
)
def test_adversarial_prompt(
    adv_prompt: AdversarialPrompt,
    gemini_client,
    results_collector: list[dict],
) -> None:
    """Each adversarial prompt must be resisted by the LLM (verdict=PASS).

    The test always appends to results_collector — even on failure — so the
    GCS report captures the full picture regardless of exit status.
    """
    response = gemini_client.generate(adv_prompt.prompt)
    result = score(adv_prompt.prompt, response, gemini_client)

    results_collector.append(
        {
            "category": adv_prompt.category,
            "prompt": adv_prompt.prompt,
            "pass_condition": adv_prompt.pass_condition,
            "response_snippet": response[:200],
            **result,
        }
    )

    assert result["verdict"] == "PASS", (
        f"\nAdversarial prompt FAILED\n"
        f"Category    : {adv_prompt.category}\n"
        f"Prompt      : {adv_prompt.prompt}\n"
        f"Response    : {response[:400]}\n"
        f"Scorer      : {result['scorer']}\n"
        f"Reason      : {result['keyword_reason'] if result['scorer'] == 'keyword' else result['judge_reason']}\n"
        f"Expected    : {adv_prompt.pass_condition}"
    )
