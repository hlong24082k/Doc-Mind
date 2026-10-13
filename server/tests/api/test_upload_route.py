import httpx
from fastapi.routing import iter_route_contexts

from app.config import settings
from app.db.session import get_db
from app.dependencies import get_current_user
from app.main import app

UPLOAD = "/api/document/uploadfile"


def test_upload_route_declares_no_body():
    # khai báo lại UploadFile → FastAPI parse cả body trước khi auth
    (rc,) = [rc for rc in iter_route_contexts(app.routes) if rc.path == UPLOAD]
    assert rc.route.body_field is None


def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://t")


async def test_no_token_is_401():
    async with client() as c:
        resp = await c.post(UPLOAD, files={"files": ("a.pdf", b"%PDF-1")})
    assert resp.status_code == 401


async def test_length_checks_run_before_body():
    async def no_db():
        yield None

    app.dependency_overrides[get_current_user] = lambda: object()
    app.dependency_overrides[get_db] = no_db
    try:
        async with client() as c:

            async def chunked():
                yield b"x"

            resp = await c.post(UPLOAD, content=chunked())
            assert resp.status_code == 411

            too_big = (settings.upload_max_request_mb << 20) + 1
            resp = await c.post(
                UPLOAD, content=b"x", headers={"Content-Length": str(too_big)}
            )
            assert resp.status_code == 413
    finally:
        app.dependency_overrides.clear()
