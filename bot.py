"""
Tooley - Lesson Plan Generator Bot
Telegram bot that generates customized lesson plans for teachers worldwide.

Version: 2.4.0
Last Updated: 2026-01-29

CHANGELOG:
---------
v2.4.0 (2026-01-29)
  - NEW: HTML format option (styled, reliable, print-friendly)
  - NEW: Format choice prompt (PDF or HTML) after generation
  - NEW: Improved welcome message with feature overview
  - NEW: Data-driven country list (top 15 by teacher population)
  - IMPROVED: PDF formatting and parsing reliability
  - IMPROVED: Lesson carousel push to website (lessons.json)

v2.3.1 (2026-01-29)
  - FIXED: Empty sections in generated lessons (Objectives, Differentiation, etc.)
  - FIXED: Redundant lesson title repeating specs box info  
  - FIXED: Numbered lists starting at 2 instead of 1
  - Stricter prompt templates with explicit section structure
  - Added "no empty sections" enforcement to system prompt

v2.3.0 (2026-01-29)
  - PDF REDESIGN: Navy primary, amber accents only, proper logo styling
  - TOPIC EXPANSION: 25+ topics per subject, 8 randomized shown each time
  - Added sub-categories for topic browsing
  - Free text always available but click-first UX preserved
  - Improved color contrast throughout PDF
  - Less saturated amber, more professional look

v2.2.0 (2026-01-29)
  - Applied Tooley brand colors to PDF (amber #f59e0b instead of green)
  - Updated ages emoji to medium-brown skin tone 🧒🏽
  - Filename prefix now starts with tooley_ (e.g., tooley_math_fractions_ages9to11_30min.pdf)
  - Fixed "Choose different topic" to loop back to topic presets (not free text)
  - Brand guide created for consistent design across all products

v2.1.0 (2026-01-29)
  - Added format choice (📱 Read in chat vs 📄 Download PDF) before generation
  - Improved PDF branding and layout
  - Structured file naming: subject_topic_ages_duration.pdf
  - Fixed lesson specs disappearing on PDF delivery
  - Fixed empty PDF bug
  - Visual selection summary shows at every step

v2.0.0 (2026-01-28)
  - Fixed PDF "Not enough horizontal space" crash
  - Removed poverty-implying language from prompts
  - Updated materials options (No materials / Basic / Full classroom)
  - Added visual summary of accumulated selections

v1.0.0 (2026-01-27)
  - Initial release
  - Basic lesson generation with subject/topic/age/duration
  - PDF and text output
  - GitHub lesson sharing

Stack:
- python-telegram-bot for Telegram interface
- anthropic for Claude API (lesson generation)
- groq for Whisper voice transcription
- fpdf2 for PDF generation
- GitHub API for lesson repository storage
"""

VERSION = "2.4.0"

import os
import logging
import json
import hashlib
import base64
import random
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
GITHUB_WEBSITE_REPO = os.environ.get("GITHUB_WEBSITE_REPO")  # For website carousel auto-push
LESSONS_FILE = "lessons.json"

# ============================================================================
# TOPIC POOLS - Comprehensive lists for each subject (v2.3.0)
# Show 8 random topics from each pool, always offer free text
# ============================================================================

