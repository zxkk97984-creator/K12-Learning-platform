import asyncio
import json

from app.ai.voice import AliyunASRProvider


class FakeWebSocket:
    def __init__(self, requested_models: list[str]):
        self.requested_models = requested_models
        self.incoming: asyncio.Queue[str] = asyncio.Queue()
        self.closed = False

    async def send(self, data):
        if isinstance(data, bytes):
            return
        message = json.loads(data)
        if message.get("header", {}).get("action") != "run-task":
            if message.get("header", {}).get("action") == "finish-task":
                await self.incoming.put(
                    json.dumps(
                        {
                            "header": {"event": "result-generated"},
                            "payload": {
                                "output": {
                                    "sentence": {"text": "测试内容", "sentence_end": True}
                                }
                            },
                        }
                    )
                )
            return
        model = message["payload"]["model"]
        self.requested_models.append(model)
        if model == "asr-a":
            await self.incoming.put(
                json.dumps(
                    {
                        "header": {
                            "event": "task-failed",
                            "error_code": "AllocationQuota.FreeTierOnly",
                            "error_message": "free quota exhausted",
                        },
                        "payload": {},
                    }
                )
            )
        else:
            await self.incoming.put(
                json.dumps({"header": {"event": "task-started"}, "payload": {}})
            )

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.closed:
            raise StopAsyncIteration
        return await self.incoming.get()

    async def close(self):
        self.closed = True

    async def wait_closed(self):
        return None


def test_aliyun_asr_switches_after_free_quota_error():
    async def run():
        requested_models: list[str] = []

        async def connect(*args, **kwargs):
            assert kwargs["additional_headers"] == {
                "Authorization": "Bearer test-key",
                "X-DashScope-DataInspection": "disable",
            }
            return FakeWebSocket(requested_models)

        provider = AliyunASRProvider(
            api_key="test-key",
            models=["asr-a", "asr-b"],
            connect=connect,
        )

        session = await provider.start_session()

        assert session.model_name == "asr-b"
        assert requested_models == ["asr-a", "asr-b"]
        assert provider.exhausted_models == ("asr-a",)
        await session.abort()

    asyncio.run(run())


def test_aliyun_asr_transcribe_async_returns_final_text():
    async def run():
        async def connect(*args, **kwargs):
            websocket = FakeWebSocket([])
            await websocket.incoming.put(
                json.dumps({"header": {"event": "task-started"}, "payload": {}})
            )
            return websocket

        provider = AliyunASRProvider(api_key="test-key", models=["asr-b"], connect=connect)
        text = await provider.transcribe_async(b"\x00\x01" * 1600)

        assert text == "测试内容"

    asyncio.run(run())
