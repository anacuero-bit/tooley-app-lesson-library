"""
Tooley - Lesson Plan Generator Bot
Telegram bot that generates customized lesson plans for teachers worldwide.

Version: 2.10.7
Last Updated: 2026-01-29

CHANGELOG:
---------
v2.10.7 (2026-01-29)
  - REMOVED: Version number from welcome message (cleaner UX)
  - ADDED: HTML output to Quick Lesson flow (now sends Chat + PDF + HTML)
  - IMPROVED: PDF branding in fallback attempt 3 (now has Tooley header/footer)

v2.10.6 (2026-01-29)
  - FIXED: Menu button width - single column layout for all subject menus
  - FIXED: Better subject labels (Language Arts, Art & Music, Mathematics)

v2.10.4 (2026-01-29)
  - FIXED: PDF/HTML downloads now use InputFile wrapper for reliable delivery
  - FIXED: HTML buffer seek(0) before sending
  - FIXED: Better error logging for file sends

v2.10.3 (2026-01-29)
  - CHANGED: Country list limited to English-education countries
  - Removed: China, Brazil, Mexico, Egypt, Vietnam, Turkey (non-English primary)
  - Added: Ghana, Tanzania, South Africa, Jamaica, Rwanda
  - Kept: India, Pakistan, Nigeria, Bangladesh, Philippines, Kenya, Uganda, US, UK, Australia, Canada

v2.10.2 (2026-01-29)
  - IMPROVED: PDF generation with triple-fallback system
  - IMPROVED: Unicode/emoji handling in safe() method - comprehensive replacements
  - IMPROVED: Better PDF logging with byte sizes
  - FIXED: PDF emoji crashes (checkmarks, stars, arrows, etc. now converted)
  
v2.10.1 (2026-01-29)
  - FIXED: Format menu now shows Chat+PDF | Chat+HTML (not HTML+PDF)
  - FIXED: HTML output now has ACTUAL SVG logo embedded
  - FIXED: PDF fallback more robust, handles None return
  - IMPROVED: PDF error logging with full traceback
  - NOTE: Website push requires GITHUB_WEBSITE_REPO env var on Railway

v2.10.0 (2026-01-29)
  - FIXED: Format button handlers now definitively working
  - FIXED: PDF generation error handling improved
  - FIXED: HTML output now properly branded with logo
  - FIXED: Website push - better error logging and validation
  - CHANGED: Format button layout reorganized:
    * Row 1: Chat only (full width)
    * Row 2: PDF only | HTML only
    * Row 3: Chat+PDF | Chat+HTML
  - IMPROVED: More robust callback handler routing
  - IMPROVED: Debug logging throughout format/generation flow

v2.9.0 (2026-01-29)
  - FIXED: Quick Lesson button now definitively working
  - FIXED: Help & Tips button now definitively working

v2.8.0 (2026-01-29)
  - FIXED: Quick Lesson button handler properly connected
  - FIXED: Help & Tips button handler properly connected
  - FIXED: PDF content now renders completely (no truncation)

v2.7.0 (2026-01-29)
  - REWRITE: Simpler PDF generation for reliability

Stack:
- python-telegram-bot for Telegram interface
- anthropic for Claude API (lesson generation)
- groq for Whisper voice transcription
- fpdf2 for PDF generation
- GitHub API for lesson repository storage
"""

VERSION = "2.10.7"

import os
import logging
import json
import hashlib
import base64
import random
import re
import traceback
from datetime import datetime
from io import BytesIO
import httpx

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
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

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "tooley/lesson-library")
GITHUB_WEBSITE_REPO = os.environ.get("GITHUB_WEBSITE_REPO")
LESSONS_FILE = "lessons.json"

# ============================================================================
# TOPIC POOLS
# ============================================================================

TOPIC_POOLS = {
    "Mathematics": {
        "Numbers": ["Addition", "Subtraction", "Multiplication", "Division", "Place value", "Rounding", "Comparing numbers"],
        "Fractions": ["Introduction to fractions", "Equivalent fractions", "Adding fractions", "Decimals"],
        "Geometry": ["Shapes", "Perimeter", "Area", "Symmetry", "Angles"],
        "Measurement": ["Time", "Length", "Weight", "Money"],
    },
    "Science": {
        "Life Science": ["Plants", "Animals", "Habitats", "Food chains", "Human body"],
        "Physical Science": ["States of matter", "Magnets", "Light", "Sound", "Simple machines"],
        "Earth Science": ["Weather", "Water cycle", "Rocks", "Solar system"],
    },
    "Language": {
        "Grammar": ["Nouns", "Verbs", "Adjectives", "Sentences", "Punctuation"],
        "Writing": ["Paragraphs", "Stories", "Letters", "Descriptions"],
        "Vocabulary": ["Word families", "Synonyms", "Prefixes", "Spelling patterns"],
    },
    "Reading": {
        "Comprehension": ["Main idea", "Story elements", "Making predictions", "Cause and effect"],
        "Phonics": ["Letter sounds", "Blending", "Sight words"],
        "Literature": ["Fables", "Poetry", "Character analysis"],
    },
    "Social Studies": {
        "Community": ["Community helpers", "Maps", "Rules and laws"],
        "History": ["Historical figures", "Timelines", "Traditions"],
        "Geography": ["Continents", "Countries", "Landforms"],
        "Global": ["Cultural diversity", "Sustainable living", "Global connections"],
    },
    "Art": {
        "Drawing": ["Lines and shapes", "Portraits", "Sketching"],
        "Painting": ["Color mixing", "Watercolors", "Abstract art"],
        "Crafts": ["Paper crafts", "Collage", "Recycled art"],
    }
}

TOPICS_BY_SUBJECT = {}
for subject, categories in TOPIC_POOLS.items():
    all_topics = []
    for cat_topics in categories.values():
        all_topics.extend(cat_topics)
    TOPICS_BY_SUBJECT[subject] = all_topics


def get_topic_categories(subject):
    return TOPIC_POOLS.get(subject, {})


def get_random_topics(subject, count=8):
    all_topics = TOPICS_BY_SUBJECT.get(subject, [])
    if len(all_topics) <= count:
        return all_topics
    return random.sample(all_topics, count)


COUNTRIES = [
    ("🇮🇳", "India"), ("🇵🇰", "Pakistan"), ("🇳🇬", "Nigeria"),
    ("🇧🇩", "Bangladesh"), ("🇵🇭", "Philippines"), ("🇰🇪", "Kenya"),
    ("🇺🇬", "Uganda"), ("🇬🇭", "Ghana"), ("🇹🇿", "Tanzania"),
    ("🇿🇦", "South Africa"), ("🇷🇼", "Rwanda"), ("🇯🇲", "Jamaica"),
    ("🇺🇸", "United States"), ("🇬🇧", "United Kingdom"), ("🇦🇺", "Australia"),
]

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

# ============================================================================
# API CLIENTS
# ============================================================================

