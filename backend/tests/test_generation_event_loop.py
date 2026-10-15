import asyncio
from threading import Event
from types import SimpleNamespace

from app.modules.chat.rag import generation


async def test_stream_model_setup_does_not_block_other_coroutines(monkeypatch):
    entered = asyncio.Event()
    release = Event()
    loop = asyncio.get_running_loop()

    def resolve(_model):
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(2), "Synchronous model setup blocked the event loop"
        return "test", "test-model", {}

    class Client:
        async def astream(self, messages):
            assert "420000" in str(messages)
            yield SimpleNamespace(content="The grant budget is 420000 dollars.")

    monkeypatch.setattr(generation, "resolve_generation_target", resolve)
    monkeypatch.setattr(generation, "create_chat_client", lambda *_: Client())

    async def collect():
        return [
            token
            async for token in generation.generate_answer_streaming(
                "What is the grant budget?", "Policy excerpt: the grant budget is 420000 dollars."
            )
        ]

    task = asyncio.create_task(collect())
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        release.set()
        assert "420000" in "".join(await task)
    finally:
        release.set()
