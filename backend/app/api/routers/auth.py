"""Authentication and session endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from chat_store import (
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    authenticate_user,
    get_user_scope_for_role,
    register_user,
)

from backend.app.api.deps import get_bearer_token, get_current_user
from backend.app.schemas.auth import AuthTokenResponse, LoginRequest, RegisterRequest, UserProfile
from backend.app.schemas.common import ApiMessage
from backend.app.services.auth_service import create_session, revoke_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=ApiMessage, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> ApiMessage:
    result = register_user(
        employee_id=payload.employee_id,
        full_name=payload.full_name,
        password=payload.password,
        email=payload.email,
    )
    if not result.success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.message)

    return ApiMessage(message=result.message)


@router.post("/login", response_model=AuthTokenResponse)
def login(payload: LoginRequest, request: Request) -> AuthTokenResponse:
    result = authenticate_user(
        employee_id=payload.employee_id,
        password=payload.password,
    )
    if not result.success or result.user_id is None:
        status_code = status.HTTP_401_UNAUTHORIZED
        if result.approval_status in {APPROVAL_PENDING, APPROVAL_REJECTED}:
            status_code = status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=status_code, detail=result.message)

    token, expires_at = create_session(
        user_id=result.user_id,
        user_scope=get_user_scope_for_role(result.role),
        user_agent=request.headers.get("user-agent"),
    )

    return AuthTokenResponse(
        access_token=token,
        expires_at=expires_at,
        user=UserProfile(
            user_id=int(result.user_id),
            employee_id=str(result.employee_id),
            full_name=str(result.full_name),
            role=str(result.role),
            approval_status=str(result.approval_status),
            email=result.email,
        ),
    )


@router.get("/me", response_model=UserProfile)
def me(current_user: dict = Depends(get_current_user)) -> UserProfile:
    return UserProfile(**current_user)


@router.post("/logout", response_model=ApiMessage)
def logout(token: str = Depends(get_bearer_token)) -> ApiMessage:
    revoked = revoke_session(token)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session already invalid.")
    return ApiMessage(message="Logged out successfully.")
