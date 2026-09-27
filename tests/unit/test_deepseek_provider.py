import asyncio
from types import SimpleNamespace

from agent_audit_api.providers.deepseek import DeepSeekProvider


class RecordingCompletions:
    def __init__(self) -> None:
        self.request = None

    async def create(self, **request):
        self.request = request
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="测试回答", tool_calls=[]))]
        )


def test_deepseek_provider_uses_flash_with_thinking_disabled() -> None:
    completions = RecordingCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    provider = DeepSeekProvider(client=client)

    response = asyncio.run(
        provider.complete([{"role": "user", "content": "测试问题"}])
    )

    assert response.content == "测试回答"
    assert completions.request["model"] == "deepseek-v4-flash"
    assert completions.request["extra_body"] == {
        "thinking": {"type": "disabled"}
    }
