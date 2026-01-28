"""
Tooley - Lesson Plan Generator Bot
Telegram bot that generates customized lesson plans for teachers in low-resource settings.

Stack:
- python-telegram-bot for Telegram interface
- anthropic for Claude API (lesson generation)
- groq for Whisper voice transcription
- fpdf2 for PDF generation
- GitHub API for lesson repository storage
"""

import os
import logging
import json
import hashlib
import base64
from datetime import datetime
from io import BytesIO
import httpx

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from anthropic import Anthropic
from groq import Groq
from fpdf import FPDF

# ============================================================================
# CONFIGURATION
# ============================================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# GitHub Repository Storage
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "tooley/lesson-library")
LESSONS_FILE = "lessons.json"

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize API clients
anthropic_client = Anthropic(api_key=CLAUDE_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ============================================================================
# SYSTEM PROMPT - THE HEART OF THE BOT
# ============================================================================

LESSON_SYSTEM_PROMPT = """You are an expert curriculum designer specializing in creating lesson plans for teachers in low-resource educational settings around the world.

CONTEXT:
You're creating lessons for teachers who work in informal schools, low-cost private schools, and community learning centers—often in India, Kenya, Nigeria, Ghana, Philippines, and similar contexts. These teachers:
- May not have formal teaching degrees
- Work with limited or no materials (no projectors, sometimes no electricity)
- Have large class sizes (25-40+ students)
- Are resourceful and dedicated
- Need practical, immediately usable content

PEDAGOGICAL PRINCIPLES (embed these naturally, don't lecture about them):
- Start with what students already know (connect to daily life)
- Active learning over passive listening
- Check understanding frequently
- Use local, familiar examples (food, games, markets, family)
- Activities that work with zero materials or everyday items (stones, leaves, recycled paper)
- Clear, simple language
- Realistic timing

LOCALIZATION:
When a country/region is specified, use culturally relevant examples:
- India: rupees, chapati, cricket, local festivals
- Kenya: shillings, ugali, football, local context
- Nigeria: naira, local foods, local references
- Universal: use generic examples that work anywhere

OUTPUT STRUCTURE:
Generate lesson plans with clear sections. Be concise but complete. Every activity must be doable with minimal resources.

TONE:
Warm, practical, encouraging. You're a helpful colleague, not a textbook. Use "you" and "your students" naturally.

IMPORTANT:
- Never suggest materials the teacher won't have (no smartboards, printed worksheets, colored markers)
- Always include at least one activity that needs ZERO materials
- Time estimates must be realistic
- Include what to say/ask, not just what to do
- Add 1-2 "teacher tips" for common challenges"""

# ============================================================================
# PROMPT TEMPLATES
# ============================================================================

def build_lesson_prompt(params: dict) -> str:
    """Build the user prompt based on collected parameters."""
    
    prompt_parts = []
    
    # Core request
    prompt_parts.append(f"Create a lesson plan for: {params.get('topic', 'general topic')}")
    
    # Subject
    if params.get('subject'):
        prompt_parts.append(f"Subject: {params['subject']}")
    
    # Age/Grade
    if params.get('ages'):
        prompt_parts.append(f"Student ages: {params['ages']}")
    
    # Duration
    if params.get('duration'):
        prompt_parts.append(f"Class duration: {params['duration']} minutes")
    
    # Class size
    if params.get('class_size'):
        prompt_parts.append(f"Class size: approximately {params['class_size']} students")
    
    # Country/Region
    if params.get('country'):
        prompt_parts.append(f"Location context: {params['country']} (use locally relevant examples)")
    
    # Available materials
    materials = params.get('materials', 'minimal')
    if materials == 'none':
        prompt_parts.append("Available materials: NONE - design activities using only voice, movement, and imagination")
    elif materials == 'basic':
        prompt_parts.append("Available materials: Basic only - chalk/board, recycled paper, everyday items (stones, sticks, leaves)")
    elif materials == 'standard':
        prompt_parts.append("Available materials: Standard classroom - chalk/board, paper, pencils, basic supplies")
    
    # Teaching style preference
    style = params.get('style')
    if style == 'interactive':
        prompt_parts.append("Teaching style: Highly interactive - lots of student participation, movement, games")
    elif style == 'structured':
        prompt_parts.append("Teaching style: Structured - clear steps, organized progression, some interaction")
    elif style == 'storytelling':
        prompt_parts.append("Teaching style: Story-based - use narratives, characters, scenarios to teach concepts")
    
    # Output depth
    depth = params.get('depth', 'standard')
    if depth == 'quick':
        prompt_parts.append("""
OUTPUT FORMAT - QUICK PLAN:
Keep it brief (~200 words). Include:
- Learning objective (1 sentence)
- 3-4 key points (bullets)
- 1 main activity (with what to say)
- 1 check-for-understanding question
- 1 teacher tip""")
    elif depth == 'standard':
        prompt_parts.append("""
OUTPUT FORMAT - STANDARD LESSON PLAN:
Complete but concise (~500 words). Include:
- Learning objective
- Materials needed (keep minimal)
- Opening hook (2-3 min) - a question or quick activity to engage
- Main lesson (step-by-step with timing)
- Practice activity (hands-on, minimal materials)
- Closing check (2-3 quick questions)
- Teacher tips (common mistakes, what to watch for)""")
    elif depth == 'full':
        prompt_parts.append("""
OUTPUT FORMAT - FULL LESSON KIT:
Comprehensive (~800 words). Include everything in Standard, PLUS:
- Differentiation: How to help struggling students / challenge advanced ones
- Assessment: 3-5 simple quiz questions with answers
- Extension: Optional homework or follow-up activity
- Connection: How this links to previous/next lessons""")
    
    # Special requests
    if params.get('special_requests'):
        prompt_parts.append(f"Special requests: {params['special_requests']}")
    
    return "\n".join(prompt_parts)


# ============================================================================
# LESSON GENERATION
# ============================================================================

def generate_lesson(params: dict) -> str:
    """Generate a lesson plan using Claude."""
    
    user_prompt = build_lesson_prompt(params)
    
    logger.info(f"Generating lesson with params: {params}")
    
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=LESSON_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )
    
    return response.content[0].text


