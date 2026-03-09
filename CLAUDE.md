# CLAUDE.md

## What This Is
AI-powered Telegram bot that generates customized lesson plans for teachers in low-resource educational settings. Includes a FastAPI web API for website integration.

## Features
- Natural language, voice, and guided step-by-step lesson creation
- Multiple output formats: quick chat, PDF standard, PDF full with quiz
- Lesson repository for sharing and browsing globally
- Multi-language support (English and Spanish)
- Lesson tweaking with natural language feedback

## Stack
- Python 3.11+
- python-telegram-bot (Telegram interface)
- Anthropic Claude API (lesson generation)
- Groq Whisper (voice transcription)
- fpdf2 (PDF generation)
- FastAPI + uvicorn (web API)
- httpx
- GitHub API (lesson repository storage)

## Hosting
- Railway (worker + API)
- Procfile: `worker: python bot.py`

## Env Vars
| Variable | Required | Notes |
|----------|----------|-------|
| TELEGRAM_TOKEN | Yes | Bot token from @BotFather |
| CLAUDE_API_KEY | Yes | Anthropic API key |
| GROQ_API_KEY | Optional | Groq API key for voice transcription |
| GITHUB_TOKEN | Optional | GitHub PAT for lesson repository |
| GITHUB_REPO | Optional | Lessons repo (default: tooley/lesson-library) |
| GITHUB_WEBSITE_REPO | Optional | Website repo for lessons.json updates |
| PORT | Optional | API server port (default: 8000) |

## Key Files
| File | Purpose |
|------|---------|
| `bot.py` | Main bot entry point |
| `api.py` | FastAPI web API |
| `requirements.txt` | Python dependencies |
| `railway.toml` | Railway config |
| `Procfile` | Railway deployment |
