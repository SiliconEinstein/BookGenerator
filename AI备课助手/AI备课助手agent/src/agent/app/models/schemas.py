from typing import Any
from pydantic import BaseModel, Field

class TaskRequest(BaseModel):
    externalTaskId: str
    taskType: int
    courseId: int
    targetId: int | None = None
    callbackUrl: str | None = ''
    config: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)

class AcceptedResponse(BaseModel):
    code: int = 0
    message: str = 'accepted'
    data: dict[str, Any]
