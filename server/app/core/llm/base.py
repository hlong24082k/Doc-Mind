from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class LLMResponse:
    text: str | None = None
    provider: str = ""
    metadata: Optional[Dict[str, Any]] = None


class LLMBase(ABC):
    """
    Abstract base class for LLM clients.
    Implementations must provide generate(prompt, **kwargs) -> LLMResponse.
    """

    def __init__(self, provider_name: str):
        self.provider = provider_name

    @abstractmethod
    def generate(self, query: str):
        """
        Generate text for the given prompt.

        :param prompt: Text prompt to send to model.
        :param max_tokens: Max tokens to generate.
        :param temperature: Sampling temperature.
        :param stop: Optional list of stop tokens.
        :param stream: If True, some adapters may call a provided stream callback (not supported uniformly).
        :param kwargs: Provider-specific keyword args.
        :return: LLMResponse
        """
        pass
