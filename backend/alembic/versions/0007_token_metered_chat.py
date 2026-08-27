"""chat billed on the tokens the vendor actually reports

Revision ID: 0007_token_metered_chat
Revises: 0006_prompt_templates
Create Date: 2026-08-27

Chat was priced as one flat credit per turn against one flat assumed vendor cost. Neither number
survives contact with a real conversation: a two-word reply and a thousand-word one cost us
different amounts and were charged the same, and the "cost" in the margin report was an estimate
somebody typed rather than anything OpenAI or Google ever billed. Long answers ran under cost;
short ones were marked up many times over.

So three changes that only make sense together:

* prices become **rates** — rupees per million input and per million output tokens, the unit every
  vendor publishes — plus a markup multiplier, since a bill that scales with the answer needs a
  margin that scales with it too;
* the ledger gains the **token counts** behind each charge, so a line can be reconciled against the
  vendor's own invoice instead of being taken on trust;
* the wallet learns **fractions of a rupee**. A metered chat turn costs a fraction of one, and an
  integer balance can only round that: up, and a short reply is overcharged many times over; down,
  and every message is free.

Image generation is untouched by design. A picture is one operation at one price with no tokens to
meter, so its rates stay zero and it keeps being billed flat.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_token_metered_chat"
down_revision = "0006_prompt_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- rates, per million tokens -----------------------------------------
    op.add_column(
        "provider_configs",
        sa.Column("input_cost_per_mtok_inr", sa.Numeric(12, 4), nullable=False, server_default="0"),
    )
    op.add_column(
        "provider_configs",
        sa.Column("output_cost_per_mtok_inr", sa.Numeric(12, 4), nullable=False, server_default="0"),
    )
    op.add_column(
        "provider_configs",
        sa.Column("markup_multiplier", sa.Numeric(6, 3), nullable=False, server_default="1.000"),
    )

    # Published list prices at the time of writing, converted at roughly ₹88/$ — the same rate the
    # 0005 figures were struck at, so the two sets of numbers stay comparable.
    #
    #   gpt-4o-mini        $0.15 / $0.60 per Mtok  ->  ₹13.20 / ₹52.80
    #   gemini-2.0-flash   $0.10 / $0.40 per Mtok  ->  ₹ 8.80 / ₹35.20
    #
    # Seeded rather than hard-coded because an administrator is expected to correct them from the
    # real invoice, and to re-check them whenever a slot is pointed at a different model — a rate
    # is tied to the model, not to the vendor.
    op.execute(
        """
        UPDATE provider_configs
           SET input_cost_per_mtok_inr = 13.2000, output_cost_per_mtok_inr = 52.8000
         WHERE capability = 'chat' AND provider = 'openai'
        """
    )
    op.execute(
        """
        UPDATE provider_configs
           SET input_cost_per_mtok_inr = 8.8000, output_cost_per_mtok_inr = 35.2000
         WHERE capability = 'chat' AND provider = 'gemini'
        """
    )
    # Chat is sold on at cost, which is the position 0005 already took when it set the chat margin
    # to zero. The difference is that it is now true: what the customer pays is what the vendor
    # charged, rather than a flat rupee that happened to be roughly ten times it. An administrator
    # who wants a margin on words raises this one number.
    op.execute("UPDATE provider_configs SET markup_multiplier = 1.000 WHERE capability = 'chat'")

    # --- the ledger remembers the tokens -----------------------------------
    op.add_column("usage_records", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("usage_records", sa.Column("output_tokens", sa.Integer(), nullable=True))

    # --- money in paise, not whole rupees ----------------------------------
    # Widening in place: every existing integer balance is exactly representable, so no balance
    # moves and nobody is credited or debited by the migration itself.
    op.alter_column(
        "credits", "balance",
        existing_type=sa.Integer(),
        type_=sa.Numeric(14, 4),
        existing_nullable=False,
        existing_server_default="0",
    )
    op.alter_column(
        "usage_records", "credits_consumed",
        existing_type=sa.Integer(),
        type_=sa.Numeric(14, 4),
        existing_nullable=False,
        existing_server_default="0",
    )


def downgrade() -> None:
    # Narrowing back to whole rupees rounds every fractional balance. Rounding *up* is the only
    # safe direction: the alternative quietly confiscates whatever paise a customer was holding.
    op.execute("UPDATE credits SET balance = CEIL(balance)")
    op.alter_column(
        "credits", "balance",
        existing_type=sa.Numeric(14, 4),
        type_=sa.Integer(),
        existing_nullable=False,
        existing_server_default="0",
    )
    op.execute("UPDATE usage_records SET credits_consumed = ROUND(credits_consumed)")
    op.alter_column(
        "usage_records", "credits_consumed",
        existing_type=sa.Numeric(14, 4),
        type_=sa.Integer(),
        existing_nullable=False,
        existing_server_default="0",
    )

    op.drop_column("usage_records", "output_tokens")
    op.drop_column("usage_records", "input_tokens")
    op.drop_column("provider_configs", "markup_multiplier")
    op.drop_column("provider_configs", "output_cost_per_mtok_inr")
    op.drop_column("provider_configs", "input_cost_per_mtok_inr")
