# EchoMind

[简体中文](README.md) | English

EchoMind is an open-source personal memory project for AI glasses and wearable audio recorders. It aims to turn everyday conversations into records you can find and use later.

One of its inspirations is [MemoMind (极米记得)](https://www.memo-mind.com/pages/memomind-one), which pairs glasses with a companion app for audio recording, summaries, captions, and more. Its memory service can pick out tasks and wishes from conversations and help people find past records. EchoMind is exploring a self-hosted, open-source approach to these experiences, with support for different devices as a longer-term goal.

The project is still at an early stage, with a working web prototype you can try.

## The experience we're working toward

A few everyday situations guide the project:

- After a meeting, look back at the main points and the things you agreed to do.
- When catching up with someone after a while, find where you left off and what has changed since.
- Rediscover places you wanted to visit or things you wanted to do, even if you only mentioned them in passing.
- At the start or end of the day, review recent conversations and anything still waiting for attention.

Over time, the aim is to keep these records in a personal memory library you can search, organize, and reuse, whether they come from glasses, a recording pin, or another device.

## What you can try today

Enter conversation text or load the built-in demo data to see memory cards, tasks, wishes, and follow-up notes. Cards retain the original dialogue. You can also search past records, review updates about people or projects, and manually generate morning and evening briefs.

Records can be exported to Obsidian, and an MCP interface lets other AI tools query them.

Local speech model integration code is included, but requires additional dependencies and model downloads. Without a configured model for extracting information, the demo uses local rules. Wearable device integration, scheduled processing, and reminders still need work; the project does not yet offer a complete everyday companion experience.

## Run locally

Requires Python 3.10 or later.

```bash
git clone https://github.com/zhaimingyou/EchoMind.git
cd EchoMind

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000> and use the demo-data button in the top-right corner, or enter some dialogue and select “立即闭合生成卡片” to create a card. The current web interface is in Chinese. Demo data is saved locally.

## Learn more

- [Development and integration](docs/development.en.md): speech models, configuration, MCP, and tests.
- [Product notes](specs/spec.md) and [design documents](specs/design.md) (Chinese): the project's design and plans, some of which are not yet implemented.
- [Example plugin](plugins/example_hud_logger.py): extend record processing and message delivery.

If you're building AI glasses, a wearable recorder, or a personal memory tool, we'd be glad to hear about your integration needs and what you run into in practice.

## License

[MIT](LICENSE). Model weights are not included in the repository and are subject to their respective licenses.