anthropic_client = Anthropic(api_key=CLAUDE_API_KEY) if CLAUDE_API_KEY else None
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ============================================================================
# SESSION STORAGE
# ============================================================================

user_sessions = {}

def get_session(user_id):
    if user_id not in user_sessions:
        user_sessions[user_id] = {'state': 'idle', 'params': {}, 'last_lesson': None, 'pending_share': False}
    return user_sessions[user_id]

def reset_session(user_id):
    user_sessions[user_id] = {'state': 'idle', 'params': {}, 'last_lesson': None, 'pending_share': False}

# ============================================================================
# LESSON GENERATION
# ============================================================================

LESSON_SYSTEM_PROMPT = """You are Tooley, an expert educational assistant helping teachers create lesson plans.
Generate clear, practical lesson plans that teachers can immediately use.
Focus on active learning, student engagement, and real-world connections.
Write in clear, simple English. Use numbered steps and bullet points for clarity.
Every section MUST have substantive content - never leave a section empty."""


def build_lesson_prompt(params):
    subject = params.get('subject', 'General')
    topic = params.get('topic', 'Introduction')
    ages = params.get('ages', '8-12')
    duration = params.get('duration', '45')
    country = params.get('country', 'Global')
    materials = params.get('materials', 'basic')
    style = params.get('style', 'mixed')
    
    materials_desc = {
        'none': 'NO MATERIALS - use only verbal activities, movement, imagination',
        'basic': 'Basic materials - paper, pencils, blackboard',
        'standard': 'Full classroom supplies available'
    }
    
    return f"""Create a {duration}-minute lesson plan on **{topic}** for {subject}.
Students are ages {ages}. Location: {country}
Materials: {materials_desc.get(materials, materials)}

Structure with these sections (all must have content):

## Learning Objectives
[3 specific, measurable objectives]

## Materials Needed
[List all required materials]

## Warm-Up (5 minutes)
[Specific activity with exact questions]

## Main Lesson ({int(duration) - 15} minutes)
[Detailed step-by-step with timing]

## Practice Activity
[Complete activity description]

## Closing (3 minutes)
[Wrap-up questions]

## Differentiation
**For students who need support:** [Strategies]
**For advanced students:** [Extensions]

## Assessment Questions
1. [Question with answer]
2. [Question with answer]
3. [Question with answer]

## Teacher Tips
- [Tip 1]
- [Tip 2]

CRITICAL: Every section must have real content."""


def generate_lesson(params):
    user_prompt = build_lesson_prompt(params)
    logger.info(f"Generating lesson: {params.get('subject')} - {params.get('topic')}")
    
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        system=LESSON_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )
    return response.content[0].text


# ============================================================================
# PDF GENERATION
# ============================================================================

class LessonPDF(FPDF):
    def __init__(self, params=None):
        super().__init__()
        self.params = params or {}
        self.set_auto_page_break(auto=True, margin=25)
        self.add_page()
    
    def header(self):
        self.set_fill_color(217, 119, 6)
        self.rect(10, 10, 4, 14, 'F')
        self.set_xy(18, 10)
        self.set_font('Helvetica', 'B', 22)
        self.set_text_color(15, 23, 42)
        self.cell(40, 14, 'tooley', align='L')
        self.set_xy(10, 24)
        self.set_font('Helvetica', '', 9)
        self.set_text_color(100, 116, 139)
        self.cell(0, 5, 'AI Lesson Plans for Teachers', align='L')
        self.set_xy(150, 14)
        self.set_font('Helvetica', '', 10)
        self.cell(50, 10, 'tooley.app', align='R')
        self.ln(12)
        self.set_draw_color(15, 23, 42)
        self.set_line_width(0.4)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(10)
    
    def footer(self):
        self.set_y(-18)
        self.set_draw_color(200, 200, 200)
        self.set_line_width(0.2)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(128, 128, 128)
        self.cell(95, 5, f'Page {self.page_no()}', align='L')
        self.cell(95, 5, 'tooley.app | Free for all teachers', align='R')
    
    def safe(self, text):
        if not text:
            return ""
        text = str(text).replace('**', '')
        # Common replacements
        replacements = {'→': '->', '←': '<-', '•': '*', '–': '-', '—': '-',
            '"': '"', '"': '"', ''': "'", ''': "'", '…': '...',
            '✓': '[x]', '✗': '[ ]', '★': '*', '☆': '*', '●': '*', '○': 'o',
            '▪': '-', '▸': '>', '◦': 'o', '✔': '[x]', '✘': '[ ]',
            '📚': '', '📖': '', '✏': '', '🎯': '', '💡': '', '⏱': '', '👥': '',
            '🔹': '-', '🔸': '-', '📝': '', '🌟': '*', '⭐': '*'}
        for old, new in replacements.items():
            text = text.replace(old, new)
        # Strip any remaining non-ASCII
        return ''.join(c if ord(c) < 128 else '' for c in text)
    
    def write_specs(self, params):
        self.set_fill_color(250, 250, 245)
        self.set_draw_color(15, 23, 42)
        self.set_line_width(0.4)
        
        specs = []
        if params.get('subject'): specs.append(('Subject', params['subject']))
        if params.get('topic'): specs.append(('Topic', params['topic']))
        if params.get('ages'): specs.append(('Ages', params['ages']))
        if params.get('duration'): specs.append(('Duration', f"{params['duration']} min"))
        if params.get('country'): specs.append(('Location', params['country']))
        if params.get('materials'):
            m = {'none': 'No materials', 'basic': 'Basic supplies', 'standard': 'Full classroom'}
            specs.append(('Materials', m.get(params['materials'], params['materials'])))
        if params.get('style'):
            s = {'interactive': 'Interactive', 'structured': 'Structured', 'storytelling': 'Story-based', 'mixed': 'Mixed'}
            specs.append(('Style', s.get(params['style'], params['style'])))
        
        box_h = 12 + len(specs) * 6
        y_start = self.get_y()
        self.rect(10, y_start, 190, box_h, 'DF')
        
        self.set_xy(15, y_start + 4)
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(217, 119, 6)
        self.cell(0, 5, 'LESSON SPECIFICATIONS')
        self.ln(7)
        
        self.set_font('Helvetica', '', 9)
        self.set_text_color(15, 23, 42)
        for label, value in specs:
            self.set_x(15)
            self.cell(35, 5, f'{label}:')
            self.cell(0, 5, self.safe(str(value)))
            self.ln(5)
        
        self.set_y(y_start + box_h + 8)
    
    def write_content(self, content):
        self.set_font('Helvetica', '', 10)
        self.set_text_color(15, 23, 42)
        
        for line in content.split('\n'):
            try:
                orig = line
                line = line.strip()
                
                if not line:
                    self.ln(3)
                    continue
                
                safe = self.safe(line)
                if not safe.strip():
                    continue
                
                # Section headers (## )
                if orig.startswith('## '):
                    self.ln(5)
                    self.set_font('Helvetica', 'B', 12)
                    self.set_text_color(15, 23, 42)
                    self.multi_cell(0, 6, safe.lstrip('# '))
                    self.set_draw_color(217, 119, 6)
                    self.set_line_width(0.5)
                    self.line(10, self.get_y() + 1, 55, self.get_y() + 1)
                    self.ln(4)
                    self.set_font('Helvetica', '', 10)
                    continue
                
                # H1 headers (# )
                if orig.startswith('# ') and not orig.startswith('## '):
                    self.ln(5)
                    self.set_font('Helvetica', 'B', 14)
                    self.set_text_color(15, 23, 42)
                    self.multi_cell(0, 7, safe.lstrip('# '))
                    self.ln(3)
                    self.set_font('Helvetica', '', 10)
                    continue
                
                # Bold lines
                if orig.startswith('**') and orig.endswith('**'):
                    self.ln(3)
                    self.set_font('Helvetica', 'B', 10)
                    self.set_text_color(51, 65, 85)
                    self.multi_cell(0, 5, safe)
                    self.set_font('Helvetica', '', 10)
                    self.set_text_color(15, 23, 42)
                    continue
                
                # Bullets
                if orig.startswith('- ') or orig.startswith('* '):
                    self.set_x(15)
                    self.multi_cell(0, 5, '* ' + self.safe(orig[2:]))
                    continue
                
                # Numbered lists
                if len(orig) > 2 and orig[0].isdigit() and orig[1] in '.):':
                    self.set_x(12)
                    self.multi_cell(0, 5, safe)
                    continue
                
                # Regular text
                self.multi_cell(0, 5, safe)
            except Exception as line_error:
                # If a single line fails, just skip it and continue
                continue


