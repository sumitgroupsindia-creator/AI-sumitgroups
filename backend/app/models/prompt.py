from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class PromptTemplate(Base, UUIDPKMixin, TimestampMixin):
    """A piece of instruction the product adds to every request, editable without a deploy.

    The product's voice lives here rather than in source, for the same reason prices do: it is the
    thing most likely to need changing, and it should not need an engineer to change it.

    `kind` decides when a row is used:

    - ``base`` — always prepended, for its scope. The identity and the house rules.
    - ``task`` — one of these may be added on top, chosen per request by the router. Its `name` and
      `description` are what the router reads, so they are instructions, not decoration.
    - ``tool`` — instructions the machinery itself runs on: the router's own prompt, and the brief
      used to read an attached photo. Disabling one of these turns that step off entirely, which is
      also how an operator switches off the extra API call it costs.
    """

    __tablename__ = "prompt_templates"
    __table_args__ = (UniqueConstraint("key", name="uq_prompt_templates_key"),)

    key: Mapped[str] = mapped_column(String(50), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)  # chat | image
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # base | task | tool
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Read by the router when deciding whether this task fits a request, so it must describe when
    # to use the template, not merely what it contains.
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
