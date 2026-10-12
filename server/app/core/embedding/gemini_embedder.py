import time
from typing import Sequence

from google import genai
from google.genai import types
from loguru import logger
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.errors import EmbeddingError

_RETRYABLE_CODES = {429, 500, 502, 503, 504}


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, genai.errors.APIError) and exc.code in _RETRYABLE_CODES


class GeminiEmbedder:
    """Embedder dùng gemini-embedding-2 (task nằm trong prefix text)."""

    def __init__(
        self,
        client: genai.Client,
        model: str = "gemini-embedding-2",
        dimension: int = 768,
        batch_size: int = 32,
        max_retries: int = 6,
        query_task: str = "question answering",
    ):
        if not 1 <= batch_size <= 100:
            raise ValueError("batch_size phải nằm trong khoảng 1..100")
        self.client = client
        self.model = model
        self._dimension = dimension
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.query_task = query_task

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_documents(
        self, title: str, texts: Sequence[str]
    ) -> list[list[float]]:
        formatted = [f"title: {title or 'none'} | text: {text}" for text in texts]
        start = time.perf_counter()
        vectors: list[list[float]] = []
        n_batches = 0
        for i in range(0, len(formatted), self.batch_size):
            batch = formatted[i : i + self.batch_size]
            vectors.extend(await self._embed_batch(batch))
            n_batches += 1
        logger.info(
            "Embedded {} texts in {} batches ({:.0f} ms)",
            len(formatted),
            n_batches,
            (time.perf_counter() - start) * 1000,
        )
        return vectors

    async def embed_query(self, query: str) -> list[float]:
        text = f"task: {self.query_task} | query: {query}"
        return (await self._embed_batch([text]))[0]

    # ------------------------------------------------------------------
    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        # Mỗi phần tử một Content riêng, nếu không API trả về 1 embedding gộp
        contents = [types.Content(parts=[types.Part.from_text(text=t)]) for t in batch]
        config = types.EmbedContentConfig(output_dimensionality=self._dimension)
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(_is_retryable),
                wait=wait_exponential_jitter(initial=2, max=60),
                stop=stop_after_attempt(self.max_retries),
                reraise=False,
            ):
                with attempt:
                    result = await self.client.aio.models.embed_content(
                        model=self.model, contents=contents, config=config
                    )
        except RetryError as e:
            raise EmbeddingError(
                f"Embedding thất bại sau {self.max_retries} lần thử: "
                f"{e.last_attempt.exception()}"
            ) from e
        except genai.errors.APIError as e:
            raise EmbeddingError(f"Embedding API error: {e}") from e

        embeddings = result.embeddings or []
        if len(embeddings) != len(batch):
            raise EmbeddingError(
                f"Số embedding trả về ({len(embeddings)}) khác số input "
                f"({len(batch)})"
            )
        vectors = [list(e.values) for e in embeddings]
        for v in vectors:
            if len(v) != self._dimension:
                raise EmbeddingError(
                    f"Embedding có {len(v)} chiều, kỳ vọng {self._dimension}"
                )
        return vectors