def create_lesson_pdf(content, params):
    """Generate PDF with multiple fallback levels"""
    
    # Helper to strip ALL non-ASCII
    def ascii_only(text):
        return ''.join(c if ord(c) < 128 else ' ' for c in str(text))
    
    # ATTEMPT 1: Full styled PDF
    try:
        logger.info("PDF attempt 1: Full styled")
        pdf = LessonPDF(params)
        pdf.write_specs(params)
        pdf.write_content(content)
        
        pdf_buffer = BytesIO()
        pdf_output = pdf.output()
        pdf_buffer.write(pdf_output)
        pdf_buffer.seek(0)
        logger.info(f"PDF created successfully, size: {len(pdf_output)} bytes")
        return pdf_buffer
    except Exception as e:
        logger.error(f"PDF attempt 1 failed: {e}")
        logger.error(traceback.format_exc())
    
    # ATTEMPT 2: Simple PDF with basic formatting
    try:
        logger.info("PDF attempt 2: Simple format")
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Header with branding
        pdf.set_fill_color(217, 119, 6)
        pdf.rect(10, 10, 4, 12, 'F')
        pdf.set_xy(18, 10)
        pdf.set_font('Helvetica', 'B', 18)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(40, 12, 'tooley')
        pdf.set_xy(150, 14)
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(50, 8, 'tooley.app', align='R')
        pdf.ln(20)
        
        # Specs box
        pdf.set_fill_color(255, 251, 235)
        pdf.set_draw_color(15, 23, 42)
        specs_y = pdf.get_y()
        spec_lines = []
        if params.get('subject'): spec_lines.append(f"Subject: {params['subject']}")
        if params.get('topic'): spec_lines.append(f"Topic: {params['topic']}")
        if params.get('ages'): spec_lines.append(f"Ages: {params['ages']}")
        if params.get('duration'): spec_lines.append(f"Duration: {params['duration']} min")
        if params.get('country'): spec_lines.append(f"Location: {params['country']}")
        
        box_h = 10 + len(spec_lines) * 6
        pdf.rect(10, specs_y, 190, box_h, 'DF')
        pdf.set_xy(15, specs_y + 4)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_text_color(217, 119, 6)
        pdf.cell(0, 5, 'LESSON SPECIFICATIONS')
        pdf.ln(6)
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(15, 23, 42)
        for spec in spec_lines:
            pdf.set_x(15)
            pdf.cell(0, 5, ascii_only(spec))
            pdf.ln(5)
        pdf.set_y(specs_y + box_h + 8)
        
        # Content - FULL content, no truncation
        pdf.set_font('Helvetica', '', 10)
        for line in content.split('\n'):
            safe = ascii_only(line)
            if not safe.strip():
                pdf.ln(3)
                continue
            if safe.strip().startswith('##'):
                pdf.ln(4)
                pdf.set_font('Helvetica', 'B', 12)
                pdf.multi_cell(0, 6, safe.replace('#', '').strip())
                pdf.set_font('Helvetica', '', 10)
            elif safe.strip().startswith('**') and safe.strip().endswith('**'):
                pdf.ln(2)
                pdf.set_font('Helvetica', 'B', 10)
                pdf.multi_cell(0, 5, safe.replace('*', ''))
                pdf.set_font('Helvetica', '', 10)
            elif safe.strip().startswith('- ') or safe.strip().startswith('* '):
                pdf.set_x(15)
                pdf.multi_cell(0, 5, '* ' + safe.strip()[2:])
            else:
                pdf.multi_cell(0, 5, safe)
        
        pdf_buffer = BytesIO()
        pdf_output = pdf.output()
        pdf_buffer.write(pdf_output)
        pdf_buffer.seek(0)
        logger.info(f"PDF attempt 2 success, size: {len(pdf_output)} bytes")
        return pdf_buffer
    except Exception as e2:
        logger.error(f"PDF attempt 2 failed: {e2}")
        logger.error(traceback.format_exc())
    
    # ATTEMPT 3: Minimal but still branded PDF
    try:
        logger.info("PDF attempt 3: Minimal branded")
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        
        # Header branding even in minimal mode
        pdf.set_fill_color(217, 119, 6)
        pdf.rect(10, 10, 4, 10, 'F')
        pdf.set_xy(18, 10)
        pdf.set_font('Helvetica', 'B', 16)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(40, 10, 'tooley')
        pdf.set_xy(150, 12)
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(50, 8, 'tooley.app', align='R')
        pdf.ln(16)
        
        # Content
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(15, 23, 42)
        pdf.multi_cell(0, 5, ascii_only(content))
        
        # Footer
        pdf.set_y(-15)
        pdf.set_font('Helvetica', '', 8)
        pdf.set_text_color(128, 128, 128)
        pdf.cell(0, 5, 'Generated by Tooley | tooley.app | Free for all teachers', align='C')
        
        pdf_buffer = BytesIO()
        pdf_buffer.write(pdf.output())
        pdf_buffer.seek(0)
        logger.info("PDF attempt 3 success")
        return pdf_buffer
    except Exception as e3:
        logger.error(f"PDF attempt 3 failed: {e3}")
        logger.error(traceback.format_exc())
        return None


