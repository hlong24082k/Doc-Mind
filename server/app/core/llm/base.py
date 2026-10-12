from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Dict,
    Literal,
    Optional,
    overload,
)

from sse_starlette.event import ServerSentEvent


@dataclass
class LLMResponse:
    text: str | None = None
    provider: str = ""
    metadata: Optional[Dict[str, Any]] = None


class LLMBase(ABC):
    """
    Abstract base class for LLM clients.

    `generate` là template method: `stream=True` (mặc định, tương thích
    ngược) trả về async iterator các ServerSentEvent; `stream=False` trả về
    awaitable LLMResponse.
    """

    def __init__(self, provider_name: str):
        self.provider = provider_name

    @overload
    def generate(
        self,
        query: str,
        *,
        system_instruction: str | None = None,
        stream: Literal[True] = True,
    ) -> AsyncIterator[ServerSentEvent]: ...

    @overload
    def generate(
        self,
        query: str,
        *,
        system_instruction: str | None = None,
        stream: Literal[False],
    ) -> Awaitable[LLMResponse]: ...

    def generate(self, query, *, system_instruction=None, stream=True):
        if stream:
            return self._generate_stream(query, system_instruction)
        return self._generate_once(query, system_instruction)

    @abstractmethod
    def _generate_stream(
        self, query: str, system_instruction: str | None
    ) -> AsyncIterator[ServerSentEvent]:
        pass

    @abstractmethod
    async def _generate_once(
        self, query: str, system_instruction: str | None
    ) -> LLMResponse:
        pass
