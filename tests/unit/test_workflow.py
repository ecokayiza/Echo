import unittest

from eco_rag.chat import Response
from eco_rag.workflow import WorkflowService


class FakeModel:
    async def generate_response(self, messages, tools=None, stop=None, callbacks=None, **kwargs):
        system = messages[0]["content"]
        user_prompt = messages[-1]["content"]

        if "Workflow Node: plan" in system:
            if "Requested skill: database_search" in user_prompt or "repo workflow" in user_prompt.lower():
                return Response(
                    content='{"next_step":"retrieve","reason":"Need retrieval before answering."}',
                    token_usage={"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
                    raw_response=None,
                )
            return Response(
                content='{"next_step":"answer","reason":"This can be answered directly."}',
                token_usage={"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
                raw_response=None,
            )

        if "Workflow Node: retrieve" in system:
            if "Explain the repo workflow in depth" in user_prompt:
                if "## database_search" not in user_prompt:
                    return Response(
                        content='{"next_step":"retrieve","reason":"Need the database skill instructions first.","tool_name":"load_skill","tool_args":{"skill_name":"database_search"}}',
                        token_usage={"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
                        raw_response=None,
                    )
                if "context::Explain the repo workflow in depth" not in user_prompt:
                    return Response(
                        content='{"next_step":"think","reason":"Need the first retrieval batch.","tool_name":"legacy_search","tool_args":{"query":"Explain the repo workflow in depth"}}',
                        token_usage={"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
                        raw_response=None,
                    )
                return Response(
                    content='{"next_step":"think","reason":"Need one more retrieval batch.","tool_name":"legacy_search","tool_args":{"query":"Explain the repo workflow in depth followup"}}',
                    token_usage={"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
                    raw_response=None,
                )

            if "Explain the repo workflow" in user_prompt:
                if "## database_search" not in user_prompt:
                    return Response(
                        content='{"next_step":"retrieve","reason":"Need the database skill instructions first.","tool_name":"load_skill","tool_args":{"skill_name":"database_search"}}',
                        token_usage={"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
                        raw_response=None,
                    )
                return Response(
                    content='{"next_step":"think","reason":"Need project context before reflection.","tool_name":"legacy_search","tool_args":{"query":"Explain the repo workflow"}}',
                    token_usage={"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
                    raw_response=None,
                )

            if "Need the db skill please" in user_prompt:
                return Response(
                    content='{"next_step":"think","reason":"The requested skill is already loaded.","tool_name":null,"tool_args":{}}',
                    token_usage={"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
                    raw_response=None,
                )

        if "Workflow Node: think" in system:
            if "Explain the repo workflow in depth" in user_prompt and "context::Explain the repo workflow in depth followup" not in user_prompt:
                return Response(
                    content='{"next_step":"retrieve","reason":"One more retrieval pass will improve the answer.","conclusion":"The first retrieval batch is not enough yet.","update_plan":"Fetch one follow-up batch before answering.","self_reflection":"I still need a deeper supporting example."}',
                    token_usage={"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
                    raw_response=None,
                )
            return Response(
                content='{"next_step":"answer","reason":"The current evidence is enough.","conclusion":"I have enough information to answer.","update_plan":"Summarize the evidence clearly.","self_reflection":"No more retrieval is necessary."}',
                token_usage={"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
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

        self.assertEqual(events[0]["event"], "state")
        self.assertEqual(events[-1]["event"], "done")
        self.assertIn("chunk", [item["event"] for item in events])
        self.assertEqual(events[-1]["data"]["status"], "completed")
        self.assertEqual(events[-1]["data"]["answer"], "answer::hello there")
        self.assertEqual(
            [item["status"] for item in events[-1]["data"]["node_statuses"]],
            ["completed", "skipped", "skipped", "skipped", "completed"],
        )
        self.assertEqual(
            [item["node"] for item in events[-1]["data"]["trace"]],
            ["plan", "answer"],
        )

    async def test_workflow_stream_routes_through_skill_load_and_reflection(self):
        async def tool_runner(query: str):
            return [{"title": "repo", "content": f"context::{query}"}]

        service = WorkflowService(model_factory=fake_model_factory, tool_runner=tool_runner)

        events = [item async for item in service.stream("Explain the repo workflow")]

        self.assertEqual(events[-1]["data"]["status"], "completed")
        self.assertEqual(
            [item["node"] for item in events[-1]["data"]["node_statuses"]],
            ["plan", "inject_skills", "retrieve", "think", "answer"],
        )
        self.assertEqual(
            [item["status"] for item in events[-1]["data"]["node_statuses"]],
            ["completed", "completed", "completed", "completed", "completed"],
        )
        self.assertEqual(
            events[-1]["data"]["context_items"],
            [{"title": "repo", "content": "context::Explain the repo workflow", "url": None, "file_path": None, "source_type": None, "skill_name": "legacy_search", "distance": None}],
        )
        self.assertEqual(
            [item["node"] for item in events[-1]["data"]["trace"]],
            ["plan", "retrieve", "retrieve", "think", "answer"],
        )
        self.assertEqual(events[-1]["data"]["trace"][1]["decision"]["tool_name"], "load_skill")
        self.assertEqual(events[-1]["data"]["trace"][2]["decision"]["tool_name"], "legacy_search")
        self.assertTrue(events[-1]["data"]["logs"])

    async def test_workflow_allows_followup_retrieve_after_think(self):
        async def tool_runner(query: str):
            return [{"title": "repo", "content": f"context::{query}"}]

        service = WorkflowService(model_factory=fake_model_factory, tool_runner=tool_runner)

        events = [item async for item in service.stream("Explain the repo workflow in depth")]
        trace = events[-1]["data"]["trace"]

        self.assertEqual(
            [item["node"] for item in trace],
            ["plan", "retrieve", "retrieve", "think", "retrieve", "think", "answer"],
        )
        self.assertEqual(trace[3]["decision"]["next_step"], "retrieve")
        self.assertEqual(trace[4]["decision"]["tool_name"], "legacy_search")

    async def test_workflow_preloads_requested_skill_commands(self):
        service = WorkflowService(model_factory=fake_model_factory)

        events = [item async for item in service.stream("/skill database_search Need the db skill please")]
        snapshot = events[-1]["data"]

        self.assertEqual(snapshot["requested_skill"], "database_search")
        self.assertEqual(snapshot["loaded_skills"][0]["name"], "database_search")
        self.assertEqual(snapshot["query"], "Need the db skill please")
        self.assertEqual(
            [item["node"] for item in snapshot["trace"]],
            ["plan", "retrieve", "think", "answer"],
        )


if __name__ == "__main__":
    unittest.main()
