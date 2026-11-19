                    "role": "system",
                    "content": (
                        "You produce accurate, cautious, "
                        "source-grounded education decision briefs."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Student: {student}\n"
                        f"Parent: {parent}\n"
                        f"Goal: {goal}\n"
                        f"Concerns: {', '.join(concerns)}\n"
                        f"Verified information: {brief}\n"
                        "Return JSON with a single key named "
                        "'enhanced_brief' containing an improved "
                        "decision brief. Do not invent facts."
                    )
                }
            ]
        )

        data = json.loads(response.choices[0].message.content)

        return {
            "categories": categories,
            "answers": answers,
            "brief": data.get("enhanced_brief", brief),
            "mode": "groq",
        }

    except Exception as e:
        print(f"Groq error: {e}")
        return {
            "categories": categories,
            "answers": answers,
            "brief": brief,
            "mode": "demo_fallback",
        }

@app.get("/api/health")
def health():
    return {"status":"ok", "service":"NIAT DecisionBridge AI", "ai_configured": bool(os.getenv("GROQ_API_KEY")), "database":"connected"}

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
        return {"total_leads":total,"parent_participation":sum(1 for r in rows if r.parent_name or json.loads(r.parent_concerns or "[]")),"ai_processed":sum(1 for r in rows if r.ai_mode in ["groq","demo","demo_fallback"]),"enrolled":statuses["Enrolled"],"statuses":statuses,"conversion_rate":round(statuses["Enrolled"]*100/total,1) if total else 0}
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
