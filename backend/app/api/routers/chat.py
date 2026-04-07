"""Conversation and message APIs for authenticated users."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status

from chat_store import (
    add_message,
    create_conversation,
    delete_conversation,
    ensure_user_has_conversation,
    get_messages,
    list_conversations,
    rename_conversation,
)

from backend.app.api.deps import get_current_user
from backend.app.schemas.chat import (
    AddMessageRequest,
    ConversationCreatedResponse,
    ConversationSummary,
    CreateConversationRequest,
    EnsureDefaultConversationResponse,
    MessageItem,
    RenameConversationRequest,
)
from backend.app.schemas.common import ApiMessage

router = APIRouter(prefix="/conversations", tags=["chat"])


def _raise_for_permission_error(error: Exception) -> None:
    if isinstance(error, PermissionError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conversation access denied.",
        ) from error


@router.get("", response_model=list[ConversationSummary])
def list_user_conversations(current_user: dict = Depends(get_current_user)) -> list[ConversationSummary]:
    user_id = int(current_user["user_id"])
    conversations = list_conversations(user_id=user_id)
    return [ConversationSummary(**conversation) for conversation in conversations]


@router.post("", response_model=ConversationCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_user_conversation(
    payload: CreateConversationRequest,
    current_user: dict = Depends(get_current_user),
) -> ConversationCreatedResponse:
    user_id = int(current_user["user_id"])
    new_id = create_conversation(user_id=user_id, title=payload.title)
    return ConversationCreatedResponse(id=new_id, title=payload.title)


@router.post("/default", response_model=EnsureDefaultConversationResponse)
def ensure_default_conversation(current_user: dict = Depends(get_current_user)) -> EnsureDefaultConversationResponse:
    user_id = int(current_user["user_id"])
    conversation_id = ensure_user_has_conversation(user_id=user_id)
    return EnsureDefaultConversationResponse(conversation_id=conversation_id)


@router.patch("/{conversation_id}", response_model=ConversationCreatedResponse)
def rename_user_conversation(
    payload: RenameConversationRequest,
    conversation_id: int = Path(ge=1),
    current_user: dict = Depends(get_current_user),
) -> ConversationCreatedResponse:
    user_id = int(current_user["user_id"])
    try:
        updated_title = rename_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            new_title=payload.new_title,
        )
    except Exception as error:
        _raise_for_permission_error(error)
        if isinstance(error, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
        raise

    return ConversationCreatedResponse(id=conversation_id, title=updated_title)


@router.delete("/{conversation_id}", response_model=ApiMessage)
def delete_user_conversation(
    conversation_id: int = Path(ge=1),
    current_user: dict = Depends(get_current_user),
) -> ApiMessage:
    user_id = int(current_user["user_id"])
    try:
        delete_conversation(conversation_id=conversation_id, user_id=user_id)
    except Exception as error:
        _raise_for_permission_error(error)
        raise

    return ApiMessage(message="Conversation deleted.")


@router.get("/{conversation_id}/messages", response_model=list[MessageItem])
def list_conversation_messages(
    conversation_id: int = Path(ge=1),
    current_user: dict = Depends(get_current_user),
) -> list[MessageItem]:
    user_id = int(current_user["user_id"])
    try:
        messages = get_messages(conversation_id=conversation_id, user_id=user_id)
    except Exception as error:
        _raise_for_permission_error(error)
        raise

    return [MessageItem(**message) for message in messages]


@router.post("/{conversation_id}/messages", response_model=ApiMessage, status_code=status.HTTP_201_CREATED)
def add_conversation_message(
    payload: AddMessageRequest,
    conversation_id: int = Path(ge=1),
    current_user: dict = Depends(get_current_user),
) -> ApiMessage:
    user_id = int(current_user["user_id"])
    try:
        add_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role=payload.role,
            content=payload.content,
            sources=payload.sources,
        )
    except Exception as error:
        _raise_for_permission_error(error)
        if isinstance(error, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
        raise

    return ApiMessage(message="Message added.")
