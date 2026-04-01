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
                "messages": [],
            },
        )

        if system_prompt and not any(item["role"] == "system" for item in session["messages"]):
            session["messages"].append({"id": "sys-1", "role": "system", "content": system_prompt})
        session["messages"].append({"id": "user-1", "role": "user", "content": message})
        session["messages"].append({"id": "assistant-1", "role": "assistant", "content": f"reply:{message}"})
        session["title"] = message
        return ChatResult(
            session=self._summary(session),
            messages=list(session["messages"]),
            reply=f"reply:{message}",
            token_usage=None,
        )

    async def update_message(self, session_id: str, message_id: str, content: str):
        session = self._sessions[session_id]
        for index, message in enumerate(session["messages"]):
            if message["id"] == message_id:
                message["content"] = content
                session["messages"] = session["messages"][: index + 1]
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
        session["messages"].append({"id": "assistant-2", "role": "assistant", "content": "reply:regenerated"})
        return ChatResult(
            session=self._summary(session),
            messages=list(session["messages"]),
            reply="reply:regenerated",
            token_usage=None,
        )

    @staticmethod
    def _summary(session: dict):
        return {
            "session_id": session["session_id"],
            "title": session["title"],
            "created_at": session["created_at"],
            "updated_at": session["updated_at"],
            "message_count": len(session["messages"]),
            "preview": session["messages"][-1]["content"][:80] if session["messages"] else "",
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
        self.assertEqual(updated.json()["messages"][-1]["content"], "edited")

        regenerated = self.client.post(f"/api/sessions/s2/messages/{user_message_id}/regenerate")
        self.assertEqual(regenerated.status_code, 200)
        self.assertEqual(regenerated.json()["reply"], "reply:regenerated")

        rolled_back = self.client.post(f"/api/sessions/s2/messages/{assistant_message_id}/rollback")
        self.assertEqual(rolled_back.status_code, 200)


if __name__ == "__main__":
    unittest.main()
