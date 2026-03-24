import base64
import os
import uuid
import yaml
import json

from ollama import Client
from dotenv import load_dotenv

load_dotenv()

# -------------------------
# CONFIG
# -------------------------

MODEL_NAME = "qwen3.5:397b-cloud"

API_KEY = "9dca452ca8ff4bdcbad638dce38edb3e.6wrp2ylkOaocRcRUFPN88d-e"

client = Client(
    host="https://ollama.com",
    headers={"Authorization": f"Bearer {API_KEY}"}
)

BASE_DIR = os.path.dirname(__file__)
ANALYZER_YAML = os.path.join(BASE_DIR, "analyzer_prompt_main.yaml")

SUPPORTED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}

UPLOAD_DIR = "app/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# -------------------------
# PROMPT BUILDER
# -------------------------

def build_analyzer_prompt(user_input: str):

    with open(ANALYZER_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    rules = "\n".join(f"- {r}" for r in cfg["rules"])
    tasks = "\n".join(f"- {t}" for t in cfg["analysis_tasks"])
    schema = json.dumps(cfg["output_schema"], indent=2)

    return f"""
SYSTEM:
{cfg['description']}

USER QUESTION:
{user_input}

RULES:
{rules}

ANALYSIS TASKS:
{tasks}

OUTPUT FORMAT (JSON ONLY):
{schema}

Analyze the image carefully.

Focus on any details that may help answer the user’s question.

Return JSON only.
""".strip()


# -------------------------
# FILE HANDLING
# -------------------------

async def analyze_files(file_set: list | None, user_input: str):

    if not file_set:
        return {
            "upload_details": [],
            "analyzer_results": {
                "files_summary": [],
                "combined_text": ""
            }
        }

    saved_files = []
    upload_details = []

    for f in file_set:

        file_type = f.get("type")
        name = f.get("name")
        content = f.get("content")

        if not name or not content:
            continue

        try:

            if "," in content:
                content = content.split(",", 1)[1]

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

    analyzer_results = await call_analyzer(saved_files, user_input)

    return {
        "upload_details": upload_details,
        "analyzer_results": analyzer_results,
    }


# -------------------------
# IMAGE ANALYSIS
# -------------------------
async def call_analyzer(files: list[str], user_input: str):

    image_files = [
        f for f in files
        if os.path.splitext(f)[1].lower() in SUPPORTED_IMAGE_EXT
    ]

    if not image_files:
        return {
            "files_summary": [],
            "combined_text": ""
        }

    prompt = build_analyzer_prompt(user_input)

    try:

        response = client.chat(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": image_files
                }
            ]
        )

        text = response["message"]["content"].strip()

        try:
            analysis = json.loads(text)
        except Exception:
            print("Analyzer returned non-JSON response.")
            analysis = {
                "scene_summary": text,
                "visible_text": "",
                "key_elements": [],
                "notable_details": []
            }

        # build planner context
        combined_text = f"""
            Images analyzed: {len(image_files)}

                Scene Summary:
                {analysis.get("scene_summary","")}

Visible Text:
{analysis.get("visible_text","")}

Key Elements:
{analysis.get("key_elements","")}

Notable Details:
{analysis.get("notable_details","")}
"""

        return {
            "files_summary": [
                {
                    "files": image_files,
                    "analysis": analysis
                }
            ],
            "combined_text": combined_text.strip()
        }

    except Exception as e:
        print(f"Vision analyzer failed: {e}")

        return {
            "files_summary": [],
            "combined_text": ""
        }