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
