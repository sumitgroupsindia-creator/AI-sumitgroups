"""seed default plans and provider configs

Revision ID: 0002_seed_data
Revises: 0001_initial
Create Date: 2026-08-25

"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0002_seed_data"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

plans_table = sa.table(
    "plans",
    sa.column("id", sa.Uuid(as_uuid=True)),
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("description", sa.String),
    sa.column("price", sa.Numeric),
    sa.column("currency", sa.String),
    sa.column("billing_interval", sa.String),
    sa.column("monthly_chat_credits", sa.Integer),
    sa.column("monthly_image_credits", sa.Integer),
    sa.column("max_upload_mb", sa.Integer),
    sa.column("priority_queue", sa.Boolean),
    sa.column("is_active", sa.Boolean),
)

provider_configs_table = sa.table(
    "provider_configs",
    sa.column("id", sa.Uuid(as_uuid=True)),
    sa.column("provider", sa.String),
    sa.column("capability", sa.String),
    sa.column("model", sa.String),
    sa.column("is_enabled", sa.Boolean),
    sa.column("credit_cost", sa.Integer),
    sa.column("display_name", sa.String),
)


def upgrade() -> None:
    op.bulk_insert(
        plans_table,
        [
            dict(
                id=uuid.uuid4(), code="free", name="Free", description="Try the platform with limited credits",
                price=0, currency="INR", billing_interval="month",
                monthly_chat_credits=50, monthly_image_credits=10, max_upload_mb=5,
                priority_queue=False, is_active=True,
            ),
            dict(
                id=uuid.uuid4(), code="pro", name="Pro", description="For regular users who need higher limits",
                price=999, currency="INR", billing_interval="month",
                monthly_chat_credits=1000, monthly_image_credits=200, max_upload_mb=10,
                priority_queue=False, is_active=True,
            ),
            dict(
                id=uuid.uuid4(), code="business", name="Business", description="Priority processing and highest limits",
                price=2999, currency="INR", billing_interval="month",
                monthly_chat_credits=5000, monthly_image_credits=1000, max_upload_mb=25,
                priority_queue=True, is_active=True,
            ),
        ],
    )

    op.bulk_insert(
        provider_configs_table,
        [
            dict(id=uuid.uuid4(), provider="openai", capability="chat", model="gpt-4o-mini",
                 is_enabled=True, credit_cost=1, display_name="OpenAI"),
            dict(id=uuid.uuid4(), provider="gemini", capability="chat", model="gemini-2.0-flash",
                 is_enabled=True, credit_cost=1, display_name="Gemini"),
            dict(id=uuid.uuid4(), provider="openai", capability="image", model="gpt-image-1",
                 is_enabled=True, credit_cost=10, display_name="OpenAI"),
            dict(id=uuid.uuid4(), provider="gemini", capability="image", model="gemini-2.5-flash-image",
                 is_enabled=True, credit_cost=10, display_name="Gemini"),
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM provider_configs")
    op.execute("DELETE FROM plans")
