import base64
import json
import os
import uuid

from app.AI.tts_streamer import stream_tts
from app.db import ensure_conversation, save_assistant_message, save_user_message, save_upload

async def ask_ai(user_input_set: dict):

    # # --- Validate input ---
    # user_input = user_input_set.get("user_input")
    # if not isinstance(user_input, str):
    #     raise ValueError("user_input must be a string")

    # # --- Conversation ---
    # conversation_id = user_input_set.get("conversation_id")
    # if not conversation_id:
    #     conversation_id = str(uuid.uuid4())
        
    # # --- Turn Id ---
    # user_message_id = str(uuid.uuid4())
    # assistant_message_id = str(uuid.uuid4())

    # # --- Auth context ---
    # user_id = user_input_set.get("user_id")     
    # session_id = user_input_set.get("session_id")

    # # --- Ensure conversation ---
    # await ensure_conversation(
    #     conversation_id=conversation_id,
    #     title="",
    #     user_id=user_id,   
    #     session_id=session_id,
    # )

    # # --- Send meta ---
    # yield {
    #     "type": "meta",
    #     "conversation_id": conversation_id,
    # }

    # Directory to save uploaded files/images
    UPLOAD_DIR = "app/uploads"
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    saved_files = []

    

    # --- Handle uploaded files ---
    for f in user_input_set.get("files"):
        file_type = f.get("type") 
        name = f.get("name")
        content = f.get("content")

        if content and name:

            # Remove data URI prefix
            if "," in content:
                content = content.split(",")[1]

            try:
                data = base64.b64decode(content)

                file_ext = os.path.splitext(name)[1].lower() 
 
                file_id = str(uuid.uuid4())
 
                await save_upload(file_id, file_ext, file_type, user_message_id, name, conversation_id)
 
                save_path = os.path.join(UPLOAD_DIR, f"{file_id}{file_ext}")
 
                with open(save_path, "wb") as fp:
                    fp.write(data)
 
                saved_files.append(save_path)
 
            except Exception as e:
                print(f"Failed to save file {name}: {e}")

    # # --- Vision Analyzer ---
    # valid_files = []

    # for f_path in saved_files:
    #     if isinstance(f_path, str) and os.path.exists(f_path):
    #         valid_files.append(f_path)

    # vision_context = ""

    # if valid_files:
    #     vision_result = await analyze_files(valid_files)
    #     vision_context = vision_result.get("combined_text", "")

    # --- Planner state build ---
    # state = await build_conversation_state(conversation_id)

    # --- Planner ---
    # planner_output = call_planner(
    #     user_input=user_input,
    #     state=state,
    #     vision_context=vision_context,
    #     date_time=datetime.now(),
    # )

    # conversation_title = planner_output.get(
    #     "conversation_title",
    #     "Untitled Conversation"
    # )

    # --- Debug ---
    # print("ASK_AI:", {
    #     "conversation_id": conversation_id,
    #     "title": conversation_title,
    #     "user_id": user_id,
    #     "session_id": session_id,
    # })

    # tool_results = {}
    # tool_calls = planner_output.get("tool_calls", [])

    # if tool_calls:
    #     for tool_call in tool_calls:
    #         tool_name = tool_call.get("name")
    #         tool_args = tool_call.get("parameters", {})

    #         if tool_name == "calculator":
    #             from app.AI.calculator import _solve_math
    #             expr = tool_args.get("expression", "")
    #             mode = tool_args.get("mode", "auto")
    #             result = _solve_math(expr, mode)
    #             tool_results[tool_call["id"]] = {
    #                 "tool": tool_name,
    #                 "parameters": tool_args,
    #                 "result": result
    #             }
    #             # print(f"Result: {result}")
                
    #         elif tool_name == "web_search":
    #             from app.AI.Web_search import web_search
    #             query = tool_args.get("query", "")
    #             max_results = tool_args.get("max_results", 5)
    #             result = web_search(query, max_results)
    #             tool_results[tool_call["id"]] = {
    #                 "tool": tool_name,
    #                 "parameters": tool_args,
    #                 "result": result
    #             }

    #         elif tool_name == "clock_and_calendar":
    #             from app.AI.clock_and_calendar import _clock_and_calendar
    #             expr = tool_args.get("expression", "")
    #             reminder_details = tool_args.get("reminder_details", "")
    #             mode = tool_args.get("mode", "auto")
    #             result = await _clock_and_calendar(expr, reminder_details, mode)

    #             tool_results[tool_call["id"]] = {
    #                 "tool": tool_name,
    #                 "parameters": tool_args,
    #                 "result": result
    #             }
    #             print(f"Result: {result}")
    #         else:
    #             print(f"Unknown tool: {tool_name}")  # Debug print

    # # --- Stream assistant ---
    # assistant_text: list[str] = []
    # assistant_text2: list[str] = []
    # tts_buffer = ""
    # response_mode = user_input_set.get("response_mode", "text")
    
    # if response_mode == "text_stream":
    #     async for chunk in call_responder_text(
    #         user_input,
    #         conversation_id,
    #         planner_output,
    #         tool_results,
    #         vision_context=vision_context
    #     ):
    #         assistant_text.append(chunk)
    #         yield {
    #             "type": "token",
    #             "message_id": assistant_message_id,
    #             "content": chunk,
    #         }
    
    # elif response_mode == "voice_stream":
    #     async for chunk in call_responder_voice(
    #         user_input,
    #         conversation_id,
    #         planner_output,
    #         tool_results
    #     ): 
    #         if chunk.get("type") == "extra":
    #             assistant_text2.append(chunk["content"])
    #             # content_text = json.dumps(chunk["content"], ensure_ascii=False)
        
    #             yield {
    #                 "type": "extra_details",
    #                 "message_id": assistant_message_id,
    #                 "content": chunk["content"],
    #             }
    #             continue
            
    #         if chunk.get("type") == "token":
    
    #             content_text = chunk["content"]
    #             assistant_text.append(chunk["content"])
    #             tts_buffer += content_text

            #     # Send when a sentence ends
            #     while any(tts_buffer.endswith(p) for p in [".", "?", "!"]):
            #         for idx, char in enumerate(tts_buffer):
            #             if char in [".", "?", "!"]:
            #                 sentence = tts_buffer[:idx + 1].strip()
            #                 tts_buffer = tts_buffer[idx + 1:].lstrip()
            #                 break
            #         else:
            #             sentence = tts_buffer
            #             tts_buffer = ""

            #         # Generate TTS for this sentence
            #         chunks = []
            #         async for audio_chunk in stream_tts(sentence):
            #             chunks.append(audio_chunk)

            #         # Send chunks sequentially
            #         for i, audio_chunk in enumerate(chunks):
            #             encoded_chunk = base64.b64encode(audio_chunk).decode("utf-8")
            #             yield {
            #                 "type": "audio_chunk",
            #                 "message_id": assistant_message_id,
            #                 "data": encoded_chunk,
            #                 "done": i == len(chunks) - 1,  # mark last chunk
            #             }

    #             yield {
    #                 "type": "token",
    #                 "message_id": assistant_message_id,
    #                 "content": content_text,
    #             }
    
    # print()
    # print("Final extra text:", "".join(assistant_text2))
    # print()
    # print()
    # print("Final text:", "".join(assistant_text))

    # # --- Save user message ---
    # await save_user_message(conversation_id, user_input, user_message_id)
    
    # # --- Persist assistant message ---
    # await save_assistant_message(
    #     conversation_id,
    #     "".join(assistant_text),
    #     assistant_message_id,
    # )

    # yield {
    #     "type": "done",
    #     "message_id": assistant_message_id,
    # # }

    # # --- Update conversation ---
    # await ensure_conversation(
    #     conversation_id=conversation_id,
    #     title=conversation_title,
    #     user_id=user_id,   
    #     session_id=session_id,
    # )

    # # --- Send meta ---
    # yield {
    #     "type": "meta",
    #     "conversation_id": conversation_id,
    #     "title": conversation_title,
    # }

# # -----------------------
# # Main Loop
# # ------------------x-----

# # if __name__ == "__main__":
# #     while True:
# #         user_input = input("You: ")
# #         if user_input.lower() in {"exit", "quit"}:
# #             break
        
# #         ask_ai(user_input)