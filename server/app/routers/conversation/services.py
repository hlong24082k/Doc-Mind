import json
from typing import AsyncIterator, Callable, Sequence

from loguru import logger
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.core.domain import (
    ContextBlock,
    ContextsEvent,
    SearchScope,
    TokenEvent,
)
from app.core.errors import RAGError
from app.core.factory import ApiServices
from app.cruds import conversation as crud
from app.db.session import AsyncSessionLocal
from app.schemas.conversation import MessageOut

SNIPPET_CHARS = 280


def sse(event: str, data: dict) -> ServerSentEvent:
    # data luôn là JSON (kể cả token) để newline không làm vỡ frame
    return ServerSentEvent(event=event, data=json.dumps(data, ensure_ascii=False))


def to_sources(contexts: Sequence[ContextBlock], cited_refs: set[int]) -> list[dict]:
    return [
        {
            "ref": c.ref,
            "document_id": c.document_id,
            "document_name": c.document_name,
            "document_title": c.document_title,
            "page_start": c.page_start,
            "page_end": c.page_end,
            "section": c.section,
            "snippet": c.text[:SNIPPET_CHARS],
            "cited": c.ref in cited_refs,
        }
        for c in contexts
    ]


async def stream_reply(
    *,
    services: ApiServices,
    user_id: str,
    conversation_id: str,
    content: str,
    scope_ids: tuple[str, ...],
    history: Sequence[tuple[str, str]],
    release: Callable[[], None],
) -> AsyncIterator[ServerSentEvent]:
    try:
        standalone = await services.rewriter.rewrite(content, history)
        yield sse("meta", {"standalone_query": standalone})
        # scope_ids KHÔNG rỗng: tuple rỗng = toàn bộ tài liệu của user
        scope = SearchScope(user_id=user_id, document_ids=scope_ids)
        async for ev in services.rag.answer_stream(standalone, scope):
            if isinstance(ev, ContextsEvent):
                yield sse("contexts", {"sources": to_sources(ev.contexts, set())})
            elif isinstance(ev, TokenEvent):
                yield sse("token", {"text": ev.text})
            else:
                a = ev.answer
                sources = to_sources(a.contexts, {c.ref for c in a.citations})
                msg = await crud.save_turn(
                    AsyncSessionLocal,
                    conversation_id,
                    content,
                    a,
                    standalone,
                    sources,
                )
                yield sse(
                    "final",
                    {
                        "message": MessageOut.model_validate(msg).model_dump(
                            mode="json"
                        ),
                        "timings_ms": dict(a.timings_ms),
                    },
                )
    except RAGError as e:
        yield sse("error", {"detail": str(e)})
    except Exception:
        logger.exception("chat stream failed")
        yield sse("error", {"detail": "Internal error"})
    finally:
        release()


class ReleasingEventSourceResponse(EventSourceResponse):
    """Gọi release kể cả khi generator chưa từng chạy (client ngắt kết nối
    trước byte đầu tiên thì `finally` của generator không bao giờ chạy)."""

    def __init__(self, content, release: Callable[[], None], **kwargs):
        super().__init__(content, **kwargs)
        self._release = release

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._release()
