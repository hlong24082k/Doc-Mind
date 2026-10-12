from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.genai import errors, types

from app.core.embedding import gemini_embedder
from app.core.embedding.gemini_embedder import GeminiEmbedder
from app.core.errors import EmbeddingError

DIM = 4


def make_client(side_effect=None):
    def respond(model, contents, config):
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1] * DIM) for _ in contents]
        )

    client = MagicMock()
    client.aio.models.embed_content = AsyncMock(side_effect=side_effect or respond)
    return client


def embedder(client, **kw):
    params = dict(dimension=DIM, batch_size=2, max_retries=3)
    params.update(kw)
    return GeminiEmbedder(client, **params)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    # bỏ thời gian chờ backoff
    monkeypatch.setattr(
        gemini_embedder,
        "wait_exponential_jitter",
        lambda **kw: __import__("tenacity").wait_none(),
    )


@pytest.mark.asyncio
async def test_batches_and_content_per_item_with_prefix():
    client = make_client()
    vectors = await embedder(client).embed_documents(
        "My Title", ["a", "b", "c", "d", "e"]
    )
    assert len(vectors) == 5
    calls = client.aio.models.embed_content.call_args_list
    assert [len(c.kwargs["contents"]) for c in calls] == [2, 2, 1]
    first = calls[0].kwargs["contents"]
    assert all(isinstance(c, types.Content) for c in first)
    assert first[0].parts[0].text == "title: My Title | text: a"
    assert calls[0].kwargs["config"].output_dimensionality == DIM


@pytest.mark.asyncio
async def test_query_prefix():
    client = make_client()
    await embedder(client, query_task="search result").embed_query("what?")
    contents = client.aio.models.embed_content.call_args.kwargs["contents"]
    assert contents[0].parts[0].text == "task: search result | query: what?"


@pytest.mark.asyncio
async def test_retries_on_429():
    state = {"n": 0}

    def flaky(model, contents, config):
        state["n"] += 1
        if state["n"] < 3:
            raise errors.APIError(429, {"error": {"message": "quota"}})
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.0] * DIM) for _ in contents]
        )

    client = make_client(side_effect=flaky)
    vectors = await embedder(client).embed_documents("t", ["a"])
    assert len(vectors) == 1
    assert state["n"] == 3


@pytest.mark.asyncio
async def test_gives_up_after_max_retries():
    def always_429(model, contents, config):
        raise errors.APIError(429, {"error": {"message": "quota"}})

    client = make_client(side_effect=always_429)
    with pytest.raises(EmbeddingError):
        await embedder(client).embed_documents("t", ["a"])
    assert client.aio.models.embed_content.call_count == 3


@pytest.mark.asyncio
async def test_count_mismatch_raises():
    def merged(model, contents, config):
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.0] * DIM)])

    client = make_client(side_effect=merged)
    with pytest.raises(EmbeddingError):
        await embedder(client).embed_documents("t", ["a", "b"])


def test_batch_size_validated():
    with pytest.raises(ValueError):
        GeminiEmbedder(MagicMock(), batch_size=101)
    with pytest.raises(ValueError):
        GeminiEmbedder(MagicMock(), batch_size=0)