TOPIC_POOLS = {
    "Mathematics": {
        "Numbers & Operations": [
            "Addition and Subtraction",
            "Multiplication Tables",
            "Division Basics",
            "Place Value",
            "Counting and Number Sense",
            "Comparing Numbers",
            "Rounding Numbers",
            "Odd and Even Numbers",
        ],
        "Fractions & Decimals": [
            "Introduction to Fractions",
            "Comparing Fractions",
            "Adding Fractions",
            "Fractions and Parts of a Whole",
            "Mixed Numbers",
            "Introduction to Decimals",
            "Percentages Basics",
        ],
        "Geometry & Measurement": [
            "Shapes and Their Properties",
            "Perimeter",
            "Area",
            "Angles and Lines",
            "Symmetry",
            "3D Shapes",
            "Measuring Length",
            "Measuring Weight and Volume",
            "Telling Time",
            "Reading Calendars",
        ],
        "Problem Solving": [
            "Word Problems",
            "Mental Math Strategies",
            "Estimation",
            "Patterns and Sequences",
            "Money and Currency",
            "Data and Graphs",
            "Probability Basics",
        ],
    },
    "Reading": {
        "Foundational Skills": [
            "Letter Recognition",
            "Phonics and Letter Sounds",
            "Blending Sounds",
            "Sight Words",
            "Syllables",
            "Word Families",
            "Decoding Strategies",
        ],
        "Comprehension": [
            "Reading Comprehension",
            "Main Idea and Details",
            "Making Predictions",
            "Cause and Effect",
            "Sequencing Events",
            "Comparing and Contrasting",
            "Drawing Conclusions",
            "Asking Questions While Reading",
        ],
        "Vocabulary & Fluency": [
            "Building Vocabulary",
            "Context Clues",
            "Synonyms and Antonyms",
            "Reading Fluently",
            "Expression in Reading",
            "Dictionary Skills",
        ],
        "Literary Elements": [
            "Characters and Setting",
            "Plot and Story Structure",
            "Fiction vs Non-Fiction",
            "Author's Purpose",
            "Point of View",
            "Genres of Literature",
        ],
    },
    "Science": {
        "Life Science": [
            "Plants and How They Grow",
            "Animal Classification",
            "Animal Habitats",
            "Life Cycles",
            "Food Chains",
            "Ecosystems",
            "The Human Body",
            "Five Senses",
            "Healthy Habits and Nutrition",
            "Insects and Their World",
        ],
        "Earth Science": [
            "Weather and Seasons",
            "The Water Cycle",
            "Rocks and Minerals",
            "Soil and Earth Layers",
            "Volcanoes and Earthquakes",
            "Oceans and Seas",
            "Climate and Environment",
            "Day and Night",
        ],
        "Space": [
            "The Solar System",
            "The Sun and Moon",
            "Stars and Constellations",
            "Phases of the Moon",
            "Planets",
        ],
        "Physical Science": [
            "States of Matter",
            "Forces and Motion",
            "Simple Machines",
            "Magnets",
            "Sound and Vibrations",
            "Light and Shadows",
            "Heat and Temperature",
            "Electricity Basics",
            "Properties of Materials",
        ],
    },
    "Social Studies": {
        "Community & Society": [
            "Community Helpers",
            "Rules and Laws",
            "Being a Good Citizen",
            "Rights and Responsibilities",
            "Local Government",
            "Jobs and Careers",
        ],
        "Geography": [
            "Maps and Globes",
            "Continents and Oceans",
            "Countries and Capitals",
            "Landforms",
            "Urban and Rural Areas",
            "Natural Resources",
            "Climate Zones",
        ],
        "History & Culture": [
            "Family and Traditions",
            "Holidays and Celebrations",
            "Cultural Diversity",
            "Historical Figures",
            "Timeline and Chronology",
            "Ancient Civilizations",
            "National History",
        ],
        "Economics": [
            "Needs vs Wants",
            "Goods and Services",
            "Money and Saving",
            "Trade and Exchange",
            "Jobs and Economy",
        ],
        "Environment": [
            "Caring for the Environment",
            "Recycling and Reduce-Reuse",
            "Conservation",
            "Pollution and Its Effects",
            "Sustainable Living",
        ],
    },
    "Arts": {
        "Visual Arts": [
            "Drawing and Sketching",
            "Painting Techniques",
            "Colors and Color Mixing",
            "Shapes in Art",
            "Patterns and Designs",
            "Collage and Mixed Media",
            "Famous Artists",
            "Art from Around the World",
        ],
        "Crafts": [
            "Paper Crafts",
            "Recycled Art",
            "Weaving and Textiles",
            "Clay and Modeling",
            "Origami",
            "Seasonal Crafts",
        ],
        "Music & Movement": [
            "Rhythm and Beat",
            "Singing Songs",
            "Musical Instruments",
            "Dance and Movement",
            "Music from Different Cultures",
            "Creating Music",
        ],
        "Drama": [
            "Role Play and Acting",
            "Puppet Shows",
            "Storytelling Performance",
            "Expressing Emotions",
            "Reader's Theater",
        ],
    },
    "Language": {
        "Grammar": [
            "Nouns and Verbs",
            "Adjectives and Adverbs",
            "Pronouns",
            "Sentence Structure",
            "Punctuation",
            "Capitalization",
            "Subject-Verb Agreement",
            "Tenses (Past, Present, Future)",
        ],
        "Writing": [
            "Writing Sentences",
            "Writing Paragraphs",
            "Narrative Writing",
            "Descriptive Writing",
            "Letter Writing",
            "Creative Writing",
            "Journal Writing",
            "Writing Process",
        ],
        "Speaking & Listening": [
            "Speaking Practice",
            "Oral Presentations",
            "Following Directions",
            "Active Listening",
            "Asking and Answering Questions",
            "Group Discussions",
        ],
        "Spelling & Handwriting": [
            "Spelling Patterns",
            "High-Frequency Words",
            "Handwriting Practice",
            "Letter Formation",
        ],
    },
}

def get_random_topics(subject: str, count: int = 8) -> list:
    """Get random topics from a subject's pool, sampling across categories."""
    if subject not in TOPIC_POOLS:
        return []
    
    # Collect all topics from all categories
    all_topics = []
    for category, topics in TOPIC_POOLS[subject].items():
        for topic in topics:
            all_topics.append((topic, category))
    
    # Randomly sample
    if len(all_topics) <= count:
        selected = all_topics
    else:
        selected = random.sample(all_topics, count)
    
    # Return just the topic names
    return [topic for topic, category in selected]

def get_topic_categories(subject: str) -> list:
    """Get the category names for a subject."""
    if subject not in TOPIC_POOLS:
        return []
    return list(TOPIC_POOLS[subject].keys())

def get_topics_in_category(subject: str, category: str) -> list:
    """Get all topics in a specific category."""
    if subject not in TOPIC_POOLS:
        return []
    return TOPIC_POOLS[subject].get(category, [])

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

LESSON_SYSTEM_PROMPT = """You are an expert curriculum designer specializing in creating practical, engaging lesson plans for teachers around the world.

CONTEXT:
You're creating lessons for dedicated teachers who work in various school settings. These teachers:
- May teach in well-resourced or resource-limited environments
- Often have large class sizes (25-40+ students)
- Are resourceful, creative, and dedicated
- Need practical, immediately usable content
- Value activities that engage all students

PEDAGOGICAL PRINCIPLES (embed these naturally, don't lecture about them):
- Start with what students already know (connect to daily life)
- Active learning over passive listening
- Check understanding frequently
- Use local, familiar examples (food, games, markets, family)
- Activities that can work with or without materials
- Clear, simple language
- Realistic timing

LOCALIZATION:
When a country/region is specified, use culturally relevant examples:
- India: rupees, chapati, cricket, local festivals
- Kenya: shillings, ugali, football, local context
- Nigeria: naira, local foods, local references
- Universal: use generic examples that work anywhere

CRITICAL OUTPUT RULES:
1. NEVER output empty sections - if you write a header like "Learning Objectives:" you MUST fill it with actual content
2. NEVER output incomplete bullet points or numbered lists - every item must be complete
3. NEVER repeat information from the specs (subject, topic, ages) in the lesson body - that's already shown separately
4. Start numbered lists at 1, not 2
5. Every section header MUST have substantive content below it
6. If a section would be empty, don't include that section at all

FORMAT RULES:
- Use ## for main section headers (e.g., ## Introduction)
- Use bullet points (-) for lists
- Use numbered lists (1. 2. 3.) for sequential steps
- Keep paragraphs short (2-3 sentences max)
- Include specific dialogue: "Ask students: [actual question]"

TONE:
Warm, practical, encouraging. You're a helpful colleague, not a textbook. Use "you" and "your students" naturally.

IMPORTANT:
- Match materials to what the teacher specified they have available
- Always include engaging activities that get students participating
- Time estimates must be realistic
- Include what to say/ask, not just what to do
- Add 1-2 "teacher tips" for common challenges
- DO NOT start with a title or repeat the topic name - jump straight into the lesson content"""

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
        prompt_parts.append("Available materials: No physical materials - design activities using voice, movement, games, and imagination only")
    elif materials == 'basic':
        prompt_parts.append("Available materials: Basic supplies - chalkboard or whiteboard, paper, pencils")
    elif materials == 'standard':
        prompt_parts.append("Available materials: Full classroom - worksheets, art supplies, manipulatives, varied resources")
    
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
OUTPUT FORMAT - QUICK PLAN (~200 words):

