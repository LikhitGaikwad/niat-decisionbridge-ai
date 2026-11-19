import os, json, uuid
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TypedDict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, String, DateTime, Text, Integer
from sqlalchemy.orm import declarative_base, sessionmaker

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parents[1]
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./decisionbridge.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Lead(Base):
    __tablename__ = "leads"
    id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    student_name = Column(String(120), nullable=False)
    email = Column(String(180), nullable=False)
    phone = Column(String(40), default="")
    city = Column(String(100), default="")
    interests = Column(Text, default="[]")
    goal = Column(Text, default="")
    student_concerns = Column(Text, default="[]")
    parent_name = Column(String(120), default="")
    parent_concerns = Column(Text, default="[]")
    budget_band = Column(String(100), default="Not shared")
    status = Column(String(40), default="New")
    analysis = Column(Text, default="{}")
    decision_brief = Column(Text, default="")
    ai_mode = Column(String(30), default="demo")


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="NIAT DecisionBridge AI",
    version="1.0.0",
    description="Student-parent decision readiness and counsellor handoff demo",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LeadInput(BaseModel):
    student_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=180)
    phone: str = Field(default="", max_length=40)
    city: str = Field(default="", max_length=100)
    interests: list[str] = Field(default_factory=list)
    goal: str = Field(default="", max_length=1200)
    student_concerns: list[str] = Field(default_factory=list)
    parent_name: str = Field(default="", max_length=120)
    parent_concerns: list[str] = Field(default_factory=list)
    budget_band: str = "Not shared"


class StatusInput(BaseModel):
    status: str


ALLOWED_STATUSES = ["New", "Contacted", "Counsellor Call Booked", "Campus Visit", "Applied", "Closed"]

# Facts below are deliberately conservative. Expand only after verifying official NIAT pages.
KNOWLEDGE = [
    {"topic": "Degree and university", "answer": "The collaborating university awards the degree. NIAT is the industry-oriented upskilling initiative associated with NxtWave. Confirm the specific university and program details for the student's chosen campus with an authorized counsellor.", "source": "NIAT Growth Hack Challenge brief; NIAT official website", "url": "https://www.niatindia.com/"},
    {"topic": "Learning approach", "answer": "The program emphasizes practical, industry-oriented learning in areas such as AI, software development, data science and robotics, alongside regular education. Ask the campus counsellor for the current curriculum and delivery details.", "source": "NIAT Growth Hack Challenge brief; NIAT official website", "url": "https://www.niatindia.com/"},
    {"topic": "Fees and scholarships", "answer": "Fees, scholarship eligibility, award amounts and payment terms can vary. This demo does not estimate or promise a scholarship. Request the latest written fee and scholarship details from an authorized NIAT counsellor.", "source": "Requires current campus-specific confirmation", "url": "https://www.niatindia.com/"},
    {"topic": "Career outcomes", "answer": "The program focuses on career readiness and practical skills. Individual outcomes depend on many factors; do not treat general outcomes or testimonials as a guarantee of placement, salary or employment.", "source": "NIAT official website; verify current outcome disclosures", "url": "https://www.niatindia.com/"},
    {"topic": "Admission and assessment", "answer": "Admission requirements, assessment steps, timelines and eligibility should be confirmed against the current official admission process for the selected campus.", "source": "NIAT official website", "url": "https://www.niatindia.com/"},
    {"topic": "Campus and accommodation", "answer": "Campus facilities, hostel availability, accommodation charges and university-specific arrangements differ. These details need confirmation from the selected university or an authorized counsellor.", "source": "Requires campus-specific confirmation", "url": "https://www.niatindia.com/"},
]


class AgentState(TypedDict, total=False):
    lead: dict
    concerns: list[str]
    categories: list[str]
    answers: list[dict]
    brief: str
    mode: str


CATEGORY_RULES = {
    "Fees & scholarships": ["fee", "fees", "cost", "scholarship", "payment", "budget", "loan"],
    "Degree & university": ["degree", "university", "college", "recognition", "accreditation", "b.tech"],
    "Career & placements": ["job", "placement", "salary", "career", "internship", "employment"],
    "Campus & accommodation": ["hostel", "campus", "accommodation", "location", "transport"],
    "Learning & curriculum": ["course", "curriculum", "ai", "robotics", "coding", "learning", "faculty"],
    "Admissions": ["admission", "eligibility", "assessment", "exam", "nat", "application"],
}

