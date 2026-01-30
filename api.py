"""
Tooley Web API
Lightweight backend for the Tooley PWA.

Version: 1.1.0
Last Updated: 2026-01-30

Endpoints:
- POST /api/lesson - Generate a lesson plan
- POST /api/pdf - Generate PDF from lesson content
- GET /api/health - Health check

Deploy as second Railway service from same repo as bot.
Start command: uvicorn api:app --host 0.0.0.0 --port $PORT

Changelog:
- 1.1.0: Added style parameter support
- 1.0.0: Initial release
"""

import os
import logging
from io import BytesIO
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import anthropic
from fpdf import FPDF

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment - same key as bot
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('CLAUDE_API_KEY')
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY or CLAUDE_API_KEY required")

# Initialize
app = FastAPI(title="Tooley API", version="1.1.0")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# CORS - allow web app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict to tooley.app in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# MODELS
# ============================================================================

class LessonRequest(BaseModel):
    subject: str
    topic: str
    ages: str = "8-12"
    duration: str = "45"
    country: str = "Global"
    materials: str = "basic"
    style: str = "mixed"  # NEW: teaching style parameter


class PDFRequest(BaseModel):
    content: str
    subject: Optional[str] = None
    topic: Optional[str] = None
    ages: Optional[str] = None
    duration: Optional[str] = None
    country: Optional[str] = None


# ============================================================================
# LESSON GENERATION (Same prompts as Telegram bot)
# ============================================================================

LESSON_SYSTEM_PROMPT = """You are Tooley, an expert educational assistant helping teachers create lesson plans.
Generate clear, practical lesson plans that teachers can immediately use.
Focus on active learning, student engagement, and real-world connections.
Write in clear, simple English. Use numbered steps and bullet points for clarity.
Every section MUST have substantive content - never leave a section empty."""


def build_lesson_prompt(params: LessonRequest) -> str:
    materials_desc = {
        'none': 'NO MATERIALS - use only verbal activities, movement, imagination',
        'basic': 'Basic materials - paper, pencils, blackboard',
        'standard': 'Full classroom supplies available'
    }
    
    style_desc = {
        'interactive': 'Use highly interactive methods with games, group work, movement, and hands-on activities. Minimize lecture time.',
        'structured': 'Use traditional structured approach with clear teacher-led instruction, note-taking, and individual practice.',
        'storytelling': 'Use story-based learning with narratives, characters, and scenario-based activities to teach concepts.',
        'mixed': 'Use a balanced mix of interactive activities and direct instruction appropriate for the content.'
    }
    
    return f"""Create a {params.duration}-minute lesson plan on **{params.topic}** for {params.subject}.
Students are ages {params.ages}. Location: {params.country}
Materials: {materials_desc.get(params.materials, params.materials)}
Teaching Style: {style_desc.get(params.style, style_desc['mixed'])}

Structure with these sections (all must have content):

## Learning Objectives
[3 specific, measurable objectives]

## Materials Needed
[List all required materials]

## Warm-Up (5 minutes)
[Specific activity with exact questions]

## Main Lesson ({int(params.duration) - 15} minutes)
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


def generate_lesson(params: LessonRequest) -> str:
    prompt = build_lesson_prompt(params)
    logger.info(f"Generating lesson: {params.subject} - {params.topic} (style: {params.style})")
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        system=LESSON_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


# ============================================================================
# PDF GENERATION (Same as Telegram bot)
# ============================================================================

def ascii_only(text: str) -> str:
    """Strip non-ASCII characters for PDF safety"""
    return ''.join(c if ord(c) < 128 else ' ' for c in str(text))


def create_pdf(content: str, params: dict) -> BytesIO:
    """Generate PDF with Tooley branding"""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    
    # Header - amber bar + logo
    pdf.set_fill_color(217, 119, 6)
    pdf.rect(10, 10, 4, 12, 'F')
    pdf.set_xy(18, 10)
    pdf.set_font('Helvetica', 'B', 18)
    pdf.set_text_color(217, 119, 6)
    pdf.cell(40, 12, 'tooley')
    pdf.set_xy(150, 14)
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(50, 8, 'tooley.app', align='R')
    pdf.ln(20)
    
    # Specs box
    if any(params.values()):
        pdf.set_fill_color(255, 251, 235)
        pdf.set_draw_color(15, 23, 42)
        specs_y = pdf.get_y()
        spec_lines = []
        if params.get('subject'): spec_lines.append(f"Subject: {params['subject']}")
        if params.get('topic'): spec_lines.append(f"Topic: {params['topic']}")
        if params.get('ages'): spec_lines.append(f"Ages: {params['ages']}")
        if params.get('duration'): spec_lines.append(f"Duration: {params['duration']} min")
        if params.get('country'): spec_lines.append(f"Location: {params['country']}")
        
        if spec_lines:
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
    
    # Content
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(15, 23, 42)
    
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
    
    # Footer
    pdf.set_y(-15)
    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 5, 'Generated by Tooley | tooley.app | Free for all teachers', align='C')
    
    buffer = BytesIO()
    buffer.write(pdf.output())
    buffer.seek(0)
    return buffer


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {"service": "Tooley API", "status": "ok", "docs": "/docs"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "tooley-api", "version": "1.1.0"}


@app.post("/api/lesson")
async def create_lesson(request: LessonRequest):
    try:
        content = generate_lesson(request)
        return {
            "success": True,
            "lesson": content,
            "params": request.model_dump()
        }
    except Exception as e:
        logger.error(f"Lesson generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pdf")
async def create_lesson_pdf(request: PDFRequest):
    try:
        params = {
            "subject": request.subject,
            "topic": request.topic,
            "ages": request.ages,
            "duration": request.duration,
            "country": request.country
        }
        pdf_buffer = create_pdf(request.content, params)
        
        # Generate filename
        topic_slug = (request.topic or "lesson").lower().replace(" ", "-")[:20]
        filename = f"tooley-{topic_slug}-{datetime.now().strftime('%Y%m%d')}.pdf"
        
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        logger.error(f"PDF generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# RUN (for local dev - Railway uses uvicorn command)
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
