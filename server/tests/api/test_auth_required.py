import re

import httpx
from fastapi.routing import APIRoute, iter_route_contexts

from app.main import app

PUBLIC = ("/api/auth", "/api/heartbeat")


def api_routes():
    # FastAPI 0.141 lồng router con → duyệt qua route context đã phẳng hóa
    return [
        rc for rc in iter_route_contexts(app.routes) if isinstance(rc.route, APIRoute)
    ]


def protected_routes():
    for rc in api_routes():
        if rc.path.startswith("/api") and not rc.path.startswith(PUBLIC):
            for method in rc.methods:
                yield method, re.sub(r"\{[^}]+\}", "x", rc.path)


async def test_every_user_data_route_requires_token():
    # ASGITransport không chạy lifespan → không cần DB
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        routes = list(protected_routes())
        assert len(routes) >= 10
        for method, path in routes:
            resp = await c.request(method, path)
            assert resp.status_code == 401, (method, path, resp.status_code)


def test_old_stream_endpoint_removed():
    paths = {rc.path for rc in api_routes()}
    assert "/api/conversation/stream" not in paths
