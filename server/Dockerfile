FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .

EXPOSE 8000
# TMPDIR phải tồn tại trước khi Python khởi động (multipart spooling)
CMD ["sh", "-c", "mkdir -p \"$TMPDIR\" && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
