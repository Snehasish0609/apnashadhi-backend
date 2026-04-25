import random
import string
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, or_
from models import User, Message, Referral, Transaction, SupportTicket, BlockedUser
from auth import hash_password, verify_password
import os

# =====================
# USERS
# =====================

async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(
        select(User).where(User.email == email)
    )
    return result.scalars().first()

async def get_user_by_mobile(db: AsyncSession, mobile: str):
    result = await db.execute(
        select(User).where(User.mobile_no == mobile)
    )
    return result.scalars().first()

def calculate_profile_score(user):
    fields = [
        user.height, user.marital_status, user.education, user.annual_income,
        user.religion, user.caste, user.mother_tongue, user.family_type,
        user.family_values, user.diet, user.habits, user.hobbies, user.bio,
        user.gender, user.looking_for, user.preferred_min_age,
        user.preferred_max_age, user.preferred_city, user.preferred_religion,
    ]
    filled = sum(1 for f in fields if f is not None and f != "")
    return int((filled / len(fields)) * 100)

async def generate_unique_referral_code(db: AsyncSession, first_name: str) -> str:
    """Create a short, unique referral code like RAHUL5X."""
    base = first_name.upper()[:5]
    for _ in range(10):  
        suffix = ''.join(random.choices(string.digits + string.ascii_uppercase, k=3))
        code = f"{base}{suffix}"
        existing = await db.execute(select(User).where(User.referral_code == code))
        if not existing.scalars().first():
            return code
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

async def create_user(db: AsyncSession, user):
    referrer = None
    if getattr(user, 'referred_by_code', None):
        ref_result = await db.execute(
            select(User).where(User.referral_code == user.referred_by_code.strip().upper())
        )
        referrer = ref_result.scalars().first()

    new_code = await generate_unique_referral_code(db, user.first_name)

    db_user = User(
        first_name=user.first_name, last_name=user.last_name, email=user.email,
        mobile_no=user.mobile_no, city=user.city, state=getattr(user, 'state', None),
        profession=user.profession, date_of_birth=user.date_of_birth,
        password=hash_password(user.password), height=user.height,
        marital_status=user.marital_status, education=user.education,
        annual_income=user.annual_income, religion=user.religion, caste=user.caste,
        mother_tongue=user.mother_tongue, family_type=user.family_type,
        family_values=user.family_values, diet=user.diet, habits=user.habits,
        hobbies=user.hobbies, bio=user.bio, gender=user.gender,
        looking_for=user.looking_for, relationship_type=getattr(user, 'relationship_type', None),
        preferred_min_age=user.preferred_min_age, preferred_max_age=user.preferred_max_age,
        preferred_city=user.preferred_city, preferred_religion=user.preferred_religion,
        account_created_by=getattr(user, 'account_created_by', None),
        terms_accepted=getattr(user, 'terms_accepted', False) or False,
        is_active=True, referral_code=new_code,
        referred_by=referrer.id if referrer else None, coin_balance=0,
    )

    db_user.profile_completed = calculate_profile_score(db_user)

    db.add(db_user)
    await db.flush()

    if referrer:
        new_referral = Referral(referrer_id=referrer.id, referred_id=db_user.id)
        db.add(new_referral)

    await db.commit()
    await db.refresh(db_user)
    return db_user

async def authenticate_user(db: AsyncSession, email: str, password: str):
    user = await get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.password):
        return None
    return user

async def get_all_users(db: AsyncSession, current_user_id: int):
    # Fetch blocks to apply masks
    blocks_res = await db.execute(
        select(BlockedUser).where(
            or_(BlockedUser.user_id == current_user_id, BlockedUser.blocked_user_id == current_user_id)
        )
    )
    blocked_ids = {b.blocked_user_id if b.user_id == current_user_id else b.user_id for b in blocks_res.scalars().all()}

    result = await db.execute(select(User).where(User.id != current_user_id))
    users = result.scalars().all()
    
    safe_users = []
    for u in users:
        user_data = u.__dict__.copy()
        user_data.pop("_sa_instance_state", None)
        user_data.pop("password", None)
        
        # 🔥 Mask presence if blocked
        if u.id in blocked_ids:
            user_data["is_blocked"] = True
            user_data["is_online"] = False
            user_data["last_seen"] = None
        else:
            user_data["is_blocked"] = False
            
        safe_users.append(user_data)
        
    return safe_users

PG_SECRET = os.getenv("PG_SECRET_KEY", "Apnashaadi.in123")

async def save_message(
    db: AsyncSession, sender_id: int, receiver_id: int, 
    message: str = None, media_url: str = None, media_type: str = None
):
    encrypted_msg = func.pgp_sym_encrypt(message, PG_SECRET) if message else None

    msg = Message(
        sender_id=sender_id, receiver_id=receiver_id, message=encrypted_msg,
        media_url=media_url, media_type=media_type, status="sent"
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    
    return {
        "id": msg.id, "sender_id": msg.sender_id, "receiver_id": msg.receiver_id,
        "message": message, "media_url": msg.media_url, "media_type": msg.media_type,
        "status": msg.status, "created_at": msg.created_at
    }

async def get_messages(db: AsyncSession, user1: int, user2: int):
    # 🔥 FIXED: Ensure we drop messages that the user marked as "deleted for me"
    result = await db.execute(
        select(
            Message.id, Message.sender_id, Message.receiver_id,
            func.pgp_sym_decrypt(Message.message, PG_SECRET).label("message"),
            Message.media_url, Message.media_type, Message.status,
            Message.created_at, Message.is_deleted
        )
        .where(
            or_(
                and_(Message.sender_id == user1, Message.receiver_id == user2, Message.deleted_by_sender == False),
                and_(Message.sender_id == user2, Message.receiver_id == user1, Message.deleted_by_receiver == False)
            )
        )
        .order_by(Message.created_at)
    )
    return [dict(r._mapping) for r in result.all()]

async def mark_messages_as_seen(db: AsyncSession, sender_id: int, receiver_id: int):
    await db.execute(
        update(Message)
        .where(
            and_(
                Message.sender_id == sender_id, Message.receiver_id == receiver_id, Message.status != "seen"
            )
        )
        .values(status="seen")
    )
    await db.commit()

async def update_user_presence(db: AsyncSession, user_id: int, is_online: bool):
    await db.execute(
        update(User).where(User.id == user_id).values(is_online=is_online, last_seen=func.now())
    )
    await db.commit()

async def credit_coins(db: AsyncSession, user_id: int, amount: int, description: str):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if user:
        user.coin_balance = (user.coin_balance or 0) + amount
        txn = Transaction(user_id=user_id, amount=amount, description=description)
        db.add(txn)
        return True
    return False

async def create_support_ticket(db: AsyncSession, email: str, subject: str, category: str, urgency: str, issue: str) -> SupportTicket:
    user_result = await db.execute(select(User).where(User.email == email.lower().strip()))
    email_verified = user_result.scalars().first() is not None

    ticket = SupportTicket(
        email=email.lower().strip(), subject=subject, category=category,
        urgency=urgency, issue=issue, email_verified=email_verified,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return ticket