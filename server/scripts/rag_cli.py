"""CLI để test RAG core: ingest / docs / chunks / search / ask / eval-gen / eval.

Chạy: cd server && uv run python scripts/rag_cli.py <cmd>
"""

import argparse
import asyncio
import glob
import json
import os
import statistics
import sys
import time
import traceback
from pathlib import Path

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, SERVER_DIR)

from sqlalchemy import select, text  # noqa: E402

from app.config import settings  # noqa: E402
from app.core import factory  # noqa: E402
from app.core.domain import (  # noqa: E402
    ContextsEvent,
    FinalEvent,
    ScoredChunk,
    SearchScope,
    TokenEvent,
)
from app.core.errors import RAGError  # noqa: E402
from app.core.llm.gemini_provider import GeminiProvider  # noqa: E402
from app.core.llm.post_processor import PostProcessor  # noqa: E402
from app.core.storage.chunk_repository import PgChunkRepository  # noqa: E402
from app.core.storage.document_repository import (  # noqa: E402
    PgDocumentRepository,
)
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models.user import User  # noqa: E402

EVAL_MODES = ("dense", "sparse", "hybrid", "hybrid+rerank")


class CLIError(RAGError):
    pass


async def resolve_user(username: str) -> str:
    async with AsyncSessionLocal() as session:
        user = (
            (await session.execute(select(User).where(User.username == username)))
            .scalars()
            .first()
        )
    if user is None:
        raise CLIError(f"Không tìm thấy user '{username}' (chạy seed.py?)")
    return user.id


def fmt_timings(timings) -> str:
    return " ".join(f"{k}={v:.0f}ms" for k, v in timings.items())


def snippet(content: str, n: int = 100) -> str:
    return " ".join(content.split())[:n]


def pages(a: int, b: int) -> str:
    return f"{a}" if a == b else f"{a}-{b}"


# ---------------------------------------------------------------- ingest
async def cmd_ingest(args) -> int:
    user_id = await resolve_user(args.user)
    paths: list[str] = []
    for pattern in args.paths:
        matched = sorted(glob.glob(pattern))
        paths.extend(matched or [pattern])
    pipeline = factory.build_ingestion_pipeline()
    ok = skipped = failed = 0
    for p in paths:
        try:
            report = await pipeline.ingest(Path(p), user_id, force=args.force)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAILED {p}: {type(e).__name__}: {e}")
            if args.debug:
                traceback.print_exc()
            continue
        if report.skipped:
            skipped += 1
            print(f"SKIPPED {p} (id={report.document_id})")
        else:
            ok += 1
            print(
                f"OK {p}\n  id={report.document_id} title={report.title!r} "
                f"pages={report.num_pages} chunks={report.num_chunks}\n"
                f"  {fmt_timings(report.timings_ms)}"
            )
    print(f"\nTotal: ok={ok} skipped={skipped} failed={failed}")
    return 1 if failed else 0


# ------------------------------------------------------------------ docs
async def cmd_docs(args) -> int:
    user_id = await resolve_user(args.user)
    docs = await PgDocumentRepository(AsyncSessionLocal).list_for_user(user_id)
    print(
        f"{'id':36} | {'name':24} | {'title':32} | {'status':10} | "
        f"{'chunks':6} | indexed_at"
    )
    for d in docs:
        print(
            f"{d.id:36} | {d.name[:24]:24} | {(d.title or '')[:32]:32} | "
            f"{d.status.value:10} | {d.num_chunks:6} | {d.indexed_at or ''}"
        )
    return 0


# ---------------------------------------------------------------- chunks
async def cmd_chunks(args) -> int:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT chunk_index, page_start, page_end, section, "
                    "token_count, content FROM document_chunks "
                    "WHERE document_id = :d ORDER BY chunk_index LIMIT :n"
                ),
                {"d": args.doc_id, "n": args.limit},
            )
        ).all()
    for r in rows:
        print(
            f"#{r.chunk_index} p.{pages(r.page_start, r.page_end)} "
            f"tokens={r.token_count} section={r.section!r}\n"
            f"   {snippet(r.content, 200)}"
        )
    if not rows:
        print("Không có chunk nào.")
    return 0


