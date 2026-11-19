import os, json, uuid
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

app = FastAPI(title="NIAT DecisionBridge AI", version="1.0.0", description="Student-parent decision readiness and counsellor handoff demo")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

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

# Facts below are deliberately conservative. Expand only after verifying official NIAT pages.
KNOWLEDGE = [
    {"topic":"Degree and university", "answer":"The collaborating university awards the degree. NIAT is the industry-oriented upskilling initiative associated with NxtWave. Confirm the specific university and program details for the student's chosen campus with an authorized counsellor.", "source":"NIAT Growth Hack Challenge brief; NIAT official website", "url":"https://www.niatindia.com/"},
    {"topic":"Learning approach", "answer":"The program emphasizes practical, industry-oriented learning in areas such as AI, software development, data science and robotics, alongside regular education. Ask the campus counsellor for the current curriculum and delivery details.", "source":"NIAT Growth Hack Challenge brief; NIAT official website", "url":"https://www.niatindia.com/"},
    {"topic":"Fees and scholarships", "answer":"Fees, scholarship eligibility, award amounts and payment terms can vary. This demo does not estimate or promise a scholarship. Request the latest written fee and scholarship details from an authorized NIAT counsellor.", "source":"Requires current campus-specific confirmation", "url":"https://www.niatindia.com/"},
    {"topic":"Career outcomes", "answer":"The program focuses on career readiness and practical skills. Individual outcomes depend on many factors; do not treat general outcomes or testimonials as a guarantee of placement, salary or employment.", "source":"NIAT official website; verify current outcome disclosures", "url":"https://www.niatindia.com/"},
    {"topic":"Admission and assessment", "answer":"Admission requirements, assessment steps, timelines and eligibility should be confirmed against the current official admission process for the selected campus.", "source":"NIAT official website", "url":"https://www.niatindia.com/"},
    {"topic":"Campus and accommodation", "answer":"Campus facilities, hostel availability, accommodation charges and university-specific arrangements differ. These details need confirmation from the selected university or an authorized counsellor.", "source":"Requires campus-specific confirmation", "url":"https://www.niatindia.com/"},
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

def classify(concerns):
    text = " ".join(concerns).lower()
    found = [category for category, words in CATEGORY_RULES.items() if any(w in text for w in words)]
    return found or ["General program information"]

def retrieve_answers(categories):
    selected = []
    for item in KNOWLEDGE:
        if any(k.lower().split()[0] in item["topic"].lower() or item["topic"].lower().split()[0] in k.lower() for k in categories):
            selected.append(item)
    return selected or [KNOWLEDGE[1], KNOWLEDGE[0]]

def demo_analysis(state: AgentState):
    lead = state["lead"]
    concerns = state["concerns"]
    categories = classify(concerns)
    answers = retrieve_answers(categories)
    student = lead.get("student_name", "The student")
    parent = lead.get("parent_name") or "Parent/guardian"
    goal = lead.get("goal") or "Explore technology-focused learning"
    brief = f"DECISION READINESS BRIEF\n\nStudent: {student}\nParent/guardian: {parent}\nGoal: {goal}\n\nSHARED PRIORITY\nHelp the family make an informed decision about whether NIAT's practical, technology-oriented upskilling model and the selected university pathway fit the student's goals.\n\nKEY TOPICS TO DISCUSS\n" + "\n".join(f"• {c}" for c in categories) + "\n\nVERIFIED INFORMATION / CLARIFICATIONS\n" + "\n\n".join(f"• {a['topic']}: {a['answer']} (Source: {a['source']}; {a['url']})" for a in answers) + "\n\nRECOMMENDED COUNSELLOR ACTION\n1. Confirm the exact collaborating university and degree-awarding arrangement for the chosen campus.\n2. Share current written fee, scholarship and admission details; do not rely on estimates.\n3. Address the family's questions above and record which remain unresolved.\n4. Agree on a follow-up date with the student and parent.\n\nSAFETY NOTE\nThis is decision support, not an admission, scholarship, placement or salary guarantee. Human verification is required for campus-specific and time-sensitive details."
    return {"categories": categories, "answers": answers, "brief": brief, "mode": "demo"}

async def run_ai(lead: dict, concerns: list[str]):
    api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    return {
        "categories": categories,
        "answers": answers,
        "brief": brief,
        "mode": "demo",
    }

try:
    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1"
    )

    response = client.chat.completions.create(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You produce accurate, cautious, source-grounded education decision briefs."
            },
            {"role": "user", "content": prompt}
        ]
    )

    data = json.loads(response.choices[0].message.content)
    return {
        "categories": categories,
        "answers": answers,
        "brief": brief,
        "mode": "groq_langgraph",
        "structured": data
    }

except Exception:
    return {
        "categories": categories,
        "answers": answers,
        "brief": brief,
        "mode": "demo_fallback"
    }

@app.get("/api/health")
def health():
    return {"status":"ok", "service":"NIAT DecisionBridge AI", "ai_configured": bool(os.getenv("OPENAI_API_KEY")), "database":"connected"}

