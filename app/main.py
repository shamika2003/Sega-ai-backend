# app/main.py
from typing import Optional
from fastapi import Response, FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import uuid

from app.ws.chat import chat_socket

from app.db import get_conversation_list, get_conversation_messages, save_get_user
from app.auth_config import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)

app = FastAPI()

# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://sega-ruby.vercel.app",
        "http://localhost:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# WebSocket
# =========================
app.websocket("/ws/chat")(chat_socket)

# =========================
# Session Middleware
# =========================
@app.middleware("http")
async def ensure_session(request: Request, call_next):
    response = await call_next(request)

    if "session_id" not in request.cookies:
        response.set_cookie(
            key="session_id",
            value=str(uuid.uuid4()),
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 30,  # 30 days
        )

    return response

# =========================
# Auth Models
# =========================
class LoginRequest(BaseModel):
    provider: str
    accessToken: str

@app.post("/api/auth/login")
async def login(request: LoginRequest, response: Response):
    if request.provider.lower() != "google":
        raise HTTPException(status_code=400, detail="Unsupported auth provider")

    # Verify token with Google
    google_response = requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {request.accessToken}"}
    )
    if google_response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    user_info = google_response.json()
    email = user_info.get("email")
    name = user_info.get("name")
    picture = user_info.get("picture")
    google_id = user_info.get("sub")

    if not email:
        raise HTTPException(status_code=400, detail="Email not available")

    # Save or get user in DB
    user_data = {
        "email": email,
        "name": name,
        "avatar_url": picture,
        "provider": "Google",
        "provider_user_id": google_id
    }
    user = await save_get_user(user_data)

    # Generate tokens
    access_token = create_access_token(user["id"])
    refresh_token = create_refresh_token(user["id"])

    # Set HttpOnly refresh token cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,            # only HTTPS in production
        samesite="lax",
        max_age=7*24*60*60      # 7 days
    )

    return {
        "access_token": access_token,
        "user": {
            "name": user["name"],
            "email": user["email"],
            "avatar_url": user["avatar_url"]
        }
    }



# =========================
# AUTH CHECK (FIXED)
# =========================
@app.post("/api/auth/check")
async def check_auth(
    request: Request,
    response: Response,
    authorization: Optional[str] = Header(None),
):
    session_id = request.cookies.get("session_id")

    if not session_id:
        session_id = str(uuid.uuid4())
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 30,
        )

    # Valid access token?
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        user_id = decode_access_token(token)
        if user_id:
            return {
                "authenticated": True,
                "access_token": token,
            }

    # Refresh token?
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        user_id = decode_refresh_token(refresh_token)
        if user_id:
            return {
                "authenticated": True,
                "access_token": create_access_token(user_id),
            }

    # Guest fallback (PRODUCTION FIX)
    guest_subject = f"guest:{session_id}"
    guest_token = create_access_token(guest_subject)

    return {
        "authenticated": True,
        "access_token": guest_token,
        "guest": True,
    }


# =========================
# Logout
# =========================
@app.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie("refresh_token")
    return {"logged_out": True}


# =========================
# Conversations
# =========================
@app.get("/api/conversations/{conversation_id}")
async def fetch_conversation(
    request: Request,
    conversation_id: str,
    authorization: Optional[str] = Header(None),
):
    user_id = None
    session_id = request.cookies.get("session_id")

    # Try decode access token if present
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        user_id = decode_access_token(token)
    
    # Fallback: use session_id for guests
    if not user_id:
        if not session_id:
            raise HTTPException(status_code=400, detail="Missing access token or session_id")

    # Fetch messages from DB
    messages = await get_conversation_messages(conversation_id)

    
    # Authorization check
    if not messages:
        # conversation not found
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Assuming each message has conversation.user_id and conversation.session_id
    conv_owner_user_id = messages[0].get("user_id")
    conv_owner_session_id = messages[0].get("session_id")

    print(user_id)
    print(messages)
    
    if user_id:
        if user_id:
            if (
                conv_owner_user_id != user_id
                and conv_owner_session_id != session_id
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized for this conversation"
                )


    return {"messages": messages}


@app.get("/api/conversations_list")
async def fetch_conversation_list(
    authorization: Optional[str] = Header(None),
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing access token")

    token = authorization.replace("Bearer ", "")
    user_id = decode_access_token(token)

    if not user_id or str(user_id).startswith("guest:"):
        return {"conversation_list": []}

    return {"conversation_list": await get_conversation_list(user_id)}