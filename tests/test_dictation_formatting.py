import json
from unittest.mock import Mock

import httpx
import pytest
from caelum.config import Config
from caelum.providers import Providers, spoken_formatting
from caelum.quality import cleanup_prompt, validate_cleanup

SHOPPING = (
    "shopping list first rice second onion third oil",
    "Shopping list:\n\n1. Rice\n2. Onion\n3. Oil",
)
ISSUES = (
    "I found a few issues, the sidebar is empty, the toggle is misplaced, and history doesn't refresh",
    "I found a few issues:\n\n- The sidebar is empty\n- The toggle is misplaced\n- History doesn't refresh",
)
STEPS = (
    "steps first open settings next choose audio then save. That fixed it for me.",
    "Steps:\n\n1. Open settings\n2. Choose audio\n3. Save\n\nThat fixed it for me.",
)
PROSE = "I first noticed the problem on Monday."


@pytest.mark.parametrize("style", ["light", "thorough"])
def test_cleanup_prompt_includes_list_rules_and_examples(style):
    prompt = cleanup_prompt(style)
    assert "two or more distinct items with clear list cues" in prompt
    assert "Use a numbered list when order is spoken or implied" in prompt
    assert 'use "- " bullets' in prompt
    for raw, formatted in (SHOPPING, ISSUES, STEPS, (PROSE, PROSE)):
        assert f"Input: {raw}\nOutput:\n{formatted}" in prompt


@pytest.mark.parametrize("raw,formatted", [
    SHOPPING, ISSUES, STEPS, (PROSE, PROSE),
    ("number one first aid and number two oil", "1. First aid\n2. Oil"),
    ("issues also two flags and one error", "Issues:\n\n- Two flags\n- One error"),
    ("steps " + " ".join(f"number {n} check file {n}" for n in range(1, 101)),
     "Steps:\n\n" + "\n".join(f"{n}. Check file {n}" for n in range(1, 101))),
])
@pytest.mark.parametrize("style", ["light", "thorough"])
async def test_mock_list_cleanup(raw, formatted, style, monkeypatch):
    config = Config()
    config.cleanup.model = "test-model"
    config.cleanup.style = style
    monkeypatch.setenv(config.cleanup.key_env, "test-key")

    def respond(request):
        body = json.loads(request.content)
        assert body["messages"] == [
            {"role": "system", "content": cleanup_prompt(config.cleanup.style)},
            {"role": "user", "content": raw},
        ]
        assert body["max_tokens"] >= len(formatted.encode())
        return httpx.Response(200, json={"choices": [{"message": {"content": formatted}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert await Providers(config, client).cleanup(raw) == (formatted, True)


@pytest.mark.parametrize("result", [
    "Shopping list:\n\n1. Rice\n2. Oil",
    "Shopping list:\n\n1. Oil\n2. Onion\n3. Rice",
    "Shopping list:\n\n1. Rice\n2. Onion\n3. Olive oil",
])
def test_changed_list_falls_back_to_dictation(result):
    raw = SHOPPING[0]
    assert validate_cleanup(raw, result, allow_lists=True) == (raw, False)


async def test_length_limited_response_never_pastes_a_partial_list(monkeypatch):
    config = Config()
    config.cleanup.model = "test-model"
    monkeypatch.setenv(config.cleanup.key_env, "test-key")
    # Even a partial completion that passes word-level validation must be rejected.
    raw = "steps first open settings second select C++"
    partial = {"finish_reason": "length", "message": {"content": "Steps:\n\n1. Open settings\n2. Select C"}}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"choices": [partial]}))
    async with httpx.AsyncClient(transport=transport) as client:
        assert await Providers(config, client).cleanup(raw) == (raw, False)


@pytest.mark.parametrize("raw,formatted", [
    ("New line.", "\n"),
    ("new paragraph", "\n\n"),
    ("BULLET POINT!", "- "),
    ("Notes, new line, one, new paragraph, two", "Notes\none\n\ntwo"),
    ("Bullet point, rice, bullet point, onion", "- rice\n- onion"),
    ("Notes. New paragraph. Bullet point. Rice.", "Notes.\n\n- Rice."),
    ("Notes:\nbullet point\nrice", "Notes:\n- rice"),
    ("A new line of business needs a new paragraph in the plan.",
     "A new line of business needs a new paragraph in the plan."),
    ("That bullet point is unclear.", "That bullet point is unclear."),
    ("New lineages, new paragraphs, bullet pointers", "New lineages, new paragraphs, bullet pointers"),
    ("renew line, submarinew paragraph, subbullet point", "renew line, submarinew paragraph, subbullet point"),
    (SHOPPING[0], SHOPPING[0]), (ISSUES[0], ISSUES[0]),
])
def test_spoken_formatting(raw, formatted):
    assert spoken_formatting(raw, "en-US") == formatted


@pytest.mark.parametrize("engine,model", [("local", "configured"), ("online", "")])
async def test_commands_without_llm(engine, model):
    config = Config()
    config.stt.engine = engine
    config.cleanup.model = model
    respond = Mock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = Providers(config, client)
        assert await provider.cleanup("Shopping list, new paragraph, bullet point, rice") == (
            "Shopping list\n\n- rice", False,
        )
        assert await provider.cleanup("new line") == ("\n", False)
        assert await provider.cleanup(SHOPPING[0]) == (SHOPPING[0], False)
        provider.metrics["language"] = "fr"
        assert await provider.cleanup("new line") == ("new line", False)
    respond.assert_not_called()
