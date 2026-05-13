import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from eco_rag.chat.chat_model import OpenAIChatModel
from apps.api.app.main import create_app
from eco_rag.chat.service import SessionState
from eco_rag.config import Config
from eco_rag.indexing.vector_database import VectorDatabase
from eco_rag.skills import manager as skills_manager
from eco_rag.workflow_sections import parse_workflow_sections

READ_ONLY_TYPES = {"plan", "think", "tool"}


def workflow_payload(
    query: str,
    *,
    status: str,
    active_node: str | None,
    answer: str = "",
    workflow_turn_id: str = "wf-1",
    token_usage: dict | None = None,
):
    payload = {
        "workflow_turn_id": workflow_turn_id,
        "query": query,
        "answer": answer,
        "status": status,
        "active_node": active_node,
        "node_statuses": [
            {"node": "plan", "status": "completed", "detail": "Will retrieve more context." if status == "completed" else "Planning the response."},
            {"node": "retrieve", "status": "completed" if status == "completed" else "queued", "detail": "Accepted 'legacy_search'." if status == "completed" else None},
            {"node": "tool", "status": "completed" if status == "completed" else "queued", "detail": "Completed round 1." if status == "completed" else None},
            {"node": "think", "status": "running" if active_node == "think" else ("completed" if status == "completed" else "queued"), "detail": "Reviewing the tool results." if active_node == "think" else ("Answer is ready." if status == "completed" else None)},
            {"node": "answer", "status": "completed" if status == "completed" else "queued", "detail": "Final answer emitted." if status == "completed" else None},
        ],
        "logs": [],
        "errors": [],
    }
    if token_usage is not None:
        payload["token_usage"] = token_usage
    return payload