## Learning Objective
[1 clear sentence: "Students will be able to..."]

## Key Points
- [Point 1 - complete sentence]
- [Point 2 - complete sentence]
- [Point 3 - complete sentence]

## Main Activity (X minutes)
[Describe the activity. Include what to say: "Ask students..."]

## Quick Check
[Write 1 specific question to ask at the end]

## Teacher Tip
[1 practical tip]

REMEMBER: Every bullet point must be complete. No empty sections.""")
    elif depth == 'standard':
        prompt_parts.append("""
OUTPUT FORMAT - STANDARD LESSON PLAN:
Complete and concise (~500 words). Structure EXACTLY like this:

## Learning Objective
[Write 1-2 specific, measurable objectives - what students will be able to DO]

## Materials Needed
[List specific items, or write "None required" if no materials]

## Opening Hook (3 minutes)
[Write the specific question or activity to grab attention. Include exact words to say.]

## Main Lesson (X minutes)
[Step-by-step instructions with timing. Include what to SAY and what to DO.]

## Practice Activity (X minutes)
[Detailed hands-on activity. Explain exactly how it works.]

## Closing (3 minutes)
[2-3 specific questions to check understanding. Write the actual questions.]

## Teacher Tips
[2 practical tips for common challenges]

REMEMBER: Every section MUST have real content. No empty sections. No placeholders.""")
    elif depth == 'full':
        prompt_parts.append("""
OUTPUT FORMAT - FULL LESSON KIT (~800 words):

## Learning Objectives
- [Objective 1 - specific and measurable]
- [Objective 2 - specific and measurable]

## Materials Needed
[List all materials, or "None required"]

## Opening Hook (3 minutes)
[Specific engaging question or activity with exact words to say]

## Main Lesson (X minutes)
[Detailed step-by-step with timing for each step. Include dialogue.]

## Practice Activity (X minutes)
[Complete activity description with clear instructions]

## Closing (3 minutes)
[Specific wrap-up questions - write the actual questions]

## Differentiation
**For students who need support:** [Specific strategies - at least 2 sentences]
**For advanced students:** [Specific extension - at least 2 sentences]

## Assessment Questions
1. [Question with answer in parentheses]
2. [Question with answer in parentheses]
3. [Question with answer in parentheses]

## Extension Activity
[Optional homework or follow-up - complete description]

## Teacher Tips
- [Tip 1 - complete thought]
- [Tip 2 - complete thought]

