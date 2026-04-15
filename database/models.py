from datetime import datetime
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float,
    Integer, String, Text, ForeignKey
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(64), nullable=True)
    first_name = Column(String(64), nullable=True)
    last_name = Column(String(64), nullable=True)
    language = Column(String(5), default="ru")

    free_messages_used = Column(Integer, default=0)
    free_minutes_used = Column(Float, default=0.0)

    message_balance = Column(Integer, default=0)

    total_messages = Column(Integer, default=0)
    total_minutes = Column(Float, default=0.0)
    total_stars_spent = Column(Integer, default=0)

    is_blocked = Column(Boolean, default=False)
    is_unlimited = Column(Boolean, default=False)   # безлимитный режим

    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("Message", back_populates="user", lazy="dynamic")
    payments = relationship("Payment", back_populates="user", lazy="dynamic")
    admin = relationship("Admin", back_populates="user", uselist=False)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    user_telegram_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)

    audio_duration = Column(Float, default=0.0)
    file_id = Column(String(256), nullable=True)
    transcription = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    recommendations = Column(Text, nullable=True)
    title = Column(String(100), nullable=True)   # короткое название (2-3 слова)
    language = Column(String(5), default="ru")
    is_free = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User", back_populates="messages")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    user_telegram_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)

    stars_amount = Column(Integer, nullable=False)
    messages_purchased = Column(Integer, nullable=False)
    payment_type = Column(String(20), nullable=False)
    telegram_charge_id = Column(String(256), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User", back_populates="payments")


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True)
    user_telegram_id = Column(BigInteger, ForeignKey("users.telegram_id"), unique=True, nullable=False)

    can_view_stats = Column(Boolean, default=True)
    can_view_finance = Column(Boolean, default=False)
    can_manage_users = Column(Boolean, default=False)
    can_add_admins = Column(Boolean, default=False)
    can_manage_permissions = Column(Boolean, default=False)

    added_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="admin")
