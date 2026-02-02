"""
Tooley - Lesson Plan Generator Bot
Telegram bot that generates customized lesson plans for teachers worldwide.

Version: 2.11.0
Last Updated: 2026-02-02

CHANGELOG:
---------
v2.11.0 (2026-02-02)
  - NEW: Multi-language support (English + Spanish)
  - NEW: Language selection at /start (remembers preference)
  - NEW: All UI strings now use translations system
  - NEW: Lessons generated in selected language via Claude prompt
  - NEW: /language command to change language anytime

v2.10.8 (2026-01-29)
  - IMPROVED: PDF header - removed "AI Lesson Plans for Teachers" text and horizontal line
  - IMPROVED: PDF logo now amber color (#d97706) instead of navy
  - IMPROVED: HTML header - removed tagline, logo now amber color (#d97706)
  - Cleaner, more minimal document headers

v2.10.7 (2026-01-29)
  - REMOVED: Version number from welcome message (cleaner UX)
  - ADDED: HTML output to Quick Lesson flow (now sends Chat + PDF + HTML)
  - IMPROVED: PDF branding in fallback attempt 3 (now has Tooley header/footer)

Stack:
- python-telegram-bot for Telegram interface
- anthropic for Claude API (lesson generation)
- groq for Whisper voice transcription
- fpdf2 for PDF generation
- GitHub API for lesson repository storage
"""

VERSION = "2.11.0"

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
# TRANSLATIONS
# ============================================================================

