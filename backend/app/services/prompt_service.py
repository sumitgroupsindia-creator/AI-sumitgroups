"""The instructions the product adds to every request, on top of what the customer typed.

Three things are assembled here, in this order:

1. the **base** template for the mode — who the assistant is, and the house style;
2. one **task** template, when the request is clearly a story, a caption, a poster; and
3. the customer's own words.

Choosing the task is a small extra model call — the router reads the task descriptions and answers
with a number. That costs money and time, so it is skippable: disabling the `task_router` row turns
routing off and leaves only the base template. The same is true of `image_vision_brief`, which is
what reads a photo the customer attached before anything is generated from it.

Every one of those helper calls is wrapped: if the router times out, misbehaves or answers nonsense,
the turn proceeds on the base template alone. A customer's request must never fail because an
optimisation did.
"""

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.prompt import PromptTemplate
from app.providers.base import ChatImage, ChatMessage
from app.providers.registry import get_chat_provider
from app.services import pricing_service, settings_service
from app.services.credit_service import record_usage

logger = get_logger("prompts")

ROUTER_KEY = "task_router"
VISION_KEY = "image_vision_brief"

# The shape asked for, in words. Also sent to OpenAI as a real `size`; Gemini's pinned SDK has no
# size parameter, so for that provider this sentence is the only control there is.
ASPECT_GUIDANCE: dict[str, str] = {
    "portrait": (
        "Compose it vertically, 9:16, for a phone — an Instagram story or WhatsApp status."
    ),
    "square": "Compose it as a 1:1 square, for an Instagram feed post.",
    "landscape": "Compose it as a wide 16:9 landscape banner.",
}
DEFAULT_ASPECT = "portrait"

_ROUTER_MAX_TOKENS = 4  # the answer is a single digit
_VISION_MAX_TOKENS = 120


@dataclass(frozen=True)
class ChatPrompt:
    system: str
    task_key: str | None


@dataclass(frozen=True)
class ImagePrompt:
    prompt: str
    task_key: str | None
    aspect: str
    vision_brief: str | None


async def _enabled(db: AsyncSession, *, scope: str, kind: str) -> list[PromptTemplate]:
    rows = (
        await db.execute(
            select(PromptTemplate)
            .where(
                PromptTemplate.scope == scope,
                PromptTemplate.kind == kind,
                PromptTemplate.is_enabled.is_(True),
            )
            .order_by(PromptTemplate.sort_order)
        )
    ).scalars().all()
    return list(rows)


async def _by_key(db: AsyncSession, key: str) -> PromptTemplate | None:
    row = (
        await db.execute(
            select(PromptTemplate).where(
                PromptTemplate.key == key, PromptTemplate.is_enabled.is_(True)
            )
        )
    ).scalar_one_or_none()
    return row


async def _spend(
    db: AsyncSession, *, user_id, request_id: str, provider: str, model: str, cost, operation: str
) -> None:
    """Record a helper call: no revenue, real cost.

    Charging the customer for it would break the price already quoted in the composer, so it is
    spent out of the margin — which is exactly why it has to reach the ledger. A cost the profit
    report cannot see is a cost that quietly eats the margin.
    """
    try:
        await record_usage(
            db,
            user_id=user_id,
            request_id=request_id,
            provider=provider,
            model=model,
            operation=operation,
            credits_consumed=0,
            cost_inr=cost,
            status="success",
        )
        await db.commit()
    except Exception:  # bookkeeping must never take down the answer it was recording
        logger.warning("prompts.spend_unrecorded", provider=provider, operation=operation, exc_info=True)
        await db.rollback()


