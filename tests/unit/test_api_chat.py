import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.app.main import create_app
from eco_rag.chat.service import ChatResult, SessionState


class FakeChatService:
    def __init__(self):
        self._sessions: dict[str, dict] = {}

    def list_sessions(self):
        return sorted(self._sessions.values(), key=lambda item: item["updated_at"], reverse=True)

    def create_session(self, session_id: str | None = None, title: str | None = None):
        resolved = session_id or str(uuid4())
        session = {
            "session_id": resolved,
            "title": title or "New Session",
            "created_at": "2026-04-01T00:00:00+00:00",
            "updated_at": "2026-04-01T00:00:00+00:00",
            "message_count": 0,
            "preview": "",
            "token_usage": {},
            "total_tokens": 0,
        }
        self._sessions[resolved] = {**session, "messages": []}
        return session

    def get_session_state(self, session_id: str):
        session = self._sessions.setdefault(
            session_id,
            {
                "session_id": session_id,
                "title": "New Session",
                "created_at": "2026-04-01T00:00:00+00:00",
                "updated_at": "2026-04-01T00:00:00+00:00",
                "message_count": 0,
                "preview": "",
                "token_usage": {},
                "total_tokens": 0,
                "messages": [],
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
                "message_count": 0,
                "preview": "",
                "token_usage": {},
                "total_tokens": 0,
                "messages": [],
            },
        )
        session["messages"] = [item for item in session["messages"] if item["role"] != "system"]
        if content:
            session["messages"].insert(0, {"id": "sys-1", "role": "system", "content": content})
        return SessionState(session=self._summary(session), messages=list(session["messages"]))

    async def send_message(self, message: str, session_id: str, system_prompt: str | None = None, settings=None):
        session = self._sessions.setdefault(
            session_id,
            {
                "session_id": session_id,
                "title": "New Session",
                "created_at": "2026-04-01T00:00:00+00:00",
                "updated_at": "2026-04-01T00:00:00+00:00",
                "message_count": 0,
                "preview": "",
                "token_usage": {},
                "total_tokens": 0,
                "messages": [],
            },
        )

        if system_prompt and not any(item["role"] == "system" for item in session["messages"]):
            session["messages"].append({"id": "sys-1", "role": "system", "content": system_prompt})
        session["messages"].append({"id": "user-1", "role": "user", "content": message})
        session["messages"].append(
            {
                "id": "assistant-1",
                "role": "assistant",
                "content": f"reply:{message}",
                "token_usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
            }
        )
        session["title"] = message
        return ChatResult(
            session=self._summary(session),
            messages=list(session["messages"]),
            reply=f"reply:{message}",
            token_usage={"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
        )

    async def stream_message(self, message: str, session_id: str, system_prompt: str | None = None, settings=None):
        yield {"event": "chunk", "data": {"delta": "reply:", "content": "reply:"}}
        yield {
            "event": "done",
            "data": {
                "session": self.create_session(session_id=session_id),
                "messages": [
                    {"id": "user-1", "role": "user", "content": message},
                    {"id": "assistant-1", "role": "assistant", "content": f"reply:{message}"},
                ],
                "reply": f"reply:{message}",
                "token_usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
            },
        }

    async def update_message(self, session_id: str, message_id: str, content: str):
        session = self._sessions[session_id]
        for message in session["messages"]:
            if message["id"] == message_id:
                message["content"] = content
                break
        return SessionState(session=self._summary(session), messages=list(session["messages"]))

    async def delete_message(self, session_id: str, message_id: str):
        session = self._sessions[session_id]
        for index, message in enumerate(session["messages"]):
            if message["id"] == message_id:
                session["messages"] = session["messages"][:index]
                break
        return SessionState(session=self._summary(session), messages=list(session["messages"]))

    async def rollback_message(self, session_id: str, message_id: str):
        session = self._sessions[session_id]
        for index, message in enumerate(session["messages"]):
            if message["id"] == message_id:
                session["messages"] = session["messages"][: index + 1]
                break
        return SessionState(session=self._summary(session), messages=list(session["messages"]))

    async def regenerate_message(self, session_id: str, message_id: str, settings=None):
        session = self._sessions[session_id]
        session["messages"] = [item for item in session["messages"] if item["role"] != "assistant"]
        session["messages"].append(
            {
                "id": "assistant-2",
                "role": "assistant",
                "content": "reply:regenerated",
                "token_usage": {"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
            }
        )
        return ChatResult(
            session=self._summary(session),
            messages=list(session["messages"]),
            reply="reply:regenerated",
            token_usage={"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
        )

    async def stream_regenerate_message(self, session_id: str, message_id: str, settings=None):
        yield {"event": "chunk", "data": {"delta": "reply:", "content": "reply:"}}
        yield {
            "event": "done",
            "data": {
                "session": self._summary(self._sessions.setdefault(session_id, self.create_session(session_id=session_id))),
                "messages": [
                    {"id": "user-1", "role": "user", "content": "hello"},
                    {"id": "assistant-2", "role": "assistant", "content": "reply:regenerated"},
                ],
                "reply": "reply:regenerated",
                "token_usage": {"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
            },
        }

    @staticmethod
    def _summary(session: dict):
        token_usage = {}
        for message in session["messages"]:
            for key, value in (message.get("token_usage") or {}).items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    token_usage[key] = token_usage.get(key, 0) + value
        return {
            "session_id": session["session_id"],
            "title": session["title"],
            "created_at": session["created_at"],
            "updated_at": session["updated_at"],
            "message_count": len(session["messages"]),
            "preview": session["messages"][-1]["content"][:80] if session["messages"] else "",
            "token_usage": token_usage,
            "total_tokens": int(token_usage.get("total_tokens", 0)),
        }


class ApiChatTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(chat_service=FakeChatService()))

    def test_session_lifecycle(self):
        created = self.client.post("/api/sessions", json={"session_id": "s1", "title": "Session One"})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["title"], "Session One")

        sessions = self.client.get("/api/sessions")
        self.assertEqual(sessions.status_code, 200)
        self.assertEqual(len(sessions.json()), 1)

        renamed = self.client.patch("/api/sessions/s1", json={"title": "Renamed"})
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["title"], "Renamed")

    def test_message_flow(self):
        self.client.post("/api/sessions", json={"session_id": "s2"})
        reply = self.client.post(
            "/api/sessions/s2/messages",
            json={"message": "hello", "system_prompt": "Be kind."},
        )
        self.assertEqual(reply.status_code, 200)
        payload = reply.json()
        self.assertEqual(payload["reply"], "reply:hello")

        user_message_id = next(item["id"] for item in payload["messages"] if item["role"] == "user")
        assistant_message_id = next(item["id"] for item in payload["messages"] if item["role"] == "assistant")

        updated = self.client.patch(
            f"/api/sessions/s2/messages/{user_message_id}",
            json={"content": "edited"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["messages"][1]["content"], "edited")

        system_prompt = self.client.patch(
            "/api/sessions/s2/system-prompt",
            json={"content": "Stay practical."},
        )
        self.assertEqual(system_prompt.status_code, 200)
        self.assertEqual(system_prompt.json()["messages"][0]["content"], "Stay practical.")
        self.assertEqual(system_prompt.json()["messages"][-1]["role"], "assistant")

        regenerated = self.client.post(f"/api/sessions/s2/messages/{user_message_id}/regenerate")
        self.assertEqual(regenerated.status_code, 200)
        self.assertEqual(regenerated.json()["reply"], "reply:regenerated")
        self.assertEqual(regenerated.json()["session"]["total_tokens"], 13)

        rolled_back = self.client.post(f"/api/sessions/s2/messages/{assistant_message_id}/rollback")
        self.assertEqual(rolled_back.status_code, 200)

    def test_streaming_endpoints(self):
        with self.client.stream(
            "POST",
            "/api/sessions/stream/messages/stream",
            json={"message": "hello stream"},
        ) as response:
            self.assertEqual(response.status_code, 200)
            body = "".join(response.iter_text())
        self.assertIn("event: chunk", body)
        self.assertIn("event: done", body)

        with self.client.stream(
            "POST",
            "/api/sessions/stream/messages/user-1/regenerate/stream",
            json={},
        ) as response:
            self.assertEqual(response.status_code, 200)
            body = "".join(response.iter_text())
        self.assertIn("reply:regenerated", body)


if __name__ == "__main__":
    unittest.main()
