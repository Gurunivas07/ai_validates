from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field

class CreateRunBody(BaseModel):
    requirements: str = Field(min_length=10, max_length=20000)

class CompilerRunOut(BaseModel):
    id: str
    requirements: str
    status: str
    currentStage: int | None
    retryCount: int
    isEvalRun: bool
    evalPromptId: str | None
    totalTokens: int | None
    totalCostUsd: float | None
    createdAt: str
    completedAt: str | None
    durationMs: int | None

class StageOut(BaseModel):
    id: str
    runId: str
    stageNumber: int
    stageName: str
    status: str
    output: dict | list | None
    error: str | None
    promptTokens: int | None
    completionTokens: int | None
    totalTokens: int | None
    estimatedCostUsd: float | None
    startedAt: str | None
    completedAt: str | None
    durationMs: int | None

class CompilerRunDetailOut(CompilerRunOut):
    stages: list[StageOut]


class RegisterBody(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=6, max_length=100)

class LoginBody(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=6, max_length=100)
