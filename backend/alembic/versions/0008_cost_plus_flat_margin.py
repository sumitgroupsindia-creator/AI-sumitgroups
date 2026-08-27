"""charge what the vendor charged, plus a flat margin

Revision ID: 0008_cost_plus_flat_margin
Revises: 0007_token_metered_chat
Create Date: 2026-08-27

0007 made chat honest about what it cost us but sold it at cost, and left image generation on a
made-up base price: images charged `credit_cost + margin_credits` (5 + 3 = 8) against a ~₹3.70
bill, so the margin was really ₹4.30 and no field said so.

Both now work the same way, and the way is the simple one:

    charge = what the vendor billed us  +  a flat margin

Chat's vendor bill comes from real token counts; an image's comes from `provider_cost_inr`. The
margin is a plain number of credits an administrator can read as rupees earned — 0.5 on a chat
turn, 3 on a picture — which is why it has to hold halves, and therefore stops being an integer.

`credit_cost` goes with it. Under the old formula it was the base the customer paid before margin;
under this one the base is whatever the vendor actually charged, so the column had no remaining
meaning and would have sat in the admin screens doing nothing.
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_cost_plus_flat_margin"
down_revision = "0007_token_metered_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Halves are the whole point: a chat turn earns 0.5, which an integer column cannot hold.
    op.alter_column(
        "provider_configs", "margin_credits",
        existing_type=sa.Integer(),
        type_=sa.Numeric(10, 4),
        existing_nullable=False,
        server_default="0",
    )

    op.execute("UPDATE provider_configs SET margin_credits = 0.5000 WHERE capability = 'chat'")
    op.execute("UPDATE provider_configs SET margin_credits = 3.0000 WHERE capability = 'image'")

    # The base price the customer used to pay before margin. The vendor's own bill is the base now.
    op.drop_column("provider_configs", "credit_cost")


def downgrade() -> None:
    op.add_column(
        "provider_configs",
        sa.Column("credit_cost", sa.Integer(), nullable=False, server_default="1"),
    )
    # The old split cannot be recovered, only approximated from the prices that were in use.
    op.execute("UPDATE provider_configs SET credit_cost = 5 WHERE capability = 'image'")
    op.execute("UPDATE provider_configs SET credit_cost = 1 WHERE capability = 'chat'")
    op.execute("UPDATE provider_configs SET margin_credits = ROUND(margin_credits)")
    op.alter_column(
        "provider_configs", "margin_credits",
        existing_type=sa.Numeric(10, 4),
        type_=sa.Integer(),
        existing_nullable=False,
        server_default="3",
    )