TRANSLATIONS = {
    "en": {
        # Language selection
        "lang_prompt": "🌐 *Choose your language:*",
        "lang_english": "🇬🇧 English",
        "lang_spanish": "🇪🇸 Español",
        "lang_changed": "✅ Language set to English",
        
        # Welcome & Menu
        "welcome": "👋 *Welcome to Tooley!*\n\nI create lesson plans for teachers around the world.\n\nWhat would you like to do?",
        "welcome_back": "👋 *Welcome to Tooley!*\n\nWhat would you like to do?",
        "quick_lesson": "⚡ Quick Lesson",
        "custom_lesson": "✨ Custom Lesson",
        "help_tips": "❓ Help & Tips",
        "change_language": "🌐 Language",
        
        # Quick Lesson
        "quick_title": "⚡ *Quick Lesson*\n\nPick a subject and I'll generate instantly!\n_Smart defaults: Ages 9-11, 30 min, basic materials_",
        
        # Subjects
        "subject_prompt": "📚 *Let's create a lesson!*\n\nWhat subject?",
        "subj_mathematics": "📐 Mathematics",
        "subj_science": "🔬 Science",
        "subj_reading": "📖 Reading",
        "subj_language": "✏️ Language Arts",
        "subj_social": "🌍 Social Studies",
        "subj_art": "🎨 Art & Music",
        "subj_other": "📝 Other Topic...",
        "subject_other_prompt": "Type your subject:",
        
        # Topic
        "topic_prompt": "📝 *Topic*\n\nChoose a suggestion or type your own:",
        "topic_custom": "✏️ Type my own",
        "topic_type_prompt": "Type your topic:",
        
        # Ages
        "ages_prompt": "🧒🏽 Age group?",
        
        # Duration
        "duration_prompt": "⏱️ Duration?",
        "min": "min",
        
        # Country
        "country_prompt": "📍 *Where do you teach?*\n\n_This helps tailor the lesson to your curriculum._",
        "country_global": "🌍 Global",
        
        # Materials
        "materials_prompt": "📦 Materials available?",
        "mat_none": "🎭 None (verbal only)",
        "mat_basic": "📝 Basic (paper, pencils)",
        "mat_standard": "📦 Full classroom",
        
        # Style
        "style_prompt": "🎯 Teaching style?",
        "style_interactive": "🎮 Interactive",
        "style_structured": "📋 Structured",
        "style_storytelling": "📖 Story-based",
        "style_mixed": "⚖️ Mixed",
        
        # Format
        "format_prompt": "📲 *Choose format:*\n• _Chat_ = read here\n• _PDF_ = print\n• _HTML_ = browser",
        "fmt_chat": "📱 Chat only",
        "fmt_pdf": "📄 PDF only",
        "fmt_html": "🌐 HTML only",
        "fmt_chatpdf": "📱+📄 Chat+PDF",
        "fmt_chathtml": "📱+🌐 Chat+HTML",
        
        # Generation
        "generating": "⏳ *Generating your lesson...*\n\n_This may take 15-30 seconds._",
        "lesson_ready": "✅ *Your lesson is ready!*",
        "generation_error": "❌ Error generating lesson. Please try again.",
        
        # Sharing
        "share_prompt": "🌍 *Share with the community?*\n\nYour lesson will appear on tooley.app for other teachers to use.",
        "share_yes": "✅ Yes, share",
        "share_no": "🔒 Keep private",
        "share_name_prompt": "🌍 *Thank you!*\n\nYour name? (or 'skip' for anonymous)",
        "share_success": "🎉 *Shared!*\n\n📍 Live on tooley.app!\n\nWhat's next?",
        "share_success_basic": "🎉 *Shared!*\n\nWhat's next?",
        "saved_private": "👍 Saved privately.\n\nWhat's next?",
        
        # Actions
        "new_lesson": "✨ New lesson",
        "menu": "🏠 Menu",
        "back": "← Back",
        
        # Summary
        "summary_header": "━━━━ *Your Lesson* ━━━━",
        "summary_footer": "━━━━━━━━━━━━━━━━━━",
        "lbl_subject": "📚 Subject",
        "lbl_topic": "📝 Topic",
        "lbl_ages": "🧒🏽 Ages",
        "lbl_duration": "⏱ Duration",
        "lbl_location": "📍 Location",
        "lbl_materials": "📦 Materials",
        "lbl_style": "🎯 Style",
        
        # Help
        "help_text": "*Tooley Help*\n\n⚡ *Quick* — Pick subject, I handle the rest\n✨ *Custom* — Full control\n\n*Formats:*\n📱 Chat = read here\n📄 PDF = print\n🌐 HTML = browser\n\n*Sharing:* Your lessons appear on tooley.app!",
        "help_command": "*Tooley Help*\n\n/start - Main menu\n/lesson - Start new lesson\n/subjects - See available subjects\n/language - Change language\n/about - About Tooley\n/feedback - Send us feedback\n/help - This help\n\n*Formats:*\n📱 Chat = read in Telegram\n📄 PDF = download for printing\n🌐 HTML = opens in browser",
        
        # About
        "about": "📚 *About Tooley*\n\nTooley is a free AI-powered lesson plan generator built for teachers in low-resource schools.\n\n🎯 *Our Mission*\nEvery teacher deserves quality lesson plans, regardless of resources or location.\n\n✨ *Features*\n• Create complete lesson plans in minutes\n• Curriculum-aligned content\n• Multiple subjects supported\n• Download as PDF for offline use\n• Always free\n\n🌍 *Community*\nJoin thousands of teachers worldwide using Tooley.\n\n💛 Built with love for teachers everywhere.\n\n🔗 tooley.app",
        
        # Subjects list
        "subjects_list": "📚 *Available Subjects*\n\n📐 *Mathematics* - Numbers, geometry, algebra, problem-solving\n\n🔬 *Science* - Biology, physics, chemistry, nature\n\n📖 *Reading* - Comprehension, phonics, literature\n\n✏️ *Language Arts* - Writing, grammar, vocabulary\n\n🌍 *Social Studies* - History, geography, civics\n\n🎨 *Art & Music* - Creative expression, crafts\n\n📝 *Other* - Any custom topic you need!\n\nReady? Use /lesson to create a plan!",
        
        # Feedback
        "feedback_prompt": "💬 *We'd love your feedback!*\n\nTell us:\n• What's working well?\n• What could be better?\n• What features would you like?\n\nJust type your message and send it.\n\n_Your feedback helps us improve Tooley for teachers everywhere._",
        "feedback_thanks": "🙏 *Thank you for your feedback!*\n\nYour input helps us make Tooley better for teachers everywhere.\n\nWhat would you like to do next?",
        
        # Errors
        "voice_not_configured": "Voice not configured. Please type.",
        "voice_error": "Voice error. Please type.",
        "voice_unclear": "Couldn't hear clearly. Try again?",
        "use_start": "Use /start to begin!",
        
        # PDF/HTML labels
        "pdf_specs_title": "LESSON SPECIFICATIONS",
        "pdf_footer": "tooley.app | Free for all teachers",
    },
    
    "es": {
        # Language selection
        "lang_prompt": "🌐 *Elige tu idioma:*",
        "lang_english": "🇬🇧 English",
        "lang_spanish": "🇪🇸 Español",
        "lang_changed": "✅ Idioma configurado: Español",
        
        # Welcome & Menu
        "welcome": "👋 *¡Bienvenido a Tooley!*\n\nCreo planes de lección para docentes de todo el mundo.\n\n¿Qué te gustaría hacer?",
        "welcome_back": "👋 *¡Bienvenido a Tooley!*\n\n¿Qué te gustaría hacer?",
        "quick_lesson": "⚡ Lección Rápida",
        "custom_lesson": "✨ Lección Personalizada",
        "help_tips": "❓ Ayuda",
        "change_language": "🌐 Idioma",
        
        # Quick Lesson
        "quick_title": "⚡ *Lección Rápida*\n\n¡Elige una materia y generaré al instante!\n_Valores predeterminados: 9-11 años, 30 min, materiales básicos_",
        
        # Subjects
        "subject_prompt": "📚 *¡Creemos una lección!*\n\n¿Qué materia?",
        "subj_mathematics": "📐 Matemáticas",
        "subj_science": "🔬 Ciencias",
        "subj_reading": "📖 Lectura",
        "subj_language": "✏️ Lenguaje",
        "subj_social": "🌍 Estudios Sociales",
        "subj_art": "🎨 Arte y Música",
        "subj_other": "📝 Otro Tema...",
        "subject_other_prompt": "Escribe tu materia:",
        
        # Topic
        "topic_prompt": "📝 *Tema*\n\nElige una sugerencia o escribe el tuyo:",
        "topic_custom": "✏️ Escribir mi tema",
        "topic_type_prompt": "Escribe tu tema:",
        
        # Ages
        "ages_prompt": "🧒🏽 ¿Grupo de edad?",
        
        # Duration
        "duration_prompt": "⏱️ ¿Duración?",
        "min": "min",
        
        # Country
        "country_prompt": "📍 *¿Dónde enseñas?*\n\n_Esto ayuda a adaptar la lección a tu currículo._",
        "country_global": "🌍 Global",
        
        # Materials
        "materials_prompt": "📦 ¿Materiales disponibles?",
        "mat_none": "🎭 Ninguno (solo verbal)",
        "mat_basic": "📝 Básicos (papel, lápices)",
        "mat_standard": "📦 Aula completa",
        
        # Style
        "style_prompt": "🎯 ¿Estilo de enseñanza?",
        "style_interactive": "🎮 Interactivo",
        "style_structured": "📋 Estructurado",
        "style_storytelling": "📖 Narrativo",
        "style_mixed": "⚖️ Mixto",
        
        # Format
        "format_prompt": "📲 *Elige formato:*\n• _Chat_ = leer aquí\n• _PDF_ = imprimir\n• _HTML_ = navegador",
        "fmt_chat": "📱 Solo Chat",
        "fmt_pdf": "📄 Solo PDF",
        "fmt_html": "🌐 Solo HTML",
        "fmt_chatpdf": "📱+📄 Chat+PDF",
        "fmt_chathtml": "📱+🌐 Chat+HTML",
        
        # Generation
        "generating": "⏳ *Generando tu lección...*\n\n_Esto puede tomar 15-30 segundos._",
        "lesson_ready": "✅ *¡Tu lección está lista!*",
        "generation_error": "❌ Error al generar la lección. Por favor, intenta de nuevo.",
        
        # Sharing
        "share_prompt": "🌍 *¿Compartir con la comunidad?*\n\nTu lección aparecerá en tooley.app para que otros docentes la usen.",
        "share_yes": "✅ Sí, compartir",
        "share_no": "🔒 Mantener privado",
        "share_name_prompt": "🌍 *¡Gracias!*\n\n¿Tu nombre? (o 'skip' para anónimo)",
        "share_success": "🎉 *¡Compartido!*\n\n📍 ¡En vivo en tooley.app!\n\n¿Qué sigue?",
        "share_success_basic": "🎉 *¡Compartido!*\n\n¿Qué sigue?",
        "saved_private": "👍 Guardado de forma privada.\n\n¿Qué sigue?",
        
        # Actions
        "new_lesson": "✨ Nueva lección",
        "menu": "🏠 Menú",
        "back": "← Atrás",
        
        # Summary
        "summary_header": "━━━━ *Tu Lección* ━━━━",
        "summary_footer": "━━━━━━━━━━━━━━━━━━",
        "lbl_subject": "📚 Materia",
        "lbl_topic": "📝 Tema",
        "lbl_ages": "🧒🏽 Edades",
        "lbl_duration": "⏱ Duración",
        "lbl_location": "📍 Ubicación",
        "lbl_materials": "📦 Materiales",
        "lbl_style": "🎯 Estilo",
        
        # Help
        "help_text": "*Ayuda de Tooley*\n\n⚡ *Rápida* — Elige materia, yo hago el resto\n✨ *Personalizada* — Control total\n\n*Formatos:*\n📱 Chat = leer aquí\n📄 PDF = imprimir\n🌐 HTML = navegador\n\n*Compartir:* ¡Tus lecciones aparecen en tooley.app!",
        "help_command": "*Ayuda de Tooley*\n\n/start - Menú principal\n/lesson - Nueva lección\n/subjects - Ver materias\n/language - Cambiar idioma\n/about - Acerca de Tooley\n/feedback - Enviar comentarios\n/help - Esta ayuda\n\n*Formatos:*\n📱 Chat = leer en Telegram\n📄 PDF = descargar para imprimir\n🌐 HTML = abrir en navegador",
        
        # About
        "about": "📚 *Acerca de Tooley*\n\nTooley es un generador gratuito de planes de lección impulsado por IA, creado para docentes en escuelas con recursos limitados.\n\n🎯 *Nuestra Misión*\nTodos los docentes merecen planes de lección de calidad, sin importar los recursos o la ubicación.\n\n✨ *Características*\n• Crea planes de lección completos en minutos\n• Contenido alineado al currículo\n• Múltiples materias disponibles\n• Descarga como PDF para uso sin conexión\n• Siempre gratis\n\n🌍 *Comunidad*\nÚnete a miles de docentes en todo el mundo usando Tooley.\n\n💛 Hecho con amor para docentes de todo el mundo.\n\n🔗 tooley.app",
        
        # Subjects list
        "subjects_list": "📚 *Materias Disponibles*\n\n📐 *Matemáticas* - Números, geometría, álgebra, resolución de problemas\n\n🔬 *Ciencias* - Biología, física, química, naturaleza\n\n📖 *Lectura* - Comprensión, fonética, literatura\n\n✏️ *Lenguaje* - Escritura, gramática, vocabulario\n\n🌍 *Estudios Sociales* - Historia, geografía, civismo\n\n🎨 *Arte y Música* - Expresión creativa, manualidades\n\n📝 *Otro* - ¡Cualquier tema que necesites!\n\n¿Listo? ¡Usa /lesson para crear un plan!",
        
        # Feedback
        "feedback_prompt": "💬 *¡Nos encantaría recibir tus comentarios!*\n\nCuéntanos:\n• ¿Qué está funcionando bien?\n• ¿Qué podría mejorar?\n• ¿Qué características te gustarían?\n\nSolo escribe tu mensaje y envíalo.\n\n_Tus comentarios nos ayudan a mejorar Tooley para docentes de todo el mundo._",
        "feedback_thanks": "🙏 *¡Gracias por tus comentarios!*\n\nTu opinión nos ayuda a hacer Tooley mejor para docentes de todo el mundo.\n\n¿Qué te gustaría hacer ahora?",
        
        # Errors
        "voice_not_configured": "Voz no configurada. Por favor, escribe.",
        "voice_error": "Error de voz. Por favor, escribe.",
        "voice_unclear": "No se escuchó claramente. ¿Intentar de nuevo?",
        "use_start": "¡Usa /start para comenzar!",
        
        # PDF/HTML labels
        "pdf_specs_title": "ESPECIFICACIONES DE LA LECCIÓN",
        "pdf_footer": "tooley.app | Gratis para todos los docentes",
    }
}

