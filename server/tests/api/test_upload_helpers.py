import hashlib
import io

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.cruds.document import UploadRejected, copy_to_tmp
from app.routers.document.limits import UploadLimiter


async def test_copy_rejects_non_pdf_and_leaves_nothing(tmp_path):
    f = UploadFile(io.BytesIO(b"hello, not a pdf"), filename="x.pdf")
    with pytest.raises(UploadRejected) as e:
        await copy_to_tmp(f, tmp_path)
    assert e.value.reason == "not_pdf"
    assert list(tmp_path.iterdir()) == []


async def test_copy_hashes_and_writes_pdf(tmp_path):
    data = b"%PDF-1.7\n" + b"x" * (3 << 20)
    f = UploadFile(io.BytesIO(data), filename="x.pdf")
    tmp, digest, size = await copy_to_tmp(f, tmp_path)
    assert tmp.name.startswith(".tmp-")
    assert tmp.read_bytes() == data
    assert digest == hashlib.sha256(data).hexdigest()
    assert size == len(data)


async def test_upload_limiter_503_when_full_and_releases():
    limiter = UploadLimiter(1)
    async with limiter.slot():
        with pytest.raises(HTTPException) as e:
            async with limiter.slot():
                pass
        assert e.value.status_code == 503
        assert e.value.headers == {"Retry-After": "5"}
    async with limiter.slot():  # slot đã được nhả
        pass
