"""
TOOLEY API - api.py
Version: 1.2.0
Updated: 2026-02-02

CHANGELOG:
v1.2.0 (2026-02-02)
- Added `language` parameter for Spanish support
- Lesson generation now respects language (en/es)
- System prompt updated for multilingual output

v1.1.0 (2026-01-30)
- Added `style` parameter to LessonRequest model

v1.0.0 (2026-01-29)
- Initial release

Endpoints:
- POST /api/lesson - Generate a lesson plan
- POST /api/pdf - Generate PDF from lesson content
- GET /api/health - Health check

Deploy to Railway:
Start command: uvicorn api:app --host 0.0.0.0 --port $PORT
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

# Environment
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('CLAUDE_API_KEY')
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY or CLAUDE_API_KEY required")

# Initialize
app = FastAPI(title="Tooley API", version="1.2.0")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# CORS - allow web app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    style: str = "mixed"
    language: str = "en"  # NEW: 'en' or 'es'


class PDFRequest(BaseModel):
    content: str
    subject: Optional[str] = None
    topic: Optional[str] = None
    ages: Optional[str] = None
    duration: Optional[str] = None
    country: Optional[str] = None


# ============================================================================
# LESSON GENERATION
# ============================================================================

LESSON_SYSTEM_PROMPT_EN = """You are Tooley, an expert educational assistant helping teachers create lesson plans.
Generate clear, practical lesson plans that teachers can immediately use.
Focus on active learning, student engagement, and real-world connections.
Write in clear, simple English. Use numbered steps and bullet points for clarity.
Every section MUST have substantive content - never leave a section empty."""

LESSON_SYSTEM_PROMPT_ES = """Eres Tooley, un asistente educativo experto que ayuda a docentes a crear planes de lección.
Genera planes de lección claros y prácticos que los docentes puedan usar inmediatamente.
Enfócate en el aprendizaje activo, la participación de los estudiantes y las conexiones con el mundo real.
Escribe en español claro y sencillo. Usa pasos numerados y viñetas para mayor claridad.
Cada sección DEBE tener contenido sustancial - nunca dejes una sección vacía."""


def build_lesson_prompt(params: LessonRequest) -> str:
    lang = params.language
    
    # Materials descriptions
    if lang == 'es':
        materials_desc = {
            'none': 'SIN MATERIALES - usar solo actividades verbales, movimiento, imaginación',
            'basic': 'Materiales básicos - papel, lápices, pizarra',
            'standard': 'Útiles completos de aula disponibles'
        }
        style_desc = {
            'interactive': 'Usa métodos altamente interactivos con juegos, trabajo en grupo, movimiento y actividades prácticas.',
            'structured': 'Usa un enfoque estructurado dirigido por el docente con instrucciones claras paso a paso.',
            'storytelling': 'Usa narrativa y cuentos para enseñar conceptos, creando personajes y escenarios.',
            'mixed': 'Equilibra diferentes estilos de enseñanza según la actividad.'
        }
    else:
        materials_desc = {
            'none': 'NO MATERIALS - use only verbal activities, movement, imagination',
            'basic': 'Basic materials - paper, pencils, blackboard',
            'standard': 'Full classroom supplies available'
        }
        style_desc = {
            'interactive': 'Use highly interactive methods with games, group work, movement, and hands-on activities.',
            'structured': 'Use a structured teacher-led approach with clear step-by-step instructions.',
            'storytelling': 'Use narrative and storytelling to teach concepts, creating characters and scenarios.',
            'mixed': 'Balance different teaching styles as appropriate for each activity.'
        }
    
    mat = materials_desc.get(params.materials, materials_desc['basic'])
    sty = style_desc.get(params.style, style_desc['mixed'])
    
    if lang == 'es':
        return f"""Crea un plan de lección detallado con estas especificaciones:

**Materia:** {params.subject}
**Tema:** {params.topic}
**Edades de los estudiantes:** {params.ages} años
**Duración:** {params.duration} minutos
**Ubicación/Contexto:** {params.country}
**Materiales disponibles:** {mat}
**Estilo de enseñanza:** {sty}

Formatea tu respuesta como un plan de lección completo con estas secciones:
## Objetivos de Aprendizaje
## Materiales Necesarios
## Introducción de la Lección ({int(int(params.duration) * 0.15)} min)
## Actividad Principal ({int(int(params.duration) * 0.6)} min)
## Cierre y Evaluación ({int(int(params.duration) * 0.25)} min)
## Consejos de Diferenciación

Pautas:
- Usa ejemplos culturalmente relevantes para {params.country}
- Mantén el lenguaje claro y accesible
- Incluye actividades específicas, no solo descripciones
- Agrega tiempo para cada sección
- Sugiere adaptaciones para diferentes niveles de habilidad

