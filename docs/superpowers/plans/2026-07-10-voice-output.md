# Voice Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add voice output to the `/chat` endpoint, generating audio files asynchronously based on the agent's mood.

**Architecture:** The `/chat` endpoint calls `Master.run()` to get the response with mood, then uses FastAPI's `BackgroundTasks` to asynchronously generate a voice audio file via Qwen3-TTS. The voice_id is returned in the response for the client to locate the audio file.

**Tech Stack:**
- Qwen3-TTS (`qwen3-tts-instruct-flash`) for speech synthesis
- FastAPI `BackgroundTasks` for async execution
- DashScope `MultiModalConversation.call()` API

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `MyTools.py:374+` | Modify | Add `MOOD_TO_INSTRUCTION` dict and `get_voice()` function |
| `server.py:103-109` | Modify | Add `BackgroundTasks` to `/chat` endpoint |
| `test_scripts/test_get_voice.py` | Create | Test script for `get_voice()` function |
| `Sound/` | Create | Audio output directory |

---

### Task 1: Create Sound Directory and Test Script

**Files:**
- Create: `Sound/.gitkeep`
- Create: `test_scripts/test_get_voice.py`

- [ ] **Step 1: Create Sound directory**

```bash
mkdir -p Sound
touch Sound/.gitkeep
```

- [ ] **Step 2: Create test script**

Create `test_scripts/test_get_voice.py`:

```python
"""
Test get_voice function without FastAPI.
Verifies audio file generation for all moods.
"""
import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from MyTools import get_voice


async def main():
    """Test get_voice for all moods."""
    moods = ["default", "upbeat", "angry", "depressed", "friendly", "cheerful"]
    test_text = "命里有时终须有，命里无时莫强求。这位施主，且听老夫一言。"
    
    for mood in moods:
        print(f"\n{'='*50}")
        print(f"Testing mood: {mood}")
        print(f"{'='*50}")
        
        voice_id = await get_voice(
            uid="test_user",
            text=test_text,
            mood=mood
        )
        
        print(f"Generated voice_id: {voice_id}")
        
        # Check if file exists
        expected_file = f"Sound/test_user/{voice_id}.wav"
        if os.path.exists(expected_file):
            size = os.path.getsize(expected_file)
            print(f"[OK] File exists: {expected_file} ({size} bytes)")
        else:
            print(f"[FAIL] File not found: {expected_file}")
    
    print(f"\n{'='*50}")
    print("All tests completed!")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Verify test script syntax**

```bash
conda run -n py310 python -c "import ast; ast.parse(open('test_scripts/test_get_voice.py').read()); print('Syntax OK')"
```

Expected: `Syntax OK`

- [ ] **Step 4: Commit**

```bash
git add Sound/.gitkeep test_scripts/test_get_voice.py
git commit -m "feat: add Sound directory and test script for voice output"
```

---

### Task 2: Add MOOD_TO_INSTRUCTION Mapping to MyTools.py

**Files:**
- Modify: `MyTools.py:19` (after DASHSCOPE_API_KEY definition)

- [ ] **Step 1: Add mood-to-instruction mapping**

Add the following code after line 19 in `MyTools.py` (after `DASHSCOPE_API_KEY = ...`):

```python
# Mood to TTS instruction mapping for Qwen3-TTS
MOOD_TO_INSTRUCTION = {
    "default": None,
    "upbeat": "用兴奋、激动的语气说话，表现出热情和活力。",
    "angry": "用愤怒、严厉的语气说话，表现出不满和警告。",
    "depressed": "用悲伤、低沉的语气说话，表现出忧虑和同情。",
    "friendly": "用友好、温和的语气说话，表现出亲切和关怀。",
    "cheerful": "用开心、愉悦的语气说话，表现出高兴和乐观。",
}
```

- [ ] **Step 2: Verify syntax**

```bash
conda run -n py310 python -c "from MyTools import MOOD_TO_INSTRUCTION; print('Moods:', list(MOOD_TO_INSTRUCTION.keys()))"
```

Expected: `Moods: ['default', 'upbeat', 'angry', 'depressed', 'friendly', 'cheerful']`

- [ ] **Step 3: Commit**

```bash
git add MyTools.py
git commit -m "feat: add MOOD_TO_INSTRUCTION mapping for voice output"
```

---

### Task 3: Add get_voice Function to MyTools.py

**Files:**
- Modify: `MyTools.py:373+` (at end of file, before `if __name__ == "__main__":`)

- [ ] **Step 1: Add get_voice function**

Add the following function at the end of `MyTools.py`, before the `if __name__ == "__main__":` block (around line 373):

```python
# ==========================================
# Voice Output (Qwen3-TTS)
# ==========================================

