from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.domain import Answer
from app.cruds import Conflict
from app.models.conversation import Conversation, Message
from app.models.document import Document
from app.models.user import User


async def _owned_documents(
    db: AsyncSession, user_id: str, ids: list[str]
) -> dict[str, Document]:
    if not ids:
        return {}
    rows = await db.execute(
        select(Document).where(Document.id.in_(ids), Document.user_id == user_id)
    )
    return {d.id: d for d in rows.scalars()}


async def create(
    db: AsyncSession, user: User, document_ids: list[str], title: str | None
) -> tuple[Conversation, list[Document]]:
    """LookupError nếu có id không thuộc user (→ 404); Conflict nếu có
    document chưa indexed (→ 409)."""
    docs = await _owned_documents(db, user.id, document_ids)
    if len(docs) != len(document_ids):
        raise LookupError("Document not found")
    if any(d.status != "indexed" for d in docs.values()):
        raise Conflict("All documents must be indexed")
    conv = Conversation(user_id=user.id, title=title, document_ids=document_ids)
    db.add(conv)
    await db.commit()
    return conv, [docs[i] for i in document_ids]


async def list_for_user(
    db: AsyncSession, user: User, limit: int = 100
) -> list[tuple[Conversation, list[Document]]]:
    convs = list(
        (
            await db.execute(
                select(Conversation)
                .where(Conversation.user_id == user.id)
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
            )
        ).scalars()
    )
    # một query cho tên document của mọi hội thoại (không N+1)
    all_ids = list({i for c in convs for i in c.document_ids})
    docs = await _owned_documents(db, user.id, all_ids)
    return [(c, [docs[i] for i in c.document_ids if i in docs]) for c in convs]


async def documents_of(
    db: AsyncSession, user: User, conv: Conversation
) -> list[Document]:
    docs = await _owned_documents(db, user.id, conv.document_ids)
    return [docs[i] for i in conv.document_ids if i in docs]


async def get_owned(
    db: AsyncSession, user: User, conversation_id: str
) -> Conversation | None:
    return (
        (
            await db.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user.id,
                )
            )
        )
        .scalars()
        .first()
    )


async def get_messages(
    db: AsyncSession, conversation_id: str, limit: int = 200
) -> list[Message]:
    """`limit` tin gần nhất, sắp tăng dần."""
    rows = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .limit(limit)
    )
    return list(reversed(rows.scalars().all()))


async def delete_owned(db: AsyncSession, user: User, conversation_id: str) -> bool:
    result = await db.execute(
        delete(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user.id
        )
    )
    await db.commit()
    return bool(result.rowcount)


async def indexed_scope(
    sf: async_sessionmaker, user_id: str, document_ids: list[str]
) -> tuple[str, ...]:
    """Giao conversation.document_ids với document indexed của user."""
    async with sf() as db:
        rows = await db.execute(
            select(Document.id).where(
                Document.id.in_(document_ids),
                Document.user_id == user_id,
                Document.status == "indexed",
            )
        )
        found = set(rows.scalars())
    return tuple(i for i in document_ids if i in found)


async def recent_history(
    sf: async_sessionmaker, conversation_id: str, turns: int
) -> list[tuple[str, str]]:
    async with sf() as db:
        msgs = await get_messages(db, conversation_id, limit=turns * 2)
    return [(m.role, m.content) for m in msgs]


async def save_turn(
    sf: async_sessionmaker,
    conversation_id: str,
    user_text: str,
    answer: Answer,
    standalone: str,
    sources: list[dict],
) -> Message:
    """Một transaction: INSERT user + assistant; cập nhật updated_at và
    title (nếu chưa có) của hội thoại."""
    async with sf() as db:
        db.add(
            Message(
                conversation_id=conversation_id,
                role="user",
                content=user_text,
                standalone_query=standalone,
            )
        )
        await db.flush()  # user message phải có id nhỏ hơn assistant
        reply = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=answer.text,
            sources=sources,
            grounded=answer.grounded,
            refused=answer.refused,
            timings_ms=dict(answer.timings_ms),
        )
        db.add(reply)
        await db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(
                updated_at=datetime.utcnow(),
                title=func.coalesce(Conversation.title, user_text[:80]),
            )
        )
        await db.commit()
    return reply
