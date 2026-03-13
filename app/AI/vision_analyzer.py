import base64
import os
import uuid
from ollama import Client

MODEL_NAME = "qwen3.5:397b-cloud"   # or qwen2.5vl:7b / 72b depending on your setup
API_KEY = "9dca452ca8ff4bdcbad638dce38edb3e.6wrp2ylkOaocRcRUFPN88d-e"

client = Client(
    host="https://ollama.com",
    headers={"Authorization": f"Bearer {API_KEY}"}
)

SUPPORTED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
UPLOAD_DIR = "app/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

async def analyze_files(files: list[str]):
    saved_files = []
    upload_details = []

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

                file_ext = os.path.splitext(name)[1].lower() 
 
                file_id = str(uuid.uuid4())
 
                save_path = os.path.join(UPLOAD_DIR, f"{file_id}{file_ext}")
 
                with open(save_path, "wb") as fp:
                    fp.write(data)

                    upload_details.append({
                        "file_id": file_id,
                        "file_ext": file_ext,
                        "file_type": file_type,
                        "name": name,
                    })
 
                saved_files.append(save_path)
 
            except Exception as e:
                print(f"Failed to save file {name}: {e}")

    analyzer_results = await call_analyzer(saved_files)

    return {
        "upload_details": upload_details,
        "analyzer_results": analyzer_results,
    }



async def call_analyzer(files: list[str]):

    summaries = []
    combined_text = ""

    for f_path in files:

        ext = os.path.splitext(f_path)[1].lower()

        # Only process images
        if ext not in SUPPORTED_IMAGE_EXT:
            continue

        try:

            response = client.chat(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "user",
                        "content": "Describe this image in detail. Include any text, charts, objects, or important information.",
                        "images": [f_path]
                    }
                ]
            )

            description = response["message"]["content"]

            summaries.append({
                "file": f_path,
                "description": description
            })

            combined_text += f"\nImage ({os.path.basename(f_path)}):\n{description}\n"

        except Exception as e:
            print(f"Vision analyzer failed for {f_path}: {e}")

    return {
        "files_summary": summaries,
        "combined_text": combined_text
    }