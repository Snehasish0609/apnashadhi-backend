from fastapi import FastAPI, Depends, HTTPException,WebSocket
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from db import engine, SessionLocal
from models import Base
from schemas import RegisterUser, LoginUser, UserResponse ,MessageCreate
from crud import create_user, authenticate_user, get_user_by_email, get_all_users, save_message, get_messages
from auth import create_access_token ,get_current_user

Base.metadata.create_all(bind=engine)

app = FastAPI()

# ✅ CORS FIX
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/register", response_model=UserResponse)
def register(user: RegisterUser, db: Session = Depends(get_db)):
    if get_user_by_email(db, user.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    return create_user(db, user)

@app.post("/login")
def login(data: LoginUser, db: Session = Depends(get_db)):
    user = authenticate_user(db, data.email, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(user.id)

    return {
        "access_token": token,
        "user_id": user.id,          # 🔥 REQUIRED
        "first_name": user.first_name
    }



# ---------------- USERS ----------------
@app.get("/users")
def list_users(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return get_all_users(db, user.id)

# ---------------- CHAT REST ----------------
@app.get("/chat/{user_id}")
def fetch_messages(user_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return get_messages(db, user.id, user_id)

@app.post("/chat/send")
def send_message(data: MessageCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return save_message(db, user.id, data.receiver_id, data.message)

# ---------------- WEBSOCKET ----------------
from typing import Dict
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime

active_connections: Dict[int, WebSocket] = {}
last_seen: Dict[int, str] = {}

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(ws: WebSocket, user_id: int):
    await ws.accept()
    active_connections[user_id] = ws
    print(f"🟢 User {user_id} online")

    # notify others user is online
    for uid, conn in active_connections.items():
        if uid != user_id:
            await conn.send_json({
                "type": "presence",
                "user_id": user_id,
                "status": "online"
            })

    try:
        while True:
            data = await ws.receive_json()
            receiver_id = data.get("receiver_id")

            if receiver_id in active_connections:
                await active_connections[receiver_id].send_json(data)

    except WebSocketDisconnect:
        print(f"🔴 User {user_id} offline")

    finally:
        active_connections.pop(user_id, None)
        last_seen[user_id] = datetime.utcnow().isoformat()

        for uid, conn in active_connections.items():
            await conn.send_json({
                "type": "presence",
                "user_id": user_id,
                "status": "offline",
                "last_seen": last_seen[user_id]
            })