async def _route(
    db: AsyncSession,
    *,
    scope: str,
    request_text: str,
    user_id,
    request_id: str,
    provider: str,
) -> PromptTemplate | None:
    """Ask a model which task template fits, if any."""
    router = await _by_key(db, ROUTER_KEY)
    if router is None:
        return None
    tasks = await _enabled(db, scope=scope, kind="task")
    if not tasks:
        return None

    catalogue = "\n".join(
        f"{i}. {task.name} — {task.description}" for i, task in enumerate(tasks, start=1)
    )
    question = f"Styles:\n{catalogue}\n\nRequest:\n{request_text}"

    # Routing is a chat call whichever mode it serves, so it is the chat row that names the model
    # and prices it.
    price = await pricing_service.price_for(db, provider, "chat")
    try:
        answer = await get_chat_provider(provider).complete(
            [ChatMessage(role="user", content=question)],
            price.model,
            system=router.content,
            max_tokens=_ROUTER_MAX_TOKENS,
        )
    except Exception as exc:  # routing is an optimisation; the turn goes on without it
        logger.warning("prompts.route_failed", provider=provider, error=str(exc))
        return None

    await _spend(
        db, user_id=user_id, request_id=request_id, provider=provider, model=price.model,
        cost=price.cost_inr, operation="assist_route",
    )

    match = re.search(r"\d+", answer or "")
    if match is None:
        return None
    choice = int(match.group())
    if 1 <= choice <= len(tasks):
        return tasks[choice - 1]
    return None  # 0, or a number the model invented


async def read_attachment(
    db: AsyncSession,
    image: ChatImage,
    *,
    user_id,
    request_id: str,
    provider: str,
) -> str | None:
    """Look at the photo the customer attached and say what is in it, in words.

    Image models are given the picture as well, but a plain description of the subject, its colours
    and any text on it keeps them from quietly replacing the product with a generic one.
    """
    brief = await _by_key(db, VISION_KEY)
    if brief is None:
        return None

    price = await pricing_service.price_for(db, provider, "chat")
    try:
        described = await get_chat_provider(provider).complete(
            [ChatMessage(role="user", content="Describe this photo.", image=image)],
            price.model,
            system=brief.content,
            max_tokens=_VISION_MAX_TOKENS,
        )
    except Exception as exc:
        logger.warning("prompts.vision_failed", provider=provider, error=str(exc))
        return None

    await _spend(
        db, user_id=user_id, request_id=request_id, provider=provider, model=price.model,
        cost=price.cost_inr, operation="assist_vision",
    )

    described = (described or "").strip()
    return described or None


async def compose_chat(
    db: AsyncSession,
    message: str,
    *,
    user_id,
    request_id: str,
    provider: str,
) -> ChatPrompt:
    """The system instructions for one chat turn."""
    parts: list[str] = []
    for base in await _enabled(db, scope="chat", kind="base"):
        parts.append(base.content)

    task = await _route(
        db, scope="chat", request_text=message, user_id=user_id, request_id=request_id,
        provider=provider,
    )
    if task is not None:
        parts.append(task.content)

    return ChatPrompt(system="\n\n".join(p for p in parts if p.strip()), task_key=task.key if task else None)


async def compose_image(
    db: AsyncSession,
    prompt: str,
    *,
    user_id,
    request_id: str,
    provider: str,
    aspect: str = DEFAULT_ASPECT,
    vision_brief: str | None = None,
) -> ImagePrompt:
    """The full text sent to an image model.

    Image APIs take one prompt and no system role, so the house style, the task, the shape, what the
    attached photo actually shows and the customer's own words are concatenated into a single
    instruction — the customer's words last, so nothing the product prepends can bury them.
    """
    parts: list[str] = []
    for base in await _enabled(db, scope="image", kind="base"):
        parts.append(base.content)

    task = await _route(
        db, scope="image", request_text=prompt, user_id=user_id, request_id=request_id,
        provider=provider,
    )
    if task is not None:
        parts.append(task.content)

    parts.append(ASPECT_GUIDANCE.get(aspect, ASPECT_GUIDANCE[DEFAULT_ASPECT]))

    if vision_brief:
        parts.append(f"The photo provided shows: {vision_brief}\nKeep that subject faithfully.")

    parts.append(f"What to make:\n{prompt}")

    return ImagePrompt(
        prompt="\n\n".join(p for p in parts if p.strip()),
        task_key=task.key if task else None,
        aspect=aspect,
        vision_brief=vision_brief,
    )


async def current_aspect() -> str:
    """The shape images are made in, from runtime settings. Portrait unless an admin says otherwise."""
    chosen = (await settings_service.get_str("image_aspect")).strip().lower()
    return chosen if chosen in ASPECT_GUIDANCE else DEFAULT_ASPECT
