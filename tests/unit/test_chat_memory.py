import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from eco_rag.chat import Messages, Sessions


class ChatMemoryTests(unittest.TestCase):
    def test_sliding_window_keeps_recent_messages(self):
        sessions = Sessions(session_id="window", storage={})
        messages = Messages(
            sessions=sessions,
            max_context_messages=2,
            preserve_system_messages=False,
        )
        messages.append("user", "one", message_type="user")
        messages.append("assistant", "two", message_type="answer")
        messages.append("user", "three", message_type="user")

        context = messages.build_context()

        self.assertEqual(
            context,
            [
                {"role": "assistant", "content": "two"},
                {"role": "user", "content": "three"},
            ],
        )

    def test_sessions_are_listed_and_isolated(self):
        storage = {}
        first_sessions = Sessions(session_id="first", storage=storage)
        second_sessions = Sessions(session_id="second", storage=storage)
        first_messages = Messages(sessions=first_sessions)
        second_messages = Messages(sessions=second_sessions)

        first_messages.append("user", "hello", message_type="user")
        second_messages.append("user", "world", message_type="user")

        sessions = first_sessions.list()

        self.assertEqual({session["session_id"] for session in sessions}, {"first", "second"})
        self.assertEqual(first_messages.history()[0]["content"], "hello")
        self.assertEqual(second_messages.history()[0]["content"], "world")

    def test_file_store_persists_session_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            first_sessions = Sessions(session_id="chat/main", base_dir=tmpdir)
            first_messages = Messages(sessions=first_sessions)
            first_messages.append("user", "persist me", message_type="user")
            first_messages.append(
                "assistant",
                "still here",
                message_type="answer",
                token_usage={
                    "prompt_tokens": 12,
                    "completion_tokens": 5,
                    "total_tokens": 17,
                    "prompt_cache_hit_tokens": 7,
                    "prompt_cache_miss_tokens": 5,
                },
            )

            session_file = next(Path(tmpdir).glob("*.json"))
            payload = json.loads(session_file.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["usage"],
                {
                    "prompt_tokens": 12,
                    "completion_tokens": 5,
                    "total_tokens": 17,
                    "prompt_cache_hit_tokens": 7,
                },
            )
            self.assertEqual(
                payload["messages"][-1]["token_usage"],
                {
                    "prompt_tokens": 12,
                    "prompt_cache_hit_tokens": 7,
                    "completion_tokens": 5,
                    "total_tokens": 17,
                },
            )

            reloaded_sessions = Sessions(session_id="chat/main", base_dir=tmpdir)
            reloaded_messages = Messages(sessions=reloaded_sessions)
            history = reloaded_messages.history()

            self.assertEqual([item["content"] for item in history], ["persist me", "still here"])
            self.assertEqual([item["role"] for item in history], ["user", "assistant"])
            self.assertEqual(
                history[-1]["token_usage"],
                {
                    "prompt_tokens": 12,
                    "prompt_cache_hit_tokens": 7,
                    "completion_tokens": 5,
                    "total_tokens": 17,
                },
            )
            self.assertEqual(reloaded_sessions.summary()["total_tokens"], 17)
            self.assertEqual(reloaded_sessions.summary()["token_usage"]["prompt_cache_hit_tokens"], 7)
            self.assertNotIn("prompt_cache_miss_tokens", payload["usage"])

    def test_next_turn_context_prefers_last_think_over_answer(self):
        sessions = Sessions(session_id="workflow-think", storage={})
        messages = Messages(sessions=sessions)
        messages.append("user", "hello", message_type="user")
        messages.append(
            "assistant",
            "[plan]\nNeed retrieval.\n[next]\nretrieve\n[retrieve]\nlegacy_search(\"hello\")",
            message_type="plan",
            workflow_turn_id="turn-1",
        )
        messages.append(
            "tool",
            "[tool]\nlegacy_search(query='hello')",
            message_type="tool",
            workflow_turn_id="turn-1",
            tool_name="legacy_search",
        )
        messages.append(
            "assistant",
            "[think]\nThe evidence is enough.\n[next]\nanswer\n[answer]\nworld",
            message_type="think",
            workflow_turn_id="turn-1",
        )
        messages.append(
            "assistant",
            "world",
            message_type="answer",
            workflow_turn_id="turn-1",
        )

        history = messages.history()
        context = messages.build_context()

        self.assertEqual(history[1]["message_type"], "plan")
        self.assertEqual(history[2]["role"], "tool")
        self.assertEqual(history[2]["tool_name"], "legacy_search")
        self.assertNotIn("workflow", history[-1])
        self.assertEqual(
            context,
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "[think]\nThe evidence is enough."},
            ],
        )

    def test_next_turn_context_uses_plan_for_direct_answer_turn(self):
        sessions = Sessions(session_id="workflow-plan", storage={})
        messages = Messages(sessions=sessions)
        messages.append("user", "hi", message_type="user")
        messages.append(
            "assistant",
            "[plan]\nThis is a greeting.\n[next]\nanswer\n[answer]\nHello!",
            message_type="plan",
            workflow_turn_id="turn-1",
        )
        messages.append(
            "assistant",
            "Hello!",
            message_type="answer",
            workflow_turn_id="turn-1",
        )

        context = messages.build_context()

        self.assertEqual(
            context,
            [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "[plan]\nThis is a greeting."},
            ],
        )


class ChatMutationTests(unittest.IsolatedAsyncioTestCase):
    async def test_internal_workflow_messages_are_read_only(self):
        sessions = Sessions(session_id="readonly", storage={})
        messages = Messages(sessions=sessions)
        plan_message = messages.append(
            "assistant",
            "[plan]\nNeed retrieval.",
            message_type="plan",
            workflow_turn_id="turn-1",
        )

        with self.assertRaisesRegex(ValueError, "read-only"):
            await messages.apply("edit", message_id=plan_message.id, content="changed")
        with self.assertRaisesRegex(ValueError, "read-only"):
            await messages.apply("delete", message_id=plan_message.id)
        with self.assertRaisesRegex(ValueError, "read-only"):
            await messages.apply("rollback", message_id=plan_message.id)
        with self.assertRaisesRegex(ValueError, "read-only"):
            await messages.apply("regenerate", message_id=plan_message.id, response_factory=lambda _context: ("x", None))

    async def test_system_prompt_reset_keeps_one_top_level_system_message(self):
        sessions = Sessions(session_id="system", storage={})
        messages = Messages(sessions=sessions, default_system_prompt="default system")
        messages.ensure_system_prompt()

        await messages.apply("system_prompt", content="custom system")
        state = sessions.get()
        self.assertEqual([item.role for item in state["messages"]], ["system"])
        self.assertEqual(state["messages"][0].content, "custom system")

        await messages.apply("delete", message_id=state["messages"][0].id)
        state = sessions.get()
        self.assertEqual([item.role for item in state["messages"]], ["system"])
        self.assertEqual(state["messages"][0].content, "default system")


if __name__ == "__main__":
    unittest.main()
