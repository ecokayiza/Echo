import unittest

from eco_rag.chat import Response
from eco_rag.workflow.nodes import _decision_from_response
from eco_rag.workflow import WorkflowService


def _user_query(messages) -> str:
    for item in reversed(messages):
        content = str(item.get("content") or "")
        if item.get("role") != "user":
            continue
        if content.startswith("[tool]"):
            continue
        text = " ".join(content.split())
        if text.startswith("/skill "):
            parts = text.split(maxsplit=2)
            return parts[2] if len(parts) > 2 else ""
        return text
    return ""


class FakeModel:
    def __init__(self):
        self.calls: list[list[dict[str, object]]] = []
        self.stream_calls: list[list[dict[str, object]]] = []

    async def generate_response(self, messages, tools=None, stop=None, callbacks=None, **kwargs):
        self.calls.append([dict(item) for item in messages])
        query = _user_query(messages)
        transcript = "\n".join(item["content"] for item in messages)
        continuation = messages[-1]["role"] == "tool"

        if not continuation:
            if query == "hello there":
                return Response(
                    content="[plan]\nThis can be answered directly.\n[answer]\nanswer::hello there",
                    token_usage={"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
                    raw_response=None,
                )
            if query == "tell me something longer":
                return Response(
                    content=(
                        "[plan]\nThis can still be answered directly.\n[answer]\n"
                        "answer::This reply is intentionally long enough to verify that the workflow "
                        "emits multiple streamed chunks instead of one single final payload."
                    ),
                    token_usage={"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
                    raw_response=None,
                )
            if query == "Need the db skill please":
                return Response(
                    content="[plan]\nA requested skill should be loaded first.\n[answer]\nshould-not-be-used",
                    token_usage={"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
                    raw_response=None,
                )
            if query == "Explain the repo workflow":
                return Response(
                    content="[plan]\nNeed repo evidence first.\n[retrieve]\nlegacy_search(\"Explain the repo workflow\")",
                    token_usage={"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
                    raw_response=None,
                )
            if query == "Explain the repo workflow in depth":
                return Response(
                    content="[plan]\nNeed an initial retrieval batch.\n[retrieve]\nlegacy_search(\"Explain the repo workflow in depth\")",
                    token_usage={"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
                    raw_response=None,
                )

        if continuation:
            if query == "Explain the repo workflow":
                return Response(
                    content="[think]\nThe evidence is enough.\n[answer]\nanswer::Explain the repo workflow",
                    token_usage={"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
                    raw_response=None,
                )
            if query == "Explain the repo workflow in depth":
                if "context::Explain the repo workflow in depth followup" not in transcript:
                    return Response(
                        content="[think]\nOne more pass will tighten the answer.\n[retrieve]\nlegacy_search(\"Explain the repo workflow in depth followup\")",
                        token_usage={"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
                        raw_response=None,
                    )
                return Response(
                    content="[think]\nThe evidence is enough.\n[answer]\nanswer::Explain the repo workflow in depth",
                    token_usage={"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
                    raw_response=None,
                )
            if query == "Need the db skill please":
                if "context::Need the db skill please" not in transcript:
                    return Response(
                        content="[think]\nThe requested skill is loaded, now search locally.\n[retrieve]\nlegacy_search(\"Need the db skill please\")",
                        token_usage={"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
                        raw_response=None,
                    )
                return Response(
                    content="[think]\nThe evidence is enough.\n[answer]\nanswer::Need the db skill please",
                    token_usage={"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
                    raw_response=None,
                )

        raise AssertionError(f"Unexpected transcript: {transcript}")

    async def stream_response(self, messages, tools=None, stop=None, callbacks=None, **kwargs):
        self.stream_calls.append([dict(item) for item in messages])
        response = await self.generate_response(messages, tools=tools, stop=stop, callbacks=callbacks, **kwargs)
        callback_map = callbacks if isinstance(callbacks, dict) else {}
        on_usage = callback_map.get("on_usage")
        if callable(on_usage):
            on_usage(response.token_usage)
        text = response.content or ""
        midpoint = max(1, len(text) // 2)
        for chunk in (text[:midpoint], text[midpoint:]):
            if chunk:
                yield chunk


def fake_model_factory(_settings=None):
    return FakeModel()


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_decision_error_includes_raw_llm_output(self):
        with self.assertRaises(ValueError) as ctx:
            _decision_from_response(
                Response(content="[plan]\nMissing action block.", token_usage=None, raw_response=None),
                node="plan",
                allow_retrieve=True,
                allowed_tool_names={"legacy_search", "database_search", "web_search", "load_skill"},
            )

        detail = str(ctx.exception)
        self.assertIn("LLM raw output:", detail)
        self.assertIn("[plan]\nMissing action block.", detail)

    async def test_workflow_reuses_one_model_instance_per_run(self):
        created_models: list[FakeModel] = []

        def counting_factory(_settings=None):
            model = FakeModel()
            created_models.append(model)
            return model

        service = WorkflowService(model_factory=counting_factory)

        events = [item async for item in service.stream("hello there")]

        self.assertEqual(events[-1]["event"], "done")
        self.assertEqual(len(created_models), 1)

    async def test_workflow_stream_answers_direct_queries(self):
        service = WorkflowService(model_factory=fake_model_factory)

        events = [item async for item in service.stream("hello there")]
        snapshot = events[-1]["data"]["snapshot"]
        records = events[-1]["data"]["records"]

        self.assertEqual(events[0]["event"], "state")
        self.assertEqual(events[-1]["event"], "done")
        self.assertIn("chunk", [item["event"] for item in events])
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["answer"], "answer::hello there")
        self.assertEqual(
            [item["status"] for item in snapshot["node_statuses"]],
            ["completed", "skipped", "skipped", "skipped", "completed"],
        )
        self.assertEqual([record["message_type"] for record in records], ["plan"])
        self.assertGreaterEqual(len([item for item in events if item["event"] == "record"]), 2)

    async def test_workflow_streams_long_answers_in_multiple_chunks(self):
        service = WorkflowService(model_factory=fake_model_factory)

        events = [item async for item in service.stream("tell me something longer")]
        chunks = [item["data"] for item in events if item["event"] == "chunk"]

        self.assertGreater(len(chunks), 1)
        self.assertEqual(
            chunks[-1]["content"],
            "answer::This reply is intentionally long enough to verify that the workflow emits multiple streamed chunks instead of one single final payload.",
        )
        self.assertEqual(
            "".join(chunk["delta"] for chunk in chunks),
            chunks[-1]["content"],
        )

    async def test_answer_block_is_enough_for_direct_answer(self):
        class AnswerBlockModel(FakeModel):
            async def generate_response(self, messages, tools=None, stop=None, callbacks=None, **kwargs):
                self.calls.append([{"role": item["role"], "content": item["content"]} for item in messages])
                return Response(
                    content="[plan]\nThis can be answered directly.\n[answer]\nanswer::inferred",
                    token_usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
                    raw_response=None,
                )

        service = WorkflowService(model_factory=lambda _settings=None: AnswerBlockModel())

        events = [item async for item in service.stream("infer next")]

        self.assertEqual(events[-1]["event"], "done")
        self.assertEqual(events[-1]["data"]["snapshot"]["answer"], "answer::inferred")

    async def test_workflow_routes_through_tool_and_think(self):
        async def tool_runner(query: str):
            return [{"title": "repo", "content": f"context::{query}"}]

        created_models: list[FakeModel] = []

        def counting_factory(_settings=None):
            model = FakeModel()
            created_models.append(model)
            return model

        service = WorkflowService(model_factory=counting_factory, tool_runner=tool_runner)

        events = [item async for item in service.stream("Explain the repo workflow")]
        snapshot = events[-1]["data"]["snapshot"]
        records = events[-1]["data"]["records"]

        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(
            [item["node"] for item in snapshot["node_statuses"]],
            ["plan", "retrieve", "tool", "think", "answer"],
        )
        self.assertEqual(
            [item["status"] for item in snapshot["node_statuses"]],
            ["completed", "completed", "completed", "completed", "completed"],
        )
        self.assertEqual([record["message_type"] for record in records], ["plan", "tool", "think"])
        self.assertEqual(records[1]["tool_name"], "legacy_search")
        self.assertEqual({record["workflow_turn_id"] for record in records}, {snapshot["workflow_turn_id"]})
        second_call = created_models[0].calls[1]
        self.assertIn("[plan]", str(second_call[2]["content"]))
        self.assertTrue(any(str(item["content"]).startswith("[tool]") for item in second_call))
        self.assertEqual(second_call[2]["role"], "assistant")
        self.assertIn("tool_calls", second_call[2])
        assistant_tool_call = second_call[2]["tool_calls"][0]
        self.assertEqual(assistant_tool_call["function"]["name"], "legacy_search")
        self.assertEqual(second_call[-1]["role"], "tool")
        self.assertTrue(str(second_call[-1]["content"]).startswith("[tool]"))
        self.assertEqual(second_call[-1]["tool_call_id"], assistant_tool_call["id"])

    async def test_multi_hop_workflow_keeps_retrieving_until_answer(self):
        async def tool_runner(query: str):
            return [{"title": "repo", "content": f"context::{query}"}]

        created_models: list[FakeModel] = []

        def counting_factory(_settings=None):
            model = FakeModel()
            created_models.append(model)
            return model

        service = WorkflowService(model_factory=counting_factory, tool_runner=tool_runner)

        events = [item async for item in service.stream("Explain the repo workflow in depth")]
        snapshot = events[-1]["data"]["snapshot"]
        records = events[-1]["data"]["records"]

        self.assertEqual(snapshot["answer"], "answer::Explain the repo workflow in depth")
        self.assertEqual([record["message_type"] for record in records], ["plan", "tool", "think", "tool", "think"])
        third_call = created_models[0].calls[2]
        self.assertTrue(any("context::Explain the repo workflow in depth" in item["content"] for item in third_call))
        self.assertTrue(any("[think]" in item["content"] for item in third_call))

    async def test_requested_skill_forces_initial_load_skill(self):
        async def tool_runner(query: str):
            return [{"title": "repo", "content": f"context::{query}"}]

        service = WorkflowService(model_factory=fake_model_factory, tool_runner=tool_runner)

        events = [item async for item in service.stream("/skill database_search Need the db skill please")]
        snapshot = events[-1]["data"]["snapshot"]
        records = events[-1]["data"]["records"]

        self.assertEqual(snapshot["answer"], "answer::Need the db skill please")
        self.assertEqual([record["message_type"] for record in records], ["plan", "tool", "think", "tool", "think"])
        self.assertEqual(records[1]["tool_name"], "load_skill")
        self.assertEqual(records[3]["tool_name"], "legacy_search")

    async def test_resume_uses_saved_live_draft(self):
        async def tool_runner(query: str):
            return [{"title": "repo", "content": f"context::{query}"}]

        created_models: list[FakeModel] = []

        def counting_factory(_settings=None):
            model = FakeModel()
            created_models.append(model)
            return model

        draft_storage: dict[str, dict] = {}
        service = WorkflowService(
            model_factory=counting_factory,
            tool_runner=tool_runner,
            draft_storage=draft_storage,
        )

        iterator = service.stream_chat(
            "Explain the repo workflow",
            context=[
                {"role": "system", "content": "system"},
                {"role": "user", "content": "Explain the repo workflow"},
            ],
            session_id="session-1",
            user_message_id="user-1",
        )
        async for _item in iterator:
            if draft_storage.get("session-1", {}).get("state", {}).get("next_step") == "retrieve":
                break
        await iterator.aclose()

        self.assertIn("session-1", draft_storage)
        self.assertEqual(draft_storage["session-1"]["state"]["next_step"], "retrieve")
        self.assertEqual([record["message_type"] for record in draft_storage["session-1"]["records"]], ["plan"])

        events = [
            item
            async for item in service.stream_chat(
                "Explain the repo workflow",
                context=[
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": "Explain the repo workflow"},
                ],
                session_id="session-1",
                user_message_id="user-1",
            )
        ]

        self.assertEqual(events[-1]["data"]["snapshot"]["status"], "completed")
        self.assertNotIn("session-1", draft_storage)
        self.assertEqual([record["message_type"] for record in events[-1]["data"]["records"]], ["plan", "tool", "think"])
        self.assertEqual(len(created_models), 2)


if __name__ == "__main__":
    unittest.main()