# Country names in both languages
COUNTRIES_TRANSLATED = {
    "en": [
        ("🇮🇳", "India"), ("🇵🇰", "Pakistan"), ("🇳🇬", "Nigeria"),
        ("🇧🇩", "Bangladesh"), ("🇵🇭", "Philippines"), ("🇰🇪", "Kenya"),
        ("🇺🇬", "Uganda"), ("🇬🇭", "Ghana"), ("🇹🇿", "Tanzania"),
        ("🇿🇦", "South Africa"), ("🇷🇼", "Rwanda"), ("🇯🇲", "Jamaica"),
        ("🇺🇸", "United States"), ("🇬🇧", "United Kingdom"), ("🇦🇺", "Australia"),
    ],
    "es": [
        ("🇮🇳", "India"), ("🇵🇰", "Pakistán"), ("🇳🇬", "Nigeria"),
        ("🇧🇩", "Bangladesh"), ("🇵🇭", "Filipinas"), ("🇰🇪", "Kenia"),
        ("🇺🇬", "Uganda"), ("🇬🇭", "Ghana"), ("🇹🇿", "Tanzania"),
        ("🇿🇦", "Sudáfrica"), ("🇷🇼", "Ruanda"), ("🇯🇲", "Jamaica"),
        ("🇺🇸", "Estados Unidos"), ("🇬🇧", "Reino Unido"), ("🇦🇺", "Australia"),
    ]
}

def t(key, lang="en"):
    """Get translated string"""
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, TRANSLATIONS["en"].get(key, key))

def get_countries(lang="en"):
    """Get country list for language"""
    return COUNTRIES_TRANSLATED.get(lang, COUNTRIES_TRANSLATED["en"])

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
        user_sessions[user_id] = {
            'state': 'idle',
            'params': {},
            'last_lesson': None,
            'pending_share': False,
            'lang': None  # None = not yet selected
        }
    return user_sessions[user_id]

def reset_session(user_id):
    lang = user_sessions.get(user_id, {}).get('lang')  # Preserve language
    user_sessions[user_id] = {
        'state': 'idle',
        'params': {},
        'last_lesson': None,
        'pending_share': False,
        'lang': lang
    }

def get_lang(user_id):
    """Get user's language, default to English"""
    session = get_session(user_id)
    return session.get('lang') or 'en'

# ============================================================================
# LESSON GENERATION
# ============================================================================

LESSON_SYSTEM_PROMPT = """You are Tooley, an expert educational assistant helping teachers create lesson plans.
Generate clear, practical lesson plans that teachers can immediately use.
Focus on active learning, student engagement, and real-world connections.
Every section MUST have substantive content - never leave a section empty."""


