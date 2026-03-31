from fastapi import FastAPI

from eco_rag.config import Config
from eco_rag.workflows.state import WorkflowStatus, WorkflowStep

app = FastAPI(
    title="Eco_RAG API",
    version="0.1.0",
    description="Backend entrypoint for the Eco_RAG desktop and web clients.",
)


@app.get("/api/health")
def health():
    return {"status": "ok", "model": Config.MODEL}


@app.get("/api/meta")
def meta():
    return {
        "workflow_statuses": [status.value for status in WorkflowStatus],
        "workflow_steps": [step.value for step in WorkflowStep],
    }
