"""chat message attachments, and generations belonging to a conversation

Revision ID: 0004_chat_thread
Revises: 0003_admin_settings
Create Date: 2026-08-25

"""
from alembic import op
import sqlalchemy as sa

revision = "0004_chat_thread"
down_revision = "0003_admin_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # An image attached to a chat turn. SET NULL, not CASCADE: deleting the stored file should not
    # take the conversation turn that referenced it with it.
    op.add_column("messages", sa.Column("upload_file_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_messages_upload_file", "messages", "uploaded_files", ["upload_file_id"], ["id"], ondelete="SET NULL"
    )

    # Lets a generation started from chat be replayed inside that conversation's timeline. Nullable
    # because generations made outside a conversation stay valid and unattached.
    op.add_column("generation_requests", sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=True))
    # Index before the constraint: MySQL creates one implicitly for a foreign key that has none, and
    # would then leave two indexes covering the same column.
    op.create_index("ix_gen_requests_conversation", "generation_requests", ["conversation_id"])
    op.create_foreign_key(
        "fk_gen_requests_conversation",
        "generation_requests",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Constraint first: MySQL refuses to drop the index a foreign key depends on.
    op.drop_constraint("fk_gen_requests_conversation", "generation_requests", type_="foreignkey")
    op.drop_index("ix_gen_requests_conversation", table_name="generation_requests")
    op.drop_column("generation_requests", "conversation_id")

    op.drop_constraint("fk_messages_upload_file", "messages", type_="foreignkey")
    op.drop_column("messages", "upload_file_id")
