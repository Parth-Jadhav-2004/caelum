import json
from unittest.mock import Mock

import httpx
import pytest
from caelum.config import Config
from caelum.providers import Providers, offline_cleanup, spoken_formatting
from caelum.quality import cleanup_prompt, validate_cleanup

SHOPPING = (
    "shopping list first rice second onion third oil",
    "Shopping list:\n\n1. Rice\n2. Onion\n3. Oil",
)
SPOKEN_SHOPPING = (
    "I want to make a shopping list then first I would like to buy some onion and second oil, third rice, fourth soap",
    "Shopping list:\n\n1. Some onion\n2. Oil\n3. Rice\n4. Soap",
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
    for raw, formatted in (SHOPPING, SPOKEN_SHOPPING, ISSUES, STEPS, (PROSE, PROSE)):
        assert f"Input: {raw}\nOutput:\n{formatted}" in prompt


@pytest.mark.parametrize("raw,formatted", [
    SHOPPING, SPOKEN_SHOPPING, ISSUES, STEPS, (PROSE, PROSE),
    ("number one first aid and number two oil", "1. First aid\n2. Oil"),
    ("issues also two flags and one error", "Issues:\n\n- Two flags\n- One error"),
    ("shopping list first rice second oil. tasks first wash second cook",
     "Shopping list:\n\n1. Rice\n2. Oil\n\nTasks:\n\n1. Wash\n2. Cook"),
    ("issues poor signal and noise. steps number one reconnect number two retry",
     "Issues:\n\n- Poor signal\n- Noise\n\nSteps:\n\n1. Reconnect\n2. Retry"),
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


@pytest.mark.parametrize("style", ["light", "thorough"])
@pytest.mark.parametrize("reply", [SPOKEN_SHOPPING[0], "Purchase two apples."])
async def test_explicit_list_needs_no_online_completion(style, reply):
    config = Config()
    config.cleanup.model = "test-model"
    config.cleanup.style = style
    respond = Mock(return_value=httpx.Response(200, json={"choices": [{"message": {"content": reply}}]}))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = Providers(config, client, credential_resolver=lambda _: "test-key")
        assert await provider.cleanup(SPOKEN_SHOPPING[0]) == (SPOKEN_SHOPPING[1], True)
        assert provider.metrics["http_calls"] == 0 and provider.metrics["cleanup_refined"]
    respond.assert_not_called()


@pytest.mark.parametrize("style", ["code", "casual", "email"])
async def test_other_online_styles_leave_list_decisions_to_provider(style):
    config = Config()
    config.cleanup.model = "test-model"
    config.cleanup.style = style
    raw = SPOKEN_SHOPPING[0]
    respond = Mock(return_value=httpx.Response(200, json={"choices": [{"message": {"content": raw}}]}))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = Providers(config, client, credential_resolver=lambda _: "test-key")
        assert await provider.cleanup(raw) == (raw, True)
    respond.assert_called_once()


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
    raw = "steps number one open settings number two select C++"
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


@pytest.mark.parametrize("raw,expected", [
    SHOPPING, SPOKEN_SHOPPING,
    (SPOKEN_SHOPPING[0].replace(",", ""), SPOKEN_SHOPPING[1]),
    ("if " + SPOKEN_SHOPPING[0], SPOKEN_SHOPPING[1]),
    ("shopping list 1st onions 2nd oil", "Shopping list:\n\n1. Onions\n2. Oil"),
    ("first rice and second onions, third oil", "1. Rice\n2. Onions\n3. Oil"),
    ("shopping list: onions, oil, rice and soap", "Shopping list:\n\n- Onions\n- Oil\n- Rice\n- Soap"),
    ("I want to make a shopping list. Then, first, I would like to buy some onion. "
     "And second, oil; third, rice; fourth, soap.", SPOKEN_SHOPPING[1]),
    ("Grocery list: first 2.5 kg of red onions, second extra virgin oil and vinegar, "
     "third iPhone cables, fourth C++ books.",
     "Grocery list:\n\n1. 2.5 kg of red onions\n2. Extra virgin oil and vinegar"
     "\n3. iPhone cables\n4. C++ books"),
])
def test_offline_spoken_list(raw, expected):
    assert offline_cleanup(raw, {}, "en-US") == expected


@pytest.mark.parametrize("raw,expected", [
    ("shopping list first apples second a third of a pound of cheese",
     "Shopping list:\n\n1. Apples\n2. A third of a pound of cheese"),
    ("shopping list first apples second cheese third rice",
     "Shopping list:\n\n1. Apples\n2. Cheese\n3. Rice"),
    ("shopping list first apples second a third of a pound of cheese third rice",
     "Shopping list:\n\n1. Apples\n2. A third of a pound of cheese\n3. Rice"),
])
def test_offline_list_distinguishes_fractions_from_markers(raw, expected):
    assert offline_cleanup(raw, {}, "en-US") == expected


@pytest.mark.parametrize("raw", [
    PROSE,
    "I put first aid supplies and second-hand books on my shopping list.",
    "I want to make a shopping list then first check the fridge.",
    "Shopping list first flour third eggs.",
    "Shopping list first tea second second-hand books. That is all.",
    "Shopping list first tea and second.",
    "I want to make a shopping list first thing tomorrow and second guess every purchase.",
    "First aid is on the second floor of the third building.",
    "First I wrote a draft, second I revised it, third I sent it.",
    "First place and second place shared a podium.",
    "Shopping list: rice and beans.",
])
def test_ambiguous_speech_stays_prose(raw):
    assert offline_cleanup(raw, {}, "en") == raw


def test_non_english_transcription_does_not_infer_english_list_commands():
    assert offline_cleanup(SPOKEN_SHOPPING[0], {}, "de") == SPOKEN_SHOPPING[0]


@pytest.mark.parametrize("wrong", [
    SPOKEN_SHOPPING[1].replace("Some onion", "Onion"),
    SPOKEN_SHOPPING[1].replace("Rice", "Brown rice"),
    SPOKEN_SHOPPING[1].replace("2. Oil\n3. Rice", "2. Rice\n3. Oil"),
])
def test_online_cleanup_preserves_contents_when_shortening_a_spoken_list_request(wrong):
    assert validate_cleanup(SPOKEN_SHOPPING[0], wrong, allow_lists=True) == (
        SPOKEN_SHOPPING[0], False,
    )


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
        assert await provider.cleanup(SHOPPING[0]) == (SHOPPING[1] if engine == "local" else SHOPPING[0], False)
        provider.metrics["language"] = "fr"
        assert await provider.cleanup("new line") == ("new line", False)
    respond.assert_not_called()


async def test_local_engine_formats_spoken_list_without_network_even_with_online_model():
    config = Config()
    config.stt.engine = "local"
    config.cleanup.model = "configured-online-editor"
    config.cleanup.style = "email"
    respond = Mock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert await Providers(config, client).cleanup(SPOKEN_SHOPPING[0]) == (
            SPOKEN_SHOPPING[1], False,
        )
    respond.assert_not_called()


@pytest.mark.parametrize("style", ["light", "thorough", "email", "casual", "code"])
@pytest.mark.parametrize("response,expected", [
    ("Notes.\n\n- Rice.", ("Notes.\n\n- Rice.", True)),
    ("Notes.\n\nRice.", ("Notes.\n\n- rice.", False)),
    ("Notes. Rice.", ("Notes.\n\n- rice.", False)),
    ("- Notes.\n\nRice.", ("Notes.\n\n- rice.", False)),
])
async def test_cleanup_keeps_explicit_single_bullet(style, response, expected, monkeypatch):
    config = Config()
    config.cleanup.style = style
    config.cleanup.model = "test-model"
    monkeypatch.setenv(config.cleanup.key_env, "test-key")
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"choices": [{"message": {"content": response}}]})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        assert await Providers(config, client).cleanup("Notes. New paragraph. Bullet point. rice.") == expected


@pytest.mark.parametrize("style", ["email", "casual", "code"])
@pytest.mark.parametrize("response,valid", [("Rice.", False), ("- Rice.", True)])
async def test_explicit_bullet_without_any_newline(monkeypatch, style, response, valid):
    config = Config()
    config.cleanup.model = "test-model"
    config.cleanup.style = style
    monkeypatch.setenv(config.cleanup.key_env, "test-key")
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"choices": [{"message": {"content": response}}]})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        assert await Providers(config, client).cleanup("Bullet point. rice.") == (
            response if valid else "- rice.", valid,
        )


