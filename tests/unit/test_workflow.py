import unittest

from eco_rag.chat import Response
from eco_rag.workflow import WorkflowService


class FakeModel:
    async def generate_response(self, messages, tools=None, stop=None, callbacks=None, **kwargs):
        system = messages[0]["content"]
        latest_user = next(message["content"] for message in reversed(messages) if message["role"] == "user")

        if "Workflow Node: plan" in system:
            if "repo workflow" in latest_user.lower():
                return Response(
                    content='{"next_step":"retrieve","reason":"Need external context before answering."}',
                    token_usage={"prompt_tokens": 5, "completion_tokens": 0, "total_tokens": 5},
                    raw_response=None,
                )
            return Response(
                content='{"next_step":"think","reason":"This can be handled directly."}',
                token_usage={"prompt_tokens": 5, "completion_tokens": 0, "total_tokens": 5},
                raw_response=None,
            )

        if "Workflow Node: retrieve" in system:
            return Response(
                content='{"next_step":"think","reason":"Use the external context before answering."}',
                token_usage={"prompt_tokens": 5, "completion_tokens": 0, "total_tokens": 5},
                raw_response=None,
            )

        if "Workflow Node: think" in system:
            return Response(
                content='{"next_step":"answer","reason":"Enough information to answer now."}',
                token_usage={"prompt_tokens": 5, "completion_tokens": 0, "total_tokens": 5},
                raw_response=None,
            )

        raise AssertionError("Answer generation should use stream_response().")

    async def stream_response(self, messages, tools=None, stop=None, callbacks=None, **kwargs):
        question = next(message["content"] for message in reversed(messages) if message["role"] == "user")
        if isinstance(callbacks, dict) and callable(callbacks.get("on_usage")):
            callbacks["on_usage"]({"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14})
        yield "answer::"
        yield question


def fake_model_factory(_settings=None):
    return FakeModel()


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_workflow_stream_answers_direct_queries(self):
        service = WorkflowService(model_factory=fake_model_factory)

        events = [item async for item in service.stream("hello there")]

        self.assertEqual(events[0]["event"], "state")
        self.assertEqual(events[-1]["event"], "done")
        self.assertIn("chunk", [item["event"] for item in events])
        self.assertEqual(events[-1]["data"]["status"], "completed")
        self.assertEqual(events[-1]["data"]["answer"], "answer::hello there")
        self.assertEqual(
            [item["status"] for item in events[-1]["data"]["node_statuses"]],
            ["completed", "skipped", "completed", "completed"],
        )

    async def test_workflow_stream_routes_through_retrieve(self):
        async def tool_runner(query: str):
            return [{"title": "repo", "content": f"context::{query}"}]

        service = WorkflowService(model_factory=fake_model_factory, tool_runner=tool_runner)

        events = [item async for item in service.stream("Explain the repo workflow")]

        self.assertEqual(events[-1]["data"]["status"], "completed")
        self.assertEqual(
            [item["node"] for item in events[-1]["data"]["node_statuses"]],
            ["plan", "retrieve", "think", "answer"],
        )
        self.assertEqual(
            [item["status"] for item in events[-1]["data"]["node_statuses"]],
            ["completed", "completed", "completed", "completed"],
        )
        self.assertEqual(events[-1]["data"]["context_items"], [{"title": "repo", "content": "context::Explain the repo workflow"}])
        self.assertTrue(events[-1]["data"]["logs"])


if __name__ == "__main__":
    unittest.main()
