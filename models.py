# models.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text,Date
from sqlalchemy.sql import func
from db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)

    email = Column(String, unique=True, index=True, nullable=False)
    mobile_no = Column(String, unique=True, index=True, nullable=False)

    city = Column(String, nullable=False)
    profession = Column(String, nullable=False)

    date_of_birth = Column(Date, nullable=False)

    password = Column(String, nullable=False)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"))
    message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())