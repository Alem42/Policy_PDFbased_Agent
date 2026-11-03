import asyncio

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient

from app.core.concurrency_limit import ConcurrencyLimitMiddleware, TurnLimit


def build(limit, release):
    app = FastAPI()

    @app.post("/chat/stream")
    async def stream():
        async def events():
            yield "data: start\n\n"
            await release.wait()
            yield "data: done\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/other")
    async def other():
        return {"ok": True}

    app.add_middleware(ConcurrencyLimitMiddleware, paths={"/chat/stream"}, limit=limit)
    return app


def test_a_stream_holds_its_slot_until_finished_and_extra_turns_get_503():
    async def scenario():
        limit, release = TurnLimit(limit=1, wait_seconds=0.2), asyncio.Event()
        transport = ASGITransport(app=build(limit, release))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = asyncio.create_task(client.post("/chat/stream"))
            for _ in range(50):
                if limit.active:
                    break
                await asyncio.sleep(0.01)
            busy = await client.post("/chat/stream")
            unrelated = await client.post("/other")
            release.set()
            done = await first
            after = await client.post("/chat/stream")
        return limit, busy, unrelated, done, after

    release_first = asyncio.run(scenario())
    limit, busy, unrelated, done, after = release_first
    assert busy.status_code == 503 and busy.headers["retry-after"] == "5"
    assert unrelated.status_code == 200
    assert done.status_code == 200 and "done" in done.text
    assert after.status_code == 200
    assert limit.snapshot() == {
        "scope": "per_process",
        "limit": 1,
        "active": 0,
        "waiting": 0,
        "rejected": 1,
    }