def generate_lesson_filename(params):
    parts = ['tooley']
    subject = params.get('subject', 'lesson')
    abbrev = {'Mathematics': 'math', 'Language': 'lang', 'Science': 'science',
        'Reading': 'reading', 'Social Studies': 'social', 'Art': 'art'}
    parts.append(abbrev.get(subject, subject[:6].lower()))
    topic = params.get('topic', 'lesson')
    topic_clean = ''.join(c for c in topic.lower().replace(' ', '-')[:20] if c.isalnum() or c == '-')
    parts.append(topic_clean)
    if params.get('ages'):
        parts.append(f"ages{params['ages'].replace('-', 'to')}")
    if params.get('duration'):
        parts.append(f"{params['duration']}min")
    return '_'.join(parts)


# ============================================================================
# HTML GENERATION
# ============================================================================

def create_lesson_html(content, params):
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
        m = {'none': 'No materials', 'basic': 'Basic supplies', 'standard': 'Full classroom'}
        specs_html += f"<div class='spec'><span class='label'>Materials:</span> {m.get(params['materials'], params['materials'])}</div>"
    if params.get('style'):
        s = {'interactive': 'Interactive', 'structured': 'Structured', 'storytelling': 'Story-based', 'mixed': 'Mixed'}
        specs_html += f"<div class='spec'><span class='label'>Style:</span> {s.get(params['style'], params['style'])}</div>"
    
    content_html = ""
    in_list = False
    
    for line in content.split('\n'):
        stripped = line.strip()
        
        if not stripped:
            if in_list:
                content_html += "</ul>"
                in_list = False
            content_html += "<br>"
            continue
        
        if line.startswith('## '):
            if in_list:
                content_html += "</ul>"
                in_list = False
            content_html += f"<h2>{stripped[3:]}</h2>"
            continue
        
        if stripped.startswith('**') and stripped.endswith('**'):
            if in_list:
                content_html += "</ul>"
                in_list = False
            content_html += f"<p class='bold'>{stripped[2:-2]}</p>"
            continue
        
        if stripped.startswith('- ') or stripped.startswith('* '):
            if not in_list:
                content_html += "<ul>"
                in_list = True
            content_html += f"<li>{stripped[2:]}</li>"
            continue
        
        if len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in '.):':
            if in_list:
                content_html += "</ul>"
                in_list = False
            content_html += f"<p class='numbered'>{stripped}</p>"
            continue
        
        if in_list:
            content_html += "</ul>"
            in_list = False
        
        processed = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
        content_html += f"<p>{processed}</p>"
    
    if in_list:
        content_html += "</ul>"
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lesson Plan - {params.get('topic', 'Tooley')}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Inter', sans-serif; font-size: 14px; line-height: 1.6; color: #0f172a; background: #fff; padding: 40px; max-width: 800px; margin: 0 auto; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; padding-bottom: 16px; border-bottom: 2px solid #0f172a; margin-bottom: 24px; }}
        .logo {{ height: 36px; }}
        .tagline {{ font-size: 12px; color: #64748b; }}
        .tagline a {{ color: #d97706; text-decoration: none; }}
        .specs-box {{ background: #fffbeb; border: 1px solid #0f172a; padding: 20px 24px; margin: 0 0 32px 0; }}
        .specs-title {{ font-size: 11px; font-weight: 700; color: #d97706; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 14px; }}
        .spec {{ font-size: 14px; margin-bottom: 6px; }}
        .spec .label {{ font-weight: 600; }}
        h2 {{ font-size: 18px; font-weight: 600; color: #0f172a; margin: 28px 0 12px 0; padding-bottom: 6px; border-bottom: 2px solid #d97706; display: inline-block; }}
        p {{ margin-bottom: 12px; }}
        p.bold {{ font-weight: 600; color: #334155; margin-top: 18px; }}
        p.numbered {{ margin-left: 18px; }}
        ul {{ margin: 12px 0 12px 28px; }}
        li {{ margin-bottom: 8px; }}
        strong {{ font-weight: 600; }}
        .footer {{ margin-top: 48px; padding-top: 20px; border-top: 1px solid #e2e8f0; text-align: center; font-size: 13px; color: #64748b; }}
        .footer a {{ color: #d97706; text-decoration: none; }}
        @media print {{ body {{ padding: 20px; max-width: 100%; }} }}
    </style>
</head>
<body>
    <div class="header">
        <svg class="logo" viewBox="0 0 975 375" xmlns="http://www.w3.org/2000/svg"><g fill="#f59e0b"><path d="M87.8 289.8H55.6V149.2H22.7v-27.1h32.9v-52.5h32.2v52.5H120.8v27.1H87.8z"/><path d="M136.9 205.8c0-17.4 3.8-32.7 11.3-45.8 7.5-13.1 18-23.5 31.2-31 13.3-7.6 28.3-11.3 45-11.3s31.6 3.8 44.8 11.3c13.1 7.6 23.5 17.9 31 31 7.6 13.1 11.4 28.4 11.4 45.8 0 17.2-3.8 32.4-11.4 45.6-7.5 13.3-17.9 23.7-31 31.2-13.2 7.5-28.1 11.3-44.8 11.3s-31.7-3.8-45-11.3c-13.2-7.5-23.7-17.9-31.2-31.2-7.5-13.2-11.3-28.4-11.3-45.6zm32.6 0c0 17.4 5.1 31.6 15.3 42.7 10.2 11.1 23.4 16.6 39.6 16.6 10.8 0 20.3-2.5 28.5-7.5 8.2-5 14.7-12 19.4-20.9 4.7-8.9 7-19.2 7-30.9s-2.3-22-7-30.9c-4.7-8.9-11.2-15.9-19.4-20.9-8.2-5-17.7-7.5-28.5-7.5-16.2 0-29.4 5.5-39.6 16.5-10.2 10.9-15.3 25.2-15.3 42.8z"/><path d="M336.2 205.8c0-17.4 3.8-32.7 11.3-45.8 7.5-13.1 18-23.5 31.2-31 13.3-7.6 28.3-11.3 45-11.3s31.6 3.8 44.8 11.3c13.1 7.6 23.5 17.9 31 31 7.6 13.1 11.4 28.4 11.4 45.8 0 17.2-3.8 32.4-11.4 45.6-7.5 13.3-17.9 23.7-31 31.2-13.2 7.5-28.1 11.3-44.8 11.3s-31.7-3.8-45-11.3c-13.2-7.5-23.7-17.9-31.2-31.2-7.5-13.2-11.3-28.4-11.3-45.6zm32.6 0c0 17.4 5.1 31.6 15.3 42.7 10.2 11.1 23.4 16.6 39.6 16.6 10.8 0 20.3-2.5 28.5-7.5 8.2-5 14.7-12 19.4-20.9 4.7-8.9 7-19.2 7-30.9s-2.3-22-7-30.9c-4.7-8.9-11.2-15.9-19.4-20.9-8.2-5-17.7-7.5-28.5-7.5-16.2 0-29.4 5.5-39.6 16.5-10.2 10.9-15.3 25.2-15.3 42.8z"/><path d="M579.3 289.8h-32.2V37.3h32.2z"/><path d="M699 293.9c-16.5 0-31-3.7-43.4-11.1-12.5-7.4-22.3-17.7-29.3-30.9-7.1-13.2-10.6-28.4-10.6-45.8 0-17.6 3.4-33 10.3-46.3 6.9-13.3 16.5-23.7 28.8-31.2 12.4-7.6 26.7-11.3 42.9-11.3 16 0 29.9 3.4 41.7 10.3 11.8 6.9 21 16.5 27.5 28.8 6.5 12.3 9.8 26.9 9.8 43.6v12h-129.7c1.1 17.6 6.2 31.2 15.3 40.7 9 9.5 21.5 14.2 37.5 14.2 25.6 0 41.3-9.8 47-29.5h30.2c-4.1 18.1-12.9 32-26.4 41.7-13.5 9.7-30.7 14.8-51.6 14.8zm-1.4-149.5c-14 0-25.3 4-34 12-8.7 8-14.1 19.4-16.1 34.3h96.7c0-14-4.2-25.2-12.7-33.6-8.5-8.5-19.8-12.7-33.9-12.7z"/><path d="M791.7 365h-21.6v-26.4h21.6c7.8 0 14.7-1.3 20.8-3.9 6.1-2.6 11-9.2 14.9-19.7l5.8-16.1-67.6-176.7h33.9l48.7 135.2 49.7-135.2h33.3L852.4 328c-5.7 14.4-12.9 24.8-21.6 31.2-8.7 6.4-19.4 9.6-32.2 9.6-5.3 0-10.2-.3-14.8-1-4.5-.7-9-1.5-13.3-2.4z"/></g></svg>
        <span class="tagline">AI Lesson Plans for Teachers | <a href="https://tooley.app">tooley.app</a></span>
    </div>
    <div class="specs-box">
        <div class="specs-title">Lesson Specifications</div>
        {specs_html}
    </div>
    <div class="content">
        {content_html}
    </div>
    <div class="footer">
        Generated by <strong>Tooley</strong> | <a href="https://tooley.app">tooley.app</a> | Free for all teachers
    </div>
</body>
</html>'''
    return html


# ============================================================================
# HELPERS
# ============================================================================

def build_selection_summary(params):
    lines = ["━━━━ *Your Lesson* ━━━━"]
    if params.get('subject'): lines.append(f"📚 Subject: {params['subject']}")
    if params.get('topic'): lines.append(f"📝 Topic: {params['topic']}")
    if params.get('ages'): lines.append(f"🧒🏽 Ages: {params['ages']}")
    if params.get('duration'): lines.append(f"⏱ Duration: {params['duration']} min")
    if params.get('country'): lines.append(f"📍 Location: {params['country']}")
    if params.get('materials'):
        m = {'none': '🎭 No materials', 'basic': '📝 Basic supplies', 'standard': '📦 Full classroom'}
        lines.append(f"📦 Materials: {m.get(params['materials'], params['materials'])}")
    if params.get('style'):
        s = {'interactive': '🎮 Interactive', 'structured': '📋 Structured', 'storytelling': '📖 Story-based', 'mixed': '⚖️ Mixed'}
        lines.append(f"🎯 Style: {s.get(params['style'], params['style'])}")
    lines.append("━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def generate_lesson_id():
    timestamp = datetime.utcnow().isoformat()
    random_part = hashlib.md5(timestamp.encode()).hexdigest()[:8]
    return f"les_{random_part}"


def create_lesson_record(params, content, teacher_name=None, public=True):
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
        "content": content,
        "public": public,
    }


# ============================================================================
# GITHUB OPERATIONS
# ============================================================================

async def save_lesson_to_github(lesson):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        logger.info("GitHub not configured for lesson storage")
        return False
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            get_response = await client.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/contents/{LESSONS_FILE}",
                headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
            )
            
            if get_response.status_code == 200:
                file_data = get_response.json()
                sha = file_data["sha"]
                existing_content = base64.b64decode(file_data["content"]).decode("utf-8")
                data = json.loads(existing_content)
                lessons = data.get("lessons", [])
            else:
                sha = None
                lessons = []
            
            lessons.insert(0, lesson)
            lessons = lessons[:500]
            
            new_data = {"lastUpdated": datetime.utcnow().isoformat() + "Z", "lessons": lessons}
            encoded_content = base64.b64encode(json.dumps(new_data, indent=2).encode("utf-8")).decode("utf-8")
            
            body = {"message": f"Add lesson: {lesson.get('topic', 'New')}", "content": encoded_content}
            if sha:
                body["sha"] = sha
            
            put_response = await client.put(
                f"https://api.github.com/repos/{GITHUB_REPO}/contents/{LESSONS_FILE}",
                headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"},
                json=body
            )
            put_response.raise_for_status()
            logger.info(f"Lesson {lesson['id']} saved to GitHub")
            return True
    except Exception as e:
        logger.error(f"Error saving lesson: {e}")
        return False


async def push_lesson_to_website(lesson):
    """Push lesson to website repo for carousel display."""
    if not GITHUB_TOKEN:
        logger.warning("Website push skipped: GITHUB_TOKEN not set")
        return False
    
    if not GITHUB_WEBSITE_REPO:
        logger.warning("Website push skipped: GITHUB_WEBSITE_REPO not set")
        return False
    
    logger.info(f"Pushing to website: {GITHUB_WEBSITE_REPO}")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            get_url = f"https://api.github.com/repos/{GITHUB_WEBSITE_REPO}/contents/lessons.json"
            logger.info(f"GET {get_url}")
            
            get_response = await client.get(
                get_url,
                headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
            )
            
            logger.info(f"GET status: {get_response.status_code}")
            
            if get_response.status_code == 200:
                file_data = get_response.json()
                sha = file_data["sha"]
                existing_content = base64.b64decode(file_data["content"]).decode("utf-8")
                data = json.loads(existing_content)
                lessons = data.get("lessons", [])
                logger.info(f"Found {len(lessons)} existing lessons")
            elif get_response.status_code == 404:
                logger.info("lessons.json not found, creating new")
                sha = None
                lessons = []
            else:
                logger.error(f"Unexpected GET response: {get_response.status_code}")
                return False
            
            carousel_lesson = {
                "id": lesson.get("id", generate_lesson_id()),
                "subject": lesson.get("subject", "General"),
                "topic": lesson.get("topic", "Untitled"),
                "ages": lesson.get("ages", "All ages"),
                "duration": str(lesson.get("duration", 45)),
                "country": lesson.get("country", "Global"),
                "teacher_name": lesson.get("teacher_name", "Anonymous"),
                "public": True,
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
            
            lessons.insert(0, carousel_lesson)
            lessons = lessons[:50]
            
            website_data = {"lastUpdated": datetime.utcnow().isoformat() + "Z", "lessons": lessons}
            encoded_content = base64.b64encode(json.dumps(website_data, indent=2).encode("utf-8")).decode("utf-8")
            
            body = {
                "message": f"🎓 New lesson: {lesson.get('topic', 'Untitled')}",
                "content": encoded_content
            }
            if sha:
                body["sha"] = sha
            
            put_url = f"https://api.github.com/repos/{GITHUB_WEBSITE_REPO}/contents/lessons.json"
            logger.info(f"PUT {put_url}")
            
            put_response = await client.put(
                put_url,
                headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"},
                json=body
            )
            
            logger.info(f"PUT status: {put_response.status_code}")
            
            if put_response.status_code in [200, 201]:
                logger.info(f"✅ Pushed to website: {carousel_lesson['topic']}")
                return True
            else:
                logger.error(f"PUT failed: {put_response.text[:300]}")
                return False
    
    except Exception as e:
        logger.error(f"Website push error: {e}")
        logger.error(traceback.format_exc())
        return False


# ============================================================================
# TELEGRAM HANDLERS
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reset_session(user_id)
    logger.info(f"START from user {user_id}")
    
    keyboard = [
        [InlineKeyboardButton("⚡ Quick Lesson", callback_data="action_quick")],
        [InlineKeyboardButton("✨ Custom Lesson", callback_data="action_new")],
        [InlineKeyboardButton("❓ Help & Tips", callback_data="action_help")],
    ]
    
    await update.message.reply_text(
        "👋 *Welcome to Tooley!*\n\nI create lesson plans for teachers around the world.\n\nWhat would you like to do?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*Tooley Help*\n\n/start - Main menu\n/lesson - Start new lesson\n/help - This help\n\n*Formats:*\n📱 Chat = read in Telegram\n📄 PDF = download for printing\n🌐 HTML = opens in browser",
        parse_mode='Markdown'
    )


async def lesson_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reset_session(user_id)
    session = get_session(user_id)
    session['state'] = 'awaiting_subject'
    
    keyboard = [
        [InlineKeyboardButton("📐 Mathematics", callback_data="subject_Mathematics")],
        [InlineKeyboardButton("🔬 Science", callback_data="subject_Science")],
        [InlineKeyboardButton("📖 Reading", callback_data="subject_Reading")],
        [InlineKeyboardButton("✏️ Language Arts", callback_data="subject_Language")],
        [InlineKeyboardButton("🌍 Social Studies", callback_data="subject_Social Studies")],
        [InlineKeyboardButton("🎨 Art & Music", callback_data="subject_Art")],
        [InlineKeyboardButton("📝 Other Topic...", callback_data="subject_other")],
    ]
    
    await update.message.reply_text(
        "📚 *Let's create a lesson!*\n\nWhat subject?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


# ============================================================================
# CALLBACK HANDLER
# ============================================================================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    session = get_session(user_id)
    
    logger.info(f"=== CALLBACK: '{data}' from user {user_id} ===")
    
    # ACTION BUTTONS
    if data == "action_quick":
        logger.info(f">>> action_quick")
        keyboard = [
            [InlineKeyboardButton("📐 Mathematics", callback_data="quick_Mathematics")],
            [InlineKeyboardButton("🔬 Science", callback_data="quick_Science")],
            [InlineKeyboardButton("📖 Reading", callback_data="quick_Reading")],
            [InlineKeyboardButton("✏️ Language Arts", callback_data="quick_Language")],
            [InlineKeyboardButton("🌍 Social Studies", callback_data="quick_Social Studies")],
            [InlineKeyboardButton("🎨 Art & Music", callback_data="quick_Art")],
        ]
        await query.edit_message_text(
            "⚡ *Quick Lesson*\n\nPick a subject and I'll generate instantly!\n_Smart defaults: Ages 9-11, 30 min, basic materials_",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    if data == "action_help":
        logger.info(f">>> action_help")
        keyboard = [[InlineKeyboardButton("← Back", callback_data="action_menu")]]
        await query.edit_message_text(
            "*Tooley Help*\n\n⚡ *Quick* — Pick subject, I handle the rest\n✨ *Custom* — Full control\n\n*Formats:*\n📱 Chat = read here\n📄 PDF = print\n🌐 HTML = browser\n\n*Sharing:* Your lessons appear on tooley.app!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    if data == "action_menu":
        logger.info(f">>> action_menu")
        reset_session(user_id)
        keyboard = [
            [InlineKeyboardButton("⚡ Quick Lesson", callback_data="action_quick")],
            [InlineKeyboardButton("✨ Custom Lesson", callback_data="action_new")],
            [InlineKeyboardButton("❓ Help & Tips", callback_data="action_help")],
        ]
        await query.edit_message_text(
            "👋 *Welcome to Tooley!*\n\nWhat would you like to do?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    if data == "action_new":
        logger.info(f">>> action_new")
        reset_session(user_id)
        session = get_session(user_id)
        session['state'] = 'awaiting_subject'
        
        keyboard = [
            [InlineKeyboardButton("📐 Mathematics", callback_data="subject_Mathematics")],
            [InlineKeyboardButton("🔬 Science", callback_data="subject_Science")],
            [InlineKeyboardButton("📖 Reading", callback_data="subject_Reading")],
            [InlineKeyboardButton("✏️ Language Arts", callback_data="subject_Language")],
            [InlineKeyboardButton("🌍 Social Studies", callback_data="subject_Social Studies")],
            [InlineKeyboardButton("🎨 Art & Music", callback_data="subject_Art")],
            [InlineKeyboardButton("📝 Other Topic...", callback_data="subject_other")],
        ]
        await query.edit_message_text(
            "📚 *Custom Lesson*\n\nWhat subject?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # QUICK LESSON
    if data.startswith("quick_"):
        subject = data.replace("quick_", "")
        logger.info(f">>> quick_{subject}")
        
        session['params'] = {
            'subject': subject, 'ages': '9-11', 'duration': '30',
            'country': 'Global', 'materials': 'basic', 'style': 'mixed'
        }
        topics = TOPICS_BY_SUBJECT.get(subject, ["General lesson"])
        session['params']['topic'] = random.choice(topics)
        
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(f"{summary}\n\n⏳ *Generating...*", parse_mode='Markdown')
        
        try:
            lesson_content = generate_lesson(session['params'])
            session['last_lesson'] = lesson_content
            session['state'] = 'lesson_generated'
            
            specs = build_selection_summary(session['params'])
            full_text = f"{specs}\n\n{lesson_content}"
            
            if len(full_text) < 4000:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=full_text, parse_mode='Markdown')
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=specs, parse_mode='Markdown')
                for chunk in [lesson_content[i:i+4000] for i in range(0, len(lesson_content), 4000)]:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=chunk)
            
            try:
                pdf_buffer = create_lesson_pdf(lesson_content, session['params'])
                if pdf_buffer:
                    filename = generate_lesson_filename(session['params']) + '.pdf'
                    await context.bot.send_document(chat_id=update.effective_chat.id, document=InputFile(pdf_buffer, filename=filename), caption="📄 *PDF ready*", parse_mode='Markdown')
            except Exception as e:
                logger.error(f"PDF error: {e}")
                logger.error(traceback.format_exc())
            
            # Also send HTML for quick lesson
            try:
                html_content = create_lesson_html(lesson_content, session['params'])
                html_buffer = BytesIO(html_content.encode('utf-8'))
                html_buffer.seek(0)
                filename = generate_lesson_filename(session['params']) + '.html'
                await context.bot.send_document(chat_id=update.effective_chat.id, document=InputFile(html_buffer, filename=filename), caption="🌐 *HTML ready*", parse_mode='Markdown')
            except Exception as e:
                logger.error(f"HTML error: {e}")
                logger.error(traceback.format_exc())
            
            keyboard = [
                [InlineKeyboardButton("🌍 Share", callback_data="share_yes"),
                 InlineKeyboardButton("🔒 Private", callback_data="share_no")],
            ]
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Share with other teachers?", reply_markup=InlineKeyboardMarkup(keyboard))
        
        except Exception as e:
            logger.error(f"Quick lesson error: {e}")
            await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Error. Please try again.")
        return
    
    # FORMAT SELECTION
    if data.startswith("format_"):
        output_format = data.replace("format_", "")
        logger.info(f">>> format_{output_format}")
        
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(f"{summary}\n\n⏳ *Generating...*", parse_mode='Markdown')
        
        try:
            lesson_content = generate_lesson(session['params'])
            session['last_lesson'] = lesson_content
            session['state'] = 'lesson_generated'
            
            specs = build_selection_summary(session['params'])
            
            # Chat output
            if output_format in ['chat', 'chatpdf', 'chathtml']:
                full_text = f"{specs}\n\n{lesson_content}"
                if len(full_text) < 4000:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=full_text, parse_mode='Markdown')
                else:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=specs, parse_mode='Markdown')
                    for chunk in [lesson_content[i:i+4000] for i in range(0, len(lesson_content), 4000)]:
                        await context.bot.send_message(chat_id=update.effective_chat.id, text=chunk)
            
            # PDF output
            if output_format in ['pdf', 'chatpdf']:
                try:
                    pdf_buffer = create_lesson_pdf(lesson_content, session['params'])
                    if pdf_buffer:
                        filename = generate_lesson_filename(session['params']) + '.pdf'
                        await context.bot.send_document(chat_id=update.effective_chat.id, document=InputFile(pdf_buffer, filename=filename), caption=f"📄 *PDF ready*", parse_mode='Markdown')
                    else:
                        await context.bot.send_message(chat_id=update.effective_chat.id, text="⚠️ _PDF issue, content above._", parse_mode='Markdown')
                except Exception as e:
                    logger.error(f"PDF send error: {e}")
                    logger.error(traceback.format_exc())
                    await context.bot.send_message(chat_id=update.effective_chat.id, text="⚠️ _PDF issue, content above._", parse_mode='Markdown')
            
            # HTML output
            if output_format in ['html', 'chathtml']:
                try:
                    html_content = create_lesson_html(lesson_content, session['params'])
                    html_buffer = BytesIO(html_content.encode('utf-8'))
                    html_buffer.seek(0)
                    filename = generate_lesson_filename(session['params']) + '.html'
                    await context.bot.send_document(chat_id=update.effective_chat.id, document=InputFile(html_buffer, filename=filename), caption=f"🌐 *HTML ready*", parse_mode='Markdown')
                except Exception as e:
                    logger.error(f"HTML error: {e}")
                    logger.error(traceback.format_exc())
            
            keyboard = [
                [InlineKeyboardButton("🌍 Share", callback_data="share_yes"),
                 InlineKeyboardButton("🔒 Private", callback_data="share_no")],
            ]
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Share with other teachers?", reply_markup=InlineKeyboardMarkup(keyboard))
        
        except Exception as e:
            logger.error(f"Generation error: {e}")
            logger.error(traceback.format_exc())
            await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Error. Please try again.")
        return
    
    # SUBJECT SELECTION
    if data.startswith("subject_"):
        subject = data.replace("subject_", "")
        logger.info(f">>> subject_{subject}")
        
        if subject == "other":
            session['state'] = 'awaiting_subject_text'
            await query.edit_message_text("Type the subject:")
            return
        
        session['params']['subject'] = subject
        session['state'] = 'awaiting_topic'
        
        topics = get_random_topics(subject, 6)
        keyboard = []
        for i in range(0, len(topics), 2):
            row = [InlineKeyboardButton(topics[i][:20], callback_data=f"topic_{topics[i][:25]}")]
            if i + 1 < len(topics):
                row.append(InlineKeyboardButton(topics[i+1][:20], callback_data=f"topic_{topics[i+1][:25]}"))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🎲 Random", callback_data="topic_random")])
        keyboard.append([InlineKeyboardButton("✏️ Type own", callback_data="topic_custom")])
        
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(f"{summary}\n\nChoose a topic:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return
    
    # TOPIC SELECTION
    if data.startswith("topic_"):
        topic_action = data.replace("topic_", "")
        logger.info(f">>> topic_{topic_action}")
        
        if topic_action == "random":
            topics = TOPICS_BY_SUBJECT.get(session['params'].get('subject', 'General'), ["General"])
            session['params']['topic'] = random.choice(topics)
        elif topic_action == "custom":
            session['state'] = 'awaiting_topic_text'
            await query.edit_message_text("Type your topic:")
            return
        else:
            session['params']['topic'] = topic_action
        
        session['state'] = 'awaiting_ages'
        keyboard = [
            [InlineKeyboardButton("5-7", callback_data="ages_5-7"),
             InlineKeyboardButton("7-9", callback_data="ages_7-9"),
             InlineKeyboardButton("9-11", callback_data="ages_9-11")],
            [InlineKeyboardButton("11-13", callback_data="ages_11-13"),
             InlineKeyboardButton("13-15", callback_data="ages_13-15"),
             InlineKeyboardButton("15+", callback_data="ages_15-18")],
        ]
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(f"{summary}\n\n🧒🏽 Age group?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return
    
    # AGES
    if data.startswith("ages_"):
        session['params']['ages'] = data.replace("ages_", "")
        session['state'] = 'awaiting_duration'
        keyboard = [
            [InlineKeyboardButton("15m", callback_data="duration_15"),
             InlineKeyboardButton("30m", callback_data="duration_30"),
             InlineKeyboardButton("45m", callback_data="duration_45")],
            [InlineKeyboardButton("60m", callback_data="duration_60"),
             InlineKeyboardButton("90m", callback_data="duration_90")],
        ]
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(f"{summary}\n\n⏱ Duration?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return
    
    # DURATION
    if data.startswith("duration_"):
        session['params']['duration'] = data.replace("duration_", "")
        session['state'] = 'awaiting_country'
        keyboard = []
        for i in range(0, len(COUNTRIES), 3):
            row = []
            for j in range(3):
                if i + j < len(COUNTRIES):
                    flag, name = COUNTRIES[i + j]
                    row.append(InlineKeyboardButton(f"{flag} {name}", callback_data=f"country_{name}"))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🌍 Global", callback_data="country_Global")])
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(f"{summary}\n\n📍 Location?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return
    
    # COUNTRY
    if data.startswith("country_"):
        session['params']['country'] = data.replace("country_", "")
        session['state'] = 'awaiting_materials'
        keyboard = [
            [InlineKeyboardButton("🎭 None", callback_data="materials_none")],
            [InlineKeyboardButton("📝 Basic", callback_data="materials_basic")],
            [InlineKeyboardButton("📦 Full", callback_data="materials_standard")],
        ]
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(f"{summary}\n\n📦 Materials?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return
    
    # MATERIALS
    if data.startswith("materials_"):
        session['params']['materials'] = data.replace("materials_", "")
        session['state'] = 'awaiting_style'
        keyboard = [
            [InlineKeyboardButton("🎮 Interactive", callback_data="style_interactive")],
            [InlineKeyboardButton("📋 Structured", callback_data="style_structured")],
            [InlineKeyboardButton("📖 Story-based", callback_data="style_storytelling")],
            [InlineKeyboardButton("⚖️ Mixed", callback_data="style_mixed")],
        ]
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(f"{summary}\n\n🎯 Style?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return
    
    # STYLE → FORMAT
    if data.startswith("style_"):
        session['params']['style'] = data.replace("style_", "")
        session['state'] = 'awaiting_format'
        
        # v2.10.1 - Fixed format buttons
        keyboard = [
            [InlineKeyboardButton("📱 Chat only", callback_data="format_chat")],
            [InlineKeyboardButton("📄 PDF only", callback_data="format_pdf"),
             InlineKeyboardButton("🌐 HTML only", callback_data="format_html")],
            [InlineKeyboardButton("📱+📄 Chat+PDF", callback_data="format_chatpdf"),
             InlineKeyboardButton("📱+🌐 Chat+HTML", callback_data="format_chathtml")],
        ]
        summary = build_selection_summary(session['params'])
        await query.edit_message_text(
            f"{summary}\n\n📲 *Choose format:*\n• _Chat_ = read here\n• _PDF_ = print\n• _HTML_ = browser",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # SHARING
    if data == "share_yes":
        logger.info(f">>> share_yes")
        session['pending_share'] = True
        session['state'] = 'awaiting_teacher_name'
        await query.edit_message_text("🌍 *Thank you!*\n\nYour name? (or 'skip' for anonymous)", parse_mode='Markdown')
        return
    
    if data == "share_no":
        logger.info(f">>> share_no")
        if session.get('last_lesson'):
            lesson_record = create_lesson_record(session['params'], session['last_lesson'], public=False)
            await save_lesson_to_github(lesson_record)
        
        keyboard = [
            [InlineKeyboardButton("✨ New lesson", callback_data="action_new")],
            [InlineKeyboardButton("🏠 Menu", callback_data="action_menu")],
        ]
        await query.edit_message_text("👍 Saved privately.\n\nWhat's next?", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    logger.warning(f"Unknown callback: {data}")


# ============================================================================
# TEXT HANDLER
# ============================================================================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session(user_id)
    text = update.message.text.strip()
    state = session.get('state', 'idle')
    
    logger.info(f"Text from {user_id}: '{text[:30]}...' state={state}")
    
    if state == 'awaiting_teacher_name':
        teacher_name = "Anonymous" if text.lower() == 'skip' else text
        
        lesson_record = create_lesson_record(session['params'], session['last_lesson'], teacher_name=teacher_name, public=True)
        await save_lesson_to_github(lesson_record)
        website_pushed = await push_lesson_to_website(lesson_record)
        
        keyboard = [
            [InlineKeyboardButton("✨ New lesson", callback_data="action_new")],
            [InlineKeyboardButton("🏠 Menu", callback_data="action_menu")],
        ]
        
        if website_pushed:
            await update.message.reply_text("🎉 *Shared!*\n\n📍 Live on tooley.app!\n\nWhat's next?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.message.reply_text("🎉 *Shared!*\n\nWhat's next?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        session['state'] = 'idle'
        return
    
    if state == 'awaiting_subject_text':
        session['params']['subject'] = text
        session['state'] = 'awaiting_topic'
        keyboard = [
            [InlineKeyboardButton("🎲 Random", callback_data="topic_random")],
            [InlineKeyboardButton("✏️ Type own", callback_data="topic_custom")],
        ]
        summary = build_selection_summary(session['params'])
        await update.message.reply_text(f"{summary}\n\nTopic for {text}?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return
    
    if state == 'awaiting_topic_text':
        session['params']['topic'] = text
        session['state'] = 'awaiting_ages'
        keyboard = [
            [InlineKeyboardButton("5-7", callback_data="ages_5-7"),
             InlineKeyboardButton("7-9", callback_data="ages_7-9"),
             InlineKeyboardButton("9-11", callback_data="ages_9-11")],
            [InlineKeyboardButton("11-13", callback_data="ages_11-13"),
             InlineKeyboardButton("13-15", callback_data="ages_13-15"),
             InlineKeyboardButton("15+", callback_data="ages_15-18")],
        ]
        summary = build_selection_summary(session['params'])
        await update.message.reply_text(f"{summary}\n\n🧒🏽 Age group?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return
    
    await update.message.reply_text("Use /start to begin!")


# ============================================================================
# VOICE HANDLER
# ============================================================================

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not groq_client:
        await update.message.reply_text("Voice not configured. Please type.")
        return
    
    voice_file = await context.bot.get_file(update.message.voice.file_id)
    voice_data = await voice_file.download_as_bytearray()
    
    try:
        transcription = groq_client.audio.transcriptions.create(
            file=("voice.ogg", bytes(voice_data)),
            model="whisper-large-v3",
            language="en"
        )
        text = transcription.text.strip()
        if text:
            update.message.text = text
            await text_handler(update, context)
        else:
            await update.message.reply_text("Couldn't hear clearly. Try again?")
    except Exception as e:
        logger.error(f"Voice error: {e}")
        await update.message.reply_text("Voice error. Please type.")


# ============================================================================
# MAIN
# ============================================================================

def main():
    logger.info(f"Starting Tooley Bot v{VERSION}")
    logger.info(f"GITHUB_TOKEN: {'SET' if GITHUB_TOKEN else 'NOT SET'}")
    logger.info(f"GITHUB_REPO: {GITHUB_REPO}")
    logger.info(f"GITHUB_WEBSITE_REPO: {GITHUB_WEBSITE_REPO or 'NOT SET'}")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("lesson", lesson_command))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    application.add_handler(MessageHandler(filters.VOICE, voice_handler))
    
    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