# ---------------------------------------------------------------- search
def print_hits(chunks) -> None:
    for i, c in enumerate(chunks, 1):
        ch = c.chunk
        sc = " ".join(f"{k}={v:.4f}" for k, v in c.scores.items())
        print(
            f"{i:>2}. {ch.document_name} p.{pages(ch.page_start, ch.page_end)}"
            f" [{ch.section or '-'}]\n    {sc}\n    {snippet(ch.content)}"
        )


async def cmd_search(args) -> int:
    user_id = await resolve_user(args.user)
    scope = SearchScope(user_id, tuple(args.doc) if args.doc else None)
    service = factory.build_rag_service(mode=args.mode)
    result = await service.search(args.query, scope, rerank=args.rerank, k=args.k)
    if args.json:
        print(
            json.dumps(
                {
                    "hits": [
                        {
                            "document": c.chunk.document_name,
                            "pages": [c.chunk.page_start, c.chunk.page_end],
                            "section": c.chunk.section,
                            "scores": dict(c.scores),
                            "ranks": dict(c.ranks),
                            "content": c.chunk.content,
                        }
                        for c in result.chunks
                    ],
                    "timings_ms": dict(result.timings_ms),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print_hits(result.chunks)
    print(f"\ntimings: {fmt_timings(result.timings_ms)}")
    return 0


# ------------------------------------------------------------------- ask
async def cmd_ask(args) -> int:
    user_id = await resolve_user(args.user)
    scope = SearchScope(user_id, tuple(args.doc) if args.doc else None)
    service = factory.build_rag_service(reranker=args.reranker)

    if args.no_stream:
        answer = await service.answer(args.query, scope)
        print(answer.text)
    else:
        answer = None
        async for event in service.answer_stream(args.query, scope):
            if isinstance(event, ContextsEvent):
                if args.show_context:
                    print_contexts(event.contexts)
            elif isinstance(event, TokenEvent):
                print(event.text, end="", flush=True)
            elif isinstance(event, FinalEvent):
                answer = event.answer
        print()
    if args.no_stream and args.show_context:
        print_contexts(answer.contexts)

    print("\nSources:")
    for c in answer.citations:
        print(
            f"  [{c.ref}] {c.document_name} — " f"p.{pages(c.page_start, c.page_end)}"
        )
    print(f"grounded={answer.grounded} refused={answer.refused}")
    print(f"timings: {fmt_timings(answer.timings_ms)}")
    return 0


def print_contexts(contexts) -> None:
    print("--- contexts ---")
    for b in contexts:
        print(
            f"[{b.ref}] {b.document_name} p.{pages(b.page_start, b.page_end)}"
            f" [{b.section or '-'}]\n{b.text}\n"
        )
    print("--- answer ---")


# --------------------------------------------------------------- eval-gen
GEN_PROMPT = (
    "Write one specific question answerable only from this passage. "
    'Return JSON {{"question": "..."}}\n\nPassage:\n{passage}'
)


async def cmd_eval_gen(args) -> int:
    user_id = await resolve_user(args.user)
    scope = SearchScope(user_id, (args.doc,))
    chunks = await PgChunkRepository(AsyncSessionLocal).sample(scope, args.n)
    llm = GeminiProvider()
    processor = PostProcessor()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with out.open("w", encoding="utf-8") as f:
        for i, c in enumerate(chunks, 1):
            resp = await llm.generate(
                GEN_PROMPT.format(passage=c.content), stream=False
            )
            try:
                data = processor.process(resp.text or "", return_json=True)
                question = str(data["question"]).strip()
            except (ValueError, KeyError) as e:
                print(f"skip chunk {c.chunk_id}: {e}")
                continue
            f.write(
                json.dumps(
                    {
                        "id": f"q{i:03d}",
                        "question": question,
                        "document_name": c.document_name,
                        "relevant_pages": list(range(c.page_start, c.page_end + 1)),
                        "source_chunk_id": c.chunk_id,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            written += 1
    print(f"Wrote {written} questions to {out}")
    return 0


# ------------------------------------------------------------------ eval
def is_relevant(c: ScoredChunk, item: dict) -> bool:
    ch = c.chunk
    if ch.document_name != item["document_name"]:
        return False
    return any(ch.page_start <= p <= ch.page_end for p in item["relevant_pages"])


def metrics(chunks, item: dict, k: int) -> tuple[float, float, float]:
    top = chunks[:k]
    hit = 0.0
    mrr = 0.0
    covered: set[int] = set()
    for rank, c in enumerate(top, 1):
        if is_relevant(c, item):
            hit = 1.0
            mrr = mrr or 1.0 / rank
            covered |= {
                p
                for p in item["relevant_pages"]
                if c.chunk.page_start <= p <= c.chunk.page_end
            }
    recall = len(covered) / len(item["relevant_pages"])
    return hit, mrr, recall


async def cmd_eval(args) -> int:
    user_id = await resolve_user(args.user)
    scope = SearchScope(user_id)
    ks = sorted(int(x) for x in args.k.split(","))
    modes = [m.strip() for m in args.modes.split(",")]
    for m in modes:
        if m not in EVAL_MODES:
            raise CLIError(f"Mode không hợp lệ: {m} (chọn {EVAL_MODES})")
    items = [
        json.loads(line)
        for line in Path(args.golden).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not items:
        raise CLIError("Golden set rỗng")

    print(f"{len(items)} questions")
    print(f"{'mode':16} {'k':>3} {'Hit@k':>7} {'MRR@k':>7} {'PageRecall@k':>13}")
    for mode in modes:
        base, rerank = ("hybrid", True) if mode == "hybrid+rerank" else (mode, False)
        service = factory.build_rag_service(mode=base)
        service.min_score = None  # eval đo xếp hạng, không lọc ngưỡng
        service.min_dense_score = None
        per_k = {k: [] for k in ks}
        latencies: list[float] = []
        for item in items:
            t = time.perf_counter()
            result = await service.search(
                item["question"], scope, rerank=rerank, k=max(ks)
            )
            latencies.append((time.perf_counter() - t) * 1000)
            for k in ks:
                per_k[k].append(metrics(result.chunks, item, k))
        for k in ks:
            rows = per_k[k]
            print(
                f"{mode:16} {k:>3} "
                f"{statistics.mean(r[0] for r in rows):>7.3f} "
                f"{statistics.mean(r[1] for r in rows):>7.3f} "
                f"{statistics.mean(r[2] for r in rows):>13.3f}"
            )
        print(f"{mode:16} latency p50 = {statistics.median(latencies):.0f} ms")
    return 0


# ------------------------------------------------------------------ main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Doc-Mind RAG CLI")
    p.add_argument("--debug", action="store_true", help="in traceback")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_user(sp):
        sp.add_argument("--user", default=settings.first_superuser)

    s = sub.add_parser("ingest")
    s.add_argument("paths", nargs="+")
    add_user(s)
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_ingest)

    s = sub.add_parser("docs")
    add_user(s)
    s.set_defaults(func=cmd_docs)

    s = sub.add_parser("chunks")
    s.add_argument("doc_id")
    s.add_argument("--limit", type=int, default=5)
    s.set_defaults(func=cmd_chunks)

    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--mode", choices=["dense", "sparse", "hybrid"], default="hybrid")
    s.add_argument("--rerank", action=argparse.BooleanOptionalAction, default=True)
    s.add_argument("-k", type=int, default=10)
    s.add_argument("--doc", action="append")
    s.add_argument("--json", action="store_true")
    add_user(s)
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("ask")
    s.add_argument("query")
    s.add_argument("--doc", action="append")
    s.add_argument("--no-stream", action="store_true")
    s.add_argument("--show-context", action="store_true")
    s.add_argument("--reranker", choices=["laya", "none"])
    add_user(s)
    s.set_defaults(func=cmd_ask)

    s = sub.add_parser("eval-gen")
    s.add_argument("--doc", required=True)
    s.add_argument("--n", type=int, default=20)
    s.add_argument("-o", "--output", default="eval/golden.jsonl")
    add_user(s)
    s.set_defaults(func=cmd_eval_gen)

    s = sub.add_parser("eval")
    s.add_argument("golden")
    s.add_argument("--k", default="1,3,5,10")
    s.add_argument("--modes", default=",".join(EVAL_MODES))
    add_user(s)
    s.set_defaults(func=cmd_eval)
    return p


async def run(args) -> int:
    try:
        return await args.func(args)
    except RAGError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        return 1
    finally:
        await engine.dispose()


def main() -> int:
    args = build_parser().parse_args()  # lỗi tham số: argparse thoát mã 2
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
