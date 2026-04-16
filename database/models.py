from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

if TYPE_CHECKING:
    pass


class Base(DeclarativeBase):
    pass


class District(Base):
    """Buxoro viloyati tumanlari (faqat shu tumanlar bo'yicha so'rovnoma)."""

    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    sort_order: Mapped[int] = mapped_column(default=0)

    directors: Mapped[list["Director"]] = relationship(back_populates="district")


class Director(Base):
    __tablename__ = "directors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id", ondelete="RESTRICT"), index=True)
    full_name: Mapped[str] = mapped_column(String(512), index=True)
    school_name: Mapped[str] = mapped_column(String(512))
    sort_order: Mapped[int] = mapped_column(default=0)

    district: Mapped["District"] = relationship(back_populates="directors")
    votes: Mapped[list["Vote"]] = relationship(back_populates="director")


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    phone_normalized: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    channel_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    instagram_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vote: Mapped["Vote | None"] = relationship(back_populates="user", uselist=False)


class Vote(Base):
    __tablename__ = "votes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        unique=True,
    )
    director_id: Mapped[int] = mapped_column(ForeignKey("directors.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="vote")
    director: Mapped["Director"] = relationship(back_populates="votes")
