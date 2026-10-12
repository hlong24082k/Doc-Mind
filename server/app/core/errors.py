class RAGError(Exception):
    """Base error của RAG core."""


class DocumentLoadError(RAGError):
    pass


class EmbeddingError(RAGError):
    pass


class RerankerUnavailableError(RAGError):
    pass


class LLMGenerationError(RAGError):
    pass
