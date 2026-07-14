# Feishu Frontend for Master Chen Design

**Goal:** Create a Feishu bot frontend (`feishu_master_chen.py`) that connects Feishu messaging with the existing `server.py` backend, supporting both text and voice responses.

**Architecture:** The bot uses Feishu's WebSocket long connection to receive messages, processes them through a queue-based worker, forwards to `server.py /chat`, and sends back both text and audio responses. The server.py is managed as a subprocess.

**Tech Stack:**
- `lark_oapi` - Feishu Python SDK
- WebSocket long connection (no public IP needed)
- Queue-based message processing
- subprocess for managing server.py lifecycle

---

## Requirements

1. Receive messages from Feishu via WebSocket
2. Forward messages to `server.py /chat` endpoint
3. Send text response back to Feishu
4. Wait for `voice_id.wav` audio file (max 20s, configurable) and send to Feishu
5. Queue-based sequential processing
6. Start/stop `server.py` together with the Feishu service

---

## API Design

### Endpoint 1: `/chat` (existing, modified)

**Input:** `query: str`

**Output:**
```json
{
    "input": "用户输入",
    "output": "陈大师回复文本",
    "qingxu": "friendly",
    "voice_id": "default_1720612345678"
}
```

**Behavior:**
- Run Master.run() to get response
- Start background task to generate audio
- Return immediately with voice_id

### Endpoint 2: `/get_audio/{voice_id}` (new)

**Input:** `voice_id: str` (path parameter)

**Output:** Audio file (WAV format, binary)

**Behavior:**
- Wait for audio file to be generated (max timeout configurable, default 20s)
- Return audio bytes as file download
- If timeout, return 404 or error

```python
@app.get("/get_audio/{voice_id}")
async def get_audio(voice_id: str, timeout: int = 20):
    """Get audio file by voice_id, wait for generation if needed."""
    # Find the audio file in Sound/{user_id}/{voice_id}.wav
    # Wait up to timeout seconds for file to appear
    # Return FileResponse or error
```

---

## Required Feishu Permissions

| Permission | Description | Status |
|------------|-------------|--------|
| `im:message` | Message capability | ✅ Already enabled |
| `im:message.p2p_msg:readonly` | Read P2P messages | ✅ Already enabled |
| `im:message:send_as_bot` | Send messages as bot | ✅ Already enabled |
| `im:resource` | Upload files/audio | ⚠️ **Need to enable** |

---

## File Structure

| File | Action | Description |
|------|--------|-------------|
| `feishu_master_chen.py` | Create | Main Feishu bot service |

---

## Component Design

### Configuration

```python
# Feishu App Config (from feishu_bot.py)
APP_ID = "your-feishu-app-id"
APP_SECRET = "your-feishu-app-secret"

# Server Config
SERVER_URL = "http://127.0.0.1:8000"
CHAT_ENDPOINT = "/chat"

# Voice Config
SOUND_DIR = "Sound"
VOICE_TIMEOUT = 20  # seconds, configurable
```

### Message Processing Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        feishu_master_chen.py                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐    ┌───────────┐    ┌─────────────────────────┐  │
│  │  WebSocket  │───→│  Queue    │───→│       Worker            │  │
│  │  Receiver   │    │ (FIFO)    │    │   (sequential loop)     │  │
│  └─────────────┘    └───────────┘    └─────────────────────────┘  │
│                                              │                    │
│                                              ▼                    │
│                        ┌──────────────────────────────────┐       │
│                        │ 1. POST /chat                    │       │
│                        │    → {output, qingxu, voice_id}  │       │
│                        │ 2. Send text to Feishu           │       │
│                        │ 3. GET /get_audio/{voice_id}     │       │
│                        │    → audio_bytes (async wait)    │       │
│                        │ 4. Convert WAV → OPUS            │       │
│                        │ 5. Upload & send audio to Feishu │       │
│                        │ 6. Next in queue                 │       │
│                        └──────────────────────────────────┘       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Worker Processing Steps

```python
def process_message(sender_id: str, text: str):
    """Process a single message through the complete flow."""
    
    # Step 1: POST to server.py /chat
    response = requests.post(f"{SERVER_URL}/chat", params={"query": text})
    result = response.json()
    
    output_text = result["output"]
    voice_id = result["voice_id"]
    
    # Step 2: Send text response to Feishu
    send_text_to_feishu(sender_id, output_text)
    
    # Step 3: Get audio from /get_audio endpoint (async wait)
    audio_response = requests.get(
        f"{SERVER_URL}/get_audio/{voice_id}",
        params={"timeout": VOICE_TIMEOUT}
    )
    
    if audio_response.status_code == 200:
        # Step 4: Convert WAV to OPUS
        wav_data = audio_response.content
        opus_data = convert_wav_to_opus_bytes(wav_data)
        
        # Step 5: Upload and send audio to Feishu
        file_key = upload_audio_to_feishu(opus_data, voice_id)
        send_audio_to_feishu(sender_id, file_key)
```