async def get_voice(uid: str, text: str, mood: str, voice: str = "Eldric Sage") -> str:
    """
    Asynchronously generate voice audio file using Qwen3-TTS.
    
    Args:
        uid: User ID (used for directory and voice_id)
        text: Text to convert to speech
        mood: Mood from Agent (default/upbeat/angry/depressed/friendly/cheerful)
        voice: Voice ID for Qwen3-TTS, default "Eldric Sage"
    
    Returns:
        voice_id: Format {uid}_{timestamp_ms}, used to locate audio file
    """
    import time
    import dashscope
    
    # Disable proxy
    for key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
        os.environ.pop(key, None)
    
    # Generate voice_id
    timestamp_ms = int(time.time() * 1000)
    voice_id = f"{uid}_{timestamp_ms}"
    
    # Create output directory
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Sound", uid)
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{voice_id}.wav")
    
    # Get TTS instruction based on mood
    instruction = MOOD_TO_INSTRUCTION.get(mood)
    logger.info(f"Generating voice: uid={uid}, mood={mood}, voice_id={voice_id}")
    
    # Build API parameters
    params = {
        "model": "qwen3-tts-instruct-flash",
        "api_key": DASHSCOPE_API_KEY,
        "text": text,
        "voice": voice,
        "language_type": "Chinese",
        "stream": False,
    }
    
    # Add instruction if mood requires it
    if instruction:
        params["instructions"] = instruction
        params["optimize_instructions"] = True
    
    try:
        # Call Qwen3-TTS API
        response = dashscope.MultiModalConversation.call(**params)
        
        if response.status_code == 200:
            audio_url = response.output.audio.url
            if audio_url:
                # Download audio file
                audio_response = requests.get(audio_url, timeout=60)
                if audio_response.status_code == 200:
                    with open(output_file, "wb") as f:
                        f.write(audio_response.content)
                    logger.info(f"Voice generated successfully: {output_file}")
                else:
                    logger.error(f"Failed to download audio: HTTP {audio_response.status_code}")
            else:
                logger.error("No audio URL in TTS response")
        else:
            logger.error(f"TTS API error: {response.code} - {response.message}")
    except Exception as e:
        logger.error(f"Voice generation failed: {e}")
    
    return voice_id
```

- [ ] **Step 2: Verify function can be imported**

```bash
conda run -n py310 python -c "from MyTools import get_voice; print('get_voice imported successfully')"
```

Expected: `get_voice imported successfully`

- [ ] **Step 3: Commit**

```bash
git add MyTools.py
git commit -m "feat: add get_voice function for Qwen3-TTS voice synthesis"
```

---

### Task 4: Test get_voice Function

**Files:**
- Test: `test_scripts/test_get_voice.py`

- [ ] **Step 1: Run test script for single mood (default)**

```bash
conda run -n py310 python -c "
import asyncio
from MyTools import get_voice

async def test():
    voice_id = await get_voice('test_user', '你好，这是测试。', 'default')
    print(f'voice_id: {voice_id}')
    
asyncio.run(test())
"
```

Expected: Should print a voice_id like `test_user_1720612345678`

- [ ] **Step 2: Verify audio file was created**

```bash
ls -la Sound/test_user/
```

Expected: Should see a `.wav` file with the voice_id name

- [ ] **Step 3: Run full test for all moods**

```bash
conda run -n py310 python test_scripts/test_get_voice.py
```

Expected: All 6 moods should generate audio files successfully

- [ ] **Step 4: Commit test results (if any fixes needed)**

```bash
git add -A
git commit -m "fix: resolve issues found during voice output testing"
```

(Only commit if fixes were needed)

---

### Task 5: Integrate get_voice into server.py /chat Endpoint

**Files:**
- Modify: `server.py:103-109`

- [ ] **Step 1: Update imports in server.py**

Change line 9-10 in `server.py` from:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
```

To:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
```

- [ ] **Step 2: Add get_voice import**

Add after line 14 (`from MyTools import add_urls_to_db`):

```python
from MyTools import get_voice
```

- [ ] **Step 3: Update /chat endpoint**

Replace lines 103-109 (the current `/chat` endpoint):

```python
@app.post("/chat")
def chat(query: str):
    # 使用 lifespan 中创建的 master_instance
    if master_instance is None:
        return {"error": "Master 实例未初始化"}
    res = master_instance.run(query)
    return res
```

With:

```python
@app.post("/chat")
def chat(query: str, background_tasks: BackgroundTasks):
    # 使用 lifespan 中创建的 master_instance
    if master_instance is None:
        return {"error": "Master 实例未初始化"}
    
    # Run agent
    res = master_instance.run(query)
    
    # Generate voice_id and add to response
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

- [ ] **Step 4: Verify server.py syntax**

```bash
conda run -n py310 python -c "import ast; ast.parse(open('server.py').read()); print('Syntax OK')"
```

Expected: `Syntax OK`

- [ ] **Step 5: Commit**

```bash
git add server.py
git commit -m "feat: integrate voice output into /chat endpoint with BackgroundTasks"
```

---

### Task 6: Integration Test with Postman

**Files:**
- None (manual testing)

- [ ] **Step 1: Start the server**

```bash
conda run -n py310 python server.py
```

- [ ] **Step 2: Test /chat endpoint with Postman**

Send POST request:
```
POST http://127.0.0.1:8000/chat
Content-Type: application/json

Body (raw JSON): "你好"
```

Expected response should include:
```json
{
    "input": "你好",
    "output": "...",
    "qingxu": "default",
    "voice_id": "default_1720612345678"
}
```

- [ ] **Step 3: Verify audio file is generated**

Wait a few seconds, then check:

```bash
ls -la Sound/default/
```

Expected: Should see a `.wav` file matching the `voice_id` from the response

- [ ] **Step 4: Test with different moods**

Send different queries to trigger different moods:
- Excited: "太棒了！我中奖了！"
- Sad: "我今天心情很不好..."
- Angry: "你这个人怎么回事！"

Verify audio files are generated with appropriate emotions.

- [ ] **Step 5: Commit any fixes if needed**

```bash
git add -A
git commit -m "fix: resolve integration issues found during Postman testing"
```

(Only commit if fixes were needed)

---

## Summary

After completing all tasks:
- `MyTools.py` will have `MOOD_TO_INSTRUCTION` dict and `get_voice()` function
- `server.py` will use `BackgroundTasks` to run `get_voice()` asynchronously
- Audio files will be saved to `Sound/{user_id}/{voice_id}.wav`
- Response will include `voice_id` for client to locate the audio file