CATEGORY_TO_TOPIC = {
    "Fees & scholarships": "Fees and scholarships",
    "Degree & university": "Degree and university",
    "Career & placements": "Career outcomes",
    "Campus & accommodation": "Campus and accommodation",
    "Learning & curriculum": "Learning approach",
    "Admissions": "Admission and assessment",
}


def classify(concerns):
    text = " ".join(concerns).lower()
    found = [category for category, words in CATEGORY_RULES.items() if any(w in text for w in words)]
    return found or ["General program information"]


# ---------- Agent pipeline: classify -> retrieve -> brief ----------

def retrieve(categories: list[str]) -> list[dict]:
    topics = [CATEGORY_TO_TOPIC[c] for c in categories if c in CATEGORY_TO_TOPIC]
    if not topics:  # general enquiry
        topics = ["Degree and university", "Learning approach"]
    return [k for k in KNOWLEDGE if k["topic"] in topics]


def readiness_score(lead: dict, categories: list[str]) -> dict:
    """Simple transparent heuristic: how ready is this family to decide?"""
    score = 40
    reasons = []
    if lead.get("goal"):
        score += 15; reasons.append("Student has a stated goal")
    if lead.get("interests"):
        score += 10; reasons.append("Student has defined interests")
    if lead.get("parent_name"):
        score += 10; reasons.append("Parent is involved")
    if lead.get("budget_band") and lead["budget_band"] != "Not shared":
        score += 10; reasons.append("Budget band shared")
    if lead.get("phone"):
        score += 5; reasons.append("Contact number available")
    open_items = len(categories)
    score -= min(open_items * 3, 15)
    if open_items:
        reasons.append(f"{open_items} open concern area(s) to resolve")
    score = max(0, min(100, score))
    label = "High" if score >= 75 else "Medium" if score >= 55 else "Low"
    return {"score": score, "label": label, "reasons": reasons}


def demo_brief(state: AgentState) -> str:
    lead = state["lead"]
    lines = [
        f"DECISION BRIEF: {lead['student_name']}"
        + (f" (parent: {lead['parent_name']})" if lead.get("parent_name") else ""),
        f"City: {lead.get('city') or 'Not shared'} | Budget band: {lead.get('budget_band')}",
        f"Interests: {', '.join(lead.get('interests') or []) or 'Not shared'}",
        f"Goal: {lead.get('goal') or 'Not shared'}",
        "",
        "Student concerns: " + ("; ".join(lead.get("student_concerns") or []) or "None listed"),
        "Parent concerns: " + ("; ".join(lead.get("parent_concerns") or []) or "None listed"),
        "",
        "Concern areas: " + ", ".join(state["categories"]),
        "",
        "Talking points for the counsellor (verify everything against current official info):",
    ]
    for a in state["answers"]:
        lines.append(f"- {a['topic']}: {a['answer']}")
    lines += [
        "",
        "Do not promise: scholarships, placements, salaries, or fee figures not confirmed in writing.",
    ]
    return "\n".join(lines)


def gemini_brief(state: AgentState) -> Optional[str]:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return None
    prompt = (
        "You are helping an admissions counsellor prepare for a call. Using ONLY the facts "
        "provided, write a concise decision brief (under 250 words). Do not invent fees, "
        "scholarships, placements or salaries. Flag anything that needs confirmation.\n\n"
        f"LEAD: {json.dumps(state['lead'])}\n"
        f"CONCERN AREAS: {state['categories']}\n"
        f"VERIFIED FACTS: {json.dumps(state['answers'])}"
    )
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return None  # fall back to demo mode


def run_pipeline(lead: dict) -> AgentState:
    state: AgentState = {"lead": lead}
    state["concerns"] = (lead.get("student_concerns") or []) + (lead.get("parent_concerns") or [])
    state["categories"] = classify(state["concerns"])
    state["answers"] = retrieve(state["categories"])
    brief = gemini_brief(state)
    if brief:
        state["brief"], state["mode"] = brief, "gemini"
    else:
        state["brief"], state["mode"] = demo_brief(state), "demo"
    return state


