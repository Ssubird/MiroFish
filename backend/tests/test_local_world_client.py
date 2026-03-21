from app.services.lottery.local_world_client import _system_prompt


def test_system_prompt_keeps_all_passages_without_clipping():
    first = "Prompt file [one.md] part 1/1:\n" + ("A" * 1200)
    second = "Workspace document [two.md] part 1/1:\n" + ("B" * 1600)
    third = "Workspace file [three.json] part 1/2:\n" + ("C" * 2000)
    agent = {
        "name": "purchase_chair",
        "description": "demo",
        "memory_blocks": {"current_issue": "issue"},
        "passages": [first, second, third],
    }

    prompt = _system_prompt(agent)

    assert first in prompt
    assert second in prompt
    assert third in prompt
    assert "..." not in prompt
