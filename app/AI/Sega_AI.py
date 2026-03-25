from datetime import datetime
import uuid

from app.AI.conversation_state import build_conversation_state
from app.db import ensure_conversation, save_assistant_message, save_user_message, save_upload, update_generate
from app.AI.tts_streamer import stream_tts
from app.AI.Planner import call_planner
from app.AI.responder_text import call_responder_text
from app.AI.responder_voice import call_responder_voice
from app.Tools.vision_analyzer import analyze_files

async def ask_ai(user_input_set: dict):

    # --- Validate input ---
    user_input = user_input_set.get("user_input")
    if not isinstance(user_input, str):
        raise ValueError("user_input must be a string")

    # --- Conversation ---
    conversation_id = user_input_set.get("conversation_id")
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
        
    # --- Turn Id ---
    # user_message_id = str(uuid.uuid4())
    assistant_message_id = str(uuid.uuid4())

    # --- Auth context ---
    user_id = user_input_set.get("user_id")     
    session_id = user_input_set.get("session_id")

    # --- Ensure conversation ---
    await ensure_conversation(
        conversation_id=conversation_id,
        title="",
        user_id=user_id,   
        session_id=session_id,
    )

    # --- Send meta ---
    yield {
        "type": "meta",
        "conversation_id": conversation_id,
    }

    # --- Vision Analyzer ---
    vision_result = []

    if(user_input_set.get("files")):

        yield {
            "type": "analyzer",
            "status": "start",
        }

        vision_result = await analyze_files(file_set=user_input_set.get("files"), user_input=user_input)
        # print(vision_result["analyzer_results"]["combined_text"])

        yield {
            "type": "analyzer",
            "status": "done",
        }

    # --- Planner state build ---
    state = await build_conversation_state(conversation_id)

    # --- Planner ---
    planner_output = call_planner(
        user_input=user_input,
        state=state,
        vision_context = (
            vision_result["analyzer_results"]["combined_text"]
            if vision_result
            else ""
        ),
        date_time=datetime.now(),
    )

    conversation_title = planner_output.get(
        "conversation_title",
        "Untitled Conversation"
    )

    tool_results = {}
    tool_calls = planner_output.get("tool_calls", [])
    image_create_file_ids = []

    if tool_calls:
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("parameters", {})

            if tool_name == "calculator":
                from app.Tools.calculator import _solve_math
                expr = tool_args.get("expression", "")
                mode = tool_args.get("mode", "auto")
                result = _solve_math(expr, mode)
                tool_results[tool_call["id"]] = {
                    "tool": tool_name,
                    "parameters": tool_args,
                    "result": result
                }
                # print(f"Result: {result}")
                
            elif tool_name == "web_search":
                from app.Tools.Web_search import web_search
                query = tool_args.get("query", "")
                max_results = tool_args.get("max_results", 5)
                result = web_search(query, max_results)
                tool_results[tool_call["id"]] = {
                    "tool": tool_name,
                    "parameters": tool_args,
                    "result": result
                }

            elif tool_name == "clock_and_calendar":
                from app.Tools.clock_and_calendar import _clock_and_calendar
                expr = tool_args.get("expression", "")
                reminder_details = tool_args.get("reminder_details", "")
                mode = tool_args.get("mode", "auto")
                result = await _clock_and_calendar(expr, reminder_details, mode)
                tool_results[tool_call["id"]] = {
                    "tool": tool_name,
                    "parameters": tool_args,
                    "result": result
                }
                print(f"Result: {result}")

            elif tool_name == "media_search":
                from app.Tools.media_search import media_search
                query = tool_args.get("query", "")
                max_results = tool_args.get("max_results", 5)
                result = media_search(query, max_results)
                tool_results[tool_call["id"]] = {
                    "tool": tool_name,
                    "parameters": tool_args,
                    "result": result
                }

            elif tool_name == "image_create":
                from app.Tools.generate_images import generate_images
                prompt = tool_args.get("prompt", "")
                style = tool_args.get("style", None)
                size = tool_args.get("size", "512x512")
                quantity = tool_args.get("quantity", 1)
                result = await generate_images(prompt, style, size, quantity)
                for img in result:
                    print("file id from results:", img["file_id"])
                    image_create_file_ids.append(img["file_id"])
                tool_results[tool_call["id"]] = {
                    "tool": tool_name,
                    "parameters": tool_args,
                    "result": result,
                    "extra_details": "give file link as url_path"
                }

            else:
                print(f"Unknown tool: {tool_name}")  # Debug print

    # --- Stream assistant ---
    assistant_text: list[str] = []
    assistant_text2: list[str] = []
    tts_buffer = ""
    response_mode = user_input_set.get("response_mode", "text")
    
    if response_mode == "text_stream":
        async for chunk in call_responder_text(
            user_input,
            conversation_id,
            planner_output,
            tool_results,
            vision_context = (
                vision_result["analyzer_results"]["combined_text"]
                if vision_result
                else ""
            ),
        ):
            assistant_text.append(chunk)
            yield {
                "type": "token",
                "message_id": assistant_message_id,
                "content": chunk,
            }
    
    elif response_mode == "voice_stream":
        async for chunk in call_responder_voice(
            user_input,
            conversation_id,
            planner_output,
            tool_results
        ): 
            if chunk.get("type") == "extra":
                assistant_text2.append(chunk["content"])
                # content_text = json.dumps(chunk["content"], ensure_ascii=False)
        
                yield {
                    "type": "extra_details",
                    "message_id": assistant_message_id,
                    "content": chunk["content"],
                }
                continue
            
            if chunk.get("type") == "token":
    
                content_text = chunk["content"]
                assistant_text.append(chunk["content"])
                tts_buffer += content_text

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

                yield {
                    "type": "token",
                    "message_id": assistant_message_id,
                    "content": content_text,
                }
    
    print()
    print("Final extra text:", "".join(assistant_text2))
    print()
    print()
    print("Final text:", "".join(assistant_text))

    yield {
        "type": "done",
        "message_id": assistant_message_id,
    }

    # --- Save user message ---
    message_id = await save_user_message(
        conversation_id, 
        user_input, 
    )
    
    # --- Persist assistant message ---
    assistant_id = await save_assistant_message(
        conversation_id,
        "".join(assistant_text),
    )

    # --- Update conversation ---
    await ensure_conversation(
        conversation_id=conversation_id,
        title=conversation_title,
        user_id=user_id,   
        session_id=session_id,
    )

    
    # --- Save Uploaded image ---
    if isinstance(vision_result, dict) and vision_result.get("upload_details") and vision_result.get("analyzer_results", {}).get("files_summary"):
        for upload, analysis in zip(
            vision_result["upload_details"],
            vision_result["analyzer_results"]["files_summary"]
        ):
            await save_upload(
                upload["file_id"],
                upload["file_ext"],
                upload["file_type"],
                message_id,
                upload["name"],
                conversation_id,
                analysis["description"],
            )

    # --- Save Generated image ---
    for file_id in image_create_file_ids:
        await update_generate(file_id, assistant_id, conversation_id)

    # --- Send meta ---
    yield {
        "type": "meta",
        "conversation_id": conversation_id,
        "title": conversation_title,
    }
