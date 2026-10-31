# Development and integration

[简体中文](development.md) | English

Follow the [README](../README.en.md#run-locally) to install and start the project. Run the commands below from the project root, with your virtual environment activated.

The backend uses Python, FastAPI, and SQLite. API documentation is available at <http://127.0.0.1:8000/docs>. Runtime data is stored in `data/` by default, and exported Markdown notes are written to `data/obsidian_vault/`.

## Local speech transcription

```bash
python -m pip install -e ".[full]"
python scripts/download_models.py
```

The download script saves models to `models/`. The service accepts mono PCM16 audio over WebSocket at `/api/v1/stream/audio`, with a default sample rate of 16 kHz.

Local transcription requires `sherpa-onnx` and the SenseVoice model weights. When dependencies or weights are missing, the backend returns placeholder text rather than an actual transcript. Speaker identification also requires its corresponding model. The voiceprint registration button in the web interface currently uses synthetic audio for demonstration. To register a voiceprint from a real recording, use:

```bash
python scripts/enroll_speaker.py --wav /path/to/voice.wav
```

## Configure an extraction model

Copy [`.env.example`](../.env.example) to `.env` and set `LLM_MODEL`, `LLM_API_KEY`, and `LLM_API_BASE`. Model calls use LiteLLM, which is included in the `full` optional dependencies above.

The default rule-based mode does not call an external model. If you configure an external model service, conversation text is sent to that service. If you configure `WEBHOOK_URL`, generated briefs are also sent to that address.

## MCP

Install `fastmcp` to run the MCP service over stdio:

```bash
python -m pip install fastmcp
python -m backend.connectors.mcp_server
```

The service provides four tools:

| Tool | Purpose |
| --- | --- |
| `search_personal_memory` | Search memory cards and related dialogue |
| `get_pending_todos` | Retrieve unfinished tasks |
| `get_wishlists_and_clues` | Retrieve wishes and follow-up notes |
| `query_entity_graph` | Retrieve facts about a person or project |

In your MCP client, set the command to the Python executable in your virtual environment, the arguments to `-m backend.connectors.mcp_server`, and the working directory to the project root. The API and MCP services must use the same data directory.

## Current limitations

- Voice activity detection uses an energy threshold. Without a speaker model, speaker identification falls back to simple spectral features.
- Search uses SQLite FTS5 and character feature vectors. Semantic embedding models have not been integrated yet.
- Audio inbox processing functions exist, but the service does not automatically scan the directory on startup. Morning and evening briefs are not scheduled yet.
- The web HUD demonstrates message display. Bluetooth integration for specific glasses or recording pins has not been implemented.

There are no performance benchmarks from real devices yet, and transcription and extraction accuracy have not been systematically evaluated.

## Development

Run the existing tests:

```bash
python -m unittest discover -s tests -v
```

Main source directories:

```text
backend/
  audio_engine/   Audio segmentation, transcription, and speaker identification
  ingest/         WebSocket input and audio file processing
  memory_core/    Memory cards, information extraction, and fact updates
  storage/        SQLite storage and search
  connectors/     MCP, Obsidian, and Webhook
plugins/          Example event-subscriber plugins
web_pwa/          Web interface
scripts/          Model downloads, voiceprint registration, and workflow demos
```

See [`plugins/example_hud_logger.py`](../plugins/example_hud_logger.py) for an example plugin. Design notes and plans are in [`specs/`](../specs/) (Chinese); some of that functionality is not yet implemented.
