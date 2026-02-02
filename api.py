"""
TOOLEY API - api.py
Version: 2.0.0
Updated: 2026-02-02

Serves static website + API from Railway (no more Netlify needed)

Endpoints:
- GET / - index.html
- GET /app.html, /app-es.html, /index-es.html - static pages
- POST /api/lesson - Generate lesson
- POST /api/share - Share to library
- GET /api/lessons - Get lessons for carousel
- GET /api/health - Health check

Deploy: uvicorn api:app --host 0.0.0.0 --port $PORT
"""

import os
import json
import logging
from io import BytesIO
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional
import anthropic
from fpdf import FPDF

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('CLAUDE_API_KEY')
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY or CLAUDE_API_KEY required")

app = FastAPI(title="Tooley API", version="2.0.0")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

STATIC_DIR = Path("static")
LESSONS_FILE = "lessons.json"

# Models
class LessonRequest(BaseModel):
    subject: str
    topic: str
    ages: str = "8-12"
    duration: str = "45"
    country: str = "Global"
    materials: str = "basic"
    style: str = "mixed"
    language: str = "en"

class PDFRequest(BaseModel):
    content: str
    subject: Optional[str] = None
    topic: Optional[str] = None
    ages: Optional[str] = None
    duration: Optional[str] = None
    country: Optional[str] = None

class ShareRequest(BaseModel):
    subject: str
    topic: str
    ages: str
    duration: str
    country: str
    teacher_name: Optional[str] = "Anonymous"
    language: str = "en"

# Lessons storage
def load_lessons():
    try:
        if os.path.exists(LESSONS_FILE):
            with open(LESSONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f).get('lessons', [])
    except Exception as e:
        logger.error(f"Load lessons error: {e}")
    return []

def save_lessons(lessons):
    try:
        with open(LESSONS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'lessons': lessons, 'updated': datetime.utcnow().isoformat()}, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Save lessons error: {e}")
        return False

# Lesson generation
SYSTEM_EN = """You are Tooley, an expert educational assistant. Generate clear, practical lesson plans.
Focus on active learning, student engagement, and real-world connections.
Write in clear English. Use numbered steps and bullet points. Every section MUST have content."""

SYSTEM_ES = """Eres Tooley, asistente educativo experto. Genera planes de lección claros y prácticos.
Enfócate en aprendizaje activo, participación estudiantil y conexiones con el mundo real.
Escribe en español claro. Usa pasos numerados y viñetas. Cada sección DEBE tener contenido."""

def build_prompt(p: LessonRequest) -> str:
    if p.language == 'es':
        mat = {'none': 'SIN MATERIALES', 'basic': 'Materiales básicos - papel, lápices, pizarra', 'standard': 'Útiles completos'}
        sty = {'interactive': 'Métodos interactivos con juegos y actividades.', 'structured': 'Enfoque estructurado dirigido por el docente.', 'storytelling': 'Narrativa y cuentos.', 'mixed': 'Estilos equilibrados.'}
        return f"""Crea un plan de lección:
**Materia:** {p.subject}
**Tema:** {p.topic}
**Edades:** {p.ages} años
**Duración:** {p.duration} minutos
**Ubicación:** {p.country}
**Materiales:** {mat.get(p.materials, mat['basic'])}
**Estilo:** {sty.get(p.style, sty['mixed'])}

Secciones requeridas:
## Objetivos de Aprendizaje
## Materiales Necesarios
## Introducción ({int(int(p.duration)*0.15)} min)
## Actividad Principal ({int(int(p.duration)*0.6)} min)
## Cierre y Evaluación ({int(int(p.duration)*0.25)} min)
## Consejos de Diferenciación
## Preguntas de Comprensión
## Consejos para el Docente"""
    else:
        mat = {'none': 'NO MATERIALS', 'basic': 'Basic materials - paper, pencils, blackboard', 'standard': 'Full classroom supplies'}
        sty = {'interactive': 'Interactive methods with games and activities.', 'structured': 'Structured teacher-led approach.', 'storytelling': 'Narrative and storytelling.', 'mixed': 'Balanced styles.'}
        return f"""Create a lesson plan:
**Subject:** {p.subject}
**Topic:** {p.topic}
**Ages:** {p.ages} years
**Duration:** {p.duration} minutes
**Location:** {p.country}
**Materials:** {mat.get(p.materials, mat['basic'])}
**Style:** {sty.get(p.style, sty['mixed'])}

Required sections:
## Learning Objectives
## Materials Needed
## Lesson Introduction ({int(int(p.duration)*0.15)} min)
## Main Activity ({int(int(p.duration)*0.6)} min)
## Wrap-Up & Assessment ({int(int(p.duration)*0.25)} min)
## Differentiation Tips
## Comprehension Questions
## Teacher Tips"""

def generate_lesson(p: LessonRequest) -> str:
    logger.info(f"Generating: {p.subject} - {p.topic} ({p.language})")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        system=SYSTEM_ES if p.language == 'es' else SYSTEM_EN,
        messages=[{"role": "user", "content": build_prompt(p)}]
    )
    return response.content[0].text

