"""initial schema (MySQL 8)

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

# SQLAlchemy's generic Uuid renders as CHAR(32) on MySQL — compact, indexable, and portable
# if the database is ever moved to Postgres later.
UUID = sa.Uuid(as_uuid=True)

TABLE_KW = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


def _pk():
    return sa.Column("id", UUID, primary_key=True)


def _timestamps():
    # fsp=6 (microseconds): plain DATETIME truncates to seconds, which ties rows created in the
    # same second and breaks created_at ordering.
    return [
        sa.Column(
            "created_at", mysql.DATETIME(fsp=6), server_default=sa.text("CURRENT_TIMESTAMP(6)"), nullable=False
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        _pk(),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("auth_provider", sa.String(50), nullable=True),
        sa.Column("provider_user_id", sa.String(255), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("email", name="uq_users_email"),
        **TABLE_KW,
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "password_resets",
        _pk(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("used", sa.Boolean, nullable=False, server_default=sa.text("0")),
        *_timestamps(),
        sa.UniqueConstraint("token_hash", name="uq_password_resets_token_hash"),
        **TABLE_KW,
    )
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])

    op.create_table(
        "plans",
        _pk(),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("billing_interval", sa.String(20), nullable=False, server_default="month"),
        sa.Column("monthly_chat_credits", sa.Integer, nullable=False, server_default="0"),
        sa.Column("monthly_image_credits", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_upload_mb", sa.Integer, nullable=False, server_default="10"),
        sa.Column("priority_queue", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        *_timestamps(),
        sa.UniqueConstraint("code", name="uq_plans_code"),
        **TABLE_KW,
    )

    op.create_table(
        "subscriptions",
        _pk(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", UUID, sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("provider", sa.String(20), nullable=False, server_default="razorpay"),
        sa.Column("provider_subscription_id", sa.String(255), nullable=True),
        sa.Column("provider_customer_id", sa.String(255), nullable=True),
        sa.Column("current_period_start", sa.DateTime, nullable=True),
        sa.Column("current_period_end", sa.DateTime, nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("cancelled_at", sa.DateTime, nullable=True),
        *_timestamps(),
        **TABLE_KW,
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"])
    op.create_index("ix_subscriptions_provider_sub_id", "subscriptions", ["provider_subscription_id"])

    op.create_table(
        "credits",
        _pk(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chat_balance", sa.Integer, nullable=False, server_default="0"),
        sa.Column("image_balance", sa.Integer, nullable=False, server_default="0"),
        *_timestamps(),
        sa.UniqueConstraint("user_id", name="uq_credits_user"),
        sa.CheckConstraint("chat_balance >= 0", name="ck_credits_chat_non_negative"),
        sa.CheckConstraint("image_balance >= 0", name="ck_credits_image_non_negative"),
        **TABLE_KW,
    )

    op.create_table(
        "usage_records",
        _pk(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("operation", sa.String(30), nullable=False),
        sa.Column("credits_consumed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        *_timestamps(),
        **TABLE_KW,
    )
    op.create_index("ix_usage_records_user_id", "usage_records", ["user_id"])
    op.create_index("ix_usage_records_request_id", "usage_records", ["request_id"])

    op.create_table(
        "idempotency_keys",
        _pk(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("response_body", sa.Text, nullable=True),
        sa.Column("status_code", sa.Integer, nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),
        **TABLE_KW,
    )

    op.create_table(
        "conversations",
        _pk(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False, server_default="New Chat"),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False, server_default="openai"),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default=sa.text("0")),
        *_timestamps(),
        **TABLE_KW,
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_index("ix_conversations_user_created", "conversations", ["user_id", "created_at"])

    op.create_table(
        "messages",
        _pk(),
        sa.Column("conversation_id", UUID, sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        *_timestamps(),
        **TABLE_KW,
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"])

    op.create_table(
        "uploaded_files",
        _pk(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stored_filename", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("stored_filename", name="uq_uploaded_files_stored_filename"),
        **TABLE_KW,
    )
    op.create_index("ix_uploaded_files_user_id", "uploaded_files", ["user_id"])

    op.create_table(
        "generation_requests",
        _pk(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("upload_file_id", UUID, sa.ForeignKey("uploaded_files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("request_ref", sa.String(64), nullable=False),
        *_timestamps(),
        **TABLE_KW,
    )
    op.create_index("ix_generation_requests_user_id", "generation_requests", ["user_id"])
    op.create_index("ix_gen_requests_user_created", "generation_requests", ["user_id", "created_at"])
    op.create_index("ix_generation_requests_request_ref", "generation_requests", ["request_ref"])

    op.create_table(
        "generated_images",
        _pk(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stored_filename", sa.String(255), nullable=False),
        sa.Column("thumbnail_filename", sa.String(255), nullable=True),
        sa.Column("content_type", sa.String(100), nullable=False, server_default="image/png"),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("size_bytes", sa.Integer, nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("stored_filename", name="uq_generated_images_stored_filename"),
        **TABLE_KW,
    )
    op.create_index("ix_generated_images_user_id", "generated_images", ["user_id"])

    op.create_table(
        "generation_results",
        _pk(),
        sa.Column("request_id", UUID, sa.ForeignKey("generation_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("parent_result_id", UUID, sa.ForeignKey("generation_results.id", ondelete="SET NULL"), nullable=True),
        sa.Column("generated_image_id", UUID, sa.ForeignKey("generated_images.id", ondelete="SET NULL"), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        *_timestamps(),
        **TABLE_KW,
    )
    op.create_index("ix_gen_results_request", "generation_results", ["request_id"])

    op.create_table(
        "provider_configs",
        _pk(),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("capability", sa.String(20), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("credit_cost", sa.Integer, nullable=False, server_default="1"),
        sa.Column("display_name", sa.String(100), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("provider", "capability", name="uq_provider_capability"),
        **TABLE_KW,
    )


def downgrade() -> None:
    op.drop_table("provider_configs")
    op.drop_table("generation_results")
    op.drop_table("generated_images")
    op.drop_table("generation_requests")
    op.drop_table("uploaded_files")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("idempotency_keys")
    op.drop_table("usage_records")
    op.drop_table("credits")
    op.drop_table("subscriptions")
    op.drop_table("plans")
    op.drop_table("password_resets")
    op.drop_table("users")
