import random
import string
import os
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, or_
from models import User, Message, Referral, Transaction, SupportTicket, BlockedUser, DeactivatedAccount, DeletedAccount, OTPCode
from auth import hash_password, verify_password

PG_SECRET = os.getenv("PG_SECRET_KEY", "Apnashaadi.in123")

# =====================
# SECURE DATA HELPERS
# =====================

def sanitize_user_dict(u):
    """Safely strips out encrypted LargeBinary objects so they don't break JSON serialization in FastAPI."""
    data = u.__dict__.copy()
    data.pop("_sa_instance_state", None)
    data.pop("password", None)
    data.pop("email_encrypted", None)
    data.pop("mobile_encrypted", None)
    # Re-attach the plaintext string if it was decrypted during the query
    if hasattr(u, 'email'): data['email'] = u.email
    if hasattr(u, 'mobile_no'): data['mobile_no'] = u.mobile_no
    return data

async def get_user_by_id(db: AsyncSession, user_id: int):
    """Fetches user and decrypts email and mobile on the fly."""
    result = await db.execute(
        select(
            User,
            func.pgp_sym_decrypt(User.email_encrypted, PG_SECRET).label("email"),
            func.pgp_sym_decrypt(User.mobile_encrypted, PG_SECRET).label("mobile_no")
        ).where(User.id == user_id)
    )
    row = result.first()
    if row:
        u, e, m = row
        u.email = e
        u.mobile_no = m
        return u
    return None

async def get_user_by_email(db: AsyncSession, email: str):
    """Searches DB by decrypting the column and comparing it to the input."""
    result = await db.execute(
        select(
            User,
            func.pgp_sym_decrypt(User.email_encrypted, PG_SECRET).label("email"),
            func.pgp_sym_decrypt(User.mobile_encrypted, PG_SECRET).label("mobile_no")
        ).where(func.pgp_sym_decrypt(User.email_encrypted, PG_SECRET) == email.lower().strip())
    )
    row = result.first()
    if row:
        u, e, m = row
        u.email = e
        u.mobile_no = m
        return u
    return None

async def get_user_by_mobile(db: AsyncSession, mobile: str):
    result = await db.execute(
        select(
            User,
            func.pgp_sym_decrypt(User.email_encrypted, PG_SECRET).label("email"),
            func.pgp_sym_decrypt(User.mobile_encrypted, PG_SECRET).label("mobile_no")
        ).where(func.pgp_sym_decrypt(User.mobile_encrypted, PG_SECRET) == mobile.strip())
    )
    row = result.first()
    if row:
        u, e, m = row
        u.email = e
        u.mobile_no = m
        return u
    return None

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
        first_name=user.first_name, last_name=user.last_name, 
        
        # 🔥 Encrypting PII at creation
        email_encrypted=func.pgp_sym_encrypt(user.email.lower().strip(), PG_SECRET),
        mobile_encrypted=func.pgp_sym_encrypt(user.mobile_no.strip(), PG_SECRET),
        
        city=user.city, state=getattr(user, 'state', None),
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
    
    # Attach plain text so Pydantic Response Model can read it
    db_user.email = user.email.lower().strip()
    db_user.mobile_no = user.mobile_no.strip()
    
    return db_user

async def authenticate_user(db: AsyncSession, email: str, password: str):
    user = await get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.password):
        return None
    return user

async def get_all_users(db: AsyncSession, current_user_id: int):
    blocks_res = await db.execute(
        select(BlockedUser).where(
            or_(BlockedUser.user_id == current_user_id, BlockedUser.blocked_user_id == current_user_id)
        )
    )
    blocked_ids = {b.blocked_user_id if b.user_id == current_user_id else b.user_id for b in blocks_res.scalars().all()}

    result = await db.execute(
        select(
            User,
            func.pgp_sym_decrypt(User.email_encrypted, PG_SECRET).label("email_dec"),
            func.pgp_sym_decrypt(User.mobile_encrypted, PG_SECRET).label("mobile_dec")
        ).where(User.id != current_user_id)
    )
    rows = result.all()
    
    safe_users = []
    for row in rows:
        u, e, m = row
        u.email = e
        u.mobile_no = m
        user_data = sanitize_user_dict(u)
        
        if u.id in blocked_ids:
            user_data["is_blocked"] = True
            user_data["is_online"] = False
            user_data["last_seen"] = None
        else:
            user_data["is_blocked"] = False
            
        safe_users.append(user_data)
        
    return safe_users


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
    user = await get_user_by_email(db, email)
    email_verified = user is not None

    ticket = SupportTicket(
        email_encrypted=func.pgp_sym_encrypt(email.lower().strip(), PG_SECRET),
        subject=subject, category=category,
        urgency=urgency, issue=issue, email_verified=email_verified,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    
    ticket.email = email.lower().strip()
    return ticket

# =====================
# ACCOUNT DEACTIVATION & DELETION
# =====================

async def deactivate_account(db: AsyncSession, user_id: int, reason: str | None = None):
    result = await db.execute(
        select(User, func.pgp_sym_decrypt(User.email_encrypted, PG_SECRET).label("email_dec"))
        .where(User.id == user_id)
    )
    row = result.first()
    
    if not row:
        return None
        
    user, email_dec = row
    user.email = email_dec
    
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=30)
    
    user.is_deactivated = True
    user.is_active = False
    user.deactivation_date = now
    user.reactivation_deadline = deadline
    
    deactivated = DeactivatedAccount(
        user_id=user.id,
        email_encrypted=func.pgp_sym_encrypt(user.email, PG_SECRET),
        first_name=user.first_name,
        last_name=user.last_name,
        deactivation_date=now,
        reactivation_deadline=deadline,
        reason=reason
    )
    db.add(deactivated)
    
    await db.commit()
    await db.refresh(user)
    
    return {
        "user_id": user.id,
        "email": user.email,
        "deactivation_date": now,
        "reactivation_deadline": deadline,
        "message": "Account deactivated successfully"
    }

