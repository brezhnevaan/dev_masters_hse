from sqlalchemy import String, Integer, Text, Boolean, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from uuid import UUID
from app.database.base import Base

class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    short_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    is_soft_expire: Mapped[bool] = mapped_column(default=False)
    last_click_at: Mapped[datetime | None] = mapped_column(nullable=True)
    clicks: Mapped[int] = mapped_column(default=0)

    user = relationship("User", back_populates="links")


class ExpiredLink(Base):
    __tablename__ = "expired_links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id"), nullable=True)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    short_code: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    last_click_at: Mapped[datetime | None] = mapped_column(nullable=True)
    clicks: Mapped[int] = mapped_column(default=0)
    is_soft_expire: Mapped[bool] = mapped_column(default=True, nullable=False)

    user = relationship("User", back_populates="expired_links")