# PDF generation
def ascii_only(text: str) -> str:
    for old, new in {'á':'a','é':'e','í':'i','ó':'o','ú':'u','Á':'A','É':'E','Í':'I','Ó':'O','Ú':'U','ñ':'n','Ñ':'N','ü':'u','¿':'?','¡':'!','–':'-','—':'-','"':'"','"':'"',''': "'",''': "'"}.items():
        text = text.replace(old, new)
    return ''.join(c if ord(c) < 128 else ' ' for c in text)

def create_pdf(content: str, params: dict) -> BytesIO:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    
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
    
    if any(params.values()):
        pdf.set_fill_color(255, 251, 235)
        pdf.set_draw_color(15, 23, 42)
        specs_y = pdf.get_y()
        spec_lines = [f"{k.title()}: {v}" for k, v in params.items() if v]
        if spec_lines:
            box_h = 8 + len(spec_lines) * 5
            pdf.rect(10, specs_y, 190, box_h, 'FD')
            pdf.set_xy(15, specs_y + 3)
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_text_color(217, 119, 6)
            pdf.cell(0, 5, 'LESSON SPECIFICATIONS')
            pdf.set_font('Helvetica', '', 9)
            pdf.set_text_color(15, 23, 42)
            for i, line in enumerate(spec_lines):
                pdf.set_xy(15, specs_y + 8 + i * 5)
                pdf.cell(0, 5, ascii_only(line))
            pdf.set_y(specs_y + box_h + 10)
    
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(15, 23, 42)
    
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            pdf.ln(3)
            continue
        safe = ascii_only(line)
        if line.startswith('## '):
            pdf.ln(5)
            pdf.set_font('Helvetica', 'B', 12)
            pdf.set_text_color(217, 119, 6)
            pdf.multi_cell(0, 6, safe[3:])
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(15, 23, 42)
        elif line.startswith('- ') or line.startswith('* '):
            pdf.multi_cell(0, 5, '  * ' + safe[2:])
        else:
            pdf.multi_cell(0, 5, safe.replace('**', ''))
    
    pdf.set_y(-20)
    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 10, 'Generated by Tooley | tooley.app | Free for all teachers', align='C')
    
    buffer = BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer

# Static file routes
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    f = STATIC_DIR / "index.html"
    return FileResponse(f, media_type="text/html") if f.exists() else HTMLResponse("<h1>Tooley API v2.0</h1><p>Visit /api/health</p>")

@app.get("/index.html", response_class=HTMLResponse)
async def serve_index_html():
    return await serve_index()

@app.get("/index-es.html", response_class=HTMLResponse)
async def serve_index_es():
    f = STATIC_DIR / "index-es.html"
    return FileResponse(f, media_type="text/html") if f.exists() else HTMLResponse("<h1>Tooley</h1>")

@app.get("/app.html", response_class=HTMLResponse)
async def serve_app():
    f = STATIC_DIR / "app.html"
    return FileResponse(f, media_type="text/html") if f.exists() else HTMLResponse("<h1>Tooley App</h1>")

@app.get("/app-es.html", response_class=HTMLResponse)
async def serve_app_es():
    f = STATIC_DIR / "app-es.html"
    return FileResponse(f, media_type="text/html") if f.exists() else HTMLResponse("<h1>Tooley App</h1>")

# API endpoints
@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0", "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/lessons")
async def get_lessons():
    lessons = load_lessons()
    return {"lessons": lessons, "count": len(lessons)}

@app.post("/api/share")
async def share_lesson(request: ShareRequest):
    try:
        lessons = load_lessons()
        new_lesson = {
            "id": f"lesson_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(lessons)}",
            "subject": request.subject,
            "topic": request.topic,
            "ages": request.ages,
            "duration": request.duration,
            "country": request.country,
            "teacher_name": request.teacher_name or "Anonymous",
            "language": request.language,
            "created_at": datetime.utcnow().isoformat()
        }
        lessons.insert(0, new_lesson)
        lessons = lessons[:100]
        if save_lessons(lessons):
            logger.info(f"Shared: {request.subject} - {request.topic}")
            return {"success": True, "lesson": new_lesson}
        raise HTTPException(status_code=500, detail="Failed to save")
    except Exception as e:
        logger.error(f"Share error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/lesson")
async def create_lesson(request: LessonRequest):
    try:
        lesson = generate_lesson(request)
        return {"lesson": lesson, "params": request.dict()}
    except Exception as e:
        logger.error(f"Lesson error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/pdf")
async def create_pdf_endpoint(request: PDFRequest):
    try:
        params = {'subject': request.subject, 'topic': request.topic, 'ages': request.ages, 'duration': request.duration, 'country': request.country}
        pdf_buffer = create_pdf(request.content, params)
        return StreamingResponse(pdf_buffer, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=tooley-lesson-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"})
    except Exception as e:
        logger.error(f"PDF error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