## Preguntas de Comprensión
1. [Pregunta con respuesta]
2. [Pregunta con respuesta]
3. [Pregunta con respuesta]

## Consejos para el Docente
- [Consejo 1]
- [Consejo 2]

CRÍTICO: Cada sección debe tener contenido real."""
    else:
        return f"""Create a detailed lesson plan with these specifications:

**Subject:** {params.subject}
**Topic:** {params.topic}
**Student Ages:** {params.ages} years old
**Duration:** {params.duration} minutes
**Location/Context:** {params.country}
**Available Materials:** {mat}
**Teaching Style:** {sty}

Format your response as a complete lesson plan with these sections:
## Learning Objectives
## Materials Needed
## Lesson Introduction ({int(int(params.duration) * 0.15)} min)
## Main Activity ({int(int(params.duration) * 0.6)} min)
## Wrap-Up & Assessment ({int(int(params.duration) * 0.25)} min)
## Differentiation Tips

Guidelines:
- Use culturally relevant examples for {params.country}
- Keep language clear and accessible
- Include specific activities, not just descriptions
- Add timing for each section
- Suggest adaptations for different skill levels

## Comprehension Questions
1. [Question with answer]
2. [Question with answer]
3. [Question with answer]

## Teacher Tips
- [Tip 1]
- [Tip 2]

CRITICAL: Every section must have real content."""


def generate_lesson(params: LessonRequest) -> str:
    prompt = build_lesson_prompt(params)
    system_prompt = LESSON_SYSTEM_PROMPT_ES if params.language == 'es' else LESSON_SYSTEM_PROMPT_EN
    
    logger.info(f"Generating lesson: {params.subject} - {params.topic} (lang: {params.language}, style: {params.style})")
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


# ============================================================================
# PDF GENERATION
# ============================================================================

def ascii_only(text: str) -> str:
    """Strip non-ASCII characters for PDF safety"""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', 'ü': 'u', 'Ü': 'U',
        '¿': '?', '¡': '!', '–': '-', '—': '-',
        '"': '"', '"': '"', ''': "'", ''': "'"
    }
    result = text
    for old, new in replacements.items():
        result = result.replace(old, new)
    return ''.join(c if ord(c) < 128 else ' ' for c in result)


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
            box_height = 8 + len(spec_lines) * 5
            pdf.rect(10, specs_y, 190, box_height, 'FD')
            pdf.set_xy(15, specs_y + 3)
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_text_color(217, 119, 6)
            pdf.cell(0, 5, 'LESSON SPECIFICATIONS')
            pdf.set_font('Helvetica', '', 9)
            pdf.set_text_color(15, 23, 42)
            for i, line in enumerate(spec_lines):
                pdf.set_xy(15, specs_y + 8 + i * 5)
                pdf.cell(0, 5, ascii_only(line))
            pdf.set_y(specs_y + box_height + 10)
    
    # Content
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(15, 23, 42)
    
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            pdf.ln(3)
            continue
        
        safe_line = ascii_only(line)
        
        if line.startswith('## '):
            pdf.ln(5)
            pdf.set_font('Helvetica', 'B', 12)
            pdf.set_text_color(217, 119, 6)
            pdf.multi_cell(0, 6, safe_line[3:])
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(15, 23, 42)
        elif line.startswith('**') and line.endswith('**'):
            pdf.set_font('Helvetica', 'B', 10)
            pdf.multi_cell(0, 5, safe_line.replace('**', ''))
            pdf.set_font('Helvetica', '', 10)
        elif line.startswith('- ') or line.startswith('* '):
            pdf.multi_cell(0, 5, '  * ' + safe_line[2:])
        else:
            pdf.multi_cell(0, 5, safe_line.replace('**', ''))
    
    # Footer
    pdf.set_y(-20)
    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 10, 'Generated by Tooley | tooley.app | Free for all teachers', align='C')
    
    buffer = BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {"message": "Tooley API v1.2.0", "docs": "/docs"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.2.0", "timestamp": datetime.utcnow().isoformat()}


@app.post("/api/lesson")
async def create_lesson(request: LessonRequest):
    try:
        lesson = generate_lesson(request)
        return {"lesson": lesson, "params": request.dict()}
    except Exception as e:
        logger.error(f"Lesson generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pdf")
async def create_pdf_endpoint(request: PDFRequest):
    try:
        params = {
            'subject': request.subject,
            'topic': request.topic,
            'ages': request.ages,
            'duration': request.duration,
            'country': request.country
        }
        pdf_buffer = create_pdf(request.content, params)
        
        filename = f"tooley-lesson-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
        
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        logger.error(f"PDF generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
