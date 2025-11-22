from fastapi import APIRouter, UploadFile, HTTPException, Depends
from fastapi.responses import FileResponse
from typing import List
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorDatabase

from src.app.dependencies import get_current_user
from src.app.config import settings
from src.app.db.session import get_db
from src.app.cruds import (
    document as crud_document,
)
from src.app.models import (
    user as model_user
)


document_router = APIRouter()


@document_router.post("/uploadfile")
async def create_upload_files(
    files: List[UploadFile], 
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: model_user.User = Depends(get_current_user)
):
    # ensure documents folder exists
    documents_dir: Path = settings.documents_folder_path
    documents_dir.mkdir(parents=True, exist_ok=True)

    saved_files: List[str] = []
    skipped_existing_on_disk: List[str] = []

    for file in files:
        name = file.filename
        save_to: Path = settings.get_document_with_path(name)
        if save_to.exists():
            skipped_existing_on_disk.append(name)
            continue

        contents = await file.read()
        with open(save_to, "wb") as f:
            f.write(contents)
        saved_files.append(name)

    if saved_files:
        created = await crud_document.create_document(db, current_user, saved_files)

    return {"documents": [d.dict(by_alias=True) for d in created]}


@document_router.get("/")
async def list_documents(
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: model_user.User = Depends(get_current_user)
):
    """Return all document records from the database."""
    docs = await crud_document.get_documents(db, current_user)
    return {"documents": [d.dict(by_alias=True) for d in docs]}


@document_router.get("/{filename}")
async def download_document(filename: str):
    """Download a specific document by filename."""
    file_path: Path = settings.get_document_with_path(filename)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=str(file_path), filename=filename)


@document_router.delete("/{file_id}")
async def delete_document(
    file_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: model_user.User = Depends(get_current_user)
):
    """Delete a specific document by filename."""
    return await crud_document.delete_document(db, current_user, file_id)
