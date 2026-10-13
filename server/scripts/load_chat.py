"""Load check cho chat SSE: N stream song song, in TTFT / tổng thời gian.

Chạy: cd server && uv run python scripts/load_chat.py \\
        --users 20 --questions 3 --conversation ID --token T
--conversation / --token lặp lại được (user thứ i dùng cặp thứ i % len),
để mô phỏng nhiều user khác nhau (mỗi user chỉ được 1 stream).
"""

import argparse
import asyncio
import json
import statistics
import time
from collections import Counter

import httpx

QUESTIONS = (
    "What is the main contribution of this document?",
    "Summarize the method in two sentences.",
    "What results are reported?",
    "What are the limitations?",
)


async def one_stream(
    client: httpx.AsyncClient, base: str, conv: str, token: str, q: str
) -> tuple[str, float | None, float]:
    start = time.perf_counter()
    ttft = None
    outcome = "ok"
    async with client.stream(
        "POST",
        f"{base}/conversation/{conv}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": q},
    ) as r:
        if r.status_code != 200:
            await r.aread()
            return str(r.status_code), None, time.perf_counter() - start
        event = None
        async for line in r.aiter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                if event == "token" and ttft is None:
                    ttft = time.perf_counter() - start
                elif event == "error":
                    outcome = "error: " + json.loads(line[5:])["detail"][:60]
    return outcome, ttft, time.perf_counter() - start


async def user(client, args, i: int, results: list) -> None:
    conv = args.conversation[i % len(args.conversation)]
    token = args.token[i % len(args.token)]
    for n in range(args.questions):
        q = QUESTIONS[(i + n) % len(QUESTIONS)]
        try:
            results.append(await one_stream(client, args.base, conv, token, q))
        except httpx.HTTPError as e:
            results.append((f"http: {type(e).__name__}", None, 0.0))


def pct(values: list[float], p: float) -> str:
    if not values:
        return "-"
    values = sorted(values)
    return f"{values[min(len(values) - 1, int(p * len(values)))]:.2f}s"


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--users", type=int, default=10)
    p.add_argument("--questions", type=int, default=1)
    p.add_argument("--conversation", action="append", required=True)
    p.add_argument("--token", action="append", required=True)
    p.add_argument("--base", default="http://localhost:8000/api")
    args = p.parse_args()

    results: list[tuple[str, float | None, float]] = []
    limits = httpx.Limits(max_connections=args.users)
    async with httpx.AsyncClient(timeout=300, limits=limits) as client:
        await asyncio.gather(
            *(user(client, args, i, results) for i in range(args.users))
        )

    ok = [r for r in results if r[0] == "ok"]
    ttfts = [r[1] for r in ok if r[1] is not None]
    totals = [r[2] for r in ok]
    print(f"requests={len(results)} ok={len(ok)}")
    print(f"TTFT  p50={pct(ttfts, 0.5)} p95={pct(ttfts, 0.95)}")
    print(f"total p50={pct(totals, 0.5)} p95={pct(totals, 0.95)}")
    if totals:
        print(f"mean total={statistics.mean(totals):.2f}s")
    print("outcomes:", dict(Counter(r[0] for r in results)))


if __name__ == "__main__":
    asyncio.run(main())