@app.get("/api/knowledge")
def knowledge():
    return [{"topic":x["topic"],"source":x["source"],"url":x["url"]} for x in KNOWLEDGE]

@app.post("/api/leads")
async def create_lead(payload: LeadInput):
    db = SessionLocal()
    try:
        lead_id = str(uuid.uuid4())
        concerns = list(dict.fromkeys(payload.student_concerns + payload.parent_concerns))
        lead_data = payload.model_dump()
        analysis = await run_ai(lead_data, concerns)
        row = Lead(id=lead_id, student_name=payload.student_name, email=payload.email, phone=payload.phone, city=payload.city, interests=json.dumps(payload.interests), goal=payload.goal, student_concerns=json.dumps(payload.student_concerns), parent_name=payload.parent_name, parent_concerns=json.dumps(payload.parent_concerns), budget_band=payload.budget_band, status="Needs counselling" if analysis.get("mode") != "error" else "New", analysis=json.dumps({"categories":analysis.get("categories",[]),"answers":analysis.get("answers",[]),"warning":analysis.get("warning"),"structured":analysis.get("structured")}, ensure_ascii=False), decision_brief=analysis.get("brief", ""), ai_mode=analysis.get("mode","demo"))
        db.add(row); db.commit(); db.refresh(row)
        return {"id":row.id,"student_name":row.student_name,"status":row.status,"analysis":json.loads(row.analysis),"decision_brief":row.decision_brief,"ai_mode":row.ai_mode,"created_at":row.created_at.isoformat() if row.created_at else None}
    except Exception as exc:
        db.rollback(); raise HTTPException(status_code=500, detail=f"Could not create lead: {str(exc)}")
    finally: db.close()

@app.get("/api/leads")
def list_leads():
    db = SessionLocal()
    try:
        rows = db.query(Lead).order_by(Lead.created_at.desc()).limit(250).all()
        return [{"id":r.id,"student_name":r.student_name,"email":r.email,"phone":r.phone,"city":r.city,"goal":r.goal,"status":r.status,"ai_mode":r.ai_mode,"created_at":r.created_at.isoformat() if r.created_at else None,"categories":json.loads(r.analysis or "{}").get("categories",[])} for r in rows]
    finally: db.close()

@app.get("/api/leads/{lead_id}")
def get_lead(lead_id: str):
    db = SessionLocal()
    try:
        r = db.query(Lead).filter(Lead.id==lead_id).first()
        if not r: raise HTTPException(404, "Lead not found")
        return {"id":r.id,"student_name":r.student_name,"email":r.email,"phone":r.phone,"city":r.city,"interests":json.loads(r.interests or "[]"),"goal":r.goal,"student_concerns":json.loads(r.student_concerns or "[]"),"parent_name":r.parent_name,"parent_concerns":json.loads(r.parent_concerns or "[]"),"budget_band":r.budget_band,"status":r.status,"analysis":json.loads(r.analysis or "{}"),"decision_brief":r.decision_brief,"ai_mode":r.ai_mode,"created_at":r.created_at.isoformat() if r.created_at else None}
    finally: db.close()

@app.patch("/api/leads/{lead_id}/status")
def update_status(lead_id: str, payload: StatusInput):
    allowed = {"New", "Needs counselling", "Counselling scheduled", "Follow-up", "Enrolled", "Not proceeding"}
    if payload.status not in allowed: raise HTTPException(400, "Invalid status")
    db = SessionLocal()
    try:
        row = db.query(Lead).filter(Lead.id==lead_id).first()
        if not row: raise HTTPException(404, "Lead not found")
        row.status=payload.status; db.commit()
        return {"id":row.id,"status":row.status}
    finally: db.close()

@app.get("/api/metrics")
def metrics():
    db=SessionLocal()
    try:
        rows=db.query(Lead).all(); total=len(rows)
        statuses={s:sum(1 for r in rows if r.status==s) for s in ["New","Needs counselling","Counselling scheduled","Follow-up","Enrolled","Not proceeding"]}
        return {"total_leads":total,"parent_participation":sum(1 for r in rows if r.parent_name or json.loads(r.parent_concerns or "[]")),"ai_processed":sum(1 for r in rows if r.ai_mode in ["openai_langgraph","demo","demo_fallback"]),"enrolled":statuses["Enrolled"],"statuses":statuses,"conversion_rate":round(statuses["Enrolled"]*100/total,1) if total else 0}
    finally: db.close()

# Serve compiled React app from the same origin for simple, free deployment.
if FRONTEND_DIST.exists():
    assets = FRONTEND_DIST / "assets"
    if assets.exists(): app.mount("/assets", StaticFiles(directory=assets), name="assets")
    @app.get("/{full_path:path}")
    def frontend(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file(): return FileResponse(candidate)
        index = FRONTEND_DIST / "index.html"
        if index.exists(): return FileResponse(index)
        return {"message":"Frontend not built. Run npm run build in frontend/."}
