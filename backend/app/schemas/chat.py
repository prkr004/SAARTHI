"""Conversation and message schemas for Phase 2 APIs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.core.sanitization import sanitize_text


class ConversationSummary(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str
    message_count: int


class CreateConversationRequest(BaseModel):
    title: str = Field(default="New Chat", min_length=1, max_length=80)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> str:
        cleaned = sanitize_text(value, collapse_whitespace=True)
        if not cleaned:
            raise ValueError("Chat title cannot be empty.")
        return cleaned[:80]


class ConversationCreatedResponse(BaseModel):
    id: int
    title: str


class EnsureDefaultConversationResponse(BaseModel):
    conversation_id: int


class RenameConversationRequest(BaseModel):
    new_title: str = Field(min_length=1, max_length=80)

    @field_validator("new_title", mode="before")
    @classmethod
    def normalize_new_title(cls, value: object) -> str:
        cleaned = sanitize_text(value, collapse_whitespace=True)
        if not cleaned:
            raise ValueError("Chat title cannot be empty.")
        return cleaned[:80]


class MessageItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    sources: list[dict[str, Any]]


class AddMessageRequest(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)
    sources: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("content", mode="before")
    @classmethod
    def normalize_content(cls, value: object) -> str:
        cleaned = sanitize_text(value, collapse_whitespace=False)
        if not cleaned:
            raise ValueError("Message content cannot be empty.")
        return cleaned
