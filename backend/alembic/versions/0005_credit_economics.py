"""one rupee-denominated wallet, and per-provider cost and margin

Revision ID: 0005_credit_economics
Revises: 0004_chat_thread
Create Date: 2026-08-26

Two changes that only make sense together.

A credit is now a rupee, which a split wallet cannot express: a customer holding "10 image credits
and 50 chat credits" holds no particular amount of money, and could be out of pictures while still
rich in words. The two balances are added together into one.

And a price is now three numbers rather than one — what the vendor bills us, what the customer pays
before margin, and the margin itself — so the product's economics are visible in the admin screens
instead of being implied by a single opaque credit_cost.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_credit_economics"
down_revision = "0004_chat_thread"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- provider economics -------------------------------------------------
    op.add_column(
        "provider_configs",
        sa.Column("provider_cost_inr", sa.Numeric(10, 4), nullable=False, server_default="0"),
    )
    op.add_column(
        "provider_configs",
        sa.Column("margin_credits", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "usage_records",
        sa.Column("cost_inr", sa.Numeric(10, 4), nullable=False, server_default="0"),
    )

    # Starting figures from published vendor pricing at the time of writing, converted at roughly
    # ₹88/$. They are seeded rather than hard-coded because an administrator is expected to correct
    # them from the real invoice — that is the entire point of putting them in the database.
    op.execute(
        """
        UPDATE provider_configs
           SET provider_cost_inr = 3.7000, credit_cost = 5, margin_credits = 3
         WHERE capability = 'image' AND provider = 'openai'
        """
    )
    op.execute(
        """
        UPDATE provider_configs
           SET provider_cost_inr = 3.5000, credit_cost = 5, margin_credits = 3
         WHERE capability = 'image' AND provider = 'gemini'
        """
    )
    # Chat carries no markup: it is the reason people come back, and a rupee-denominated wallet
    # already earns its margin on the pictures.
    op.execute(
        """
        UPDATE provider_configs
           SET provider_cost_inr = 0.1000, credit_cost = 1, margin_credits = 0
         WHERE capability = 'chat' AND provider = 'openai'
        """
    )
    op.execute(
        """
        UPDATE provider_configs
           SET provider_cost_inr = 0.0500, credit_cost = 1, margin_credits = 0
         WHERE capability = 'chat' AND provider = 'gemini'
        """
    )

    # --- one wallet ---------------------------------------------------------
    op.add_column("credits", sa.Column("balance", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE credits SET balance = chat_balance + image_balance")
    op.drop_column("credits", "chat_balance")
    op.drop_column("credits", "image_balance")

    op.add_column("plans", sa.Column("monthly_credits", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE plans SET monthly_credits = monthly_chat_credits + monthly_image_credits")
    op.drop_column("plans", "monthly_chat_credits")
    op.drop_column("plans", "monthly_image_credits")

    # Retuned so the allowance reads as the money paid: ₹999 buys 1000 credits. The old split
    # allowances summed to figures that no longer mean anything now that a credit is a rupee — 1200
    # for the Pro plan, most of it unspendable on pictures at the old image price.
    op.execute("UPDATE plans SET monthly_credits = 50 WHERE code = 'free'")
    op.execute("UPDATE plans SET monthly_credits = 1000 WHERE code = 'pro'")
    op.execute("UPDATE plans SET monthly_credits = 3000 WHERE code = 'business'")


def downgrade() -> None:
    op.add_column("plans", sa.Column("monthly_image_credits", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("plans", sa.Column("monthly_chat_credits", sa.Integer(), nullable=False, server_default="0"))
    # The split cannot be recovered, only guessed at: everything goes back to the chat side, which
    # at least preserves the total the customer is owed.
    op.execute("UPDATE plans SET monthly_chat_credits = monthly_credits")
    op.drop_column("plans", "monthly_credits")

    op.add_column("credits", sa.Column("image_balance", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("credits", sa.Column("chat_balance", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE credits SET chat_balance = balance")
    op.drop_column("credits", "balance")

    op.drop_column("usage_records", "cost_inr")
    op.drop_column("provider_configs", "margin_credits")
    op.drop_column("provider_configs", "provider_cost_inr")
