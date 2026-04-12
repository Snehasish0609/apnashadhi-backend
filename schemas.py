from pydantic import BaseModel, EmailStr, Field, validator
from datetime import date, datetime
from typing import Dict, List, Optional

class RegisterUser(BaseModel):
    # Required
    first_name: str = Field(min_length=2, max_length=50)
    last_name: str = Field(min_length=2, max_length=50)
    email: EmailStr
    mobile_no: str = Field(min_length=10, max_length=15)
    password: str = Field(min_length=6)
    date_of_birth: date
    city: str
    profession: str

    # =====================
    # NEW FIELDS
    # =====================
    gender: str | None = None
    looking_for: str | None = None

    preferred_min_age: int | None = None
    preferred_max_age: int | None = None
    preferred_city: str | None = None
    preferred_religion: str | None = None

    # Optional fields (existing)
    height: str | None = None
    marital_status: str | None = None
    education: str | None = None
    annual_income: str | None = None
    
    religion: str | None = None
    caste: str | None = None
    mother_tongue: str | None = None
    family_type: str | None = None
    family_values: str | None = None
    
    diet: str | None = None
    habits: str | None = None
    hobbies: str | None = None
    bio: str | None = None

    # UPDATED: Referral code during registration
    referred_by_code: str | None = None 

    # ✅ Age validation (FIXED for precise date comparison)
    @validator("date_of_birth")
    def validate_age(cls, v):
        today = date.today()
        # Checks if the birthday has occurred yet this year
        age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
        if age < 18:
            raise ValueError("User must be at least 18 years old")
        return v


class UpdateUser(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    mobile_no: str | None = None
    city: str | None = None
    profession: str | None = None
    gender: str | None = None
    looking_for: str | None = None
    
    preferred_min_age: int | None = None
    preferred_max_age: int | None = None
    preferred_city: str | None = None
    preferred_religion: str | None = None

    height: str | None = None
    marital_status: str | None = None
    education: str | None = None
    annual_income: str | None = None
    religion: str | None = None
    caste: str | None = None
    mother_tongue: str | None = None
    family_type: str | None = None
    family_values: str | None = None
    diet: str | None = None
    habits: str | None = None
    hobbies: str | None = None
    bio: str | None = None

    
class LoginUser(BaseModel):
    email: str | None = None
    mobile_no: str | None = None
    password: str

class UserResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: EmailStr
    profile_completed: int | None = 0 # Added to track progress in response

    class Config:
        from_attributes = True


class UserOut(BaseModel):
    id: int
    first_name: str
    last_name: str | None = None
    profile_pic: str | None = None
    city: str | None = None
    profession: str | None = None

    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    receiver_id: int
    message: str


class MessageOut(BaseModel):
    id: int # Added ID
    sender_id: int
    receiver_id: int
    message: str
    created_at: datetime # Changed to datetime for proper serialization

    class Config:
        from_attributes = True

# ADDED: Full support for profile visits, interests, and rejects
class InteractionCreate(BaseModel):
    target_id: int
    action: str  # 'interest', 'reject', or 'visit'


class MatchmakerQuizParams(BaseModel):
    answers: Dict[str, str]


# =====================================================================
# NEW: REFERRAL & WALLET SCHEMAS (From Intern Code)
# =====================================================================

class TransactionOut(BaseModel):
    id: int
    amount: int
    description: str
    created_at: datetime

    class Config:
        from_attributes = True

class ReferralHistoryItem(BaseModel):
    referred_name: str
    status: str       # 'Pending' or 'Completed'
    coins_earned: int
    profile_completion: int

class WalletInfo(BaseModel):
    coin_balance: int
    total_earned: int
    total_spent: int
    transactions: List[TransactionOut]