import pytest
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from app.core.errors import LLMGenerationError
from app.core.llm.base import LLMResponse
from app.core.llm.openai_provider import OpenAIProvider


def chunk(choices):
    return ChatCompletionChunk.model_validate(
        {
            "id": "c",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "m",
            "choices": choices,
        }
    )


def delta(content):
    return {"index": 0, "delta": {"content": content}, "finish_reason": None}


COMPLETION = ChatCompletion.model_validate(
    {
        "id": "c",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "hi"},
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
)


class FakeStream:
    def __init__(self, chunks):
        self.chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def __aiter__(self):
        for c in self.chunks:
            yield c


class FakeClient:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.kwargs = result, error, None
        self.chat = self
        self.completions = self

    async def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.result


async def test_stream_yields_text_chunks_only():
    stream = FakeStream(
        [
            chunk([delta("Hel")]),
            chunk([]),
            chunk([delta(None)]),
            chunk([delta("lo")]),
        ]
    )
    client = FakeClient(stream)
    events = [
        e
        async for e in OpenAIProvider(client, "m").generate(
            "q", system_instruction="sys"
        )
    ]
    assert [(e.event, e.data) for e in events] == [
        ("message", "Hel"),
        ("message", "lo"),
    ]
    assert client.kwargs["stream"] is True
    assert [m["role"] for m in client.kwargs["messages"]] == ["system", "user"]


async def test_stream_error_becomes_error_event():
    client = FakeClient(error=RuntimeError("boom"))
    events = [e async for e in OpenAIProvider(client, "m").generate("q")]
    assert len(events) == 1 and events[0].event == "error"
    assert events[0].data.startswith("[Error]") and "boom" in events[0].data


async def test_non_stream_response():
    resp = await OpenAIProvider(FakeClient(COMPLETION), "m").generate(
        "q", stream=False
    )
    assert isinstance(resp, LLMResponse)
    assert resp.text == "hi" and resp.provider == "openai"
    assert resp.metadata["model"] == "m"
    assert resp.metadata["finish_reason"] == "stop"
    assert resp.metadata["usage"]["total_tokens"] == 2


async def test_non_stream_error_raises():
    with pytest.raises(LLMGenerationError):
        await OpenAIProvider(FakeClient(error=RuntimeError("x")), "m").generate(
            "q", stream=False
        )


@pytest.mark.parametrize("effort", [None, "minimal"])
async def test_reasoning_effort_only_sent_when_set(effort):
    client = FakeClient(COMPLETION)
    await OpenAIProvider(client, "m", reasoning_effort=effort).generate(
        "q", stream=False
    )
    assert ("reasoning_effort" in client.kwargs) is (effort is not None)
    if effort:
        assert client.kwargs["reasoning_effort"] == effort


async def test_no_system_message_when_none():
    client = FakeClient(COMPLETION)
    await OpenAIProvider(client, "m").generate("q", stream=False)
    assert client.kwargs["messages"] == [{"role": "user", "content": "q"}]
