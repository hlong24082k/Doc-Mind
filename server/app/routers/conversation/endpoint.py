from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.cruds import Conflict
from app.cruds import conversation as crud
from app.db.session import AsyncSessionLocal, get_db
from app.dependencies import get_current_user
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.user import User
from app.routers.conversation.services import (
    ReleasingEventSourceResponse,
    stream_reply,
)
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    DocumentRef,
    MessageCreate,
    MessageOut,
)

conversation_router = APIRouter()


def _out(conv: Conversation, docs: list[Document]) -> ConversationOut:
    return ConversationOut(
        id=conv.id,
        title=conv.title,
        documents=[DocumentRef.model_validate(d) for d in docs],
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@conversation_router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=ConversationOut
)
async def create_conversation(
    body: ConversationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        conv, docs = await crud.create(db, user, body.document_ids, body.title)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except Conflict as e:
        raise HTTPException(409, str(e))
    return _out(conv, docs)


@conversation_router.get("/")
async def list_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[ConversationOut]]:
    rows = await crud.list_for_user(db, user)
    return {"conversations": [_out(c, docs) for c, docs in rows]}


@conversation_router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await crud.get_owned(db, user, conversation_id)
    if conv is None:
        raise HTTPException(404, "Conversation not found")
    docs = await crud.documents_of(db, user, conv)
    messages = await crud.get_messages(db, conv.id)
    return ConversationDetail(
        **_out(conv, docs).model_dump(),
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@conversation_router.delete(
    "/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await crud.delete_owned(db, user, conversation_id):
        raise HTTPException(404, "Conversation not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@conversation_router.post("/{conversation_id}/messages")
async def post_message(
    conversation_id: str,
    body: MessageCreate,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Không dùng get_db: mọi truy cập DB qua session ngắn, nên không giữ
    connection nào trong suốt pha stream LLM."""
    async with AsyncSessionLocal() as db:
        conv = await crud.get_owned(db, user, conversation_id)
    if conv is None:
        raise HTTPException(404, "Conversation not found")
    scope_ids = await crud.indexed_scope(AsyncSessionLocal, user.id, conv.document_ids)
    if not scope_ids:  # bất biến: scope của API không bao giờ rỗng
        raise HTTPException(409, "Documents in this chat are no longer available")
    history = await crud.recent_history(
        AsyncSessionLocal, conv.id, settings.chat_history_turns
    )
    release = await request.app.state.chat_limiter.acquire(user.id)  # 429/503
    return ReleasingEventSourceResponse(
        stream_reply(
            services=request.app.state.services,
            user_id=user.id,
            conversation_id=conv.id,
            content=body.content,
            scope_ids=scope_ids,
            history=history,
            release=release,
        ),
        release=release,
    )
