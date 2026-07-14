# Voice Output Feature Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add voice output to the `/chat` endpoint, generating audio files asynchronously based on the agent's mood.

**Architecture:** The `/chat` endpoint calls `Master.run()` to get the response with mood, then uses FastAPI's `BackgroundTasks` to asynchronously generate a voice audio file via Qwen3-TTS. The voice_id is returned in the response for the client to locate the audio file.

**Tech Stack:**
- Qwen3-TTS (`qwen3-tts-instruct-flash`) for speech synthesis
- FastAPI `BackgroundTasks` for async execution
- DashScope `MultiModalConversation.call()` API

---

## Requirements

1. Add `get_voice()` function in `MyTools.py`
2. Generate audio files to `Sound/{user_id}/` directory
3. voice_id format: `{uid}_{timestamp_ms}`
4. Mood-to-TTS instruction mapping:

| Agent Mood | TTS Instruction |
|------------|-----------------|
| `default` | None (default calm) |
| `upbeat` | "用兴奋、激动的语气说话，表现出热情和活力。" |
| `angry` | "用愤怒、严厉的语气说话，表现出不满和警告。" |
| `depressed` | "用悲伤、低沉的语气说话，表现出忧虑和同情。" |
| `friendly` | "用友好、温和的语气说话，表现出亲切和关怀。" |
| `cheerful` | "用开心、愉悦的语气说话，表现出高兴和乐观。" |

---

## File Structure

| File | Action | Description |
|------|--------|-------------|
| `MyTools.py` | Modify | Add `get_voice()` function and `MOOD_TO_INSTRUCTION` mapping |
| `server.py` | Modify | Integrate `BackgroundTasks` in `/chat` endpoint |
| `test_scripts/test_get_voice.py` | Create | Non-FastAPI test script |
| `Sound/{user_id}/` | Create directory | Audio file storage |

---

## Component Design

### 1. `get_voice` Function (MyTools.py)

```python
# Mood to TTS instruction mapping
MOOD_TO_INSTRUCTION = {
    "default": None,
    "upbeat": "用兴奋、激动的语气说话，表现出热情和活力。",
    "angry": "用愤怒、严厉的语气说话，表现出不满和警告。",
    "depressed": "用悲伤、低沉的语气说话，表现出忧虑和同情。",
    "friendly": "用友好、温和的语气说话，表现出亲切和关怀。",
    "cheerful": "用开心、愉悦的语气说话，表现出高兴和乐观。",
}

async def get_voice(uid: str, text: str, mood: str, voice: str = "Eldric Sage") -> str:
    """
    Asynchronously generate voice audio file.
    
    Args:
        uid: User ID
        text: Text to convert to speech
        mood: Mood (default/upbeat/angry/depressed/friendly/cheerful)
        voice: Voice ID, default "Eldric Sage"
    
    Returns:
        voice_id: Format {uid}_{timestamp_ms}
    """
    import time
    import os
    import dashscope
    import requests
    
    # Generate voice_id
    timestamp_ms = int(time.time() * 1000)
    voice_id = f"{uid}_{timestamp_ms}"
    
    # Create output directory
    output_dir = os.path.join("Sound", uid)
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{voice_id}.wav")
    
    # Get TTS instruction based on mood
    instruction = MOOD_TO_INSTRUCTION.get(mood)
    
    # Call Qwen3-TTS API
    params = {
        "model": "qwen3-tts-instruct-flash",
        "api_key": DASHSCOPE_API_KEY,
        "text": text,
        "voice": voice,
        "language_type": "Chinese",
        "stream": False,
    }
    if instruction:
        params["instructions"] = instruction
        params["optimize_instructions"] = True
    
    response = dashscope.MultiModalConversation.call(**params)
    
    if response.status_code == 200:
        audio_url = response.output.audio.url
        if audio_url:
            # Download audio file
            audio_response = requests.get(audio_url, timeout=60)
            if audio_response.status_code == 200:
                with open(output_file, "wb") as f:
                    f.write(audio_response.content)
                logger.info(f"Voice generated: {output_file}")
            else:
                logger.error(f"Failed to download audio: HTTP {audio_response.status_code}")
        else:
            logger.error("No audio URL in response")
    else:
        logger.error(f"TTS API error: {response.code} - {response.message}")
    
    return voice_id
```

### 2. Server Integration (server.py)

```python
from fastapi import BackgroundTasks
from MyTools import get_voice

@app.post("/chat")
def chat(query: str, background_tasks: BackgroundTasks):
    if master_instance is None:
        return {"error": "Master 实例未初始化"}
    
    # Run agent
    res = master_instance.run(query)
    
    # Generate voice_id
    import time
    timestamp_ms = int(time.time() * 1000)
    voice_id = f"{master_instance.user_id}_{timestamp_ms}"
    res["voice_id"] = voice_id
    
    # Add background task for voice generation (non-blocking)
    background_tasks.add_task(
        get_voice,
        uid=master_instance.user_id,
        text=res["output"],
        mood=res["qingxu"],
        voice="Eldric Sage"
    )
    
    return res
```

### 3. Test Script (test_scripts/test_get_voice.py)

```python
"""
Test get_voice function without FastAPI
"""
import asyncio
from MyTools import get_voice

async def main():
    # Test all moods
    moods = ["default", "upbeat", "angry", "depressed", "friendly", "cheerful"]
    
    for mood in moods:
        print(f"\nTesting mood: {mood}")
        voice_id = await get_voice(
            uid="test_user",
            text="命里有时终须有，命里无时莫强求。这位施主，且听老夫一言。",
            mood=mood
        )
        print(f"Generated voice_id: {voice_id}")
    
    print("\nAll tests completed!")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Data Flow

```
POST /chat?query=你好
    │
    ▼
Master.run(query)
    │
    ▼
res = {
    "input": "你好",
    "output": "施主你好，老夫陈玉楼...",
    "qingxu": "friendly"
}
    │
    ▼
voice_id = "default_1720612345678"
res["voice_id"] = voice_id
    │
    ▼
background_tasks.add_task(get_voice, ...)
    │
    ▼
return res  ← Response sent immediately
    │
    │  (Background task runs async)
    ▼
get_voice() → Sound/default/default_1720612345678.wav
```

---

## Directory Structure

```
Sound/
└── default/
    ├── default_1720612345678.wav
    └── default_1720612345999.wav
└── test_user/
    ├── test_user_1720612400000.wav
    └── ...
```

---

## Error Handling

1. **TTS API failure**: Log error, voice_id still returned (audio file won't exist)
2. **Download failure**: Log error, voice_id still returned
3. **Directory creation failure**: Log error, function continues

---

## Testing Strategy

1. **Unit test**: Run `test_get_voice.py` to verify `get_voice()` works for all moods
2. **Integration test**: Use Postman to test `/chat` endpoint, verify:
   - Response contains `voice_id`
   - Audio file is generated in `Sound/{user_id}/` directory
   - Audio plays correctly with expected emotion

---

## Dependencies

- `dashscope` (already installed)
- `requests` (already installed)
- No new dependencies required
