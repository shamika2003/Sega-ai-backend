import asyncio
from typing import AsyncGenerator
from elevenlabs.client import ElevenLabs

ELEVENLABS_API_KEY = "sk_0dc7c3224346c5dc39d7ce93427f982af5f644357adb8d47"
VOICE_ID = "hpp4J3VqNfWAUOO0d1Us"  
MODEL_ID = "eleven_multilingual_v2"

client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

async def stream_tts(text: str) -> AsyncGenerator[dict, None]:
    audio_stream = client.text_to_speech.stream(
        text=text,
        voice_id=VOICE_ID,
        model_id=MODEL_ID,
    )

    for chunk in audio_stream:
        if chunk:
            yield chunk
        await asyncio.sleep(0)

    # yield {"type": "done"}
