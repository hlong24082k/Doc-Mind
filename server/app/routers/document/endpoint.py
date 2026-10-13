import asyncio

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile  # form() trả về lớp này

from app.config import settings
from app.core.storage.naming import canonical_document_name
from app.cruds import Conflict
from app.cruds import document as crud
from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.routers.document.limits import check_content_length, check_disk_free
from app.schemas.document import (
    DocumentList,
    DocumentOut,
    RejectedFile,
    UploadResult,
)

document_router = APIRouter()


@document_router.post("/uploadfile", response_model=UploadResult)
async def upload(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """KHÔNG khai báo UploadFile: FastAPI sẽ parse cả body trước auth.
    Mọi kiểm tra chạy trước request.form()."""
    length = check_content_length(request, settings.upload_max_request_mb << 20)
    async with request.app.state.upload_limiter.slot():
        await check_disk_free(
            settings.documents_folder_path,
            length,
            settings.upload_min_free_mb << 20,
        )
        used = await crud.usage(db, user.id)
        # nhả connection trước khi đọc body (có thể mất vài giây)
        await db.rollback()
        # chặn sớm khi đã đầy hẳn; kiểm tra chính xác nằm trong upsert_upload
        if used.bytes >= used.quota_bytes or used.documents >= used.quota_documents:
            raise HTTPException(409, "quota_exceeded")

        user_dir = settings.documents_folder_path / user.id
        await asyncio.to_thread(user_dir.mkdir, parents=True, exist_ok=True)

        documents: list[DocumentOut] = []
        rejected: list[RejectedFile] = []
        max_size = settings.upload_max_mb << 20
        async with request.form(
            max_files=settings.upload_max_files, max_fields=1
        ) as form:
            files = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
            for f in files:  # tuần tự
                filename = f.filename or ""
                name = canonical_document_name(filename)
                reason = None
                if name is None:
                    reason = "empty_name"
                elif not filename.lower().endswith(".pdf"):
                    reason = "not_pdf"
                elif (f.size or 0) > max_size:
                    reason = "too_large"
                else:
                    try:
                        tmp, digest, size = await crud.copy_to_tmp(f, user_dir)
                    except crud.UploadRejected as e:
                        reason = e.reason
                    else:
                        doc, reason = await crud.upsert_upload(
                            db, user, name, tmp, digest, size
                        )
                        if doc is not None:
                            documents.append(DocumentOut.model_validate(doc))
                if reason:
                    rejected.append(RejectedFile(filename=filename, reason=reason))

    usage = await crud.usage(db, user.id)
    return UploadResult(documents=documents, rejected=rejected, usage=usage)


@document_router.get("/", response_model=DocumentList)
async def list_documents(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    docs = await crud.list_documents(db, user)
    return DocumentList(
        documents=[DocumentOut.model_validate(d) for d in docs],
        usage=await crud.usage(db, user.id),
    )


@document_router.get("/{document_id}/file")
async def get_document_file(
    document_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await crud.get_owned(db, user, document_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    path = settings.document_file_path(user.id, doc.name)
    if not await asyncio.to_thread(path.is_file):
        raise HTTPException(404, "File not found")
    # Starlette tự encode tên Unicode theo RFC 5987 (filename*=utf-8''…)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"{doc.name}.pdf",
        content_disposition_type="inline",
    )


@document_router.post(
    "/{document_id}/reindex",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentOut,
)
async def reindex_document(
    document_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        doc = await crud.requeue_owned(db, user, document_id)
    except Conflict as e:
        raise HTTPException(409, str(e))
    if doc is None:
        raise HTTPException(404, "Document not found")
    return DocumentOut.model_validate(doc)


@document_router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await crud.delete_owned(db, user, document_id):
        raise HTTPException(404, "Document not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