CRITICAL: Every single section must have substantive content. If you write a header, you MUST fill it in completely. No empty sections allowed.""")
    
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
    """Custom PDF class for lesson plans with Tooley branding.
    
    Brand Colors (v2.3.0):
    - Navy (primary): #0f172a / RGB(15, 23, 42)
    - Slate (secondary): #334155 / RGB(51, 65, 85)
    - Amber (accent): #d97706 / RGB(217, 119, 6) - darker, less saturated
    - Amber Light: #fbbf24 / RGB(251, 191, 36) - for highlights
    - Cream background: #fffbeb / RGB(255, 251, 235)
    """
    
    def __init__(self, params: dict = None):
        super().__init__()
        self.params = params or {}
        self.add_page()
        self.set_auto_page_break(auto=True, margin=20)
    
    def header(self):
        # --- TOOLEY LOGO ---
        # Draw amber accent bar at top
        self.set_fill_color(217, 119, 6)  # Amber accent #d97706
        self.rect(10, 10, 4, 12, 'F')  # Small vertical accent bar
        
        # Logo text "tooley" in navy
        self.set_xy(18, 10)
        self.set_font('Helvetica', 'B', 20)
        self.set_text_color(15, 23, 42)  # Navy #0f172a
        self.cell(40, 12, 'tooley', align='L')
        
        # Tagline
        self.set_xy(10, 22)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(100, 116, 139)  # Stone #64748b
        self.cell(0, 5, 'AI Lesson Plans for Teachers', align='L')
        
        # Page indicator on right
        self.set_xy(160, 10)
        self.set_font('Helvetica', '', 9)
        self.set_text_color(100, 116, 139)
        self.cell(40, 12, 'tooley.app', align='R')
        
        self.ln(22)
        
        # Divider line - navy, not amber
        self.set_draw_color(15, 23, 42)  # Navy
        self.set_line_width(0.3)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(8)
    
    def footer(self):
        self.set_y(-20)
        # Divider line
        self.set_draw_color(200, 200, 200)
        self.set_line_width(0.3)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 5, f'Page {self.page_no()}', align='C')
        self.ln(4)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(100, 116, 139)
        self.cell(0, 5, 'Generated by Tooley | tooley.app | Free for all teachers', align='C')
    
    def _break_long_words(self, text: str, max_chars: int = 55) -> str:
        """Break very long words to prevent PDF rendering issues."""
        words = text.split(' ')
        result = []
        for word in words:
            if len(word) > max_chars:
                chunks = [word[i:i+max_chars] for i in range(0, len(word), max_chars)]
                result.append(' '.join(chunks))
            else:
                result.append(word)
        return ' '.join(result)
    
    def add_specs_box(self, params: dict):
        """Add a branded lesson specs box - cream bg, navy border, amber title."""
        # Cream background with navy border
        self.set_fill_color(255, 251, 235)  # Warm cream #fffbeb
        self.set_draw_color(15, 23, 42)     # Navy border #0f172a
        self.set_line_width(0.5)
        
        # Calculate box height based on content
        specs = []
        if params.get('subject'):
            specs.append(f"Subject: {params['subject']}")
        if params.get('topic'):
            specs.append(f"Topic: {params['topic']}")
        if params.get('ages'):
            specs.append(f"Ages: {params['ages']}")
        if params.get('duration'):
            specs.append(f"Duration: {params['duration']} minutes")
        if params.get('country'):
            specs.append(f"Location: {params['country']}")
        if params.get('materials'):
            materials_map = {'none': 'No materials', 'basic': 'Basic supplies', 'standard': 'Full classroom'}
            specs.append(f"Materials: {materials_map.get(params['materials'], params['materials'])}")
        if params.get('style'):
            style_map = {'interactive': 'Interactive', 'structured': 'Structured', 'storytelling': 'Story-based'}
            specs.append(f"Style: {style_map.get(params['style'], params['style'])}")
        
        box_height = 10 + (len(specs) * 6)
        self.rect(10, self.get_y(), 190, box_height, 'DF')
        
        # Title with amber accent
        self.set_xy(15, self.get_y() + 4)
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(217, 119, 6)  # Amber accent #d97706
        self.cell(0, 5, 'LESSON SPECIFICATIONS')
        self.ln(7)
        
        # Specs in navy text
        self.set_font('Helvetica', '', 9)
        self.set_text_color(15, 23, 42)  # Navy #0f172a
        for spec in specs:
            self.set_x(15)
            self.cell(0, 5, self._safe_text(spec))
            self.ln(5)
        
        self.ln(8)
    
    def add_lesson_content(self, content: str, params: dict):
        """Add the lesson content to PDF with improved formatting.
        
        Color scheme v2.3.0:
        - Main headers: Navy (#0f172a) - prominent, professional
        - Section headers: Slate (#334155) - secondary
        - Body text: Navy (#0f172a) - readable
        - Accent underlines: Amber (#d97706) - subtle highlights
        """
        
        # Add specs box first
        self.add_specs_box(params)
        
        # Main content
        self.set_font('Helvetica', '', 10)
        self.set_text_color(15, 23, 42)  # Navy #0f172a
        
        in_section = False
        
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                self.ln(4)
                continue
            
            safe_line = self._break_long_words(self._safe_text(line))
            
            try:
                # Main headers (## or lines starting with #) - NAVY with amber underline
                if line.startswith('## ') or line.startswith('# '):
                    self.ln(6)
                    self.set_font('Helvetica', 'B', 12)
                    self.set_text_color(15, 23, 42)  # Navy #0f172a (not amber!)
                    header_text = safe_line.lstrip('#').strip()
                    self.multi_cell(0, 7, header_text)
                    # Small amber accent line under header
                    self.set_draw_color(217, 119, 6)  # Amber
                    self.set_line_width(0.5)
                    self.line(10, self.get_y(), 50, self.get_y())
                    self.set_font('Helvetica', '', 10)
                    self.set_text_color(15, 23, 42)  # Navy
                    self.ln(4)
                    in_section = True
                
                # Bold lines (**text**) - Slate
                elif line.startswith('**') and line.endswith('**'):
                    self.ln(3)
                    self.set_font('Helvetica', 'B', 10)
                    self.set_text_color(51, 65, 85)  # Slate
                    clean_text = safe_line.strip('*').strip()
                    self.multi_cell(0, 6, clean_text)
                    self.set_font('Helvetica', '', 10)
                    self.set_text_color(15, 23, 42)  # Navy
                
                # Section headers (lines ending with :) - Slate
                elif line.endswith(':') and len(line) < 60 and not line.startswith('-'):
                    self.ln(4)
                    self.set_font('Helvetica', 'B', 10)
                    self.set_text_color(51, 65, 85)  # Slate #334155
                    self.multi_cell(0, 6, safe_line)
                    self.set_font('Helvetica', '', 10)
                    self.set_text_color(15, 23, 42)  # Navy
                
                # Bullet points
                elif line.startswith('- ') or line.startswith('* ') or line.startswith('• '):
                    bullet_text = '    ' + chr(149) + ' ' + self._break_long_words(self._safe_text(line[2:]))
                    self.multi_cell(0, 5, bullet_text)
                
                # Numbered items
                elif len(line) > 2 and line[0].isdigit() and line[1] in '.):':
                    self.multi_cell(0, 5, '  ' + safe_line)
                
                # Regular text
                else:
                    self.multi_cell(0, 5, safe_line)
                    
            except Exception as e:
                logger.warning(f"PDF line rendering failed: {e}")
                continue
    
    def _safe_text(self, text: str) -> str:
        """Convert text to safe ASCII for PDF."""
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
            '📚': '',
            '📝': '',
            '🎯': '',
            '💡': '[Tip]',
            '⏱': '',
            '👥': '',
            '₱': 'PHP ',
            '₹': 'Rs ',
            '₦': 'NGN ',
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text.encode('ascii', 'replace').decode('ascii')


def create_lesson_pdf(content: str, params: dict) -> BytesIO:
    """Create a PDF from lesson content."""
    
    try:
        pdf = LessonPDF(params)
        pdf.add_lesson_content(content, params)
        
        # Output to BytesIO
        pdf_buffer = BytesIO()
        pdf_output = pdf.output()
        pdf_buffer.write(pdf_output)
        pdf_buffer.seek(0)
        
        return pdf_buffer
    except Exception as e:
        logger.error(f"PDF creation failed: {e}")
        # Return a simple fallback PDF with error info
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font('Helvetica', 'B', 14)
        pdf.cell(0, 10, "Tooley - Lesson Plan")
        pdf.ln(15)
        pdf.set_font('Helvetica', '', 11)
        # Add the content as plain text
        for line in content.split('\n')[:50]:  # First 50 lines
            safe_line = line.encode('ascii', 'replace').decode('ascii')[:90]
            pdf.multi_cell(0, 6, safe_line)
        pdf_buffer = BytesIO()
        pdf_buffer.write(pdf.output())
        pdf_buffer.seek(0)
        return pdf_buffer


def generate_lesson_filename(params: dict) -> str:
    """Generate a structured filename for the lesson PDF.
    Format: tooley_{subject}_{topic}_{ages}_{duration}.pdf
    """
    parts = ['tooley']  # Always start with tooley_
    
    # Subject (abbreviated)
    subject = params.get('subject', 'lesson')
    subject_abbrev = {
        'Mathematics': 'math',
        'Language': 'lang',
        'Science': 'science',
        'Reading': 'reading',
        'Social Studies': 'social',
        'Art': 'art',
        'Physical Education': 'pe',
        'Music': 'music',
    }
    parts.append(subject_abbrev.get(subject, subject[:6].lower()))
    
    # Topic (sanitized)
    topic = params.get('topic', 'lesson')
    topic_clean = topic.lower().replace(' ', '-')[:20]
    topic_clean = ''.join(c for c in topic_clean if c.isalnum() or c == '-')
    parts.append(topic_clean)
    
    # Ages
    if params.get('ages'):
        parts.append(f"ages{params['ages'].replace('-', 'to')}")
    
    # Duration
    if params.get('duration'):
        parts.append(f"{params['duration']}min")
    
    return '_'.join(parts)


def create_lesson_html(content: str, params: dict) -> str:
    """Create a styled HTML document from lesson content.
    
    This produces a beautiful, print-ready HTML file that renders
    markdown-style content with Tooley branding.
    """
    
    # Build specs info
    specs_html = ""
    if params.get('subject'):
        specs_html += f"<div class='spec'><span class='label'>Subject:</span> {params['subject']}</div>"
    if params.get('topic'):
        specs_html += f"<div class='spec'><span class='label'>Topic:</span> {params['topic']}</div>"
    if params.get('ages'):
        specs_html += f"<div class='spec'><span class='label'>Ages:</span> {params['ages']}</div>"
    if params.get('duration'):
        specs_html += f"<div class='spec'><span class='label'>Duration:</span> {params['duration']} minutes</div>"
    if params.get('country'):
        specs_html += f"<div class='spec'><span class='label'>Location:</span> {params['country']}</div>"
    if params.get('materials'):
        materials_map = {'none': 'No materials', 'basic': 'Basic supplies', 'standard': 'Full classroom'}
        specs_html += f"<div class='spec'><span class='label'>Materials:</span> {materials_map.get(params['materials'], params['materials'])}</div>"
    if params.get('style'):
        style_map = {'interactive': 'Interactive', 'structured': 'Structured', 'storytelling': 'Story-based'}
        specs_html += f"<div class='spec'><span class='label'>Style:</span> {style_map.get(params['style'], params['style'])}</div>"
    
    # Convert markdown-style content to HTML
    content_html = ""
    lines = content.split('\n')
    in_list = False
    
    for line in lines:
        line = line.strip()
        if not line:
            if in_list:
                content_html += "</ul>"
                in_list = False
            content_html += "<br>"
            continue
        
        # Headers
        if line.startswith('## '):
            if in_list:
                content_html += "</ul>"
                in_list = False
            content_html += f"<h2>{line[3:]}</h2>"
        elif line.startswith('# '):
            if in_list:
                content_html += "</ul>"
                in_list = False
            content_html += f"<h1>{line[2:]}</h1>"
        # Bold lines
        elif line.startswith('**') and line.endswith('**'):
            if in_list:
                content_html += "</ul>"
                in_list = False
            content_html += f"<p class='bold'>{line.strip('*')}</p>"
        # Bullet points
        elif line.startswith('- ') or line.startswith('* ') or line.startswith('• '):
            if not in_list:
                content_html += "<ul>"
                in_list = True
            content_html += f"<li>{line[2:]}</li>"
        # Numbered items
        elif len(line) > 2 and line[0].isdigit() and line[1] in '.):':
            if in_list:
                content_html += "</ul>"
                in_list = False
            content_html += f"<p class='numbered'>{line}</p>"
        # Regular text
        else:
            if in_list:
                content_html += "</ul>"
                in_list = False
            # Handle inline bold **text**
            import re
            line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            content_html += f"<p>{line}</p>"
    
    if in_list:
        content_html += "</ul>"
    
    topic = params.get('topic', 'Lesson Plan')
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{topic} - Tooley Lesson Plan</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: 14px;
            line-height: 1.6;
            color: #0f172a;
            background: #ffffff;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 30px;
        }}
        
        /* Header */
        .header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 8px;
            padding-bottom: 16px;
            border-bottom: 2px solid #0f172a;
        }}
        
        .logo {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .logo-bar {{
            width: 4px;
            height: 28px;
            background: #d97706;
            border-radius: 2px;
        }}
        
        .logo-text {{
            font-size: 24px;
            font-weight: 700;
            color: #0f172a;
            letter-spacing: -0.5px;
        }}
        
        .tagline {{
            font-size: 11px;
            color: #64748b;
            margin-left: auto;
        }}
        
        /* Specs Box */
        .specs-box {{
            background: #fffbeb;
            border: 1px solid #0f172a;
            padding: 16px 20px;
            margin: 20px 0 30px 0;
        }}
        
        .specs-title {{
            font-size: 11px;
            font-weight: 700;
            color: #d97706;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            margin-bottom: 12px;
        }}
        
        .spec {{
            font-size: 13px;
            margin-bottom: 4px;
        }}
        
        .spec .label {{
            font-weight: 600;
        }}
        
        /* Content */
        h1 {{
            font-size: 22px;
            font-weight: 700;
            color: #0f172a;
            margin: 28px 0 12px 0;
            padding-bottom: 6px;
            border-bottom: 2px solid #d97706;
            display: inline-block;
        }}
        
        h2 {{
            font-size: 18px;
            font-weight: 600;
            color: #0f172a;
            margin: 24px 0 10px 0;
            padding-bottom: 4px;
            border-bottom: 2px solid #d97706;
            display: inline-block;
        }}
        
        p {{
            margin-bottom: 10px;
        }}
        
        p.bold {{
            font-weight: 600;
            color: #334155;
            margin-top: 16px;
        }}
        
        p.numbered {{
            margin-left: 16px;
        }}
        
        ul {{
            margin: 10px 0 10px 24px;
        }}
        
        li {{
            margin-bottom: 6px;
        }}
        
        strong {{
            font-weight: 600;
        }}
        
        /* Footer */
        .footer {{
            margin-top: 40px;
            padding-top: 16px;
            border-top: 1px solid #e2e8f0;
            text-align: center;
            font-size: 12px;
            color: #64748b;
        }}
        
        /* Print styles */
        @media print {{
            body {{
                padding: 20px;
                max-width: 100%;
            }}
            .specs-box {{
                break-inside: avoid;
            }}
            h2 {{
                break-after: avoid;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">
            <div class="logo-bar"></div>
            <span class="logo-text">tooley</span>
        </div>
        <span class="tagline">AI Lesson Plans for Teachers | tooley.app</span>
    </div>
    
    <div class="specs-box">
        <div class="specs-title">Lesson Specifications</div>
        {specs_html}
    </div>
    
    <div class="content">
        {content_html}
    </div>
    
    <div class="footer">
        Generated by Tooley | tooley.app | Free for all teachers
    </div>
</body>
</html>'''
    
    return html


# ============================================================================
# UX HELPERS
# ============================================================================

def build_selection_summary(params: dict) -> str:
    """Build a visual summary of selections made so far."""
    lines = ["━━━━ *Your Lesson* ━━━━"]
    
    if params.get('subject'):
        lines.append(f"📚 Subject: {params['subject']}")
    if params.get('topic'):
        lines.append(f"📝 Topic: {params['topic']}")
    if params.get('ages'):
        lines.append(f"🧒🏽 Ages: {params['ages']}")
    if params.get('duration'):
        lines.append(f"⏱ Duration: {params['duration']} min")
    if params.get('country'):
        lines.append(f"📍 Location: {params['country']}")
    if params.get('materials'):
        materials_map = {
            'none': '🎭 No materials',
            'basic': '📝 Basic supplies', 
            'standard': '📦 Full classroom'
        }
        lines.append(f"📦 Materials: {materials_map.get(params['materials'], params['materials'])}")
    if params.get('style'):
        style_map = {
            'interactive': '🎮 Interactive',
            'structured': '📋 Structured',
            'storytelling': '📖 Story-based'
        }
        lines.append(f"🎯 Style: {style_map.get(params['style'], params['style'])}")
    
    lines.append("━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


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


async def push_lesson_to_website(lesson: dict) -> bool:
    """Push lesson to website repo for carousel display.
    
    This updates the website's lessons.json which powers the carousel
    on the public landing page. Netlify auto-deploys when the file changes.
    """
    if not GITHUB_TOKEN or not GITHUB_WEBSITE_REPO:
        logger.info("Website push skipped (GITHUB_WEBSITE_REPO not configured)")
        return False
    
    try:
        async with httpx.AsyncClient() as client:
            # Get current lessons.json from website repo
            get_response = await client.get(
                f"https://api.github.com/repos/{GITHUB_WEBSITE_REPO}/contents/lessons.json",
                headers={
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            
            # Load existing or start fresh
            if get_response.status_code == 200:
                file_data = get_response.json()
                sha = file_data["sha"]
                existing_content = base64.b64decode(file_data["content"]).decode("utf-8")
                data = json.loads(existing_content)
                lessons = data.get("lessons", [])
            else:
                sha = None
                lessons = []
            
            # Create carousel-friendly record (subset of full data)
            carousel_lesson = {
                "id": lesson.get("id", generate_lesson_id()),
                "subject": lesson.get("subject", "General").upper(),
                "topic": lesson.get("topic", "Untitled"),
                "ages": lesson.get("ages", "All ages"),
                "duration": str(lesson.get("duration", 45)),
                "country": lesson.get("country", "Global"),
                "teacher_name": lesson.get("teacher_name", "Anonymous"),
                "public": True,
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
            
            # Add to beginning
            lessons.insert(0, carousel_lesson)
            
            # Keep only last 50 lessons for website
            lessons = lessons[:50]
            
            # Build the JSON structure the website expects
            website_data = {
                "lastUpdated": datetime.utcnow().isoformat() + "Z",
                "lessons": lessons
            }
            
            # Encode
            new_content = json.dumps(website_data, indent=2, ensure_ascii=False)
            encoded_content = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
            
            # Prepare request
            body = {
                "message": f"🎓 New lesson: {lesson.get('topic', 'Untitled')} ({lesson.get('country', 'Global')})",
                "content": encoded_content,
            }
            if sha:
                body["sha"] = sha
            
            # Push to website repo
            put_response = await client.put(
                f"https://api.github.com/repos/{GITHUB_WEBSITE_REPO}/contents/lessons.json",
                headers={
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json"
                },
                json=body
            )
            
            put_response.raise_for_status()
            logger.info(f"Pushed lesson {lesson['id']} to website carousel")
            return True
    
    except Exception as e:
        logger.error(f"Error pushing to website: {e}")
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
        'Nigeria': '🇳🇬',
        'Philippines': '🇵🇭',
        'Indonesia': '🇮🇩',
        'Pakistan': '🇵🇰',
        'Bangladesh': '🇧🇩',
        'Kenya': '🇰🇪',
        'Ethiopia': '🇪🇹',
        'South Africa': '🇿🇦',
        'Tanzania': '🇹🇿',
        'Brazil': '🇧🇷',
        'Mexico': '🇲🇽',
        'Ghana': '🇬🇭',
        'Uganda': '🇺🇬',
    }
    return flags.get(country, '🌍')


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    
    # Get stats for social proof
    stats = await get_lesson_stats()
    stats_text = ""
    if stats['total'] > 0:
        stats_text = f"\n🌍 *{stats['total']} lessons* created by teachers worldwide\n"
    
    welcome_text = f"""🧒🏽 *Welcome to Tooley!*

Your free AI teaching assistant. Create ready-to-use lesson plans in minutes.
{stats_text}
━━━━━━━━━━━━━━━━━━━━━━

*3 ways to create a lesson:*

💬 *Just type* what you need:
_"Fractions lesson for ages 8-10 in Kenya"_

🎤 *Send a voice message*
_Describe your lesson in any accent_

🔘 *Guided mode* - we'll ask step by step
_Best for your first lesson_

━━━━━━━━━━━━━━━━━━━━━━

*What you get:*
📄 Formatted lesson plan (PDF or HTML)
🎯 Learning objectives, activities, timing
💡 Teacher tips for common challenges
🌍 Examples relevant to YOUR country

━━━━━━━━━━━━━━━━━━━━━━

Tap a button below or type /new to start 👇"""
    
    keyboard = [
        [InlineKeyboardButton("🆕 Create a lesson", callback_data="action_new")],
        [
            InlineKeyboardButton("⚡ Quick lesson", callback_data="action_quick"),
            InlineKeyboardButton("📚 Browse", callback_data="action_browse"),
        ],
        [InlineKeyboardButton("❓ Help & tips", callback_data="action_help")]
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
        
        # Show topic categories for this subject OR random topics
        # First show categories, let them drill down OR pick random
        categories = get_topic_categories(subject)
        
        if categories:
            # Two-tier system: Categories OR random sampling
            keyboard = []
            
            # Add category buttons (2 per row)
            for i in range(0, len(categories), 2):
                row = []
                for cat in categories[i:i+2]:
                    # Truncate long category names
                    display_name = cat if len(cat) <= 20 else cat[:18] + "..."
                    row.append(InlineKeyboardButton(display_name, callback_data=f"topiccat_{cat}"))
                keyboard.append(row)
            
            # Add "Surprise me" and "Type my own" options
            keyboard.append([InlineKeyboardButton("🎲 Surprise me (8 random topics)", callback_data="topiccat_random")])
            keyboard.append([InlineKeyboardButton("✏️ Type my own topic...", callback_data="topic_custom")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            summary = build_selection_summary(session['params'])
            await query.edit_message_text(
                f"{summary}\n\n📂 *Choose a category or get random suggestions:*",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            # Fallback for unknown subjects
            session['state'] = 'awaiting_topic'
            summary = build_selection_summary(session['params'])
            await query.edit_message_text(
                f"{summary}\n\n✏️ *Type your topic:*",
                parse_mode='Markdown'
            )
        return
    
    # Topic category selection (new v2.3.0)
    if data.startswith("topiccat_"):
        category = data.replace("topiccat_", "")
        subject = session['params'].get('subject', '')
        
        if category == "random":
            # Get 8 random topics from the full pool
            random_topics = get_random_topics(subject, 8)
            keyboard = []
            for topic in random_topics:
                callback = f"topic_{topic}"
                if len(callback) > 64:  # Telegram limit
                    callback = f"topic_{topic[:55]}"
                keyboard.append([InlineKeyboardButton(topic, callback_data=callback)])
            keyboard.append([InlineKeyboardButton("🎲 Shuffle (new 8)", callback_data="topiccat_random")])
            keyboard.append([InlineKeyboardButton("📂 Back to categories", callback_data=f"subject_{subject}")])
            keyboard.append([InlineKeyboardButton("✏️ Type my own topic...", callback_data="topic_custom")])
        else:
            # Show all topics in this category
            topics = get_topics_in_category(subject, category)
            keyboard = []
            for topic in topics:
                callback = f"topic_{topic}"
                if len(callback) > 64:
                    callback = f"topic_{topic[:55]}"
                keyboard.append([InlineKeyboardButton(topic, callback_data=callback)])
            keyboard.append([InlineKeyboardButton("📂 Back to categories", callback_data=f"subject_{subject}")])
            keyboard.append([InlineKeyboardButton("✏️ Type my own topic...", callback_data="topic_custom")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        summary = build_selection_summary(session['params'])
        category_label = "Random selection" if category == "random" else category
        await query.edit_message_text(
            f"{summary}\n\n📝 *{category_label}* - Pick a topic:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Topic selection
    if data.startswith("topic_"):
        topic = data.replace("topic_", "")
        if topic == "custom":
            session['state'] = 'awaiting_topic'
            summary = build_selection_summary(session['params'])
            await query.edit_message_text(
                f"{summary}\n\n✏️ *Type your topic:*"
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
        
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(
            f"{summary}\n\n🧒🏽 *What age are your students?*",
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
        
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(
            f"{summary}\n\n⏱ *How long is your class?*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Duration selection
    if data.startswith("duration_"):
        duration = data.replace("duration_", "")
        session['params']['duration'] = duration
        session['state'] = 'awaiting_country'
        
        # Top countries by teacher population + educational development focus
        # Data-driven: UNESCO/World Bank teacher population stats
        keyboard = [
            [
                InlineKeyboardButton("🇮🇳 India", callback_data="country_India"),
                InlineKeyboardButton("🇳🇬 Nigeria", callback_data="country_Nigeria"),
            ],
            [
                InlineKeyboardButton("🇵🇭 Philippines", callback_data="country_Philippines"),
                InlineKeyboardButton("🇮🇩 Indonesia", callback_data="country_Indonesia"),
            ],
            [
                InlineKeyboardButton("🇵🇰 Pakistan", callback_data="country_Pakistan"),
                InlineKeyboardButton("🇧🇩 Bangladesh", callback_data="country_Bangladesh"),
            ],
            [
                InlineKeyboardButton("🇰🇪 Kenya", callback_data="country_Kenya"),
                InlineKeyboardButton("🇪🇹 Ethiopia", callback_data="country_Ethiopia"),
            ],
            [
                InlineKeyboardButton("🇿🇦 South Africa", callback_data="country_South Africa"),
                InlineKeyboardButton("🇹🇿 Tanzania", callback_data="country_Tanzania"),
            ],
            [
                InlineKeyboardButton("🇧🇷 Brazil", callback_data="country_Brazil"),
                InlineKeyboardButton("🇲🇽 Mexico", callback_data="country_Mexico"),
            ],
            [
                InlineKeyboardButton("🇬🇭 Ghana", callback_data="country_Ghana"),
                InlineKeyboardButton("🇺🇬 Uganda", callback_data="country_Uganda"),
            ],
            [
                InlineKeyboardButton("🌍 Other (type)", callback_data="country_other"),
                InlineKeyboardButton("🌐 Universal", callback_data="country_skip"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(
            f"{summary}\n\n📍 *Where are you teaching?*\n(helps with local examples)",
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
            [InlineKeyboardButton("🎭 No materials - voice & movement", callback_data="materials_none")],
            [InlineKeyboardButton("📝 Basic - board, paper, pencils", callback_data="materials_basic")],
            [InlineKeyboardButton("📦 Full classroom - worksheets & supplies", callback_data="materials_standard")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Build summary of selections so far
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(
            f"{summary}\n\n📦 *What materials do you have?*",
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
        
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(
            f"{summary}\n\n🎨 *What teaching style works best?*",
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
        
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(
            f"{summary}\n\n📊 *How detailed should the lesson plan be?*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Depth selection - ask format preference
    if data.startswith("depth_"):
        depth = data.replace("depth_", "")
        session['params']['depth'] = depth
        session['state'] = 'awaiting_format'
        
        keyboard = [
            [InlineKeyboardButton("📱 Read in chat", callback_data="format_chat")],
            [InlineKeyboardButton("📄 PDF document", callback_data="format_pdf")],
            [InlineKeyboardButton("🌐 HTML (opens in browser)", callback_data="format_html")],
            [InlineKeyboardButton("📱📄 Chat + PDF", callback_data="format_both")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(
            f"{summary}\n\n📲 *Choose your format:*\n_PDF works offline, HTML is print-friendly_",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Format selection - NOW GENERATE!
    if data.startswith("format_"):
        output_format = data.replace("format_", "")
        session['params']['output_format'] = output_format
        
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(
            f"{summary}\n\n⏳ *Generating your lesson plan...*", 
            parse_mode='Markdown'
        )
        
        try:
            lesson_content = generate_lesson(session['params'])
            session['last_lesson'] = lesson_content
            session['state'] = 'lesson_generated'
            
            # Build the summary to include with output
            specs_text = build_selection_summary(session['params'])
            
            # Send based on format choice
            if output_format in ['chat', 'both']:
                # Split long messages
                full_text = f"{specs_text}\n\n{lesson_content}"
                if len(full_text) < 4000:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=full_text,
                        parse_mode='Markdown'
                    )
                else:
                    # Send specs first, then content
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=specs_text,
                        parse_mode='Markdown'
                    )
                    # Split content into chunks
                    chunks = [lesson_content[i:i+4000] for i in range(0, len(lesson_content), 4000)]
                    for chunk in chunks:
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=chunk
                        )
            
            if output_format in ['pdf', 'both']:
                pdf_buffer = create_lesson_pdf(lesson_content, session['params'])
                filename = generate_lesson_filename(session['params']) + '.pdf'
                
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=pdf_buffer,
                    filename=filename,
                    caption=f"📄 *Your lesson plan is ready!*\n\n{specs_text}",
                    parse_mode='Markdown'
                )
            
            if output_format == 'html':
                html_content = create_lesson_html(lesson_content, session['params'])
                html_buffer = BytesIO(html_content.encode('utf-8'))
                filename = generate_lesson_filename(session['params']) + '.html'
                
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=html_buffer,
                    filename=filename,
                    caption=f"🌐 *Your lesson plan is ready!*\nOpen in any browser, print-friendly.\n\n{specs_text}",
                    parse_mode='Markdown'
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
        # Keep same params but choose new topic - show categories
        session['state'] = 'awaiting_topic'
        subject = session['params'].get('subject', '')
        
        # Use the new category system (v2.3.0)
        categories = get_topic_categories(subject)
        
        keyboard = []
        if categories:
            # Add category buttons (2 per row)
            for i in range(0, len(categories), 2):
                row = []
                for cat in categories[i:i+2]:
                    display_name = cat if len(cat) <= 20 else cat[:18] + "..."
                    row.append(InlineKeyboardButton(display_name, callback_data=f"topiccat_{cat}"))
                keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton("🎲 Surprise me (8 random topics)", callback_data="topiccat_random")])
        keyboard.append([InlineKeyboardButton("✏️ Type my own topic...", callback_data="topic_custom")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Show current params without topic
        params_summary = f"📚 Subject: {subject}\n🧒🏽 Ages: {session['params'].get('ages', '?')}\n📍 Location: {session['params'].get('country', '?')}"
        
        await query.edit_message_text(
            f"━━━━ *Same Settings* ━━━━\n{params_summary}\n━━━━━━━━━━━━━━━━━━\n\n📂 *Pick a different topic:*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
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
            
            # Also push to website carousel (async, don't block on failure)
            website_pushed = await push_lesson_to_website(lesson_record)
            
            if saved:
                country = session['params'].get('country', 'the world')
                website_note = "\n📍 Your lesson is now live on tooley.app!" if website_pushed else ""
                await update.message.reply_text(
                    f"✅ *Shared with the community!*\n\n"
                    f"Teachers in {country} and beyond can now use your lesson.{website_note}\n"
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
            [InlineKeyboardButton("🎭 No materials - voice & movement", callback_data="materials_none")],
            [InlineKeyboardButton("📝 Basic - board, paper, pencils", callback_data="materials_basic")],
            [InlineKeyboardButton("📦 Full classroom - worksheets & supplies", callback_data="materials_standard")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        summary = build_selection_summary(session['params'])
        await update.message.reply_text(
            f"{summary}\n\n📦 *What materials do you have?*",
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
