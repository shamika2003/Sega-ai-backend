import os
from ollama import Client

MODEL_NAME = "qwen3.5:397b-cloud"   # or qwen2.5vl:7b / 72b depending on your setup
API_KEY = "9dca452ca8ff4bdcbad638dce38edb3e.6wrp2ylkOaocRcRUFPN88d-e"

client = Client(
    host="https://ollama.com",
    headers={"Authorization": f"Bearer {API_KEY}"}
)

SUPPORTED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


async def analyze_files(files: list[str]):

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