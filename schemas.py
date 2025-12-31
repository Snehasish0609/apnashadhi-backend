# schemas.py
from pydantic import BaseModel, EmailStr
from datetime import date

class RegisterUser(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    mobile_no: str
    city: str
    profession: str
    date_of_birth: date
    password: str

class LoginUser(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: EmailStr

    class Config:
        from_attributes = True


class UserOut(BaseModel):
    id: int
    first_name: str

    class Config:
        from_attributes = True

class MessageCreate(BaseModel):
    receiver_id: int
    message: str

class MessageOut(BaseModel):
    sender_id: int
    receiver_id: int
    message: str
    created_at: str