async def reactivate_account(db: AsyncSession, user_id: int):
    result = await db.execute(
        select(User, func.pgp_sym_decrypt(User.email_encrypted, PG_SECRET).label("email_dec"))
        .where(User.id == user_id)
    )
    row = result.first()
    if not row:
        return None
        
    user, email_dec = row
    user.email = email_dec
    
    if not user.is_deactivated:
        return {"message": "Account is already active", "status": "already_active"}
    
    now = datetime.now(timezone.utc)
    if user.reactivation_deadline and now > user.reactivation_deadline:
        return {"message": "Reactivation deadline has passed. Account cannot be reactivated.", "status": "deadline_passed"}
    
    user.is_deactivated = False
    user.is_active = True
    user.deactivation_date = None
    user.reactivation_deadline = None
    
    deactivated = await db.execute(
        select(DeactivatedAccount).where(DeactivatedAccount.user_id == user_id)
    )
    deactivated_record = deactivated.scalars().first()
    if deactivated_record:
        await db.delete(deactivated_record)
    
    await db.commit()
    await db.refresh(user)
    
    return {
        "user_id": user.id,
        "email": user.email,
        "status": "reactivated",
        "message": "Account reactivated successfully"
    }

async def delete_account_permanently(db: AsyncSession, user_id: int, reason: str | None = None):
    result = await db.execute(
        select(
            User,
            func.pgp_sym_decrypt(User.email_encrypted, PG_SECRET).label("email_dec"),
            func.pgp_sym_decrypt(User.mobile_encrypted, PG_SECRET).label("mobile_dec")
        ).where(User.id == user_id)
    )
    row = result.first()
    if not row:
        return None
        
    user, email_dec, mobile_dec = row
    user.email = email_dec
    user.mobile_no = mobile_dec
    
    now = datetime.now(timezone.utc)
    
    archived_data = {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "mobile_no": user.mobile_no,
        "gender": user.gender,
        "city": user.city,
        "profession": user.profession,
        "profile_id": user.profile_id,
        "plan_type": user.plan_type,
        "created_at": str(user.created_at),
    }
    
    deleted = DeletedAccount(
        user_id=user.id,
        email_encrypted=func.pgp_sym_encrypt(user.email, PG_SECRET),
        mobile_encrypted=func.pgp_sym_encrypt(user.mobile_no, PG_SECRET) if user.mobile_no else None,
        first_name=user.first_name,
        last_name=user.last_name,
        profile_pic=user.profile_pic,
        bio=user.bio,
        deletion_date=now,
        reason=reason,
        archived_data_encrypted=func.pgp_sym_encrypt(json.dumps(archived_data), PG_SECRET)
    )
    db.add(deleted)
    
    user.password = hash_password(os.urandom(32).hex())
    user.is_active = False
    user.is_deactivated = False
    
    await db.commit()
    
    return {
        "user_id": user.id,
        "email": user.email,
        "deletion_date": now,
        "status": "deleted",
        "message": "Account permanently deleted"
    }

async def check_deactivation_deadline(db: AsyncSession):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(DeactivatedAccount).where(DeactivatedAccount.reactivation_deadline <= now)
    )
    expired_accounts = result.scalars().all()
    
    for account in expired_accounts:
        await delete_account_permanently(db, account.user_id, reason="Deactivation deadline expired")
    
    return len(expired_accounts) if expired_accounts else 0