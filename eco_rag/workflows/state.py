from enum import Enum

from pydantic import BaseModel, Field


class WorkflowStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStep(str, Enum):
    QUERY_PROCESSING = "query_processing"
    RETRIEVAL = "retrieval"
    GENERATION = "generation"
    FINALIZATION = "finalization"


class StepState(BaseModel):
    step: WorkflowStep
    status: WorkflowStatus = WorkflowStatus.QUEUED
    detail: str | None = None


class ChatRunState(BaseModel):
    user_query: str
    status: WorkflowStatus = WorkflowStatus.QUEUED
    steps: list[StepState] = Field(default_factory=list)
    final_answer: str | None = None
    events: list[dict] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    def set_step(self, step: WorkflowStep, status: WorkflowStatus, detail: str | None = None):
        for existing in self.steps:
            if existing.step == step:
                existing.status = status
                existing.detail = detail
                return
        self.steps.append(StepState(step=step, status=status, detail=detail))