def test_cleanup_rejects_inferred_single_bullet():
    assert validate_cleanup("Rice.", "- Rice.", allow_lists=True) == ("Rice.", False)


@pytest.mark.parametrize("raw,formatted", [SHOPPING, ISSUES])
@pytest.mark.parametrize("keep_paragraph", [True, False])
async def test_command_break_after_inferred_list(raw, formatted, keep_paragraph, monkeypatch):
    config = Config()
    config.cleanup.model = "test-model"
    monkeypatch.setenv(config.cleanup.key_env, "test-key")
    content = formatted + ("\n\n" if keep_paragraph else " ") + "That's all."
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        assert await Providers(config, client).cleanup(raw + ". New paragraph. That's all.") == (
            content if keep_paragraph else raw + ".\n\nThat's all.", keep_paragraph,
        )


@pytest.mark.parametrize("commands,suffix", [
    ("Bullet point.", "\n- "),
    ("New paragraph. Bullet point. Bullet point.", "\n\n- \n- "),
])
async def test_trailing_empty_bullets_stay_outside_cleanup(commands, suffix, monkeypatch):
    config = Config()
    config.cleanup.model = "test-model"
    monkeypatch.setenv(config.cleanup.key_env, "test-key")

    def respond(request):
        assert json.loads(request.content)["messages"][-1]["content"] == "notes."
        return httpx.Response(200, json={"choices": [{"message": {"content": "Notes."}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert await Providers(config, client).cleanup("notes. " + commands) == ("Notes." + suffix, True)
