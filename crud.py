import random
import string
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models import User, Message, Referral, Transaction
from auth import hash_password, verify_password

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
        user.height,
        user.marital_status,
        user.education,
        user.annual_income,
        user.religion,
        user.caste,
        user.mother_tongue,
        user.family_type,
        user.family_values,
        user.diet,
        user.habits,
        user.hobbies,
        user.bio,
        user.gender,
        user.looking_for,
        user.preferred_min_age,
        user.preferred_max_age,
        user.preferred_city,
        user.preferred_religion,
    ]
    filled = sum(1 for f in fields if f is not None and f != "")
    return int((filled / len(fields)) * 100)


# ✅ NEW: Referral Code Generator
async def generate_unique_referral_code(db: AsyncSession, first_name: str) -> str:
    """Create a short, unique referral code like RAHUL5X."""
    base = first_name.upper()[:5]
    for _ in range(10):  # Try 10 times to find a unique suffix
        suffix = ''.join(random.choices(string.digits + string.ascii_uppercase, k=3))
        code = f"{base}{suffix}"
        existing = await db.execute(select(User).where(User.referral_code == code))
        if not existing.scalars().first():
            return code
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


async def create_user(db: AsyncSession, user):
    # 1. Resolve referrer if a code was provided
    referrer = None
    if getattr(user, 'referred_by_code', None):
        ref_result = await db.execute(
            select(User).where(User.referral_code == user.referred_by_code.strip().upper())
        )
        referrer = ref_result.scalars().first()

    # 2. Generate new user's code
    new_code = await generate_unique_referral_code(db, user.first_name)

    db_user = User(
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        mobile_no=user.mobile_no,
        city=user.city,
        profession=user.profession,
        date_of_birth=user.date_of_birth,
        password=hash_password(user.password),

        # Optional Fields
        height=user.height,
        marital_status=user.marital_status,
        education=user.education,
        annual_income=user.annual_income,
        religion=user.religion,
        caste=user.caste,
        mother_tongue=user.mother_tongue,
        family_type=user.family_type,
        family_values=user.family_values,
        diet=user.diet,
        habits=user.habits,
        hobbies=user.hobbies,
        bio=user.bio,
        gender=user.gender,
        looking_for=user.looking_for,
        profile_pic=None,
        preferred_min_age=user.preferred_min_age,
        preferred_max_age=user.preferred_max_age,
        preferred_city=user.preferred_city,
        preferred_religion=user.preferred_religion,

        # Referral & Wallet Initialization
        referral_code=new_code,
        referred_by=referrer.id if referrer else None,
        coin_balance=0,
    )

    db_user.profile_completed = calculate_profile_score(db_user)

    db.add(db_user)
    await db.flush()  # To get db_user.id for the Referral table

    # 3. Log the referral relationship
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
    result = await db.execute(
        select(User).where(User.id != current_user_id)
    )
    return result.scalars().all()


# =====================
# CHAT
# =====================

async def save_message(
    db: AsyncSession,
    sender_id: int,
    receiver_id: int,
    message: str,
):
    msg = Message(
        sender_id=sender_id,
        receiver_id=receiver_id,
        message=message,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def get_messages(db: AsyncSession, user1: int, user2: int):
    result = await db.execute(
        select(Message)
        .where(
            ((Message.sender_id == user1) & (Message.receiver_id == user2)) |
            ((Message.sender_id == user2) & (Message.receiver_id == user1))
        )
        .order_by(Message.created_at)
    )
    return result.scalars().all()

# =====================
# WALLET HELPERS
# =====================

async def credit_coins(db: AsyncSession, user_id: int, amount: int, description: str):
    """Helper to add coins and log the transaction."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if user:
        user.coin_balance = (user.coin_balance or 0) + amount
        txn = Transaction(user_id=user_id, amount=amount, description=description)
        db.add(txn)
        return True
    return False