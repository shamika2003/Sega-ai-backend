import base64
import uuid

from app.AI.tts_streamer import stream_tts
from app.AI.conversation_state import build_conversation_state
from app.AI.responder import call_responder
from app.db import ensure_conversation, save_assistant_message, save_user_message
from app.AI.Planner import call_planner

async def ask_ai(user_input_set: dict):
    # --- Validate input ---
    user_input = user_input_set.get("user_input")
    if not isinstance(user_input, str):
        raise ValueError("user_input must be a string")

    # --- Conversation ---
    conversation_id = user_input_set.get("conversation_id")
    if not conversation_id:
        conversation_id = str(uuid.uuid4())

    # --- Auth context (TRUST WS) ---
    user_id = user_input_set.get("user_id")     
    session_id = user_input_set.get("session_id")

    # --- Planner ---

    state = await build_conversation_state(conversation_id)

    planner_output = call_planner(
        user_input=user_input,
        state=state
    )

    conversation_title = planner_output.get(
        "conversation_title",
        "Untitled Conversation"
    )

    print("ASK_AI:", {
        "conversation_id": conversation_id,
        "title": conversation_title,
        "user_id": user_id,
        "session_id": session_id,
    })

    # --- Ensure conversation ---
    await ensure_conversation(
        conversation_id=conversation_id,
        title=conversation_title,
        user_id=user_id,   
        session_id=session_id,
    )

    # --- Save user message ---
    await save_user_message(conversation_id, user_input)

    # --- Send meta ---
    yield {
        "type": "meta",
        "conversation_id": conversation_id,
        "title": conversation_title,
    }
    
    tool_results = {}
    
    tool_calls = planner_output.get("tool_calls", [])
    
    if tool_calls:
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("parameters", {})
            
            if tool_name == "calculator":
                from app.AI.calculator import _solve_math
                expr = tool_args.get("expression", "")
                mode = tool_args.get("mode", "auto")
                result = _solve_math(expr, mode)
                tool_results[tool_call["id"]] = {
                    "tool": tool_name,
                    "parameters": tool_args,
                    "result": result
                }
                print(f"Result: {result}")
            elif tool_name == "web_search":
                from app.AI.Web_search import web_search

                query = tool_args.get("query", "")
                max_results = tool_args.get("max_results", 5)

                result = web_search(query, max_results)
                tool_results[tool_call["id"]] = {
                    "tool": tool_name,
                    "parameters": tool_args,
                    "result": result
                }
            else:
                print(f"Unknown tool: {tool_name}")  # Debug print

    # --- Stream assistant ---
    assistant_message_id = str(uuid.uuid4())
    assistant_text: list[str] = []
    tts_buffer = ""
    response_mode = user_input_set.get("response_mode", "text")


    async for chunk in call_responder(
        user_input,
        conversation_id,
        planner_output,
        tool_results,
        response_mode,
    ):
        assistant_text.append(chunk) 

        if response_mode == "voice_stream":
            tts_buffer += chunk  # accumulate text

            # Send when a sentence ends
            while any(tts_buffer.endswith(p) for p in [".", "?", "!"]):
            # Extract the first complete sentence
                for idx, char in enumerate(tts_buffer):
                    if char in [".", "?", "!"]:
                        sentence = tts_buffer[:idx + 1].strip()
                        tts_buffer = tts_buffer[idx + 1:].lstrip()
                        break
                else:
                    sentence = tts_buffer
                    tts_buffer = ""

                # Generate TTS for this sentence
                chunks = []
                async for audio_chunk in stream_tts(sentence):
                    chunks.append(audio_chunk)

                # Send chunks sequentially
                for i, audio_chunk in enumerate(chunks):
                    encoded_chunk = base64.b64encode(audio_chunk).decode("utf-8")
                    yield {
                        "type": "audio_chunk",
                        "message_id": assistant_message_id,
                        "data": encoded_chunk,
                        "done": i == len(chunks) - 1,  # mark last chunk
                    }

        yield {
            "type": "token",
            "message_id": assistant_message_id,
            "content": chunk,
        }


    # --- Persist assistant message ---
    await save_assistant_message(
        conversation_id,
        "".join(assistant_text),
    )

    yield {
        "type": "done",
        "message_id": assistant_message_id,
    }

# # -----------------------
# # Main Loop
# # ------------------x-----

# # if __name__ == "__main__":
# #     while True:
# #         user_input = input("You: ")
# #         if user_input.lower() in {"exit", "quit"}:
# #             break
        
# #         ask_ai(user_input)