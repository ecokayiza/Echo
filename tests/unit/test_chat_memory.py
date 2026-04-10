import json
import tempfile
import unittest
from pathlib import Path

from eco_rag.chat import (
    Messages,
    Sessions,
)


class ChatMemoryTests(unittest.TestCase):
    def test_sliding_window_keeps_recent_messages(self):
        sessions = Sessions(session_id="window", storage={})
        messages = Messages(
            sessions=sessions,
            max_context_messages=2,
            preserve_system_messages=False,
        )
        messages.append("user", "one")
        messages.append("assistant", "two")
        messages.append("user", "three")

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

        first_messages.append("user", "hello")
        second_messages.append("user", "world")

        sessions = first_sessions.list()

        self.assertEqual({session["session_id"] for session in sessions}, {"first", "second"})
        self.assertEqual(first_messages.history()[0]["content"], "hello")
        self.assertEqual(second_messages.history()[0]["content"], "world")

    def test_file_store_persists_session_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            first_sessions = Sessions(session_id="chat/main", base_dir=tmpdir)
            first_messages = Messages(sessions=first_sessions)
            first_messages.append("user", "persist me")
            first_messages.append(
                "assistant",
                "still here",
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

    def test_workflow_metadata_persists_without_entering_llm_context(self):
        sessions = Sessions(session_id="workflow", storage={})
        messages = Messages(sessions=sessions)
        messages.append("user", "hello")
        messages.append(
            "assistant",
            "world",
            workflow={
                "status": "completed",
                "answer": "world",
                "trace": [{"node": "plan", "output": '{"next_step":"answer"}'}],
            },
        )

        history = messages.history()
        context = messages.build_context()

        self.assertEqual(history[-1]["workflow"]["answer"], "world")
        self.assertEqual(history[-1]["workflow"]["trace"][0]["node"], "plan")
        self.assertEqual(
            context,
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "world"},
            ],
        )

if __name__ == "__main__":
    unittest.main()
