# app/ws/chat.py
import json
from fastapi import WebSocket, WebSocketDisconnect
from app.auth_config import decode_access_token, decode_refresh_token
from app.AI.Sega_AI import ask_ai


async def chat_socket(websocket: WebSocket):
    # --- Resolve session from cookie ---
    session_id = websocket.cookies.get("session_id")
    if not session_id:
        await websocket.close(code=4401)
        return

    # --- Resolve user from token ---
    user_id = None

    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        user_id = decode_access_token(token)

    if not user_id:
        refresh_token = websocket.cookies.get("refresh_token")
        if refresh_token:
            user_id = decode_refresh_token(refresh_token)

    await websocket.accept()
    print("WS connected:", {
        "session_id": session_id,
        "user_id": user_id
    })

    try:
        while True:
            raw_msg = await websocket.receive_text()
            payload = json.loads(raw_msg)

            # --- STRICT payload contract ---
            user_input = payload.get("user_input")
            conversation_id = payload.get("conversation_id")
            response_mode = payload.get("response_mode", "text")

            if not user_input:
                continue

            ai_payload = {
                "user_input": user_input,
                "conversation_id": conversation_id,
                "session_id": session_id,
                "user_id": user_id,  # None = guest
                "response_mode": response_mode
            }

            async for msg in ask_ai(ai_payload):
                await websocket.send_text(json.dumps(msg))

    except WebSocketDisconnect:
        print("WebSocket disconnected")

    except Exception as e:
        print("WebSocket error:", e)
        await websocket.close(code=1011)