### File Upload to Feishu

```python
def upload_file_to_feishu(file_path: str) -> str:
    """Upload audio file to Feishu and return file_key."""
    request = CreateFileRequest.builder() \
        .request_body(CreateFileRequestBody.builder()
            .file_type("opus")  # or "mp3" depending on format
            .file_name(os.path.basename(file_path))
            .file(open(file_path, "rb"))
            .build()) \
        .build()
    
    response = client.im.v1.file.create(request)
    return response.data.file_key
```

### Send Audio Message

```python
def send_audio_to_feishu(sender_id: str, file_key: str):
    """Send audio message to Feishu user."""
    content = json.dumps({"file_key": file_key})
    
    request = CreateMessageRequest.builder() \
        .receive_id_type("open_id") \
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(sender_id)
            .msg_type("audio")
            .content(content)
            .build()
        ) \
        .build()
    
    client.im.v1.message.create(request)
```

### Server Lifecycle Management

```python
import subprocess
import signal

server_process = None

def start_server():
    """Start server.py as subprocess."""
    global server_process
    server_process = subprocess.Popen(
        ["conda", "run", "-n", "py310", "python", "server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    # Wait for server to be ready
    time.sleep(3)

def stop_server():
    """Stop server.py subprocess."""
    global server_process
    if server_process:
        server_process.terminate()
        server_process.wait()
```

### Main Entry Point

```python
def main():
    """Start server and Feishu bot."""
    print("[Master Chen] Starting server.py...")
    start_server()
    
    print("[Master Chen] Starting Feishu bot...")
    
    # Create event handler
    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(on_message_event) \
        .build()
    
    # Start WebSocket client
    ws_client = lark.ws.Client(
        APP_ID,
        APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )
    
    try:
        ws_client.start()
    except KeyboardInterrupt:
        print("[Master Chen] Shutting down...")
        stop_server()
```

---

## Audio File Format

**Important:** Feishu audio messages (msg_type: audio) **require OPUS format**.

### Conversion Flow

```
server.py generates .wav
        ↓
Convert to .opus (using pydub + ffmpeg)
        ↓
Upload to Feishu (file_type: "opus")
        ↓
Send as audio message (msg_type: "audio")
        ↓
Playable directly in Feishu
```

### Conversion Code

```python
from pydub import AudioSegment
import io

def convert_wav_to_opus_bytes(wav_data: bytes) -> bytes:
    """Convert WAV bytes to OPUS bytes for Feishu audio messages."""
    audio = AudioSegment.from_file(io.BytesIO(wav_data), format="wav")
    opus_buffer = io.BytesIO()
    audio.export(opus_buffer, format="opus")
    return opus_buffer.getvalue()
```

### Dependencies

- `pydub` - Python audio library
- `ffmpeg` - Must be installed on system (pydub dependency)

---

## Error Handling

1. **Server not ready:** Wait and retry for up to 10 seconds on startup
2. **POST /chat fails:** Send error message to Feishu user
3. **Audio timeout:** Log warning, skip audio (text already sent)
4. **File upload fails:** Log error, continue with text-only response

---

## Testing Strategy

1. **Unit test:** Test file waiting logic with mock files
2. **Integration test:** Use Feishu app to send messages
3. **Verify:**
   - Text response received
   - Audio file uploaded and sent
   - Queue processing is sequential (no race conditions)
   - Server starts/stops correctly

---

## Dependencies

| Package | Status | Purpose |
|---------|--------|---------|
| `lark_oapi` | ✅ Installed | Feishu SDK |
| `requests` | ✅ Installed | HTTP calls to server.py |
| `pydub` | ⚠️ Need to install | Audio format conversion |
| `ffmpeg` | ⚠️ Need to install | pydub dependency (system) |

### Install Commands

```bash
# Python package
pip install pydub

# FFmpeg (Windows)
# Option 1: Download from https://ffmpeg.org/download.html
# Option 2: Using chocolatey: choco install ffmpeg
# Option 3: Using conda: conda install -c conda-forge ffmpeg
```
