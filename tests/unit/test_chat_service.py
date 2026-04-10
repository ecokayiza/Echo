import unittest

from eco_rag.chat import ChatService, Response


class FakeModel:
    async def generate_response(self, messages, tools=None, stop=None, callbacks=None, **kwargs):
        system = messages[0]["content"]

        if "Workflow Node: plan" in system:
            return Response(
                content='{"next_step":"answer","reason":"Direct answer is enough."}',
                token_usage={"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
                raw_response=None,
            )

        raise AssertionError("Only the planner should run before the final answer in this test.")

    async def stream_response(self, messages, tools=None, stop=None, callbacks=None, **kwargs):
        latest_user = next(message["content"] for message in reversed(messages) if message["role"] == "user")
        if isinstance(callbacks, dict) and callable(callbacks.get("on_usage")):
            callbacks["on_usage"]({"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14})
        yield "echo:"
        yield latest_user


def fake_model_factory(_settings=None):
    return FakeModel()


class ChatServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_message_creates_session_and_reply(self):
        service = ChatService(model_factory=fake_model_factory, storage={})

        events = [item async for item in service.stream_message("hello there", "test-session", system_prompt="Be helpful.")]

        self.assertEqual(events[0]["event"], "workflow")
        self.assertIn("chunk", [item["event"] for item in events])
        self.assertEqual(events[-1]["event"], "done")
        self.assertEqual(events[-1]["data"]["reply"], "echo:hello there")
        self.assertEqual(events[-1]["data"]["session"]["title"], "hello there")
        self.assertEqual([item["role"] for item in events[-1]["data"]["messages"]], ["system", "user", "assistant"])
        self.assertEqual(events[-1]["data"]["session"]["total_tokens"], 20)
        self.assertEqual(events[-1]["data"]["workflow"]["status"], "completed")
        self.assertEqual(events[-1]["data"]["messages"][-1]["workflow"]["answer"], "echo:hello there")

    async def test_update_and_stream_regenerate_keep_context_until_regen(self):
        service = ChatService(model_factory=fake_model_factory, storage={})
        initial_events = [item async for item in service.stream_message("first question", "session-a")]
        initial = initial_events[-1]["data"]
        user_message_id = next(item["id"] for item in initial["messages"] if item["role"] == "user")

        updated = await service.update_message("session-a", user_message_id, "edited question")
        self.assertEqual([item["role"] for item in updated.messages], ["user", "assistant"])
        self.assertEqual(updated.messages[0]["content"], "edited question")

        regenerated_events = [item async for item in service.stream_regenerate_message("session-a", user_message_id)]
        regenerated = regenerated_events[-1]["data"]
        self.assertEqual(regenerated["reply"], "echo:edited question")
        self.assertEqual([item["role"] for item in regenerated["messages"]], ["user", "assistant"])
        regenerated_assistant_id = next(item["id"] for item in regenerated["messages"] if item["role"] == "assistant")

        rollback = await service.rollback_message("session-a", regenerated_assistant_id)
        self.assertEqual([item["role"] for item in rollback.messages], ["user", "assistant"])

    async def test_delete_message_removes_only_the_selected_message(self):
        service = ChatService(model_factory=fake_model_factory, storage={})
        events = [item async for item in service.stream_message("first question", "session-delete")]
        payload = events[-1]["data"]
        assistant_message_id = next(item["id"] for item in payload["messages"] if item["role"] == "assistant")

        deleted = await service.delete_message("session-delete", assistant_message_id)

        self.assertEqual([item["role"] for item in deleted.messages], ["user"])

    async def test_update_system_prompt_preserves_following_messages(self):
        service = ChatService(model_factory=fake_model_factory, storage={})
        [item async for item in service.stream_message("first question", "session-system", system_prompt="Initial prompt")]
        [item async for item in service.stream_message("second question", "session-system")]

        updated = await service.update_system_prompt("session-system", "Updated prompt")

        self.assertEqual([item["role"] for item in updated.messages], ["system", "user", "assistant", "user", "assistant"])
        self.assertEqual(updated.messages[0]["content"], "Updated prompt")

    async def test_session_lifecycle(self):
        service = ChatService(model_factory=fake_model_factory, storage={})

        created = service.create_session(session_id="manual", title="Manual")
        self.assertEqual(created["title"], "Manual")

        sessions = service.list_sessions()
        self.assertEqual(sessions[0]["session_id"], "manual")

        service.delete_session("manual")
        self.assertEqual(service.list_sessions(), [])

    async def test_workflow_metadata_is_persisted_on_assistant_messages(self):
        service = ChatService(model_factory=fake_model_factory, storage={})

        [item async for item in service.stream_message("remember workflow", "persisted")]
        state = service.get_session_state("persisted")

        self.assertEqual(state.messages[-1]["role"], "assistant")
        self.assertEqual(state.messages[-1]["workflow"]["answer"], "echo:remember workflow")
        self.assertEqual(state.messages[-1]["workflow"]["trace"][0]["node"], "plan")


if __name__ == "__main__":
    unittest.main()