# ============================================================================
# PDF GENERATION
# ============================================================================

class LessonPDF(FPDF):
    """Custom PDF class for lesson plans."""
    
    def __init__(self):
        super().__init__()
        self.add_page()
        # Use built-in fonts that support basic characters
        self.set_auto_page_break(auto=True, margin=15)
    
    def header(self):
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(30, 123, 70)  # Green
        self.cell(0, 10, 'Tooley - Lesson Plan', align='C')
        self.ln(15)
    
    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, 'tooley.app | Free lesson plans for teachers everywhere', align='C')
    
    def add_lesson_content(self, content: str, params: dict):
        """Add the lesson content to PDF."""
        
        # Title section
        self.set_font('Helvetica', 'B', 14)
        self.set_text_color(26, 26, 46)
        
        topic = params.get('topic', 'Lesson Plan')
        subject = params.get('subject', '')
        title = f"{subject}: {topic}" if subject else topic
        # Use multi_cell for title to handle long titles
        self.multi_cell(0, 10, self._safe_text(title[:80]))  # Truncate if too long
        
        # Metadata line
        self.set_font('Helvetica', '', 10)
        self.set_text_color(100, 100, 100)
        meta_parts = []
        if params.get('ages'):
            meta_parts.append(f"Ages {params['ages']}")
        if params.get('duration'):
            meta_parts.append(f"{params['duration']} min")
        if params.get('country'):
            meta_parts.append(params['country'])
        if meta_parts:
            self.multi_cell(0, 6, " | ".join(meta_parts))
        
        self.ln(5)
        
        # Main content
        self.set_font('Helvetica', '', 11)
        self.set_text_color(26, 26, 46)
        
        # Process content line by line for basic formatting
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                self.ln(3)
                continue
            
            # Sanitize line first
            safe_line = self._safe_text(line)
            
            # Detect headers (lines in ALL CAPS or ending with :)
            if line.isupper() or (line.endswith(':') and len(line) < 50):
                self.ln(3)
                self.set_font('Helvetica', 'B', 11)
                self.set_text_color(30, 123, 70)
                self.multi_cell(0, 6, safe_line)
                self.set_font('Helvetica', '', 11)
                self.set_text_color(26, 26, 46)
            # Bullet points - use text indent instead of cell
            elif line.startswith('- ') or line.startswith('• ') or line.startswith('* '):
                bullet_text = '  - ' + self._safe_text(line[2:])
                self.multi_cell(0, 6, bullet_text)
            # Numbered items
            elif len(line) > 2 and line[0].isdigit() and line[1] in '.):':
                self.multi_cell(0, 6, safe_line)
            # Regular text
            else:
                self.multi_cell(0, 6, safe_line)
    
    def _safe_text(self, text: str) -> str:
        """Convert text to safe ASCII for PDF."""
        # Replace common unicode characters
        replacements = {
            '→': '->',
            '←': '<-',
            '•': '-',
            '–': '-',
            '—': '-',
            '"': '"',
            '"': '"',
            ''': "'",
            ''': "'",
            '…': '...',
            '✓': '[x]',
            '✗': '[ ]',
            '★': '*',
            '📚': '[Book]',
            '📝': '[Note]',
            '🎯': '[Target]',
            '💡': '[Tip]',
            '⏱': '[Time]',
            '👥': '[Group]',
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        # Remove any remaining non-ASCII
        return text.encode('ascii', 'replace').decode('ascii')


def create_lesson_pdf(content: str, params: dict) -> BytesIO:
    """Create a PDF from lesson content."""
    
    pdf = LessonPDF()
    pdf.add_lesson_content(content, params)
    
    # Output to BytesIO
    pdf_buffer = BytesIO()
    pdf_output = pdf.output()
    pdf_buffer.write(pdf_output)
    pdf_buffer.seek(0)
    
    return pdf_buffer


# ============================================================================
# LESSON REPOSITORY
# ============================================================================

def generate_lesson_id() -> str:
    """Generate a unique lesson ID."""
    timestamp = datetime.utcnow().isoformat()
    random_part = hashlib.md5(timestamp.encode()).hexdigest()[:8]
    return f"les_{random_part}"


async def get_lessons_from_github() -> list:
    """Fetch current lessons from GitHub repository."""
    if not GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN not set, repository disabled")
        return []
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/contents/{LESSONS_FILE}",
                headers={
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            
            if response.status_code == 404:
                # File doesn't exist yet
                return []
            
            response.raise_for_status()
            data = response.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            return json.loads(content)
    
    except Exception as e:
        logger.error(f"Error fetching lessons: {e}")
        return []


async def save_lesson_to_github(lesson: dict) -> bool:
    """Save a new lesson to the GitHub repository."""
    if not GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN not set, cannot save lesson")
        return False
    
    try:
        async with httpx.AsyncClient() as client:
            # Get current file (for SHA)
            get_response = await client.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/contents/{LESSONS_FILE}",
                headers={
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            
            # Load existing lessons or start fresh
            if get_response.status_code == 200:
                file_data = get_response.json()
                sha = file_data["sha"]
                existing_content = base64.b64decode(file_data["content"]).decode("utf-8")
                lessons = json.loads(existing_content)
            else:
                sha = None
                lessons = []
            
            # Add new lesson at the beginning (newest first)
            lessons.insert(0, lesson)
            
            # Keep only last 1000 lessons to prevent file bloat
            lessons = lessons[:1000]
            
            # Encode new content
            new_content = json.dumps(lessons, indent=2, ensure_ascii=False)
            encoded_content = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
            
            # Prepare request body
            body = {
                "message": f"Add lesson: {lesson.get('topic', 'Untitled')} ({lesson.get('country', 'Global')})",
                "content": encoded_content,
            }
            if sha:
                body["sha"] = sha
            
            # Push to GitHub
            put_response = await client.put(
                f"https://api.github.com/repos/{GITHUB_REPO}/contents/{LESSONS_FILE}",
                headers={
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json"
                },
                json=body
            )
            
            put_response.raise_for_status()
            logger.info(f"Saved lesson {lesson['id']} to repository")
            return True
    
    except Exception as e:
        logger.error(f"Error saving lesson: {e}")
        return False


def create_lesson_record(params: dict, content: str, teacher_name: str = None, public: bool = True) -> dict:
    """Create a lesson record for the repository."""
    return {
        "id": generate_lesson_id(),
        "created": datetime.utcnow().isoformat() + "Z",
        "teacher_name": teacher_name or "Anonymous",
        "country": params.get("country", "Global"),
        "subject": params.get("subject", "General"),
        "topic": params.get("topic", "Untitled"),
        "ages": params.get("ages", "All ages"),
        "duration": params.get("duration", 45),
        "materials": params.get("materials", "basic"),
        "style": params.get("style", "mixed"),
        "depth": params.get("depth", "standard"),
        "content": content,
        "public": public,
        "views": 0,
        "downloads": 0
    }


async def search_lessons(
    subject: str = None,
    ages: str = None,
    country: str = None,
    limit: int = 10
) -> list:
    """Search lessons in the repository."""
    lessons = await get_lessons_from_github()
    
    # Filter to public only
    results = [l for l in lessons if l.get("public", True)]
    
    # Apply filters
    if subject:
        results = [l for l in results if l.get("subject", "").lower() == subject.lower()]
    if ages:
        results = [l for l in results if l.get("ages") == ages]
    if country:
        results = [l for l in results if l.get("country", "").lower() == country.lower()]
    
    return results[:limit]


async def get_recent_lessons(limit: int = 5) -> list:
    """Get most recent public lessons."""
    lessons = await get_lessons_from_github()
    public_lessons = [l for l in lessons if l.get("public", True)]
    return public_lessons[:limit]


async def get_lesson_stats() -> dict:
    """Get repository statistics."""
    lessons = await get_lessons_from_github()
    public_lessons = [l for l in lessons if l.get("public", True)]
    
    # Count by country
    countries = {}
    for l in public_lessons:
        country = l.get("country", "Global")
        countries[country] = countries.get(country, 0) + 1
    
    # Count by subject
    subjects = {}
    for l in public_lessons:
        subject = l.get("subject", "General")
        subjects[subject] = subjects.get(subject, 0) + 1
    
    return {
        "total": len(public_lessons),
        "countries": countries,
        "subjects": subjects
    }


# ============================================================================
# VOICE TRANSCRIPTION
# ============================================================================

async def transcribe_voice(voice_file: BytesIO) -> str:
    """Transcribe voice message using Groq Whisper."""
    
    if not groq_client:
        return None
    
    try:
        transcription = groq_client.audio.transcriptions.create(
            file=("voice.ogg", voice_file),
            model="whisper-large-v3",
            language="en"
        )
        return transcription.text
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return None


# ============================================================================
# TELEGRAM HANDLERS
# ============================================================================

# Store user session data
user_sessions = {}

def get_session(user_id: int) -> dict:
    """Get or create user session."""
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            'params': {},
            'state': 'idle',
            'last_lesson': None,
            'pending_share': False
        }
    return user_sessions[user_id]


def get_country_flag(country: str) -> str:
    """Get emoji flag for country."""
    flags = {
        'India': '🇮🇳',
        'Kenya': '🇰🇪',
        'Nigeria': '🇳🇬',
        'Ghana': '🇬🇭',
        'Philippines': '🇵🇭',
        'South Africa': '🇿🇦',
        'Tanzania': '🇹🇿',
        'Uganda': '🇺🇬',
        'Pakistan': '🇵🇰',
        'Bangladesh': '🇧🇩',
    }
    return flags.get(country, '🌍')


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    
    # Get stats for social proof
    stats = await get_lesson_stats()
    stats_text = ""
    if stats['total'] > 0:
        stats_text = f"\n📊 *{stats['total']} lessons* shared by teachers worldwide\n"
    
    welcome_text = f"""📚 *Welcome to Tooley!*

Free AI-powered lesson plans for teachers everywhere.
{stats_text}
*How to create a lesson:*

📝 *Type* your request:
"Math lesson about fractions for 8-10 year olds"

🎤 *Send a voice message* describing what you need

🔘 *Use guided mode* with /new

*Commands:*
/new - Start guided lesson creation
/quick - Fast lesson (just topic + age)
/browse - Browse lessons from other teachers
/help - Tips and examples

_Part of the global movement supporting teachers in low-resource schools._
"""
    
    keyboard = [
        [
            InlineKeyboardButton("🆕 Create lesson", callback_data="action_new"),
            InlineKeyboardButton("📚 Browse lessons", callback_data="action_browse"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text, 
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    
    help_text = """📚 *Tooley - Help*

*Creating Lessons:*

1️⃣ *Quick way* - Just type or say:
"Science lesson about plants for 6-8 year olds in Kenya"
"45-minute math class on multiplication, ages 10-12"

2️⃣ *Guided way* - Use /new
Bot will ask you step-by-step:
- Subject & Topic
- Student ages
- Class duration
- Your country (for local examples)
- Available materials
- Teaching style

*Output Options:*
📋 Quick - Key points in chat (~200 words)
📄 Standard - Full lesson plan as PDF
📚 Complete - PDF with quiz & extensions

*Tips:*
• Be specific about the topic
• Mention your country for relevant examples
• Specify if you have NO materials
• You can always tweak after generating

*Examples:*
• "Reading comprehension for beginners, no materials"
• "Interactive geometry lesson, 40 students, India"
• "Story-based history lesson about local heroes"
"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /new command - start guided lesson creation."""
    
    user_id = update.effective_user.id
    session = get_session(user_id)
    session['params'] = {}
    session['state'] = 'awaiting_subject'
    
    keyboard = [
        [
            InlineKeyboardButton("📐 Math", callback_data="subject_Mathematics"),
            InlineKeyboardButton("📖 Reading", callback_data="subject_Reading"),
        ],
        [
            InlineKeyboardButton("🔬 Science", callback_data="subject_Science"),
            InlineKeyboardButton("🌍 Social Studies", callback_data="subject_Social Studies"),
        ],
        [
            InlineKeyboardButton("🎨 Arts", callback_data="subject_Arts"),
            InlineKeyboardButton("📝 Language", callback_data="subject_Language"),
        ],
        [
            InlineKeyboardButton("Other...", callback_data="subject_other"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "📚 *Let's create a lesson plan!*\n\nWhat subject?"
    
    # Check if this came from a callback (button press) or direct command
    if update.callback_query:
        # From button press - edit the existing message
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    elif update.message:
        # From /new command - send new message
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )


async def quick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /quick command - minimal input lesson."""
    
    user_id = update.effective_user.id
    session = get_session(user_id)
    session['params'] = {'depth': 'quick'}
    session['state'] = 'awaiting_quick_input'
    
    await update.message.reply_text(
        "⚡ *Quick Lesson*\n\n"
        "Tell me the topic and student ages in one message.\n\n"
        "_Example: Fractions for 8-10 year olds_",
        parse_mode='Markdown'
    )


async def browse_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /browse command - browse lesson library."""
    
    await update.message.reply_text("📚 Loading lesson library...")
    
    recent = await get_recent_lessons(5)
    stats = await get_lesson_stats()
    
    if not recent:
        keyboard = [[InlineKeyboardButton("🆕 Create first lesson", callback_data="action_new")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📚 *Lesson Library*\n\n"
            "No lessons shared yet. Be the first!\n\n"
            "Create a lesson and share it with teachers worldwide.",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return
    
    text = f"📚 *Lesson Library*\n"
    text += f"_{stats['total']} lessons from teachers worldwide_\n\n"
    text += "*Recent lessons:*\n\n"
    
    for i, lesson in enumerate(recent, 1):
        flag = get_country_flag(lesson.get('country', ''))
        text += f"{i}. {flag} *{lesson['topic']}*\n"
        text += f"   {lesson['subject']} | Ages {lesson['ages']} | {lesson['country']}\n"
        text += f"   _by {lesson.get('teacher_name', 'Anonymous')}_\n\n"
    
    keyboard = []
    for lesson in recent:
        keyboard.append([InlineKeyboardButton(
            f"📄 Get: {lesson['topic'][:25]}",
            callback_data=f"get_lesson_{lesson['id']}"
        )])
    
    keyboard.append([
        InlineKeyboardButton("🔍 Search by subject", callback_data="browse_by_subject"),
    ])
    keyboard.append([
        InlineKeyboardButton("🆕 Create new lesson", callback_data="action_new"),
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
    
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    session = get_session(user_id)
    data = query.data
    
    # Subject selection
    if data.startswith("subject_"):
        subject = data.replace("subject_", "")
        if subject == "other":
            session['state'] = 'awaiting_subject_text'
            await query.edit_message_text("Type the subject:")
            return
        
        session['params']['subject'] = subject
        session['state'] = 'awaiting_topic'
        
        # Offer popular topic suggestions based on subject
        topic_suggestions = {
            "Mathematics": [
                ("Addition/Subtraction", "topic_Addition and Subtraction"),
                ("Multiplication", "topic_Multiplication"),
                ("Fractions", "topic_Fractions"),
                ("Shapes & Geometry", "topic_Shapes and Geometry"),
            ],
            "Reading": [
                ("Reading Comprehension", "topic_Reading Comprehension"),
                ("Phonics", "topic_Phonics and Letter Sounds"),
                ("Storytelling", "topic_Storytelling"),
                ("Vocabulary", "topic_Building Vocabulary"),
            ],
            "Science": [
                ("Plants & Animals", "topic_Plants and Animals"),
                ("Human Body", "topic_The Human Body"),
                ("Water Cycle", "topic_Water Cycle"),
                ("Simple Machines", "topic_Simple Machines"),
            ],
            "Social Studies": [
                ("Community Helpers", "topic_Community Helpers"),
                ("Maps & Directions", "topic_Maps and Directions"),
                ("Family & Culture", "topic_Family and Culture"),
                ("Environment", "topic_Caring for Environment"),
            ],
            "Arts": [
                ("Drawing", "topic_Drawing and Sketching"),
                ("Music & Rhythm", "topic_Music and Rhythm"),
                ("Drama/Role Play", "topic_Drama and Role Play"),
                ("Crafts", "topic_Simple Crafts"),
            ],
            "Language": [
                ("Sentence Building", "topic_Building Sentences"),
                ("Speaking Practice", "topic_Speaking Practice"),
                ("Writing Stories", "topic_Writing Short Stories"),
                ("Grammar Basics", "topic_Basic Grammar"),
            ],
        }
        
        suggestions = topic_suggestions.get(subject, [
            ("Custom topic", "topic_custom"),
        ])
        
        keyboard = []
        for label, callback in suggestions:
            keyboard.append([InlineKeyboardButton(label, callback_data=callback)])
        keyboard.append([InlineKeyboardButton("✏️ Type my own topic...", callback_data="topic_custom")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"📚 Subject: *{subject}*\n\nPick a topic or type your own:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Topic selection
    if data.startswith("topic_"):
        topic = data.replace("topic_", "")
        if topic == "custom":
            session['state'] = 'awaiting_topic'
            await query.edit_message_text(
                f"📚 Subject: *{session['params'].get('subject', 'General')}*\n\n✏️ Type your topic:"
            , parse_mode='Markdown')
            return
        
        session['params']['topic'] = topic
        session['state'] = 'awaiting_ages'
        
        keyboard = [
            [
                InlineKeyboardButton("5-7 years", callback_data="ages_5-7"),
                InlineKeyboardButton("7-9 years", callback_data="ages_7-9"),
            ],
            [
                InlineKeyboardButton("9-11 years", callback_data="ages_9-11"),
                InlineKeyboardButton("11-13 years", callback_data="ages_11-13"),
            ],
            [
                InlineKeyboardButton("13-15 years", callback_data="ages_13-15"),
                InlineKeyboardButton("15+ years", callback_data="ages_15-18"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📚 *{session['params'].get('subject')}*: {topic}\n\nWhat age are your students?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Age selection
    if data.startswith("ages_"):
        ages = data.replace("ages_", "").replace("-", "-")
        session['params']['ages'] = ages
        session['state'] = 'awaiting_duration'
        
        keyboard = [
            [
                InlineKeyboardButton("30 min", callback_data="duration_30"),
                InlineKeyboardButton("45 min", callback_data="duration_45"),
            ],
            [
                InlineKeyboardButton("60 min", callback_data="duration_60"),
                InlineKeyboardButton("90 min", callback_data="duration_90"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"👥 Ages: *{ages}*\n\nHow long is your class?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Duration selection
    if data.startswith("duration_"):
        duration = data.replace("duration_", "")
        session['params']['duration'] = duration
        session['state'] = 'awaiting_country'
        
        keyboard = [
            [
                InlineKeyboardButton("🇮🇳 India", callback_data="country_India"),
                InlineKeyboardButton("🇰🇪 Kenya", callback_data="country_Kenya"),
            ],
            [
                InlineKeyboardButton("🇳🇬 Nigeria", callback_data="country_Nigeria"),
                InlineKeyboardButton("🇬🇭 Ghana", callback_data="country_Ghana"),
            ],
            [
                InlineKeyboardButton("🇵🇭 Philippines", callback_data="country_Philippines"),
                InlineKeyboardButton("🌍 Other", callback_data="country_other"),
            ],
            [
                InlineKeyboardButton("Skip (universal)", callback_data="country_skip"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"⏱ Duration: *{duration} minutes*\n\n"
            "What country? (helps with local examples)",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Country selection
    if data.startswith("country_"):
        country = data.replace("country_", "")
        if country == "other":
            session['state'] = 'awaiting_country_text'
            await query.edit_message_text("Type your country:")
            return
        if country != "skip":
            session['params']['country'] = country
        
        session['state'] = 'awaiting_materials'
        
        keyboard = [
            [InlineKeyboardButton("None - voice & movement only", callback_data="materials_none")],
            [InlineKeyboardButton("Basic - chalk, recycled paper, everyday items", callback_data="materials_basic")],
            [InlineKeyboardButton("Standard - paper, pencils, board", callback_data="materials_standard")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        location = session['params'].get('country', 'Universal')
        await query.edit_message_text(
            f"📍 Location: *{location}*\n\nWhat materials do you have?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Materials selection
    if data.startswith("materials_"):
        materials = data.replace("materials_", "")
        session['params']['materials'] = materials
        session['state'] = 'awaiting_style'
        
        keyboard = [
            [InlineKeyboardButton("🎮 Interactive - games, movement, participation", callback_data="style_interactive")],
            [InlineKeyboardButton("📋 Structured - clear steps, organized", callback_data="style_structured")],
            [InlineKeyboardButton("📖 Story-based - narratives, characters", callback_data="style_storytelling")],
            [InlineKeyboardButton("🔀 Mix / No preference", callback_data="style_mixed")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎨 What teaching style works best for you?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Style selection
    if data.startswith("style_"):
        style = data.replace("style_", "")
        if style != "mixed":
            session['params']['style'] = style
        
        session['state'] = 'awaiting_depth'
        
        keyboard = [
            [InlineKeyboardButton("📋 Quick - key points only", callback_data="depth_quick")],
            [InlineKeyboardButton("📄 Standard - complete lesson plan", callback_data="depth_standard")],
            [InlineKeyboardButton("📚 Full - lesson + quiz + extras", callback_data="depth_full")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📊 How detailed should the lesson plan be?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Depth selection - GENERATE!
    if data.startswith("depth_"):
        depth = data.replace("depth_", "")
        session['params']['depth'] = depth
        
        await query.edit_message_text("⏳ *Generating your lesson plan...*", parse_mode='Markdown')
        
        try:
            lesson_content = generate_lesson(session['params'])
            session['last_lesson'] = lesson_content
            session['state'] = 'lesson_generated'
            
            # For quick depth, send as message
            if depth == 'quick':
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=lesson_content
                )
            else:
                # Send as PDF
                pdf_buffer = create_lesson_pdf(lesson_content, session['params'])
                topic = session['params'].get('topic', 'lesson')
                filename = f"{topic.lower().replace(' ', '-')[:30]}.pdf"
                
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=pdf_buffer,
                    filename=filename,
                    caption="📄 Your lesson plan is ready!"
                )
                
                # Also send text version
                if len(lesson_content) < 4000:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=lesson_content
                    )
            
            # Follow-up options - ask about sharing
            keyboard = [
                [
                    InlineKeyboardButton("🌍 Share with teachers", callback_data="share_yes"),
                    InlineKeyboardButton("🔒 Keep private", callback_data="share_no"),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Would you like to share this lesson with other teachers around the world?",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Generation error: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Sorry, something went wrong. Please try again."
            )
        return
    
    # Share decision
    if data == "share_yes":
        session['pending_share'] = True
        session['state'] = 'awaiting_teacher_name'
        await query.edit_message_text(
            "🌍 *Thank you for sharing!*\n\n"
            "What name should we display? (or type 'skip' to stay anonymous)",
            parse_mode='Markdown'
        )
        return
    
    if data == "share_no":
        # Save as private
        if session.get('last_lesson'):
            lesson_record = create_lesson_record(
                session['params'],
                session['last_lesson'],
                teacher_name="Anonymous",
                public=False
            )
            await save_lesson_to_github(lesson_record)
        
        # Show regular follow-up
        keyboard = [
            [
                InlineKeyboardButton("✏️ Tweak this", callback_data="action_tweak"),
                InlineKeyboardButton("🔄 Try different topic", callback_data="action_new_topic"),
            ],
            [
                InlineKeyboardButton("📚 Browse lessons", callback_data="action_browse"),
                InlineKeyboardButton("🆕 New lesson", callback_data="action_new"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("What next?", reply_markup=reply_markup)
        return
    
    # Browse lessons
    if data == "action_browse":
        await query.edit_message_text("📚 Loading lesson library...")
        
        recent = await get_recent_lessons(5)
        stats = await get_lesson_stats()
        
        if not recent:
            await query.edit_message_text(
                "📚 *Lesson Library*\n\n"
                "No lessons shared yet. Be the first!\n\n"
                "Use /new to create a lesson.",
                parse_mode='Markdown'
            )
            return
        
        text = f"📚 *Lesson Library*\n"
        text += f"_{stats['total']} lessons from teachers worldwide_\n\n"
        text += "*Recent lessons:*\n\n"
        
        for i, lesson in enumerate(recent, 1):
            flag = get_country_flag(lesson.get('country', ''))
            text += f"{i}. {flag} *{lesson['topic']}*\n"
            text += f"   {lesson['subject']} | Ages {lesson['ages']} | {lesson['country']}\n"
            text += f"   _by {lesson.get('teacher_name', 'Anonymous')}_\n\n"
        
        keyboard = []
        for i, lesson in enumerate(recent):
            keyboard.append([InlineKeyboardButton(
                f"📄 Get: {lesson['topic'][:25]}...",
                callback_data=f"get_lesson_{lesson['id']}"
            )])
        
        keyboard.append([
            InlineKeyboardButton("🔍 Search by subject", callback_data="browse_by_subject"),
        ])
        keyboard.append([
            InlineKeyboardButton("🆕 Create new lesson", callback_data="action_new"),
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    # Browse by subject
    if data == "browse_by_subject":
        keyboard = [
            [
                InlineKeyboardButton("📐 Math", callback_data="search_subject_Mathematics"),
                InlineKeyboardButton("📖 Reading", callback_data="search_subject_Reading"),
            ],
            [
                InlineKeyboardButton("🔬 Science", callback_data="search_subject_Science"),
                InlineKeyboardButton("🌍 Social Studies", callback_data="search_subject_Social Studies"),
            ],
            [
                InlineKeyboardButton("« Back", callback_data="action_browse"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🔍 *Search by subject:*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Search results
    if data.startswith("search_subject_"):
        subject = data.replace("search_subject_", "")
        results = await search_lessons(subject=subject, limit=5)
        
        if not results:
            keyboard = [[InlineKeyboardButton("« Back", callback_data="action_browse")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"No {subject} lessons found yet.\n\nBe the first to create one!",
                reply_markup=reply_markup
            )
            return
        
        text = f"📐 *{subject} Lessons*\n\n"
        for i, lesson in enumerate(results, 1):
            flag = get_country_flag(lesson.get('country', ''))
            text += f"{i}. {flag} *{lesson['topic']}*\n"
            text += f"   Ages {lesson['ages']} | {lesson['country']}\n\n"
        
        keyboard = []
        for lesson in results:
            keyboard.append([InlineKeyboardButton(
                f"📄 Get: {lesson['topic'][:25]}",
                callback_data=f"get_lesson_{lesson['id']}"
            )])
        keyboard.append([InlineKeyboardButton("« Back", callback_data="action_browse")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    # Get specific lesson
    if data.startswith("get_lesson_"):
        lesson_id = data.replace("get_lesson_", "")
        lessons = await get_lessons_from_github()
        lesson = next((l for l in lessons if l['id'] == lesson_id), None)
        
        if not lesson:
            await query.edit_message_text("Lesson not found.")
            return
        
        # Send the lesson content
        await query.edit_message_text(f"📄 *{lesson['topic']}*\n\n_Loading..._", parse_mode='Markdown')
        
        # Send as PDF
        session['params'] = {
            'topic': lesson['topic'],
            'subject': lesson['subject'],
            'ages': lesson['ages'],
            'country': lesson['country'],
            'duration': lesson.get('duration', 45)
        }
        
        pdf_buffer = create_lesson_pdf(lesson['content'], session['params'])
        filename = f"{lesson['topic'].lower().replace(' ', '-')[:30]}.pdf"
        
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=pdf_buffer,
            filename=filename,
            caption=f"📄 {lesson['topic']}\nCreated by {lesson.get('teacher_name', 'Anonymous')} in {lesson['country']}"
        )
        
        # Also send text if not too long
        if len(lesson['content']) < 4000:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=lesson['content']
            )
        
        keyboard = [
            [
                InlineKeyboardButton("📚 Browse more", callback_data="action_browse"),
                InlineKeyboardButton("🆕 Create new", callback_data="action_new"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="What next?",
            reply_markup=reply_markup
        )
        return

    # Action buttons
    if data == "action_tweak":
        session['state'] = 'awaiting_tweak'
        await query.edit_message_text(
            "✏️ *Tweak Mode*\n\n"
            "Tell me what to change:\n"
            "• _Make it more interactive_\n"
            "• _Add more examples_\n"
            "• _Simplify the language_\n"
            "• _Remove the quiz_",
            parse_mode='Markdown'
        )
        return
    
    if data == "action_new_topic":
        session['state'] = 'awaiting_topic'
        # Keep other params, just ask for new topic
        await query.edit_message_text(
            "📝 What topic would you like instead?"
        )
        return
    
    if data == "action_new":
        session['params'] = {}
        session['state'] = 'idle'
        # Trigger /new flow
        await new_command(update, context)
        return


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages based on conversation state."""
    
    user_id = update.effective_user.id
    session = get_session(user_id)
    text = update.message.text.strip()
    
    state = session.get('state', 'idle')
    
    # Awaiting teacher name for sharing
    if state == 'awaiting_teacher_name':
        teacher_name = "Anonymous" if text.lower() == 'skip' else text
        
        # Save lesson to repository
        if session.get('last_lesson'):
            lesson_record = create_lesson_record(
                session['params'],
                session['last_lesson'],
                teacher_name=teacher_name,
                public=True
            )
            saved = await save_lesson_to_github(lesson_record)
            
            if saved:
                country = session['params'].get('country', 'the world')
                await update.message.reply_text(
                    f"✅ *Shared with the community!*\n\n"
                    f"Teachers in {country} and beyond can now use your lesson.\n"
                    f"Thank you for contributing to education worldwide! 🌍",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    "Saved! (Note: Community sharing is being set up)"
                )
        
        session['state'] = 'idle'
        session['pending_share'] = False
        
        # Show follow-up options
        keyboard = [
            [
                InlineKeyboardButton("✏️ Tweak this", callback_data="action_tweak"),
                InlineKeyboardButton("🔄 New topic", callback_data="action_new_topic"),
            ],
            [
                InlineKeyboardButton("📚 Browse lessons", callback_data="action_browse"),
                InlineKeyboardButton("🆕 New lesson", callback_data="action_new"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("What next?", reply_markup=reply_markup)
        return
    
    # Awaiting subject text (custom subject)
    if state == 'awaiting_subject_text':
        session['params']['subject'] = text
        session['state'] = 'awaiting_topic'
        await update.message.reply_text(
            f"📚 Subject: *{text}*\n\nWhat specific topic?",
            parse_mode='Markdown'
        )
        return
    
    # Awaiting topic
    if state == 'awaiting_topic':
        session['params']['topic'] = text
        session['state'] = 'awaiting_ages'
        
        keyboard = [
            [
                InlineKeyboardButton("5-7", callback_data="ages_5-7"),
                InlineKeyboardButton("7-9", callback_data="ages_7-9"),
                InlineKeyboardButton("9-11", callback_data="ages_9-11"),
            ],
            [
                InlineKeyboardButton("11-13", callback_data="ages_11-13"),
                InlineKeyboardButton("13-15", callback_data="ages_13-15"),
                InlineKeyboardButton("15+", callback_data="ages_15+"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📝 Topic: *{text}*\n\nWhat are the student ages?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Awaiting country text
    if state == 'awaiting_country_text':
        session['params']['country'] = text
        session['state'] = 'awaiting_materials'
        
        keyboard = [
            [InlineKeyboardButton("None - voice & movement only", callback_data="materials_none")],
            [InlineKeyboardButton("Basic - chalk, recycled paper, everyday items", callback_data="materials_basic")],
            [InlineKeyboardButton("Standard - paper, pencils, board", callback_data="materials_standard")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📍 Location: *{text}*\n\nWhat materials do you have?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Awaiting quick input
    if state == 'awaiting_quick_input':
        session['params']['topic'] = text
        session['params']['depth'] = 'quick'
        
        await update.message.reply_text("⏳ *Generating quick lesson...*", parse_mode='Markdown')
        
        try:
            lesson_content = generate_lesson(session['params'])
            session['last_lesson'] = lesson_content
            session['state'] = 'lesson_generated'
            
            await update.message.reply_text(lesson_content)
            
            keyboard = [
                [
                    InlineKeyboardButton("📄 Get as PDF", callback_data="depth_standard"),
                    InlineKeyboardButton("✏️ Tweak", callback_data="action_tweak"),
                ],
                [
                    InlineKeyboardButton("📚 New lesson", callback_data="action_new"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text("What next?", reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Generation error: {e}")
            await update.message.reply_text("❌ Sorry, something went wrong. Please try again.")
        return
    
    # Awaiting tweak
    if state == 'awaiting_tweak':
        # Regenerate with tweak
        session['params']['special_requests'] = text
        
        await update.message.reply_text("⏳ *Revising lesson...*", parse_mode='Markdown')
        
        try:
            # Build tweak prompt
            tweak_prompt = f"""Here is a lesson plan I previously created:

{session['last_lesson']}

The teacher has requested these changes: {text}

Please revise the lesson plan incorporating their feedback. Keep the same general structure and format."""

            response = anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=LESSON_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": tweak_prompt}]
            )
            
            lesson_content = response.content[0].text
            session['last_lesson'] = lesson_content
            
            # Send based on original depth
            depth = session['params'].get('depth', 'standard')
            if depth == 'quick':
                await update.message.reply_text(lesson_content)
            else:
                pdf_buffer = create_lesson_pdf(lesson_content, session['params'])
                topic = session['params'].get('topic', 'lesson')
                filename = f"{topic.lower().replace(' ', '-')[:30]}-revised.pdf"
                
                await update.message.reply_document(
                    document=pdf_buffer,
                    filename=filename,
                    caption="📄 Revised lesson plan!"
                )
                
                if len(lesson_content) < 4000:
                    await update.message.reply_text(lesson_content)
            
            keyboard = [
                [
                    InlineKeyboardButton("✏️ Tweak again", callback_data="action_tweak"),
                    InlineKeyboardButton("📚 New lesson", callback_data="action_new"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text("What next?", reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Tweak error: {e}")
            await update.message.reply_text("❌ Sorry, something went wrong. Please try again.")
        return
    
    # IDLE STATE - Natural language input
    # Try to parse as a lesson request
    session['params'] = {'topic': text, 'depth': 'standard'}
    session['state'] = 'confirming_natural'
    
    keyboard = [
        [
            InlineKeyboardButton("📋 Quick (chat)", callback_data="depth_quick"),
            InlineKeyboardButton("📄 Standard (PDF)", callback_data="depth_standard"),
        ],
        [
            InlineKeyboardButton("📚 Full (PDF + quiz)", callback_data="depth_full"),
        ],
        [
            InlineKeyboardButton("🔘 Customize more...", callback_data="action_new"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📝 Creating lesson about:\n*{text}*\n\nHow detailed?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages."""
    
    if not groq_client:
        await update.message.reply_text(
            "Voice input is not configured. Please type your request instead."
        )
        return
    
    await update.message.reply_text("🎤 Transcribing...")
    
    try:
        # Download voice file
        voice_file = await update.message.voice.get_file()
        voice_bytes = BytesIO()
        await voice_file.download_to_memory(voice_bytes)
        voice_bytes.seek(0)
        
        # Transcribe
        transcript = await transcribe_voice(voice_bytes)
        
        if not transcript:
            await update.message.reply_text(
                "❌ Couldn't transcribe that. Please try again or type your request."
            )
            return
        
        # Confirm transcription
        user_id = update.effective_user.id
        session = get_session(user_id)
        session['params'] = {'topic': transcript, 'depth': 'standard'}
        session['state'] = 'confirming_voice'
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Generate this", callback_data="depth_standard"),
                InlineKeyboardButton("✏️ Edit", callback_data="action_edit_transcript"),
            ],
            [
                InlineKeyboardButton("❌ Cancel", callback_data="action_cancel"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🎤 Heard:\n\n\"{transcript}\"\n\nGenerate lesson plan?",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Voice handling error: {e}")
        await update.message.reply_text(
            "❌ Error processing voice. Please try again or type your request."
        )


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Start the bot."""
    
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN environment variable not set")
    if not CLAUDE_API_KEY:
        raise ValueError("CLAUDE_API_KEY environment variable not set")
    
    # Create application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("new", new_command))
    application.add_handler(CommandHandler("quick", quick_command))
    application.add_handler(CommandHandler("browse", browse_command))
    
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start polling
    logger.info("Starting Tooley bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
