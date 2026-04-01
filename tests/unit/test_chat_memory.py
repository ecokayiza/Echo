import tempfile
import unittest

from eco_rag.chat import (
    FileSessionStore,
    InMemorySessionStore,
    Messages,
    Sessions,
    SlidingWindowMemoryPolicy,
)


class ChatMemoryTests(unittest.TestCase):
    def test_sliding_window_keeps_recent_messages(self):
        sessions = Sessions(session_id="window", store=InMemorySessionStore())
        messages = Messages(
            sessions=sessions,
            policy=SlidingWindowMemoryPolicy(max_messages=2, preserve_system_messages=False),
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
        store = InMemorySessionStore()
        first_sessions = Sessions(session_id="first", store=store)
        second_sessions = Sessions(session_id="second", store=store)
        first_messages = Messages(sessions=first_sessions)
        second_messages = Messages(sessions=second_sessions)

        first_messages.append("user", "hello")
        second_messages.append("user", "world")

        sessions = first_sessions.list()

        self.assertEqual({session.session_id for session in sessions}, {"first", "second"})
        self.assertEqual(first_messages.history()[0]["content"], "hello")
        self.assertEqual(second_messages.history()[0]["content"], "world")

    def test_file_store_persists_session_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileSessionStore(base_dir=tmpdir)
            first_sessions = Sessions(session_id="chat/main", store=store)
            first_messages = Messages(sessions=first_sessions)
            first_messages.append("user", "persist me")
            first_messages.append("assistant", "still here")

            reloaded_sessions = Sessions(session_id="chat/main", store=store)
            reloaded_messages = Messages(sessions=reloaded_sessions)
            history = reloaded_messages.history()

            self.assertEqual([item["content"] for item in history], ["persist me", "still here"])
            self.assertEqual([item["role"] for item in history], ["user", "assistant"])


if __name__ == "__main__":
    unittest.main()