# ---------- Helpers ----------

def serialize(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "student_name": lead.student_name,
        "email": lead.email,
        "phone": lead.phone,
        "city": lead.city,
        "interests": json.loads(lead.interests or "[]"),
        "goal": lead.goal,
        "student_concerns": json.loads(lead.student_concerns or "[]"),
        "parent_name": lead.parent_name,
        "parent_concerns": json.loads(lead.parent_concerns or "[]"),
        "budget_band": lead.budget_band,
        "status": lead.status,
        "analysis": json.loads(lead.analysis or "{}"),
        "decision_brief": lead.decision_brief,
        "ai_mode": lead.ai_mode,
    }


# ---------- API routes ----------

@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.get("/api/knowledge", tags=["knowledge"])
def knowledge():
    return {"items": KNOWLEDGE}


@app.post("/api/leads", tags=["leads"])
def create_lead(payload: LeadInput):
    data = payload.model_dump()
    state = run_pipeline(data)
    analysis = {
        "categories": state["categories"],
        "answers": state["answers"],
        "readiness": readiness_score(data, state["categories"]),
    }
    lead = Lead(
        id=str(uuid.uuid4()),
        student_name=data["student_name"],
        email=data["email"],
        phone=data["phone"],
        city=data["city"],
        interests=json.dumps(data["interests"]),
        goal=data["goal"],
        student_concerns=json.dumps(data["student_concerns"]),
        parent_name=data["parent_name"],
        parent_concerns=json.dumps(data["parent_concerns"]),
        budget_band=data["budget_band"],
        analysis=json.dumps(analysis),
        decision_brief=state["brief"],
        ai_mode=state["mode"],
    )
    db = SessionLocal()
    try:
        db.add(lead)
        db.commit()
        db.refresh(lead)
        return serialize(lead)
    finally:
        db.close()


@app.get("/api/leads", tags=["leads"])
def list_leads(status: Optional[str] = None, limit: int = 100):
    db = SessionLocal()
    try:
        q = db.query(Lead).order_by(Lead.created_at.desc())
        if status:
            q = q.filter(Lead.status == status)
        return {"items": [serialize(l) for l in q.limit(min(limit, 500)).all()]}
    finally:
        db.close()


@app.get("/api/leads/{lead_id}", tags=["leads"])
def get_lead(lead_id: str):
    db = SessionLocal()
    try:
        lead = db.get(Lead, lead_id)
        if not lead:
            raise HTTPException(404, "Lead not found")
        return serialize(lead)
    finally:
        db.close()


@app.patch("/api/leads/{lead_id}/status", tags=["leads"])
def update_status(lead_id: str, payload: StatusInput):
    if payload.status not in ALLOWED_STATUSES:
        raise HTTPException(400, f"Status must be one of: {', '.join(ALLOWED_STATUSES)}")
    db = SessionLocal()
    try:
        lead = db.get(Lead, lead_id)
        if not lead:
            raise HTTPException(404, "Lead not found")
        lead.status = payload.status
        db.commit()
        db.refresh(lead)
        return serialize(lead)
    finally:
        db.close()


@app.delete("/api/leads/{lead_id}", tags=["leads"])
def delete_lead(lead_id: str):
    db = SessionLocal()
    try:
        lead = db.get(Lead, lead_id)
        if not lead:
            raise HTTPException(404, "Lead not found")
        db.delete(lead)
        db.commit()
        return {"deleted": lead_id}
    finally:
        db.close()


@app.get("/api/stats", tags=["leads"])
def stats():
    db = SessionLocal()
    try:
        leads = db.query(Lead).all()
        by_status: dict[str, int] = {}
        for l in leads:
            by_status[l.status] = by_status.get(l.status, 0) + 1
        return {"total": len(leads), "by_status": by_status}
    finally:
        db.close()


# ---------- Frontend (must stay LAST so it doesn't shadow /api routes) ----------

if FRONTEND_DIST.exists():
    assets = FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
