"""admin-managed settings, their audit trail, and provider branding

Revision ID: 0003_admin_settings
Revises: 0002_seed_data
Create Date: 2026-08-25

"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0003_admin_settings"
down_revision = "0002_seed_data"
branch_labels = None
depends_on = None

provider_brands_table = sa.table(
    "provider_brands",
    sa.column("id", sa.Uuid(as_uuid=True)),
    sa.column("provider", sa.String),
    sa.column("slot", sa.String),
    sa.column("tier", sa.String),
    sa.column("description", sa.String),
    sa.column("sort_order", sa.Integer),
)


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False, unique=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
    )

    op.create_table(
        "app_setting_audits",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("actor_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_email", sa.String(255), nullable=False),
        sa.Column("old_preview", sa.String(255), nullable=False, server_default=""),
        sa.Column("new_preview", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
    )
    op.create_index("ix_app_setting_audits_key", "app_setting_audits", ["key"])

    op.create_table(
        "provider_brands",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False, unique=True),
        sa.Column("slot", sa.String(50), nullable=False),
        sa.Column("tier", sa.String(50), nullable=False),
        sa.Column("description", sa.String(255), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
    )

    # Seeded to exactly what the frontend previously hard-coded, so the customer-facing UI is
    # unchanged the moment this lands and only moves when an administrator decides it should.
    op.bulk_insert(
        provider_brands_table,
        [
            dict(
                id=uuid.uuid4(), provider="openai", slot="Model 1", tier="Standard",
                description="Balanced quality and speed for everyday prompts.", sort_order=1,
            ),
            dict(
                id=uuid.uuid4(), provider="gemini", slot="Model 2", tier="Premium",
                description="Alternative interpretation, often stronger on detail and lighting.",
                sort_order=2,
            ),
        ],
    )


def downgrade() -> None:
    op.drop_table("provider_brands")
    op.drop_index("ix_app_setting_audits_key", table_name="app_setting_audits")
    op.drop_table("app_setting_audits")
    op.drop_table("app_settings")
