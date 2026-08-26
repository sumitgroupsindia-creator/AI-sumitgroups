"""editable master prompts, and a smaller signup grant

Revision ID: 0006_prompt_templates
Revises: 0005_credit_economics
Create Date: 2026-08-26

The product previously sent the customer's words to the model untouched: no identity, no house
style, no format. Every answer was whatever the vendor's default happened to be, and the white
labelling stopped at the UI — a model asked who it was would happily say.

These rows are the instructions the product adds on top. They live in the database rather than in
source because prompt wording is the thing most likely to need changing, and changing it should not
need an engineer.
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0006_prompt_templates"
down_revision = "0005_credit_economics"
branch_labels = None
depends_on = None

prompt_templates = sa.table(
    "prompt_templates",
    sa.column("id", sa.Uuid(as_uuid=True)),
    sa.column("key", sa.String),
    sa.column("scope", sa.String),
    sa.column("kind", sa.String),
    sa.column("name", sa.String),
    sa.column("description", sa.String),
    sa.column("content", sa.Text),
    sa.column("is_enabled", sa.Boolean),
    sa.column("sort_order", sa.Integer),
)

CHAT_BASE = """You are the AI assistant of Sumit Groups.

Who you are writing for: owners of small Indian businesses — shops, cafes, salons, boutiques — who
are doing their own marketing. They are not marketers and not technical.

How to answer:
- Reply in the language they wrote in. Hindi in, Hindi out. Hinglish in, Hinglish out.
- Give them the finished thing — the caption, the message, the script — not advice on how to write
  one.
- Keep it short unless they ask for length. Most of what they need fits in a few lines.
- Use rupees, Indian festivals, and Indian phone and address formats.
- If a request is vague, make one sensible assumption, say what you assumed in a single line, and
  deliver the work anyway. Do not open with questions.

Never name the AI model or company behind you, and never claim to be one. You are Sumit Groups'
assistant."""

IMAGE_BASE = """Produce a finished, ready-to-post image.

- Sharp, well lit, clean composition, with room to breathe at the top and bottom where a phone's
  interface sits over the picture.
- Any text in the image must be spelled correctly and be large enough to read on a phone.
- Where people, food, clothing or signage appear, keep the setting recognisably Indian.
- No watermarks, no logos you were not asked for, no borders, no stock-photo artefacts."""

STORY = """They want a story or a script. Write the piece itself, not an outline of one.

- Open on a concrete moment. No throat-clearing, no "once upon a time".
- One character who wants one thing, and something in the way of it.
- Carry it with action and dialogue. Keep description tight.
- Land the ending. Do not trail off, and do not tack on a moral.
- Match the length asked for. With no length given, aim for 300-500 words; for a reel or video
  script, write to the seconds requested and mark the shots.
- Write in the register a person actually speaks, in their language."""

CAPTION = """They want social copy — a caption, a post, a broadcast message or an ad line.

- Lead with the hook. The first line has to work alone, because it is all most people will see.
- One idea per post. Cut whatever is not that idea.
- Close with one clear thing to do: call, message, visit, order.
- Hashtags only if asked for, and then a handful that fit, not thirty.
- When the request is short, give two or three options so they can pick."""

POSTER = """The image has to carry text — a poster, banner, offer or menu.

- The headline is the design. Make it the largest element and readable at a glance on a phone.
- Hold strong contrast between text and background. Never set small text over a busy area.
- Leave a clear band for the details — price, dates, phone number — and keep them legible.
- Reproduce every name, number and price exactly as given. Invent nothing, change nothing."""

TASK_ROUTER = """You match a request to the writing style that fits it.

You are given a numbered list of styles and one request. Answer with the number of the best fit, or
0 if none clearly applies. A style has to be a real fit — when in doubt, answer 0.

Answer with the number alone. No words, no punctuation, no explanation."""

VISION_BRIEF = """Describe the attached photo for an image generator that cannot see it.

In 60 words or fewer, give: what the subject is, its colours and materials, any text or branding
visible on it, and the lighting. Be specific and factual — "a matte black steel bottle with a bamboo
lid, 'HYDRA' printed in white" beats "a bottle".

Do not judge the photo, do not suggest improvements, and leave the background out unless the subject
makes no sense without it."""


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(50), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", mysql.DATETIME(fsp=6), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column(
            "updated_at", mysql.DATETIME(fsp=6), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.UniqueConstraint("key", name="uq_prompt_templates_key"),
    )

    op.bulk_insert(
        prompt_templates,
        [
            dict(
                id=uuid.uuid4(), key="chat_base", scope="chat", kind="base",
                name="Assistant identity",
                description="Always applied to every chat turn.",
                content=CHAT_BASE, is_enabled=True, sort_order=1,
            ),
            dict(
                id=uuid.uuid4(), key="image_base", scope="image", kind="base",
                name="Image house style",
                description="Always applied to every generated image.",
                content=IMAGE_BASE, is_enabled=True, sort_order=2,
            ),
            dict(
                id=uuid.uuid4(), key="story", scope="chat", kind="task",
                name="Story or script",
                description=(
                    "The person wants a story, a narrative, a reel or video script, or any piece of "
                    "writing with characters and a plot."
                ),
                content=STORY, is_enabled=True, sort_order=10,
            ),
            dict(
                id=uuid.uuid4(), key="caption", scope="chat", kind="task",
                name="Social caption or ad copy",
                description=(
                    "The person wants a social media caption, an Instagram or WhatsApp post, a "
                    "broadcast message, a tagline or an advertisement line."
                ),
                content=CAPTION, is_enabled=True, sort_order=11,
            ),
            dict(
                id=uuid.uuid4(), key="poster", scope="image", kind="task",
                name="Poster or banner",
                description=(
                    "The image is a poster, banner, offer, sale announcement, menu or anything whose "
                    "main job is to display text such as a price, a date or a phone number."
                ),
                content=POSTER, is_enabled=True, sort_order=12,
            ),
            dict(
                id=uuid.uuid4(), key="task_router", scope="chat", kind="tool",
                name="Task router",
                description=(
                    "Picks which task template fits a request. Turning this off skips the routing "
                    "call and its cost, leaving only the base template."
                ),
                content=TASK_ROUTER, is_enabled=True, sort_order=90,
            ),
            dict(
                id=uuid.uuid4(), key="image_vision_brief", scope="image", kind="tool",
                name="Read the attached photo",
                description=(
                    "Studies a photo the customer attached and describes it for the image model. "
                    "Turning this off skips the extra vision call and its cost."
                ),
                content=VISION_BRIEF, is_enabled=True, sort_order=91,
            ),
        ],
    )

    # A signup grant of 50 credits was six free images. Ten is one image and a short conversation —
    # enough to see what the product does, not enough to be the product.
    op.execute("UPDATE plans SET monthly_credits = 10 WHERE code = 'free'")


def downgrade() -> None:
    op.execute("UPDATE plans SET monthly_credits = 50 WHERE code = 'free'")
    op.drop_table("prompt_templates")
