import os
from pyparsing import Any, Mapping
import yaml
import json
from ollama import Client
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(__file__)
PLANNER_YAML = os.path.join(BASE_DIR, "planner_prompt.yaml")

API_KEY = "9dca452ca8ff4bdcbad638dce38edb3e.6wrp2ylkOaocRcRUFPN88d-e"
MODEL_NAME = "gpt-oss:120b-cloud"

client = Client(
    host="https://ollama.com",
    headers={"Authorization": f"Bearer {API_KEY}"}
)

def build_planner_prompt(
    user_input: str,
    state: Mapping[str, Any]
) -> str:
    with open(PLANNER_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    rules = "\n".join(f"- {r}" for r in cfg["rules"])
    tasks = "\n".join(f"- {t}" for t in cfg["planning_tasks"])
    tools = "\n".join(f"- {t}" for t in cfg["tools"])

    schema = json.dumps(cfg["output_schema"], indent=2)

    return f"""
SYSTEM:
{cfg['description']}

CONVERSATION STATE (READ-ONLY):
{json.dumps(state, indent=2)}

RULES:
{rules}

PLANNING TASKS:
{tasks}

PLANNING TOOLS:
{tools}

OUTPUT FORMAT (JSON ONLY):
{schema}

USER INPUT:
{user_input}

OUTPUT JSON:
""".strip()


def call_planner(
    user_input: str,
    state: Mapping[str, Any]
) -> dict:
    prompt = build_planner_prompt(user_input, state)

    messages = [{"role": "user", "content": prompt}]

    full_response = ""
    for part in client.chat(MODEL_NAME, messages=messages, stream=True):
        full_response += part['message']['content']

    text = full_response.strip()
    
    print("Planner Response:", text)  # Debug print
    
    if not text:
        raise RuntimeError("Planner returned empty response")

    try:
        planner_output = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError(f"Planner output invalid JSON:\n{text}")

    required_keys = {
        "intent",
        "requires_tools",
        "tool_calls",
        "memory_candidates",
        "response_style"
    }

    missing = required_keys - planner_output.keys()
    if missing:
        raise ValueError(f"Planner missing keys: {missing}")

    return planner_output