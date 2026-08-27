from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import StreamingResponse

from app.core.deps import get_current_user, get_db
from app.core.logging import get_logger, new_request_id
from app.models.chat import Conversation, Message
from app.models.image import GenerationRequest, UploadedFile
from app.models.user import User
from app.api.v1.images import to_request_response
from app.schemas.chat import (
    ChatStreamRequest,
    CreateConversationRequest,
    ConversationDetailResponse,
    ConversationResponse,
    MessageResponse,
    RenameConversationRequest,
)
from app.services import entitlement_service, chat_service

router = APIRouter(prefix="/chat", tags=["chat"])
conversations_router = APIRouter(prefix="/conversations", tags=["chat"])
logger = get_logger("chat.api")


@router.post("/stream")
async def chat_stream(
    payload: ChatStreamRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request_id = new_request_id()
    primary = payload.providers[0]

    # Before anything is reserved or streamed: a slot the plan does not include is refused outright
    # rather than half-answered.
    try:
        await entitlement_service.check_allowed(db, user.id, payload.providers)
    except entitlement_service.PlanNotEntitledError:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="This model needs a paid plan. Upgrade to use it.",
        )

    try:
        model = await chat_service.resolve_chat_model(db, primary)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    # Rejected here rather than dropped silently in the service: a user who attached an image and
    # got a reply that ignored it would have no way to tell what went wrong.
    if payload.upload_file_id is not None:
        owned = (
            await db.execute(
                select(UploadedFile).where(
                    UploadedFile.id == payload.upload_file_id, UploadedFile.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        if owned is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    try:
        conversation = await chat_service.get_or_create_conversation(
            db, user.id, payload.conversation_id, primary, model, payload.message
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    conversation_id = conversation.id

    async def event_source():
        async for chunk in chat_service.stream_chat_message(
            user_id=user.id,
            conversation_id=conversation_id,
            user_message=payload.message,
            provider_names=payload.providers,
            upload_file_id=payload.upload_file_id,
            request_id=request_id,
        ):
            if await request.is_disconnected():
                logger.info("chat.stream_client_disconnected", request_id=request_id)
                break
            yield chunk

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Request-Id": request_id, "X-Conversation-Id": str(conversation_id)},
    )


@conversations_router.get("", response_model=list[ConversationResponse])
async def list_conversations(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id, Conversation.is_archived == False)  # noqa: E712
        .order_by(Conversation.updated_at.desc())
    )
    return result.scalars().all()


@conversations_router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: CreateConversationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Opens an empty thread so a session that starts with an image generation still has one."""
    try:
        model = await chat_service.resolve_chat_model(db, payload.provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    conversation = Conversation(
        user_id=user.id, title=payload.title[:255], provider=payload.provider, model=model
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


@conversations_router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    await db.refresh(conversation, attribute_names=["messages"])

    # Images generated from inside this conversation belong in its thread. Returned separately
    # rather than merged server-side because a generation may still be running while the messages
    # around it are already final — the client interleaves them by created_at and polls the rest.
    generations = (
        (
            await db.execute(
                select(GenerationRequest)
                .where(GenerationRequest.conversation_id == conversation_id)
                .options(selectinload(GenerationRequest.results))
                .order_by(GenerationRequest.created_at)
            )
        )
        .scalars()
        .all()
    )

    return ConversationDetailResponse(
        **ConversationResponse.model_validate(conversation).model_dump(),
        messages=[MessageResponse.model_validate(m) for m in conversation.messages],
        generations=[to_request_response(g) for g in generations],
    )


@conversations_router.patch("/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: UUID,
    payload: RenameConversationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    conversation.title = payload.title
    await db.commit()
    await db.refresh(conversation)
    return conversation


@conversations_router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    await db.execute(delete(Conversation).where(Conversation.id == conversation.id))
    await db.commit()
    return None