def build_lesson_prompt(params, lang="en"):
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
    
    # Language instruction
    if lang == "es":
        lang_instruction = "\n\n**IMPORTANT: Generate this entire lesson plan in SPANISH (Español).**\n"
    else:
        lang_instruction = "\n\nWrite in clear, simple English."
    
    return f"""Create a {duration}-minute lesson plan on **{topic}** for {subject}.
Students are ages {ages}. Location: {country}
Materials: {materials_desc.get(materials, materials)}
{lang_instruction}

Use numbered steps and bullet points for clarity.

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


def generate_lesson(params, lang="en"):
    user_prompt = build_lesson_prompt(params, lang)
    logger.info(f"Generating lesson: {params.get('subject')} - {params.get('topic')} (lang={lang})")
    
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
    def __init__(self, params=None, lang="en"):
        super().__init__()
        self.params = params or {}
        self.lang = lang
        self.set_auto_page_break(auto=True, margin=25)
        self.add_page()
    
    def header(self):
        # Amber bar
        self.set_fill_color(217, 119, 6)
        self.rect(10, 10, 4, 14, 'F')
        # Logo text in amber
        self.set_xy(18, 10)
        self.set_font('Helvetica', 'B', 22)
        self.set_text_color(217, 119, 6)
        self.cell(40, 14, 'tooley', align='L')
        # URL on right
        self.set_xy(150, 14)
        self.set_font('Helvetica', '', 10)
        self.set_text_color(100, 116, 139)
        self.cell(50, 10, 'tooley.app', align='R')
        self.ln(18)
    
    def footer(self):
        self.set_y(-18)
        self.set_draw_color(200, 200, 200)
        self.set_line_width(0.2)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(128, 128, 128)
        self.cell(95, 5, f'Page {self.page_no()}', align='L')
        self.cell(95, 5, t('pdf_footer', self.lang), align='R')
    
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
            '🔹': '-', '🔸': '-', '📝': '', '🌟': '*', '⭐': '*',
            'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
            'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
            'ñ': 'n', 'Ñ': 'N', '¿': '?', '¡': '!'}
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
        self.cell(0, 5, t('pdf_specs_title', self.lang))
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
                
                if safe.startswith('## '):
                    self.ln(5)
                    self.set_font('Helvetica', 'B', 12)
                    self.set_text_color(217, 119, 6)
                    self.multi_cell(0, 6, safe[3:])
                    self.set_font('Helvetica', '', 10)
                    self.set_text_color(15, 23, 42)
                    self.ln(2)
                elif safe.startswith('# '):
                    self.ln(5)
                    self.set_font('Helvetica', 'B', 14)
                    self.multi_cell(0, 7, safe[2:])
                    self.set_font('Helvetica', '', 10)
                    self.ln(2)
                elif safe.startswith('- ') or safe.startswith('* '):
                    self.set_x(15)
                    self.multi_cell(0, 5, f"  {safe}")
                elif len(safe) > 2 and safe[0].isdigit() and safe[1] in '.):':
                    self.set_x(15)
                    self.multi_cell(0, 5, safe)
                else:
                    self.multi_cell(0, 5, safe)
                    self.ln(1)
            except Exception as e:
                logger.warning(f"PDF line error: {e}")
                continue


def create_lesson_pdf(content, params, lang="en"):
    logger.info("Creating PDF...")
    
    # Attempt 1: Full formatting
    try:
        pdf = LessonPDF(params, lang)
        pdf.write_specs(params)
        pdf.write_content(content)
        buffer = BytesIO()
        pdf.output(buffer)
        buffer.seek(0)
        data = buffer.getvalue()
        logger.info(f"PDF created: {len(data)} bytes")
        if len(data) > 500:
            return data
    except Exception as e:
        logger.error(f"PDF attempt 1 failed: {e}")
    
    # Attempt 2: Simpler formatting
    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font('Helvetica', '', 10)
        
        # Simple header
        pdf.set_font('Helvetica', 'B', 16)
        pdf.cell(0, 10, 'Tooley Lesson Plan', ln=True)
        pdf.set_font('Helvetica', '', 10)
        pdf.ln(5)
        
        # Safe content
        safe_content = content.replace('**', '')
        for char in ['→', '←', '•', '–', '—', '"', '"', ''', ''', '…', '✓', '✗', '★', '☆', '●', '○']:
            safe_content = safe_content.replace(char, '-')
        safe_content = ''.join(c if ord(c) < 128 else '' for c in safe_content)
        
        for line in safe_content.split('\n'):
            line = line.strip()
            if line:
                try:
                    pdf.multi_cell(0, 5, line[:500])
                except:
                    pass
            else:
                pdf.ln(3)
        
        buffer = BytesIO()
        pdf.output(buffer)
        buffer.seek(0)
        data = buffer.getvalue()
        logger.info(f"PDF (simple) created: {len(data)} bytes")
        if len(data) > 500:
            return data
    except Exception as e:
        logger.error(f"PDF attempt 2 failed: {e}")
    
    # Attempt 3: Minimal with branding
    try:
        pdf = FPDF()
        pdf.add_page()
        
        # Amber bar + logo
        pdf.set_fill_color(217, 119, 6)
        pdf.rect(10, 10, 4, 14, 'F')
        pdf.set_xy(18, 10)
        pdf.set_font('Helvetica', 'B', 22)
        pdf.set_text_color(217, 119, 6)
        pdf.cell(40, 14, 'tooley', align='L')
        pdf.set_xy(150, 14)
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(50, 10, 'tooley.app', align='R')
        pdf.ln(25)
        
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(0, 0, 0)
        
        ascii_content = ''.join(c if ord(c) < 128 else ' ' for c in content)
        ascii_content = ascii_content.replace('**', '')
        
        for line in ascii_content.split('\n')[:200]:
            line = line.strip()[:200]
            if line:
                try:
                    pdf.multi_cell(0, 5, line)
                except:
                    pass
            pdf.ln(2)
        
        buffer = BytesIO()
        pdf.output(buffer)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        logger.error(f"PDF attempt 3 failed: {e}")
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

def create_lesson_html(content, params, lang="en"):
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
    
    footer_text = t('pdf_footer', lang)
    
    html = f'''<!DOCTYPE html>
<html lang="{lang}">
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
        <svg class="logo" viewBox="0 0 975 375" xmlns="http://www.w3.org/2000/svg"><g fill="#d97706"><path d="M87.8 289.8H55.6V149.2H22.7v-27.1h32.9v-52.5h32.2v52.5H120.8v27.1H87.8z"/><path d="M136.9 205.8c0-17.4 3.8-32.7 11.3-45.8 7.5-13.1 18-23.5 31.2-31 13.3-7.6 28.3-11.3 45-11.3s31.6 3.8 44.8 11.3c13.1 7.6 23.5 17.9 31 31 7.6 13.1 11.4 28.4 11.4 45.8 0 17.2-3.8 32.4-11.4 45.6-7.5 13.3-17.9 23.7-31 31.2-13.2 7.5-28.1 11.3-44.8 11.3s-31.7-3.8-45-11.3c-13.2-7.5-23.7-17.9-31.2-31.2-7.5-13.2-11.3-28.4-11.3-45.6zm32.6 0c0 17.4 5.1 31.6 15.3 42.7 10.2 11.1 23.4 16.6 39.6 16.6 10.8 0 20.3-2.5 28.5-7.5 8.2-5 14.7-12 19.4-20.9 4.7-8.9 7-19.2 7-30.9s-2.3-22-7-30.9c-4.7-8.9-11.2-15.9-19.4-20.9-8.2-5-17.7-7.5-28.5-7.5-16.2 0-29.4 5.5-39.6 16.5-10.2 10.9-15.3 25.2-15.3 42.8z"/><path d="M336.2 205.8c0-17.4 3.8-32.7 11.3-45.8 7.5-13.1 18-23.5 31.2-31 13.3-7.6 28.3-11.3 45-11.3s31.6 3.8 44.8 11.3c13.1 7.6 23.5 17.9 31 31 7.6 13.1 11.4 28.4 11.4 45.8 0 17.2-3.8 32.4-11.4 45.6-7.5 13.3-17.9 23.7-31 31.2-13.2 7.5-28.1 11.3-44.8 11.3s-31.7-3.8-45-11.3c-13.2-7.5-23.7-17.9-31.2-31.2-7.5-13.2-11.3-28.4-11.3-45.6zm32.6 0c0 17.4 5.1 31.6 15.3 42.7 10.2 11.1 23.4 16.6 39.6 16.6 10.8 0 20.3-2.5 28.5-7.5 8.2-5 14.7-12 19.4-20.9 4.7-8.9 7-19.2 7-30.9s-2.3-22-7-30.9c-4.7-8.9-11.2-15.9-19.4-20.9-8.2-5-17.7-7.5-28.5-7.5-16.2 0-29.4 5.5-39.6 16.5-10.2 10.9-15.3 25.2-15.3 42.8z"/><path d="M579.3 289.8h-32.2V37.3h32.2z"/><path d="M699 293.9c-16.5 0-31-3.7-43.4-11.1-12.5-7.4-22.3-17.7-29.3-30.9-7.1-13.2-10.6-28.4-10.6-45.8 0-17.6 3.4-33 10.3-46.3 6.9-13.3 16.5-23.7 28.8-31.2 12.4-7.6 26.7-11.3 42.9-11.3 16 0 29.9 3.4 41.7 10.3 11.8 6.9 21 16.5 27.5 28.8 6.5 12.3 9.8 26.9 9.8 43.6v12h-129.7c1.1 17.6 6.2 31.2 15.3 40.7 9 9.5 21.5 14.2 37.5 14.2 25.6 0 41.3-9.8 47-29.5h30.2c-4.1 18.1-12.9 32-26.4 41.7-13.5 9.7-30.7 14.8-51.6 14.8zm-1.4-149.5c-14 0-25.3 4-34 12-8.7 8-14.1 19.4-16.1 34.3h96.7c0-14-4.2-25.2-12.7-33.6-8.5-8.5-19.8-12.7-33.9-12.7z"/><path d="M791.7 365h-21.6v-26.4h21.6c7.8 0 14.7-1.3 20.8-3.9 6.1-2.6 11-9.2 14.9-19.7l5.8-16.1-67.6-176.7h33.9l48.7 135.2 49.7-135.2h33.3L852.4 328c-5.7 14.4-12.9 24.8-21.6 31.2-8.7 6.4-19.4 9.6-32.2 9.6-5.3 0-10.2-.3-14.8-1-4.5-.7-9-1.5-13.3-2.4z"/></g></svg>
        <span class="tagline"><a href="https://tooley.app">tooley.app</a></span>
    </div>
    <div class="specs-box">
        <div class="specs-title">{t('pdf_specs_title', lang)}</div>
        {specs_html}
    </div>
    <div class="content">
        {content_html}
    </div>
    <div class="footer">
        Generated by <strong>Tooley</strong> | <a href="https://tooley.app">tooley.app</a> | {footer_text}
    </div>
</body>
</html>'''
    return html


# ============================================================================
# HELPERS
# ============================================================================

def build_selection_summary(params, lang="en"):
    lines = [t('summary_header', lang)]
    if params.get('subject'): lines.append(f"{t('lbl_subject', lang)}: {params['subject']}")
    if params.get('topic'): lines.append(f"{t('lbl_topic', lang)}: {params['topic']}")
    if params.get('ages'): lines.append(f"{t('lbl_ages', lang)}: {params['ages']}")
    if params.get('duration'): lines.append(f"{t('lbl_duration', lang)}: {params['duration']} {t('min', lang)}")
    if params.get('country'): lines.append(f"{t('lbl_location', lang)}: {params['country']}")
    if params.get('materials'):
        m = {'none': t('mat_none', lang), 'basic': t('mat_basic', lang), 'standard': t('mat_standard', lang)}
        lines.append(f"{t('lbl_materials', lang)}: {m.get(params['materials'], params['materials'])}")
    if params.get('style'):
        s = {'interactive': t('style_interactive', lang), 'structured': t('style_structured', lang),
             'storytelling': t('style_storytelling', lang), 'mixed': t('style_mixed', lang)}
        lines.append(f"{t('lbl_style', lang)}: {s.get(params['style'], params['style'])}")
    lines.append(t('summary_footer', lang))
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
                existing = json.loads(base64.b64decode(file_data['content']).decode('utf-8'))
                sha = file_data['sha']
            else:
                existing = {"lessons": []}
                sha = None
            
            existing["lessons"].insert(0, lesson)
            existing["lessons"] = existing["lessons"][:100]
            
            new_content = base64.b64encode(json.dumps(existing, indent=2).encode('utf-8')).decode('utf-8')
            
            body = {
                "message": f"Add lesson: {lesson['topic']}",
                "content": new_content,
            }
            if sha:
                body["sha"] = sha
            
            put_response = await client.put(
                f"https://api.github.com/repos/{GITHUB_REPO}/contents/{LESSONS_FILE}",
                headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"},
                json=body
            )
            
            if put_response.status_code in [200, 201]:
                logger.info(f"Saved to GitHub: {lesson['topic']}")
                return True
            else:
                logger.error(f"GitHub save failed: {put_response.text[:200]}")
                return False
    
    except Exception as e:
        logger.error(f"GitHub error: {e}")
        return False


async def push_lesson_to_website(lesson):
    if not GITHUB_TOKEN or not GITHUB_WEBSITE_REPO:
        logger.info("Website repo not configured")
        return False
    
    try:
        carousel_lesson = {
            "id": lesson["id"],
            "subject": lesson["subject"],
            "topic": lesson["topic"],
            "ages": lesson["ages"],
            "duration": lesson["duration"],
            "country": lesson["country"],
            "teacher": lesson.get("teacher_name", "Anonymous"),
            "created": lesson["created"],
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            get_url = f"https://api.github.com/repos/{GITHUB_WEBSITE_REPO}/contents/lessons.json"
            get_response = await client.get(
                get_url,
                headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
            )
            
            logger.info(f"GET status: {get_response.status_code}")
            
            if get_response.status_code == 200:
                file_data = get_response.json()
                existing = json.loads(base64.b64decode(file_data['content']).decode('utf-8'))
                sha = file_data['sha']
            else:
                existing = {"lessons": []}
                sha = None
            
            existing["lessons"].insert(0, carousel_lesson)
            existing["lessons"] = existing["lessons"][:20]
            
            new_content = base64.b64encode(json.dumps(existing, indent=2).encode('utf-8')).decode('utf-8')
            
            body = {
                "message": f"Add lesson: {carousel_lesson['topic']}",
                "content": new_content,
            }
            if sha:
                body["sha"] = sha
            
            put_url = f"https://api.github.com/repos/{GITHUB_WEBSITE_REPO}/contents/lessons.json"
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
    session = get_session(user_id)
    
    logger.info(f"START from user {user_id}")
    
    # If no language set, ask for language first
    if session.get('lang') is None:
        session['state'] = 'awaiting_language'
        keyboard = [
            [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
            [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
        ]
        await update.message.reply_text(
            "🌐 *Choose your language / Elige tu idioma:*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # Language already set, show main menu
    lang = get_lang(user_id)
    keyboard = [
        [InlineKeyboardButton(t('quick_lesson', lang), callback_data="action_quick")],
        [InlineKeyboardButton(t('custom_lesson', lang), callback_data="action_new")],
        [InlineKeyboardButton(t('help_tips', lang), callback_data="action_help")],
        [InlineKeyboardButton(t('change_language', lang), callback_data="action_language")],
    ]
    
    await update.message.reply_text(
        t('welcome', lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change language anytime with /language"""
    user_id = update.effective_user.id
    session = get_session(user_id)
    session['state'] = 'awaiting_language'
    
    keyboard = [
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
    ]
    await update.message.reply_text(
        "🌐 *Choose your language / Elige tu idioma:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    await update.message.reply_text(t('help_command', lang), parse_mode='Markdown')


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    await update.message.reply_text(t('about', lang), parse_mode='Markdown')


async def subjects_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    await update.message.reply_text(t('subjects_list', lang), parse_mode='Markdown')


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session(user_id)
    lang = get_lang(user_id)
    session['state'] = 'awaiting_feedback'
    
    await update.message.reply_text(t('feedback_prompt', lang), parse_mode='Markdown')


async def lesson_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reset_session(user_id)
    session = get_session(user_id)
    lang = get_lang(user_id)
    session['state'] = 'awaiting_subject'
    
    keyboard = [
        [InlineKeyboardButton(t('subj_mathematics', lang), callback_data="subject_Mathematics")],
        [InlineKeyboardButton(t('subj_science', lang), callback_data="subject_Science")],
        [InlineKeyboardButton(t('subj_reading', lang), callback_data="subject_Reading")],
        [InlineKeyboardButton(t('subj_language', lang), callback_data="subject_Language")],
        [InlineKeyboardButton(t('subj_social', lang), callback_data="subject_Social Studies")],
        [InlineKeyboardButton(t('subj_art', lang), callback_data="subject_Art")],
        [InlineKeyboardButton(t('subj_other', lang), callback_data="subject_other")],
    ]
    
    await update.message.reply_text(
        t('subject_prompt', lang),
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
    lang = get_lang(user_id)
    
    logger.info(f"=== CALLBACK: '{data}' from user {user_id} (lang={lang}) ===")
    
    # LANGUAGE SELECTION
    if data.startswith("lang_"):
        selected_lang = data.replace("lang_", "")
        session['lang'] = selected_lang
        session['state'] = 'idle'
        lang = selected_lang
        
        keyboard = [
            [InlineKeyboardButton(t('quick_lesson', lang), callback_data="action_quick")],
            [InlineKeyboardButton(t('custom_lesson', lang), callback_data="action_new")],
            [InlineKeyboardButton(t('help_tips', lang), callback_data="action_help")],
            [InlineKeyboardButton(t('change_language', lang), callback_data="action_language")],
        ]
        
        await query.edit_message_text(
            f"{t('lang_changed', lang)}\n\n{t('welcome_back', lang)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # ACTION: Change language
    if data == "action_language":
        session['state'] = 'awaiting_language'
        keyboard = [
            [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
            [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
        ]
        await query.edit_message_text(
            "🌐 *Choose your language / Elige tu idioma:*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # ACTION: Quick Lesson
    if data == "action_quick":
        logger.info(f">>> action_quick")
        keyboard = [
            [InlineKeyboardButton(t('subj_mathematics', lang), callback_data="quick_Mathematics")],
            [InlineKeyboardButton(t('subj_science', lang), callback_data="quick_Science")],
            [InlineKeyboardButton(t('subj_reading', lang), callback_data="quick_Reading")],
            [InlineKeyboardButton(t('subj_language', lang), callback_data="quick_Language")],
            [InlineKeyboardButton(t('subj_social', lang), callback_data="quick_Social Studies")],
            [InlineKeyboardButton(t('subj_art', lang), callback_data="quick_Art")],
        ]
        await query.edit_message_text(
            t('quick_title', lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # ACTION: Help
    if data == "action_help":
        logger.info(f">>> action_help")
        keyboard = [[InlineKeyboardButton(t('back', lang), callback_data="action_menu")]]
        await query.edit_message_text(
            t('help_text', lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # ACTION: Menu
    if data == "action_menu":
        logger.info(f">>> action_menu")
        reset_session(user_id)
        keyboard = [
            [InlineKeyboardButton(t('quick_lesson', lang), callback_data="action_quick")],
            [InlineKeyboardButton(t('custom_lesson', lang), callback_data="action_new")],
            [InlineKeyboardButton(t('help_tips', lang), callback_data="action_help")],
            [InlineKeyboardButton(t('change_language', lang), callback_data="action_language")],
        ]
        await query.edit_message_text(
            t('welcome_back', lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # ACTION: New custom lesson
    if data == "action_new":
        logger.info(f">>> action_new")
        reset_session(user_id)
        session = get_session(user_id)
        session['state'] = 'awaiting_subject'
        
        keyboard = [
            [InlineKeyboardButton(t('subj_mathematics', lang), callback_data="subject_Mathematics")],
            [InlineKeyboardButton(t('subj_science', lang), callback_data="subject_Science")],
            [InlineKeyboardButton(t('subj_reading', lang), callback_data="subject_Reading")],
            [InlineKeyboardButton(t('subj_language', lang), callback_data="subject_Language")],
            [InlineKeyboardButton(t('subj_social', lang), callback_data="subject_Social Studies")],
            [InlineKeyboardButton(t('subj_art', lang), callback_data="subject_Art")],
            [InlineKeyboardButton(t('subj_other', lang), callback_data="subject_other")],
        ]
        await query.edit_message_text(
            t('subject_prompt', lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # QUICK LESSON - generate immediately
    if data.startswith("quick_"):
        subject = data.replace("quick_", "")
        logger.info(f">>> quick lesson: {subject}")
        
        topics = get_random_topics(subject, 1)
        topic = topics[0] if topics else "Introduction"
        
        session['params'] = {
            'subject': subject,
            'topic': topic,
            'ages': '9-11',
            'duration': '30',
            'country': 'Global',
            'materials': 'basic',
            'style': 'mixed'
        }
        
        await query.edit_message_text(t('generating', lang), parse_mode='Markdown')
        
        try:
            lesson_content = generate_lesson(session['params'], lang)
            session['last_lesson'] = lesson_content
            
            # Send chat message
            await context.bot.send_message(chat_id=user_id, text=lesson_content[:4000])
            
            # Send PDF
            pdf_data = create_lesson_pdf(lesson_content, session['params'], lang)
            if pdf_data:
                filename = generate_lesson_filename(session['params'])
                pdf_buffer = BytesIO(pdf_data)
                pdf_buffer.seek(0)
                await context.bot.send_document(
                    chat_id=user_id,
                    document=InputFile(pdf_buffer, filename=f"{filename}.pdf"),
                    caption="📄 PDF"
                )
            
            # Send HTML
            html_content = create_lesson_html(lesson_content, session['params'], lang)
            html_buffer = BytesIO(html_content.encode('utf-8'))
            html_buffer.seek(0)
            filename = generate_lesson_filename(session['params'])
            await context.bot.send_document(
                chat_id=user_id,
                document=InputFile(html_buffer, filename=f"{filename}.html"),
                caption="🌐 HTML"
            )
            
            # Share prompt
            keyboard = [
                [InlineKeyboardButton(t('share_yes', lang), callback_data="share_yes"),
                 InlineKeyboardButton(t('share_no', lang), callback_data="share_no")],
            ]
            await context.bot.send_message(
                chat_id=user_id,
                text=t('share_prompt', lang),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Quick lesson error: {e}")
            logger.error(traceback.format_exc())
            await context.bot.send_message(chat_id=user_id, text=t('generation_error', lang))
        return
    
    # SUBJECT SELECTION
    if data.startswith("subject_"):
        subject = data.replace("subject_", "")
        
        if subject == "other":
            session['state'] = 'awaiting_subject_text'
            await query.edit_message_text(t('subject_other_prompt', lang))
            return
        
        session['params']['subject'] = subject
        session['state'] = 'awaiting_topic'
        
        topics = get_random_topics(subject, 6)
        keyboard = [[InlineKeyboardButton(topic, callback_data=f"topic_{topic}")] for topic in topics]
        keyboard.append([InlineKeyboardButton(t('topic_custom', lang), callback_data="topic_custom")])
        
        summary = build_selection_summary(session['params'], lang)
        await query.edit_message_text(
            f"{summary}\n\n{t('topic_prompt', lang)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # TOPIC SELECTION
    if data.startswith("topic_"):
        topic = data.replace("topic_", "")
        
        if topic == "custom":
            session['state'] = 'awaiting_topic_text'
            await query.edit_message_text(t('topic_type_prompt', lang))
            return
        
        session['params']['topic'] = topic
        session['state'] = 'awaiting_ages'
        
        keyboard = [
            [InlineKeyboardButton("5-7", callback_data="ages_5-7"),
             InlineKeyboardButton("7-9", callback_data="ages_7-9"),
             InlineKeyboardButton("9-11", callback_data="ages_9-11")],
            [InlineKeyboardButton("11-13", callback_data="ages_11-13"),
             InlineKeyboardButton("13-15", callback_data="ages_13-15"),
             InlineKeyboardButton("15+", callback_data="ages_15-18")],
        ]
        summary = build_selection_summary(session['params'], lang)
        await query.edit_message_text(
            f"{summary}\n\n{t('ages_prompt', lang)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # AGES → DURATION
    if data.startswith("ages_"):
        session['params']['ages'] = data.replace("ages_", "")
        session['state'] = 'awaiting_duration'
        keyboard = [
            [InlineKeyboardButton(f"15 {t('min', lang)}", callback_data="dur_15"),
             InlineKeyboardButton(f"30 {t('min', lang)}", callback_data="dur_30")],
            [InlineKeyboardButton(f"45 {t('min', lang)}", callback_data="dur_45"),
             InlineKeyboardButton(f"60 {t('min', lang)}", callback_data="dur_60")],
        ]
        summary = build_selection_summary(session['params'], lang)
        await query.edit_message_text(
            f"{summary}\n\n{t('duration_prompt', lang)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # DURATION → COUNTRY
    if data.startswith("dur_"):
        session['params']['duration'] = data.replace("dur_", "")
        session['state'] = 'awaiting_country'
        
        countries = get_countries(lang)
        keyboard = [[InlineKeyboardButton(t('country_global', lang), callback_data="country_Global")]]
        for i in range(0, len(countries), 2):
            row = []
            for j in range(2):
                if i + j < len(countries):
                    flag, name = countries[i + j]
                    row.append(InlineKeyboardButton(f"{flag} {name}", callback_data=f"country_{name}"))
            keyboard.append(row)
        
        summary = build_selection_summary(session['params'], lang)
        await query.edit_message_text(
            f"{summary}\n\n{t('country_prompt', lang)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # COUNTRY → MATERIALS
    if data.startswith("country_"):
        session['params']['country'] = data.replace("country_", "")
        session['state'] = 'awaiting_materials'
        keyboard = [
            [InlineKeyboardButton(t('mat_none', lang), callback_data="mat_none")],
            [InlineKeyboardButton(t('mat_basic', lang), callback_data="mat_basic")],
            [InlineKeyboardButton(t('mat_standard', lang), callback_data="mat_standard")],
        ]
        summary = build_selection_summary(session['params'], lang)
        await query.edit_message_text(
            f"{summary}\n\n{t('materials_prompt', lang)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # MATERIALS → STYLE
    if data.startswith("mat_"):
        session['params']['materials'] = data.replace("mat_", "")
        session['state'] = 'awaiting_style'
        keyboard = [
            [InlineKeyboardButton(t('style_interactive', lang), callback_data="style_interactive")],
            [InlineKeyboardButton(t('style_structured', lang), callback_data="style_structured")],
            [InlineKeyboardButton(t('style_storytelling', lang), callback_data="style_storytelling")],
            [InlineKeyboardButton(t('style_mixed', lang), callback_data="style_mixed")],
        ]
        summary = build_selection_summary(session['params'], lang)
        await query.edit_message_text(
            f"{summary}\n\n{t('style_prompt', lang)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # STYLE → FORMAT
    if data.startswith("style_"):
        session['params']['style'] = data.replace("style_", "")
        session['state'] = 'awaiting_format'
        
        keyboard = [
            [InlineKeyboardButton(t('fmt_chat', lang), callback_data="format_chat")],
            [InlineKeyboardButton(t('fmt_pdf', lang), callback_data="format_pdf"),
             InlineKeyboardButton(t('fmt_html', lang), callback_data="format_html")],
            [InlineKeyboardButton(t('fmt_chatpdf', lang), callback_data="format_chatpdf"),
             InlineKeyboardButton(t('fmt_chathtml', lang), callback_data="format_chathtml")],
        ]
        summary = build_selection_summary(session['params'], lang)
        await query.edit_message_text(
            f"{summary}\n\n{t('format_prompt', lang)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # FORMAT SELECTION → GENERATE
    if data.startswith("format_"):
        format_choice = data.replace("format_", "")
        logger.info(f">>> format: {format_choice}")
        
        await query.edit_message_text(t('generating', lang), parse_mode='Markdown')
        
        try:
            lesson_content = generate_lesson(session['params'], lang)
            session['last_lesson'] = lesson_content
            
            # Send based on format
            if format_choice in ['chat', 'chatpdf', 'chathtml']:
                await context.bot.send_message(chat_id=user_id, text=lesson_content[:4000])
            
            if format_choice in ['pdf', 'chatpdf']:
                pdf_data = create_lesson_pdf(lesson_content, session['params'], lang)
                if pdf_data:
                    filename = generate_lesson_filename(session['params'])
                    pdf_buffer = BytesIO(pdf_data)
                    pdf_buffer.seek(0)
                    await context.bot.send_document(
                        chat_id=user_id,
                        document=InputFile(pdf_buffer, filename=f"{filename}.pdf"),
                        caption="📄 PDF"
                    )
            
            if format_choice in ['html', 'chathtml']:
                html_content = create_lesson_html(lesson_content, session['params'], lang)
                html_buffer = BytesIO(html_content.encode('utf-8'))
                html_buffer.seek(0)
                filename = generate_lesson_filename(session['params'])
                await context.bot.send_document(
                    chat_id=user_id,
                    document=InputFile(html_buffer, filename=f"{filename}.html"),
                    caption="🌐 HTML"
                )
            
            # Share prompt
            keyboard = [
                [InlineKeyboardButton(t('share_yes', lang), callback_data="share_yes"),
                 InlineKeyboardButton(t('share_no', lang), callback_data="share_no")],
            ]
            await context.bot.send_message(
                chat_id=user_id,
                text=t('share_prompt', lang),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Generation error: {e}")
            logger.error(traceback.format_exc())
            await context.bot.send_message(chat_id=user_id, text=t('generation_error', lang))
        return
    
    # SHARING
    if data == "share_yes":
        logger.info(f">>> share_yes")
        session['pending_share'] = True
        session['state'] = 'awaiting_teacher_name'
        await query.edit_message_text(t('share_name_prompt', lang), parse_mode='Markdown')
        return
    
    if data == "share_no":
        logger.info(f">>> share_no")
        if session.get('last_lesson'):
            lesson_record = create_lesson_record(session['params'], session['last_lesson'], public=False)
            await save_lesson_to_github(lesson_record)
        
        keyboard = [
            [InlineKeyboardButton(t('new_lesson', lang), callback_data="action_new")],
            [InlineKeyboardButton(t('menu', lang), callback_data="action_menu")],
        ]
        await query.edit_message_text(
            t('saved_private', lang),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    logger.warning(f"Unknown callback: {data}")


# ============================================================================
# TEXT HANDLER
# ============================================================================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session(user_id)
    lang = get_lang(user_id)
    text = update.message.text.strip()
    state = session.get('state', 'idle')
    
    logger.info(f"Text from {user_id}: '{text[:30]}...' state={state}")
    
    # Handle feedback
    if state == 'awaiting_feedback':
        user = update.effective_user
        username = user.username or "no_username"
        name = user.full_name or "Anonymous"
        
        logger.info(f"FEEDBACK from {name} (@{username}): {text}")
        
        keyboard = [
            [InlineKeyboardButton(t('new_lesson', lang), callback_data="action_new")],
            [InlineKeyboardButton(t('menu', lang), callback_data="action_menu")],
        ]
        
        await update.message.reply_text(
            t('feedback_thanks', lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        session['state'] = 'idle'
        return
    
    if state == 'awaiting_teacher_name':
        teacher_name = "Anonymous" if text.lower() == 'skip' else text
        
        lesson_record = create_lesson_record(session['params'], session['last_lesson'], teacher_name=teacher_name, public=True)
        await save_lesson_to_github(lesson_record)
        website_pushed = await push_lesson_to_website(lesson_record)
        
        keyboard = [
            [InlineKeyboardButton(t('new_lesson', lang), callback_data="action_new")],
            [InlineKeyboardButton(t('menu', lang), callback_data="action_menu")],
        ]
        
        if website_pushed:
            await update.message.reply_text(
                t('share_success', lang),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                t('share_success_basic', lang),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        
        session['state'] = 'idle'
        return
    
    if state == 'awaiting_subject_text':
        session['params']['subject'] = text
        session['state'] = 'awaiting_topic'
        keyboard = [
            [InlineKeyboardButton(t('topic_custom', lang), callback_data="topic_custom")],
        ]
        summary = build_selection_summary(session['params'], lang)
        await update.message.reply_text(
            f"{summary}\n\n{t('topic_prompt', lang)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
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
        summary = build_selection_summary(session['params'], lang)
        await update.message.reply_text(
            f"{summary}\n\n{t('ages_prompt', lang)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    await update.message.reply_text(t('use_start', lang))


# ============================================================================
# VOICE HANDLER
# ============================================================================

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    
    if not groq_client:
        await update.message.reply_text(t('voice_not_configured', lang))
        return
    
    voice_file = await context.bot.get_file(update.message.voice.file_id)
    voice_data = await voice_file.download_as_bytearray()
    
    try:
        # Use Spanish transcription if user's language is Spanish
        transcription_lang = "es" if lang == "es" else "en"
        
        transcription = groq_client.audio.transcriptions.create(
            file=("voice.ogg", bytes(voice_data)),
            model="whisper-large-v3",
            language=transcription_lang
        )
        text = transcription.text.strip()
        if text:
            update.message.text = text
            await text_handler(update, context)
        else:
            await update.message.reply_text(t('voice_unclear', lang))
    except Exception as e:
        logger.error(f"Voice error: {e}")
        await update.message.reply_text(t('voice_error', lang))


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
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("subjects", subjects_command))
    application.add_handler(CommandHandler("feedback", feedback_command))
    application.add_handler(CommandHandler("language", language_command))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    application.add_handler(MessageHandler(filters.VOICE, voice_handler))
    
    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
