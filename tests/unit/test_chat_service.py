import unittest

from eco_rag.chat import ChatService, Response


class FakeModel:
    async def generate_response(self, messages, tools=None, stop=None, callbacks=None, **kwargs):
        latest_user = next(message["content"] for message in reversed(messages) if message["role"] == "user")
        return Response(
            content=f"echo:{latest_user}",
            token_usage={
                "prompt_tokens": len(messages) * 10,
                "completion_tokens": 4,
                "total_tokens": len(messages) * 10 + 4,
            },
            raw_response=None,
        )

    async def stream_response(self, messages, tools=None, stop=None, callbacks=None, **kwargs):
        usage = {
            "prompt_tokens": len(messages) * 10,
            "completion_tokens": 4,
            "total_tokens": len(messages) * 10 + 4,
        }
        if isinstance(callbacks, dict) and callable(callbacks.get("on_usage")):
            callbacks["on_usage"](usage)
        for chunk in ["echo:", next(message["content"] for message in reversed(messages) if message["role"] == "user")]:
            yield chunk


def fake_model_factory(_settings=None):
    return FakeModel()


class ChatServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_message_creates_session_and_reply(self):
        service = ChatService(model_factory=fake_model_factory, storage={})

        result = await service.send_message(
            message="hello there",
            session_id="test-session",
            system_prompt="Be helpful.",
        )

        self.assertEqual(result.reply, "echo:hello there")
        self.assertEqual(result.session["title"], "hello there")
        self.assertEqual([item["role"] for item in result.messages], ["system", "user", "assistant"])
        self.assertEqual(result.messages[-1]["token_usage"]["total_tokens"], 24)
        self.assertEqual(result.session["total_tokens"], 24)

    async def test_update_and_regenerate_keep_context_until_regen(self):
        service = ChatService(model_factory=fake_model_factory, storage={})
        initial = await service.send_message(message="first question", session_id="session-a")
        user_message_id = next(item["id"] for item in initial.messages if item["role"] == "user")

        updated = await service.update_message("session-a", user_message_id, "edited question")
        self.assertEqual([item["role"] for item in updated.messages], ["user", "assistant"])
        self.assertEqual(updated.messages[0]["content"], "edited question")

        regenerated = await service.regenerate_message("session-a", user_message_id)
        self.assertEqual(regenerated.reply, "echo:edited question")
        self.assertEqual([item["role"] for item in regenerated.messages], ["user", "assistant"])
        regenerated_assistant_id = next(item["id"] for item in regenerated.messages if item["role"] == "assistant")

        rollback = await service.rollback_message("session-a", regenerated_assistant_id)
        self.assertEqual([item["role"] for item in rollback.messages], ["user", "assistant"])

    async def test_update_system_prompt_preserves_following_messages(self):
        service = ChatService(model_factory=fake_model_factory, storage={})
        await service.send_message(
            message="first question",
            session_id="session-system",
            system_prompt="Initial prompt",
        )

        updated = await service.update_system_prompt("session-system", "Updated prompt")

        self.assertEqual([item["role"] for item in updated.messages], ["system", "user", "assistant"])
        self.assertEqual(updated.messages[0]["content"], "Updated prompt")

    async def test_stream_message_persists_reply_and_token_usage(self):
        service = ChatService(model_factory=fake_model_factory, storage={})

        events = [item async for item in service.stream_message("hello stream", "stream-session")]

        self.assertEqual(events[0]["event"], "chunk")
        self.assertEqual(events[-1]["event"], "done")
        self.assertEqual(events[-1]["data"]["reply"], "echo:hello stream")
        self.assertEqual(events[-1]["data"]["session"]["total_tokens"], 14)

    async def test_session_lifecycle(self):
        service = ChatService(model_factory=fake_model_factory, storage={})

        created = service.create_session(session_id="manual", title="Manual")
        self.assertEqual(created["title"], "Manual")

        sessions = service.list_sessions()
        self.assertEqual(sessions[0]["session_id"], "manual")

        service.delete_session("manual")
        self.assertEqual(service.list_sessions(), [])


if __name__ == "__main__":
    unittest.main()
