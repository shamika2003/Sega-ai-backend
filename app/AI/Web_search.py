import requests
import os
from dotenv import load_dotenv

load_dotenv()

TAVILY_API_KEY = "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"
TAVILY_URL = "https://api.tavily.com/search"


def web_search(query: str, max_results: int = 5):

    if not query:
        return {"error": "Query is empty"}

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
    }

    try:
        response = requests.post(TAVILY_URL, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()

        results = []
        for r in data.get("results", []):
            results.append({
                "title": r.get("title"),
                "url": r.get("url"),
                "content": r.get("content"),
                "score": r.get("score"),
            })

        return {
            "query": query,
            "results": results
        }

    except Exception as e:
        return {"error": str(e)}
