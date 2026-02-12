
from elevenlabs.client import ElevenLabs

# Set your API key
client = ElevenLabs(api_key="sk_0dc7c3224346c5dc39d7ce93427f982af5f644357adb8d47")

# Get available voices
available_voices = client.voices.get_all()

# Print voices
for voice in available_voices.voices:
    print(f"Name: {voice.name}, ID: {voice.voice_id}")