# crud.py
from sqlalchemy.orm import Session
from models import User, Message
from auth import hash_password, verify_password

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, user):
    db_user = User(
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        mobile_no=user.mobile_no,
        city=user.city,
        profession=user.profession,
        date_of_birth=user.date_of_birth,
        password=hash_password(user.password),
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def authenticate_user(db: Session, email: str, password: str):
    user = get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.password):
        return None
    return user


def get_all_users(db: Session, current_user_id: int):
    return db.query(User).filter(User.id != current_user_id).all()

def save_message(db: Session, sender_id: int, receiver_id: int, message: str):
    msg = Message(
        sender_id=sender_id,
        receiver_id=receiver_id,
        message=message
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg

def get_messages(db: Session, user1: int, user2: int):
    return db.query(Message).filter(
        ((Message.sender_id == user1) & (Message.receiver_id == user2)) |
        ((Message.sender_id == user2) & (Message.receiver_id == user1))
    ).order_by(Message.created_at).all()