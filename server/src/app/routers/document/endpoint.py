from fastapi import APIRouter, UploadFile, HTTPException, Depends
from fastapi.responses import FileResponse, JSONResponse
from typing import List
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorDatabase

from src.app.config import settings
from src.app.db.session import get_db
from src.app.cruds.document import (
    create_document as crud_create_document,
    get_documents as crud_get_documents,
)


document_router = APIRouter()


@document_router.post("/uploadfile")
async def create_upload_files(
    files: List[UploadFile], db: AsyncIOMotorDatabase = Depends(get_db)
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
        created = await crud_create_document(db, saved_files)

    return {"documents": [d.dict(by_alias=True) for d in created]}


@document_router.get("/documents")
async def list_documents(db: AsyncIOMotorDatabase = Depends(get_db)):
    """Return all document records from the database."""
    docs = await crud_get_documents(db)
    return {"documents": [d.dict(by_alias=True) for d in docs]}


@document_router.get("/documents/{filename}")
async def download_document(filename: str):
    """Download a specific document by filename."""
    file_path: Path = settings.get_document_with_path(filename)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=str(file_path), filename=filename)
