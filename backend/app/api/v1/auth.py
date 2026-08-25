from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await auth_service.register_user(db, payload.email, payload.password, payload.full_name)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    access, refresh = auth_service.issue_tokens(user)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await auth_service.authenticate_user(db, payload.email, payload.password)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    access, refresh = auth_service.issue_tokens(user)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        access, refresh_token = await auth_service.refresh_access_token(db, payload.refresh_token)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return TokenResponse(access_token=access, refresh_token=refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(_: User = Depends(get_current_user)):
    # Stateless JWTs: logout is enforced client-side by discarding tokens. A denylist keyed by jti
    # in Redis can be added here later if immediate server-side revocation becomes a requirement.
    return None


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.request_password_reset(db, payload.email)
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password_endpoint(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    try:
        await auth_service.reset_password(db, payload.token, payload.new_password)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return None
