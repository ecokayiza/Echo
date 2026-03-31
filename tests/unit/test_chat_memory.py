import tempfile
import unittest

from eco_rag.chat import ContextManager, FileMessageStore, InMemoryMessageStore, SlidingWindowMemoryPolicy


class ContextManagerTests(unittest.TestCase):
    def test_sliding_window_keeps_recent_messages(self):
        manager = ContextManager(
            store=InMemoryMessageStore(),
            policy=SlidingWindowMemoryPolicy(max_messages=2, preserve_system_messages=False),
        )
        manager.append("user", "one")
        manager.append("assistant", "two")
        manager.append("user", "three")

        context = manager.build_context()

        self.assertEqual(
            context,
            [
                {"role": "assistant", "content": "two"},
                {"role": "user", "content": "three"},
            ],
        )

    def test_system_message_is_preserved(self):
        manager = ContextManager(
            store=InMemoryMessageStore(),
            policy=SlidingWindowMemoryPolicy(max_messages=1),
        )
        manager.append("system", "You are helpful.")
        manager.append("user", "first")
        manager.append("assistant", "second")

        context = manager.build_context()

        self.assertEqual(
            context,
            [
                {"role": "system", "content": "You are helpful."},
                {"role": "assistant", "content": "second"},
            ],
        )

    def test_sessions_can_share_store_without_leaking_history(self):
        shared_store = InMemoryMessageStore()
        first = ContextManager(session_id="first", store=shared_store)
        second = ContextManager(session_id="second", store=shared_store)

        first.append("user", "hello")
        second.append("user", "world")

        self.assertEqual(first.get_history(), [{"role": "user", "content": "hello"}])
        self.assertEqual(second.get_history(), [{"role": "user", "content": "world"}])

    def test_file_store_persists_session_history_on_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileMessageStore(base_dir=tmpdir)
            first = ContextManager(session_id="chat/main", store=store)
            first.append("user", "persist me")
            first.append("assistant", "still here")

            reloaded = ContextManager(session_id="chat/main", store=store)

            self.assertEqual(
                reloaded.get_history(),
                [
                    {"role": "user", "content": "persist me"},
                    {"role": "assistant", "content": "still here"},
                ],
            )


if __name__ == "__main__":
    unittest.main()
