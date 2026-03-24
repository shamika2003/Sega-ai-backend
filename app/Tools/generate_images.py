import os
import asyncio
import uuid
from fastapi import Request
import requests
from dotenv import load_dotenv

load_dotenv()

# -------------------------
# CONFIG
# -------------------------
ACCOUNT_ID = "f8db28ac8f1caa11b3655c63362d350f"
API_TOKEN = "cfut_iMFXdhJ3nUj5yJ5g4kHsIG9MF5u5PKaKYAIGMeu7caf961c6"

MODEL_URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/@cf/stabilityai/stable-diffusion-xl-base-1.0"

SAVED_DIR = "app/generate"
os.makedirs(SAVED_DIR, exist_ok=True)

# -------------------------
# Generate images
# -------------------------
async def generate_images(prompt: str, style: str = None, size: str = "512x512", quantity: int = 1):

    width, height = map(int, size.lower().split("x"))

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }

    results = [] 

    for i in range(quantity):

        full_prompt = prompt if not style else f"{prompt}, style: {style}"

        data = {
            "prompt": full_prompt,
            "width": width,
            "height": height
        }

        try:
            response = await asyncio.to_thread(
                lambda: requests.post(MODEL_URL, headers=headers, json=data, timeout=60)
            )

            if response.status_code == 200:

                file_id = str(uuid.uuid4())
                filename = f"{file_id}.png"
                file_path = os.path.join(SAVED_DIR, filename)

                with open(file_path, "wb") as f:
                    f.write(response.content)

                results.append({
                    "prompt": prompt,
                    "style": style,
                    "size": size,
                    "url": f"{Request.base_url}images/{filename}"
                })
                


            else:
                results.append({"error": response.text})

        except Exception as e:
            results.append({"error": str(e)})

    return results


# -------------------------
# Test execution
# -------------------------
# if __name__ == "__main__":

#     prompt = "A futuristic neon city skyline, cinematic lighting"

#     images = asyncio.run(generate_images(prompt, quantity=2))

#     for idx, img in enumerate(images):

#         if "image_bytes" in img:

#             file_path = os.path.join(SAVED_DIR, f"cloudflare_{idx}.png")

#             with open(file_path, "wb") as f:
#                 f.write(img["image_bytes"])

#             print("Saved:", file_path)

#         else:
#             print("Error:", img["error"])