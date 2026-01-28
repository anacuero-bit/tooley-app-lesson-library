# Tooley — AI Lesson Plans for Teachers

A Telegram bot that generates customized lesson plans for teachers in low-resource educational settings around the world.

**Named after James Tooley**, the researcher who documented the phenomenon of low-cost private schools serving millions of children in developing countries.

## Features

- **Multiple Input Methods:**
  - Natural language text ("Math lesson about fractions for 8-10 year olds")
  - Voice messages (transcribed via Whisper)
  - Guided step-by-step flow with buttons

- **Customization Options:**
  - Subject (Math, Reading, Science, Social Studies, Arts, Language)
  - Specific topic (free text)
  - Student age range
  - Class duration
  - Country/region (for localized examples)
  - Available materials (none, basic, standard)
  - Teaching style (interactive, structured, story-based)

- **Output Formats:**
  - Quick (chat message) - ~200 words, key points
  - Standard (PDF) - ~500 words, complete lesson plan
  - Full (PDF) - ~800 words, includes quiz and extensions

- **Lesson Repository:**
  - Share lessons with teachers worldwide
  - Browse lessons by subject, country, age
  - Community-built library grows automatically
  - Every shared lesson tagged and searchable

- **Tweak Feature:**
  - Refine generated lessons with natural language feedback
  - "Make it more interactive"
  - "Add more examples"
  - "Simplify the language"

## Tech Stack

- **Python 3.11+**
- **python-telegram-bot** - Telegram interface
- **anthropic** - Claude API for lesson generation
- **groq** - Whisper voice transcription
- **fpdf2** - PDF generation
- **GitHub API** - Lesson repository storage

## Setup

### 1. Create Telegram Bot

1. Message @BotFather on Telegram
2. Send `/newbot`
3. Choose a name (e.g., "Tooley")
4. Choose a username (e.g., "TooleyAppBot")
5. Copy the token

### 2. Get API Keys

- **Anthropic (Claude):** https://console.anthropic.com/
- **Groq (Whisper):** https://console.groq.com/ (free tier available)
- **GitHub Token:** https://github.com/settings/tokens (for lesson repository)

### 3. Create GitHub Repository for Lessons

1. Create a new repository (e.g., `tooley-app/lesson-library`)
2. Make it public (so lessons are accessible)
3. Generate a Personal Access Token with `repo` scope

### 4. Environment Variables

```
TELEGRAM_TOKEN=your_telegram_bot_token
CLAUDE_API_KEY=your_anthropic_api_key
GROQ_API_KEY=your_groq_api_key (optional, for voice)
GITHUB_TOKEN=your_github_token (for lesson repository)
GITHUB_REPO=tooley-app/lesson-library
```

### 5. Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export TELEGRAM_TOKEN="..."
export CLAUDE_API_KEY="..."
export GROQ_API_KEY="..."
export GITHUB_TOKEN="..."
export GITHUB_REPO="..."

# Run
python bot.py
```

### 6. Deploy to Railway

1. Create account at https://railway.app
2. New Project → Deploy from GitHub
3. Connect your repository
4. Add environment variables in Railway dashboard
5. Deploy

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and instructions |
| `/help` | Detailed usage guide |
| `/new` | Start guided lesson creation |
| `/quick` | Fast mode - just topic and ages |
| `/browse` | Browse lessons from other teachers |

## User Flows

### Create & Share Flow
```
User: /new
Bot: [Guided flow through parameters]
Bot: [Generates lesson plan]
Bot: "Share with other teachers?"
     [🌍 Share] [🔒 Keep private]
User: [🌍 Share]
Bot: "What name to display?"
User: "Maria"
Bot: "✅ Shared! Teachers worldwide can now use your lesson."
```

### Browse Flow
```
User: /browse
Bot: "📚 Lesson Library
     247 lessons from teachers worldwide
     
     Recent:
     1. 🇰🇪 Basic Fractions - Math | Ages 8-10
     2. 🇮🇳 Water Cycle - Science | Ages 9-11
     ..."
     [📄 Get: Basic Fractions]
     [📄 Get: Water Cycle]
     [🔍 Search by subject]
```

## Repository Data Model

```json
{
  "id": "les_abc123",
  "created": "2026-01-28T15:30:00Z",
  "teacher_name": "Maria",
  "country": "Kenya",
  "subject": "Mathematics",
  "topic": "Basic Fractions",
  "ages": "8-10",
  "duration": 45,
  "materials": "basic",
  "style": "interactive",
  "content": "...",
  "public": true,
  "views": 47,
  "downloads": 12
}
```

## Website Integration

The `lessons.json` file in the GitHub repository can be fetched by the website to show:
- Live carousel: "Maria in Kenya just created: Basic Fractions"
- Browse page with filters
- Statistics (total lessons, by country, by subject)

Fetch endpoint:
```
https://raw.githubusercontent.com/{GITHUB_REPO}/main/lessons.json
```

## The Story

In the slums of Hyderabad, Lagos, and Nairobi, James Tooley discovered something remarkable: poor parents were paying for private schools out of their own pockets, even when free government schools existed nearby. Why? Because these small, scrappy, community-run schools actually taught their children.

These teachers—often without formal degrees, working with chalk and determination—were delivering results that put well-funded government schools to shame.

**Tooley.app** is built for them. Free AI-powered lesson plans, available via a simple Telegram bot, designed for classrooms with nothing but a teacher and students ready to learn.

---

Built with ❤️ for teachers everywhere.

**tooley.app**
