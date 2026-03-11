# app/ws/chat.py
import json
import os
import base64
import uuid
from fastapi import WebSocket, WebSocketDisconnect
from app.auth_config import decode_access_token, decode_refresh_token
from app.AI.Sega_AI import ask_ai
from app.db import save_upload

# Directory to save uploaded files/images
UPLOAD_DIR = "app/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


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
            files = payload.get("files", [])  
            conversation_id = payload.get("conversation_id")
            response_mode = payload.get("response_mode", "text")

            saved_files = []

            # --- Handle uploaded files ---
            for f in files:
                file_type = f.get("type") 
                name = f.get("name")
                content = f.get("content")

                if content and name:

                    # Remove data URI prefix
                    if "," in content:
                        content = content.split(",")[1]

                    try:
                        data = base64.b64decode(content)

                        # Extract file extension
                        file_ext = os.path.splitext(name)[1].lower() 

                        file_id = str(uuid.uuid4())

                        await save_upload(file_id, file_ext, file_type, name)

                        save_path = os.path.join(UPLOAD_DIR, f"{file_id}{file_ext}")

                        with open(save_path, "wb") as fp:
                            fp.write(data)

                        saved_files.append(save_path)

                    except Exception as e:
                        print(f"Failed to save file {name}: {e}")

            # --- Prepare AI payload ---
            ai_payload = {
                "user_input": user_input,
                "conversation_id": conversation_id,
                "session_id": session_id,
                "user_id": user_id,  # None = guest
                "response_mode": response_mode,
                "files": saved_files 
            }

            # --- Stream AI response ---
            async for msg in ask_ai(ai_payload):
                await websocket.send_text(json.dumps(msg))

    except WebSocketDisconnect:
        print("WebSocket disconnected")

    except Exception as e:
        print("WebSocket error:", e)
        await websocket.close(code=1011)