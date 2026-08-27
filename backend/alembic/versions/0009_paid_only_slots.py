"""some slots are for paying customers only

Revision ID: 0009_paid_only_slots
Revises: 0008_cost_plus_flat_margin
Create Date: 2026-08-27

The premium slot — and therefore asking both slots at once — becomes something a free account
cannot reach.

Carried on the *brand* rather than on a plan, because the question "is this slot premium?" is a
property of the slot, and the brand row is already the one thing that describes a slot as customers
meet it. Putting it here also means an administrator can move which slot is premium from the
Branding screen without a deploy, and without anybody hard-coding "gemini is the paid one" into
the billing path — the product deliberately never names vendors to customers, and a gate that did
would leak one.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_paid_only_slots"
down_revision = "0008_cost_plus_flat_margin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_brands",
        sa.Column("requires_paid_plan", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # The second slot in display order is the premium one. Addressed by sort_order rather than by
    # provider name so this says what it means: the *second* slot is the paid one, whichever vendor
    # happens to sit behind it today.
    op.execute(
        """
        UPDATE provider_brands
           SET requires_paid_plan = TRUE
         WHERE sort_order = (SELECT * FROM (SELECT MAX(sort_order) FROM provider_brands) AS m)
           AND (SELECT * FROM (SELECT COUNT(*) FROM provider_brands) AS c) > 1
        """
    )


def downgrade() -> None:
    op.drop_column("provider_brands", "requires_paid_plan")
