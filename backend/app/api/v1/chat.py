from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.core.deps import get_current_user, get_db
from app.core.logging import get_logger, new_request_id
from app.models.chat import Conversation, Message
from app.models.user import User
from app.schemas.chat import (
    ChatStreamRequest,
    ConversationDetailResponse,
    ConversationResponse,
    RenameConversationRequest,
)
from app.services import chat_service
from app.core.config import get_settings

router = APIRouter(prefix="/chat", tags=["chat"])
conversations_router = APIRouter(prefix="/conversations", tags=["chat"])
logger = get_logger("chat.api")
settings = get_settings()

_DEFAULT_MODELS = {"openai": settings.openai_chat_model, "gemini": settings.gemini_chat_model}


@router.post("/stream")
async def chat_stream(
    payload: ChatStreamRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    model = _DEFAULT_MODELS[payload.provider]
    request_id = new_request_id()

    try:
        conversation = await chat_service.get_or_create_conversation(
            db, user.id, payload.conversation_id, payload.provider, model, payload.message
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    conversation_id = conversation.id

    async def event_source():
        async for chunk in chat_service.stream_chat_message(
            user_id=user.id,
            conversation_id=conversation_id,
            user_message=payload.message,
            provider_name=payload.provider,
            model=model,
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
    return conversation


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
