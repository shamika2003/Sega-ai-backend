import requests
import os
from dotenv import load_dotenv

load_dotenv()

PIXABAY_API_KEY = "55090628-c19470b532cf3c2ab097d48d9"
PEXELS_API_KEY = "NthM4i3wrQfL3CJ5GXDvaiFa5Mx2mNOKssfdUVEXeQidz7MMAuxg4rUg"


def media_search(query: str, max_results: int = 5):

    if not query:
        return {"error": "Query is empty"}

    images = []

    try:
        # -------------------------
        # Pixabay Search
        # -------------------------
        pixabay_url = "https://pixabay.com/api/"

        pixabay_params = {
            "key": PIXABAY_API_KEY,
            "q": query,
            "image_type": "photo",
            "per_page": max_results,
            "safesearch": True
        }

        r = requests.get(pixabay_url, params=pixabay_params, timeout=10)
        r.raise_for_status()

        data = r.json()

        for img in data.get("hits", []):
            images.append({
                "title": img.get("tags"),
                "image_url": img.get("webformatURL"),
                "page_url": img.get("pageURL"),
                "source": "Pixabay"
            })

    except Exception as e:
        print("Pixabay error:", e)

    try:
        # -------------------------
        # Pexels Search
        # -------------------------
        pexels_url = "https://api.pexels.com/v1/search"

        headers = {
            "Authorization": PEXELS_API_KEY
        }

        params = {
            "query": query,
            "per_page": max_results
        }

        r = requests.get(pexels_url, headers=headers, params=params, timeout=10)
        r.raise_for_status()

        data = r.json()

        for img in data.get("photos", []):
            images.append({
                "title": query,
                "image_url": img["src"]["medium"],
                "page_url": img["url"],
                "source": "Pexels"
            })

    except Exception as e:
        print("Pexels error:", e)

    return {
        "query": query,
        "results": images[:max_results]
    }