class FakeChatService:
    def __init__(self):
        self._sessions: dict[str, dict] = {}

    def default_system_prompt(self) -> str:
        return "System prompt."

    def list_sessions(self):
        return sorted([self._summary(session) for session in self._sessions.values()], key=lambda item: item["updated_at"], reverse=True)

    def create_session(self, session_id: str | None = None, title: str | None = None):
        resolved = session_id or str(uuid4())
        session = {
            "session_id": resolved,
            "title": title or "New Session",
            "created_at": "2026-04-01T00:00:00+00:00",
            "updated_at": "2026-04-01T00:00:00+00:00",
            "messages": [{"id": "sys-1", "role": "system", "content": self.default_system_prompt(), "message_type": "system"}],
        }
        self._sessions[resolved] = session
        return self._summary(session)

    def get_session_state(self, session_id: str):
        session = self._sessions.setdefault(
            session_id,
            {
                "session_id": session_id,
                "title": "New Session",
                "created_at": "2026-04-01T00:00:00+00:00",
                "updated_at": "2026-04-01T00:00:00+00:00",
                "messages": [{"id": "sys-1", "role": "system", "content": self.default_system_prompt(), "message_type": "system"}],
            },
        )
        return SessionState(session=self._summary(session), messages=list(session["messages"]))

    def update_session_title(self, session_id: str, title: str):
        session = self._sessions[session_id]
        session["title"] = title
        return self._summary(session)

    def delete_session(self, session_id: str):
        self._sessions.pop(session_id, None)

    async def update_system_prompt(self, session_id: str, content: str | None):
        session = self._sessions.setdefault(
            session_id,
            {
                "session_id": session_id,
                "title": "New Session",
                "created_at": "2026-04-01T00:00:00+00:00",
                "updated_at": "2026-04-01T00:00:00+00:00",
                "messages": [{"id": "sys-1", "role": "system", "content": self.default_system_prompt(), "message_type": "system"}],
            },
        )
        session["messages"] = [item for item in session["messages"] if item["role"] != "system"]
        session["messages"].insert(
            0,
            {"id": "sys-1", "role": "system", "content": content or self.default_system_prompt(), "message_type": "system"},
        )
        return SessionState(session=self._summary(session), messages=list(session["messages"]))

    async def stream_message(self, message: str, session_id: str, system_prompt: str | None = None, settings=None):
        session = self._sessions.setdefault(
            session_id,
            {
                "session_id": session_id,
                "title": "New Session",
                "created_at": "2026-04-01T00:00:00+00:00",
                "updated_at": "2026-04-01T00:00:00+00:00",
                "messages": [{"id": "sys-1", "role": "system", "content": self.default_system_prompt(), "message_type": "system"}],
            },
        )
        workflow_turn_id = "wf-1"
        if system_prompt:
            session["messages"][0] = {"id": "sys-1", "role": "system", "content": system_prompt, "message_type": "system"}

        session["messages"] = [item for item in session["messages"] if item["role"] == "system"]
        session["messages"].append({"id": "user-1", "role": "user", "content": message, "message_type": "user"})

        yield {"event": "workflow", "data": workflow_payload(message, status="running", active_node="think", workflow_turn_id=workflow_turn_id)}
        yield {"event": "chunk", "data": {"delta": "reply:", "content": f"reply:{message}"}}

        session["messages"].extend(
            [
                {
                    "id": "plan-1",
                    "role": "assistant",
                    "content": "<plan>\nNeed retrieval.\n</plan>\n<retrieve>\nlegacy_search(\"hello\")\n</retrieve>",
                    "message_type": "plan",
                    "workflow_turn_id": workflow_turn_id,
                    "token_usage": {"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
                },
                {
                    "id": "tool-1",
                    "role": "tool",
                    "content": "<tool>\nlegacy_search(query='hello')\n\n1.\ncontext::hello\n</tool>",
                    "message_type": "tool",
                    "workflow_turn_id": workflow_turn_id,
                    "tool_name": "legacy_search",
                },
                {
                    "id": "think-1",
                    "role": "assistant",
                    "content": "<think>\nThe evidence is enough.\n</think>\n<answer>\nreply:hello\n</answer>",
                    "message_type": "think",
                    "workflow_turn_id": workflow_turn_id,
                    "token_usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
                },
            ]
        )

        snapshot = workflow_payload(
            message,
            status="completed",
            active_node=None,
            answer=f"reply:{message}",
            workflow_turn_id=workflow_turn_id,
            token_usage={"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
        )
        session["title"] = message
        yield {
            "event": "done",
            "data": {
                "session": self._summary(session),
                "messages": list(session["messages"]),
                "reply": f"reply:{message}",
                "token_usage": {"prompt_tokens": 18, "completion_tokens": 7, "total_tokens": 25},
                "workflow": snapshot,
            },
        }

    async def update_message(self, session_id: str, message_id: str, content: str):
        session = self._sessions[session_id]
        message = self._find_message(session, message_id)
        if message.get("message_type") in READ_ONLY_TYPES:
            raise ValueError("Workflow messages are read-only.")
        message["content"] = content
        return SessionState(session=self._summary(session), messages=list(session["messages"]))

    async def delete_message(self, session_id: str, message_id: str):
        session = self._sessions[session_id]
        message = self._find_message(session, message_id)
        if message.get("message_type") in READ_ONLY_TYPES:
            raise ValueError("Workflow messages are read-only.")
        if message["role"] == "system":
            message["content"] = self.default_system_prompt()
        else:
            session["messages"] = [item for item in session["messages"] if item["id"] != message_id]
        return SessionState(session=self._summary(session), messages=list(session["messages"]))

    async def rollback_message(self, session_id: str, message_id: str):
        session = self._sessions[session_id]
        message = self._find_message(session, message_id)
        if message.get("message_type") in READ_ONLY_TYPES:
            raise ValueError("Workflow messages are read-only.")
        for index, item in enumerate(session["messages"]):
            if item["id"] == message_id:
                session["messages"] = session["messages"][: index + 1]
                break
        return SessionState(session=self._summary(session), messages=list(session["messages"]))

    async def stream_regenerate_message(self, session_id: str, message_id: str, settings=None):
        session = self._sessions[session_id]
        session["messages"] = [item for item in session["messages"] if item["message_type"] not in {"plan", "think", "tool", "answer"}]
        workflow_turn_id = "wf-2"
        yield {"event": "workflow", "data": workflow_payload("hello", status="running", active_node="think", workflow_turn_id=workflow_turn_id)}
        yield {"event": "chunk", "data": {"delta": "reply:", "content": "reply:regenerated"}}
        snapshot = workflow_payload("hello", status="completed", active_node=None, answer="reply:regenerated", workflow_turn_id=workflow_turn_id)
        session["messages"].extend(
            [
                {
                    "id": "plan-2",
                    "role": "assistant",
                    "content": "<plan>\nNeed retrieval.\n</plan>\n<retrieve>\nlegacy_search(\"hello\")\n</retrieve>",
                    "message_type": "plan",
                    "workflow_turn_id": workflow_turn_id,
                },
                {
                    "id": "tool-2",
                    "role": "tool",
                    "content": "<tool>\nlegacy_search(query='hello')\n\n1.\ncontext::hello\n</tool>",
                    "message_type": "tool",
                    "workflow_turn_id": workflow_turn_id,
                    "tool_name": "legacy_search",
                },
                {
                    "id": "think-2",
                    "role": "assistant",
                    "content": "<think>\nThe evidence is enough.\n</think>\n<answer>\nreply:regenerated\n</answer>",
                    "message_type": "think",
                    "workflow_turn_id": workflow_turn_id,
                    "token_usage": {"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
                },
            ]
        )
        yield {
            "event": "done",
            "data": {
                "session": self._summary(session),
                "messages": list(session["messages"]),
                "reply": "reply:regenerated",
                "token_usage": {"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
                "workflow": snapshot,
            },
        }

    @staticmethod
    def _find_message(session: dict, message_id: str) -> dict:
        for message in session["messages"]:
            if message["id"] == message_id:
                return message
        raise ValueError("Message not found.")

    @staticmethod
    def _summary(session: dict):
        token_usage = {}
        for message in session["messages"]:
            for key, value in (message.get("token_usage") or {}).items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    token_usage[key] = token_usage.get(key, 0) + value
                    
        preview = ""
        for message in reversed(session["messages"]):
            if message["role"] == "assistant" and message["content"].strip():
                content = message["content"].strip()
                preview = (parse_workflow_sections(content).get("answer") or content)[:80]
                break
                
        if not preview:
            for message in reversed(session["messages"]):
                if message["role"] != "system" and message["content"].strip():
                    preview = message["content"].strip()[:80]
                    break
        
        message_count = len([item for item in session["messages"] if item["role"] != "system"])
        return {
            "session_id": session["session_id"],
            "title": session["title"],
            "created_at": session["created_at"],
            "updated_at": session["updated_at"],
            "message_count": message_count,
            "preview": preview,
            "token_usage": token_usage,
            "total_tokens": int(token_usage.get("total_tokens", 0)),
        }


def write_test_skill(name: str, description: str, content: str):
    path = skills_manager.SKILLS_DIR / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: {description}\n---\n\n{content}\n", encoding="utf-8")


class ApiChatTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._previous_models_path = Config.MODELS_PATH
        self._previous_databases_path = Config.DATABASES_PATH
        self._previous_settings_path = Config.SETTINGS_PATH
        self._previous_db_path = Config.DB_PATH
        self._previous_data_dir = Config.DATA_DIR
        self._previous_skills_dir = skills_manager.SKILLS_DIR
        Config.MODELS_PATH = type(Config.MODELS_PATH)(self._temp_dir.name) / "models.json"
        Config.DATABASES_PATH = type(Config.DATABASES_PATH)(self._temp_dir.name) / "databases.json"
        Config.SETTINGS_PATH = type(Config.SETTINGS_PATH)(self._temp_dir.name) / "settings.json"
        Config.DB_PATH = type(Config.DB_PATH)(self._temp_dir.name) / "db"
        Config.DATA_DIR = type(Config.DATA_DIR)(self._temp_dir.name) / "data"
        Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        skills_manager.SKILLS_DIR = type(skills_manager.SKILLS_DIR)(self._temp_dir.name) / "skills"
        write_test_skill("search", "Search skill.", "# Search\n\nUse search.")
        write_test_skill("workspace-files", "Workspace skill.", "# Workspace Files\n\nUse files.")
        Config.MODELS_PATH.write_text(
            json.dumps(
                {
                    "active_chat_model": "Test Chat",
                    "active_embedding_model": "Test Embedding",
                    "chat_models": [
                        {
                            "name": "Test Chat",
                            "model": "test-model",
                            "api_key": "test-key",
                            "base_url": "https://example.test",
                            "temperature": 0.8,
                            "top_p": 0.9,
                            "custom_request_params": {"max_tokens": 512},
                        }
                    ],
                    "embedding_models": [
                        {
                            "name": "Test Embedding",
                            "model": "test-embedding-model",
                            "api_key": "embedding-key",
                            "base_url": "https://embedding.example.test",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self.client = TestClient(create_app(chat_service=FakeChatService()))

    def tearDown(self):
        Config.MODELS_PATH = self._previous_models_path
        Config.DATABASES_PATH = self._previous_databases_path
        Config.SETTINGS_PATH = self._previous_settings_path
        Config.DB_PATH = self._previous_db_path
        Config.DATA_DIR = self._previous_data_dir
        skills_manager.SKILLS_DIR = self._previous_skills_dir
        try:
            self._temp_dir.cleanup()
        except PermissionError:
            pass

    def test_meta_and_session_lifecycle(self):
        meta = self.client.get("/api/meta")
        self.assertEqual(meta.status_code, 200)
        self.assertEqual(meta.json()["workflow_steps"], ["plan", "retrieve", "tool", "think", "answer"])
        self.assertEqual(meta.json()["default_system_prompt"], "System prompt.")

        created = self.client.post("/api/sessions", json={"session_id": "s1", "title": "Session One"})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["title"], "Session One")

        sessions = self.client.get("/api/sessions")
        self.assertEqual(sessions.status_code, 200)
        self.assertEqual(len(sessions.json()), 1)

        renamed = self.client.patch("/api/sessions/s1", json={"title": "Renamed"})
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["title"], "Renamed")

    def test_message_mutation_routes(self):
        self.client.post("/api/sessions", json={"session_id": "s2"})
        with self.client.stream("POST", "/api/sessions/s2/messages/stream", json={"message": "hello", "system_prompt": "Be kind."}) as response:
            self.assertEqual(response.status_code, 200)
            body = "".join(response.iter_text())
        self.assertIn("event: workflow", body)
        self.assertIn("event: chunk", body)
        self.assertIn("event: done", body)
        self.assertIn("\"active_node\": \"think\"", body)
        self.assertIn("\"message_type\": \"plan\"", body)
        self.assertIn("\"message_type\": \"tool\"", body)

        state = self.client.get("/api/sessions/s2").json()
        self.assertEqual(state["messages"][0]["role"], "system")
        self.assertNotIn("workflow", next(item for item in state["messages"] if item.get("message_type") == "think"))
        user_message_id = next(item["id"] for item in state["messages"] if item["role"] == "user")
        plan_message_id = next(item["id"] for item in state["messages"] if item.get("message_type") == "plan")
        tool_message_id = next(item["id"] for item in state["messages"] if item.get("message_type") == "tool")
        assistant_message_id = next(item["id"] for item in state["messages"] if item.get("message_type") == "think")

        updated = self.client.patch(f"/api/sessions/s2/messages/{user_message_id}", json={"content": "edited"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(next(item for item in updated.json()["messages"] if item["id"] == user_message_id)["content"], "edited")

        rejected_edit = self.client.patch(f"/api/sessions/s2/messages/{plan_message_id}", json={"content": "changed"})
        self.assertEqual(rejected_edit.status_code, 400)

        rejected_delete = self.client.delete(f"/api/sessions/s2/messages/{tool_message_id}")
        self.assertEqual(rejected_delete.status_code, 400)

        system_prompt = self.client.patch("/api/sessions/s2/system-prompt", json={"content": "Stay practical."})
        self.assertEqual(system_prompt.status_code, 200)
        self.assertEqual(system_prompt.json()["messages"][0]["content"], "Stay practical.")

        rolled_back = self.client.post(f"/api/sessions/s2/messages/{user_message_id}/rollback")
        self.assertEqual(rolled_back.status_code, 200)

        deleted = self.client.delete(f"/api/sessions/s2/messages/{user_message_id}")
        self.assertEqual(deleted.status_code, 200)
        remaining_ids = [item["id"] for item in deleted.json()["messages"]]
        self.assertNotIn(user_message_id, remaining_ids)

    def test_database_routes(self):
        listed = self.client.get("/api/databases")
        self.assertEqual(listed.status_code, 200)
        payload = listed.json()
        self.assertEqual(len(payload["databases"]), 0)
        self.assertIsNone(payload["active_database_id"])

        created = self.client.post(
            "/api/databases",
            json={"name": "Research Notes", "embedding_model_name": "Test Embedding"},
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(len(created.json()["databases"]), 1)
        created_database = next(item for item in created.json()["databases"] if item["name"] == "Research Notes")

        renamed = self.client.patch(f"/api/databases/{created_database['id']}", json={"name": "Renamed Notes"})
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(
            next(item for item in renamed.json()["databases"] if item["id"] == created_database["id"])["name"],
            "Renamed Notes",
        )

        selected = self.client.post(f"/api/databases/{created_database['id']}/select")
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(selected.json()["active_database_id"], created_database["id"])

        deleted = self.client.delete(f"/api/databases/{created_database['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(len(deleted.json()["databases"]), 0)

    def test_database_document_upload_route(self):
        created = self.client.post("/api/databases", json={"name": "Test DB"}).json()
        database = created["databases"][0]
        
        with patch("apps.api.app.main.Assembler.delete_file") as delete_file:
            with patch("apps.api.app.main.Assembler.store_file") as store_file:
                uploaded = self.client.post(
                    f"/api/databases/{database['id']}/documents",
                    files=[("files", ("notes.md", b"# Notes\nHello world", "text/markdown"))],
                )

        self.assertEqual(uploaded.status_code, 200)
        saved_path = str(store_file.call_args.args[0])
        self.assertTrue(saved_path.endswith("notes.md"))
        self.assertTrue((Config.DATA_DIR / "uploads" / database["collection_name"] / "notes.md").exists())
        delete_file.assert_called_once_with(saved_path)

    def test_database_upload_job_current_route_survives_app_recreation(self):
        created = self.client.post("/api/databases", json={"name": "Test DB"}).json()
        database = created["databases"][0]

        with patch("apps.api.app.main._process_database_upload_job"):
            created_job = self.client.post(
                f"/api/databases/{database['id']}/documents/jobs",
                files=[("files", ("notes.md", b"# Notes\nHello world", "text/markdown"))],
            )

        self.assertEqual(created_job.status_code, 200)
        job_payload = created_job.json()
        self.assertEqual(job_payload["status"], "queued")
        self.assertTrue((Config.DATA_DIR / "upload_jobs.json").exists())

        current = self.client.get(f"/api/databases/{database['id']}/documents/jobs/current")
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json()["job_id"], job_payload["job_id"])

        recreated_client = TestClient(create_app(chat_service=FakeChatService()))
        restored = recreated_client.get(f"/api/databases/{database['id']}/documents/jobs/current")
        self.assertEqual(restored.status_code, 200)
        self.assertIsNone(restored.json())

    def test_database_document_preview_route(self):
        created = self.client.post("/api/databases", json={"name": "Test DB"}).json()
        database = created["databases"][0]
        vector_db = VectorDatabase(collection_name=database["collection_name"])
        vector_db.add_documents(
            texts=["first chunk", "second chunk", "guide chunk"],
            embeddings=[[0.1, 0.2], [0.2, 0.3], [0.3, 0.4]],
            metadatas=[
                {"source_name": "notes.md", "source_type": "md", "file_path": "uploads/test/notes.md", "chunk_index": 0},
                {"source_name": "notes.md", "source_type": "md", "file_path": "uploads/test/notes.md", "chunk_index": 1},
                {"source_name": "guide.pdf", "source_type": "pdf", "file_path": "uploads/test/guide.pdf", "chunk_index": 0},
            ],
            ids=["chunk-1", "chunk-2", "chunk-3"],
        )

        response = self.client.get(f"/api/databases/{database['id']}/documents")
        self.assertEqual(response.status_code, 200)
        documents = response.json()
        self.assertEqual(len(documents), 2)

        guide = next(item for item in documents if item["source_name"] == "guide.pdf")
        notes = next(item for item in documents if item["source_name"] == "notes.md")
        self.assertEqual(guide["chunk_count"], 1)
        self.assertEqual(notes["chunk_count"], 2)

    def test_stream_regenerate_endpoint(self):
        self.client.post("/api/sessions", json={"session_id": "stream"})
        with self.client.stream("POST", "/api/sessions/stream/messages/stream", json={"message": "hello"}) as response:
            self.assertEqual(response.status_code, 200)
            _ = "".join(response.iter_text())

        with self.client.stream("POST", "/api/sessions/stream/messages/assistant-1/regenerate/stream", json={}) as response:
            self.assertEqual(response.status_code, 200)
            body = "".join(response.iter_text())
        self.assertIn("event: workflow", body)
        self.assertIn("event: chunk", body)
        self.assertIn("reply:regenerated", body)
        self.assertIn("\"workflow_turn_id\": \"wf-2\"", body)

    def test_sync_chat_routes_are_removed(self):
        send = self.client.post("/api/sessions/sync/messages", json={"message": "hello"})
        regenerate = self.client.post("/api/sessions/sync/messages/user-1/regenerate", json={})
        local_embedding = self.client.post("/local-embedding/v1/embeddings", json={"input": "hello", "model": "test"})
        local_download = self.client.post("/api/local-embedding/download")
        self.assertEqual(send.status_code, 404)
        self.assertEqual(regenerate.status_code, 404)
        self.assertEqual(local_embedding.status_code, 404)
        self.assertEqual(local_download.status_code, 404)

    def test_model_settings_endpoints_read_and_write_models_json(self):
        current = self.client.get("/api/model-settings")
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json()["active_chat_model"], "Test Chat")
        self.assertEqual(current.json()["chat_models"][0]["model"], "test-model")
        self.assertNotIn("enable_thinking", current.json()["chat_models"][0])

        updated = self.client.put(
            "/api/model-settings",
            json={
                "active_chat_model": "Updated Chat",
                "active_embedding_model": "Updated Embedding",
                "chat_models": [
                    {
                        "name": "Updated Chat",
                        "model": "updated-model",
                        "api_key": "updated-key",
                        "base_url": "https://updated.example",
                        "temperature": 1.1,
                        "top_p": 0.95,
                        "custom_request_params": {"max_tokens": 2048, "metadata": {"source": "settings"}},
                    }
                ],
                "embedding_models": [
                    {
                        "name": "Updated Embedding",
                        "model": "updated-embedding-model",
                        "api_key": "updated-embedding-key",
                        "base_url": "https://updated.embedding.example",
                    }
                ],
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["active_chat_model"], "Updated Chat")
        self.assertEqual(updated.json()["chat_models"][0]["model"], "updated-model")
        self.assertNotIn("enable_thinking", updated.json()["chat_models"][0])

        persisted = json.loads(Config.MODELS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(persisted["chat_models"][0]["model"], "updated-model")
        self.assertEqual(persisted["chat_models"][0]["api_key"], "updated-key")
        self.assertNotIn("enable_thinking", persisted["chat_models"][0])
        self.assertEqual(persisted["chat_models"][0]["custom_request_params"]["max_tokens"], 2048)
        self.assertEqual(persisted["embedding_models"][0]["model"], "updated-embedding-model")

    def test_chat_model_request_payload_uses_custom_request_params_only(self):
        model = OpenAIChatModel(
            api_key="test-key",
            base_url="https://example.test",
            model="test-model",
            custom_request_params={"max_tokens": 2048},
        )

        payload = model._build_request_payload([{"role": "user", "content": "hello"}])

        self.assertEqual(payload["extra_body"], {"max_tokens": 2048})

        plain_model = OpenAIChatModel(
            api_key="test-key",
            base_url="https://example.test",
            model="test-model",
        )
        plain_payload = plain_model._build_request_payload([{"role": "user", "content": "hello"}])
        self.assertNotIn("extra_body", plain_payload)

    def test_model_settings_test_route_probes_chat_and_embedding(self):
        class FakeModel:
            async def generate_response(self, messages):
                return SimpleNamespace(content="OK")

        with patch("apps.api.app.main.build_chat_model", return_value=FakeModel()) as build_chat_model:
            chat_response = self.client.post(
                "/api/model-settings/test",
                json={
                    "kind": "chat",
                    "chat_model": {
                        "name": "Draft Chat",
                        "model": "draft-model",
                        "api_key": "draft-key",
                        "base_url": "https://draft.example",
                        "temperature": 0.7,
                    },
                },
            )

        self.assertEqual(chat_response.status_code, 200)
        self.assertTrue(chat_response.json()["ok"])
        self.assertIn("Chat API test succeeded", chat_response.json()["message"])
        self.assertEqual(build_chat_model.call_args.args[0].name, "Draft Chat")

        with patch("apps.api.app.main.OpenAICompatibleEmbedder.embed_documents", return_value=[[0.1, 0.2, 0.3]]):
            embedding_response = self.client.post(
                "/api/model-settings/test",
                json={
                    "kind": "embedding",
                    "embedding_model": {
                        "name": "Draft Embedding",
                        "model": "draft-embedding",
                        "api_key": "embedding-key",
                        "base_url": "https://embedding.example",
                    },
                },
            )

        self.assertEqual(embedding_response.status_code, 200)
        self.assertTrue(embedding_response.json()["ok"])
        self.assertIn("Vector dimensions: 3", embedding_response.json()["message"])

    def test_app_settings_endpoint_manages_runtime_settings_json(self):
        current = self.client.get("/api/app-settings")
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json()["chunk_size"], Config.CHUNK_SIZE)
        self.assertEqual(current.json()["web_search_backend"], "auto")
        self.assertNotIn("max_context_messages", current.json())
        self.assertNotIn("prompt_truncate_chars", current.json())

        updated = self.client.put(
            "/api/app-settings",
            json={
                "chunk_size": 640,
                "chunk_overlap": 96,
                "max_retrieve_rounds": 4,
                "use_marker_pdf_loader": False,
                "web_search_backend": "baidu",
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["chunk_size"], 640)
        self.assertFalse(updated.json()["use_marker_pdf_loader"])
        self.assertEqual(updated.json()["web_search_backend"], "baidu")

        persisted = json.loads(Config.SETTINGS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(persisted["chunk_size"], 640)
        self.assertEqual(persisted["chunk_overlap"], 96)
        self.assertEqual(persisted["max_retrieve_rounds"], 4)
        self.assertFalse(persisted["use_marker_pdf_loader"])
        self.assertEqual(persisted["web_search_backend"], "baidu")
        self.assertNotIn("max_context_messages", persisted)
        self.assertNotIn("prompt_truncate_chars", persisted)

    def test_skill_settings_endpoints_manage_skill_files_and_runtime_flags(self):
        current = self.client.get("/api/skills")
        self.assertEqual(current.status_code, 200)
        skills = current.json()["skills"]
        self.assertEqual([skill["name"] for skill in skills], ["search", "workspace-files"])
        self.assertTrue(next(skill for skill in skills if skill["name"] == "search")["protected"])

        updated = self.client.put(
            "/api/skills",
            json={
                "skills": [
                    {
                        "name": "search",
                        "description": "Updated search skill.",
                        "content": "# Search\n\nUpdated search guidance.",
                        "enabled": True,
                        "default": True,
                        "protected": True,
                    },
                    {
                        "name": "workspace-files",
                        "description": "Workspace skill.",
                        "content": "# Workspace Files\n\nUse files.",
                        "enabled": False,
                        "default": False,
                        "protected": True,
                    },
                    {
                        "name": "custom-notes",
                        "description": "Custom notes skill.",
                        "content": "# Custom Notes\n\nUse notes.",
                        "enabled": True,
                        "default": False,
                        "protected": False,
                    },
                ]
            },
        )
        self.assertEqual(updated.status_code, 200)
        payload = updated.json()
        self.assertEqual([skill["name"] for skill in payload["skills"]], ["search", "workspace-files", "custom-notes"])
        self.assertFalse(next(skill for skill in payload["skills"] if skill["name"] == "workspace-files")["enabled"])
        self.assertTrue((skills_manager.SKILLS_DIR / "custom-notes" / "SKILL.md").exists())

        persisted_settings = json.loads(Config.SETTINGS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(persisted_settings["enabled_skills"], ["search", "custom-notes"])
        self.assertEqual(persisted_settings["default_skills"], ["search"])
        self.assertIn("Updated search guidance.", (skills_manager.SKILLS_DIR / "search" / "SKILL.md").read_text(encoding="utf-8"))

        delete_protected = self.client.put(
            "/api/skills",
            json={
                "skills": [
                    {
                        "name": "workspace-files",
                        "description": "Workspace skill.",
                        "content": "# Workspace Files\n\nUse files.",
                        "enabled": True,
                        "default": True,
                        "protected": True,
                    }
                ]
            },
        )
        self.assertEqual(delete_protected.status_code, 400)


if __name__ == "__main__":
    unittest.main()
