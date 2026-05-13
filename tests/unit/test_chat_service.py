import unittest

from eco_rag.chat.service import ChatService


def _snapshot(*, status: str, answer: str = ""):
    return {
        "workflow_turn_id": "turn-1",
        "query": "hello",
        "answer": answer,
        "status": status,
        "active_node": None if status == "completed" else "plan",
        "tool_name": None,
        "node_statuses": [
            {"node": "plan", "status": "completed" if status == "completed" else "running", "detail": None},
            {"node": "retrieve", "status": "skipped" if status == "completed" else "queued", "detail": None},
            {"node": "tool", "status": "skipped" if status == "completed" else "queued", "detail": None},
            {"node": "think", "status": "skipped" if status == "completed" else "queued", "detail": None},
            {"node": "answer", "status": "completed" if status == "completed" else "queued", "detail": None},
        ],
        "logs": [],
        "errors": [],
    }


class FakeWorkflowService:
    async def stream_chat(self, question, *, context=None, workflow_turn_id=None):
        yield {"event": "state", "data": _snapshot(status="running")}
        yield {
            "event": "record",
            "data": {
                "role": "assistant",
                "content": "<plan>\nThis can be answered directly.\n</plan>\n<answer>\nhello\n</answer>",
                "message_type": "plan",
                "workflow_turn_id": "turn-1",
                "token_usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        }
        yield {"event": "chunk", "data": {"delta": "hello", "content": "hello"}}
        yield {
            "event": "done",
            "data": {
                "snapshot": _snapshot(status="completed", answer="hello"),
                "records": [
                    {
                        "role": "assistant",
                        "content": "<plan>\nThis can be answered directly.\n</plan>\n<answer>\nhello\n</answer>",
                        "message_type": "plan",
                        "workflow_turn_id": "turn-1",
                        "token_usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                    }
                ],
                "token_usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        }


class ChatServiceStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_message_forwards_record_events_and_finishes(self):
        service = ChatService(storage={}, workflow_factory=lambda: FakeWorkflowService())

        events = [item async for item in service.stream_message("hello", session_id="session-1")]

        self.assertEqual([item["event"] for item in events], ["workflow", "record", "chunk", "done"])
        self.assertEqual(events[-1]["data"]["reply"], "hello")

        messages = events[-1]["data"]["messages"]
        self.assertEqual([item["role"] for item in messages], ["system", "user", "assistant"])
        self.assertEqual(messages[2]["message_type"], "plan")


if __name__ == "__main__":
    unittest.main()
