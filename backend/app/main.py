from __future__ import annotations

import io
import os
import uuid
import zipfile
import hashlib
import secrets
from datetime import datetime, timezone
from threading import Thread
from fastapi import Depends, FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import text
from dotenv import load_dotenv
from .database import Base, engine, get_db, SessionLocal
from .models import CompilerRun, CompilerStage, User
from .schemas import CreateRunBody, RegisterBody, LoginBody
from .pipeline import STAGE_NAMES, run_pipeline
from .eval_prompts import EVAL_PROMPTS

load_dotenv()
Base.metadata.create_all(bind=engine)

# Small SQLite-friendly migration for projects created before role support.
def ensure_user_role_column():
    with engine.begin() as conn:
        try:
            columns = [row[1] for row in conn.execute(text("PRAGMA table_info(users)"))]
            if "role" not in columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR NOT NULL DEFAULT 'user'"))
        except Exception:
            # Non-SQLite databases created from the updated model already have this column.
            pass

ensure_user_role_column()

app = FastAPI(title=os.getenv("APP_NAME", "AI App Compiler"), version="1.0.0")
origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FREE_RUNS_PER_DAY = int(os.getenv("FREE_RUNS_PER_DAY", "5"))
premium_ips: set[str] = set()


def configured_admin_emails() -> set[str]:
    raw = os.getenv("ADMIN_EMAILS", "")
    return {email.strip().lower() for email in raw.split(",") if email.strip()}


def decide_new_user_role(email: str, db: Session) -> str:
    # Make setup simple: the first registered account becomes admin.
    # You can also set ADMIN_EMAILS in .env, for example: ADMIN_EMAILS=admin@example.com
    if email in configured_admin_emails():
        return "admin"
    existing_count = db.query(User).count()
    return "admin" if existing_count == 0 else "user"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, digest = password_hash.split("$", 1)
    except ValueError:
        return False
    expected = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return secrets.compare_digest(expected, digest)


def make_token() -> str:
    return secrets.token_urlsafe(48)


def format_user(user: User):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "plan": user.plan,
        "role": getattr(user, "role", "user"),
        "isAdmin": getattr(user, "role", "user") == "admin",
        "createdAt": iso(user.created_at),
    }


def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Login required")
    token = authorization.split(" ", 1)[1].strip()
    user = db.query(User).filter(User.current_token == token).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user

def require_admin(user: User = Depends(get_current_user)) -> User:
    if getattr(user, "role", "user") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

def iso(dt):
    return dt.isoformat() if dt else None

def duration_ms(start, end):
    if not start or not end:
        return None
    return int((end - start).total_seconds() * 1000)

def format_run(run: CompilerRun):
    return {
        "id": run.id,
        "requirements": run.requirements,
        "status": run.status,
        "currentStage": run.current_stage,
        "retryCount": run.retry_count,
        "isEvalRun": run.is_eval_run,
        "evalPromptId": run.eval_prompt_id,
        "totalTokens": run.total_tokens,
        "totalCostUsd": run.total_cost_usd,
        "createdAt": iso(run.created_at),
        "completedAt": iso(run.completed_at),
        "durationMs": duration_ms(run.created_at, run.completed_at),
    }

def format_stage(stage: CompilerStage):
    return {
        "id": stage.id,
        "runId": stage.run_id,
        "stageNumber": stage.stage_number,
        "stageName": stage.stage_name,
        "status": stage.status,
        "output": stage.output,
        "error": stage.error,
        "promptTokens": stage.prompt_tokens,
        "completionTokens": stage.completion_tokens,
        "totalTokens": stage.total_tokens,
        "estimatedCostUsd": stage.estimated_cost_usd,
        "startedAt": iso(stage.started_at),
        "completedAt": iso(stage.completed_at),
        "durationMs": duration_ms(stage.started_at, stage.completed_at),
    }

def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def create_run_with_stages(db: Session, requirements: str, is_eval=False, eval_prompt_id=None, ip=None) -> CompilerRun:
    run = CompilerRun(
        id=str(uuid.uuid4()),
        requirements=requirements,
        status="pending",
        retry_count=0,
        is_eval_run=is_eval,
        eval_prompt_id=eval_prompt_id,
        client_ip=ip,
    )
    db.add(run)
    db.flush()
    for index, name in enumerate(STAGE_NAMES, start=1):
        db.add(CompilerStage(id=str(uuid.uuid4()), run_id=run.id, stage_number=index, stage_name=name, status="pending"))
    db.commit()
    db.refresh(run)
    return run

def launch_pipeline(run_id: str, requirements: str):
    Thread(target=run_pipeline, args=(run_id, requirements, SessionLocal), daemon=True).start()

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "fastapi", "mockPipeline": os.getenv("MOCK_PIPELINE", "true").lower() == "true"}

@app.post("/api/auth/register", status_code=201)
def register(body: RegisterBody, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        id=str(uuid.uuid4()),
        name=body.name.strip(),
        email=email,
        password_hash=hash_password(body.password),
        current_token=make_token(),
        role=decide_new_user_role(email, db),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"access_token": user.current_token, "token_type": "bearer", "user": format_user(user)}

@app.post("/api/auth/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user.current_token = make_token()
    db.commit()
    db.refresh(user)
    return {"access_token": user.current_token, "token_type": "bearer", "user": format_user(user)}

@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    return format_user(user)

@app.post("/api/auth/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.current_token = None
    db.commit()
    return {"ok": True}

@app.get("/api/compiler/runs")
def list_runs(db: Session = Depends(get_db)):
    runs = db.query(CompilerRun).order_by(CompilerRun.created_at.desc()).all()
    return [format_run(r) for r in runs]

@app.post("/api/compiler/runs", status_code=201)
def create_run(body: CreateRunBody, request: Request, db: Session = Depends(get_db)):
    run = create_run_with_stages(db, body.requirements, ip=client_ip(request))
    launch_pipeline(run.id, body.requirements)
    return format_run(run)

@app.get("/api/compiler/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(CompilerRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {**format_run(run), "stages": [format_stage(s) for s in run.stages]}

@app.delete("/api/compiler/runs/{run_id}", status_code=204)
def delete_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(CompilerRun, run_id)
    if run:
        db.delete(run)
        db.commit()
    return Response(status_code=204)

@app.post("/api/compiler/runs/{run_id}/retry")
def retry_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(CompilerRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    for stage in list(run.stages):
        db.delete(stage)
    run.status = "pending"
    run.current_stage = None
    run.completed_at = None
    run.retry_count += 1
    run.total_tokens = None
    run.total_cost_usd = None
    db.flush()
    for index, name in enumerate(STAGE_NAMES, start=1):
        db.add(CompilerStage(id=str(uuid.uuid4()), run_id=run.id, stage_number=index, stage_name=name, status="pending"))
    db.commit()
    launch_pipeline(run.id, run.requirements)
    return format_run(run)

@app.get("/api/compiler/stats")
def compiler_stats(db: Session = Depends(get_db)):
    runs = db.query(CompilerRun).all()
    total = len(runs)
    completed = sum(r.status == "completed" for r in runs)
    failed = sum(r.status == "failed" for r in runs)
    running = sum(r.status in {"running", "pending"} for r in runs)
    durations = [duration_ms(r.created_at, r.completed_at) for r in runs if r.completed_at]
    durations = [d for d in durations if d is not None]
    return {
        "totalRuns": total,
        "completedRuns": completed,
        "failedRuns": failed,
        "runningRuns": running,
        "avgDurationMs": round(sum(durations) / len(durations)) if durations else None,
        "successRate": round((completed / total) * 100) if total else 0,
        "totalTokensUsed": sum(r.total_tokens or 0 for r in runs),
        "totalCostUsd": sum(r.total_cost_usd or 0 for r in runs),
        "avgCostPerRun": (sum(r.total_cost_usd or 0 for r in runs if r.status == "completed") / completed) if completed else None,
    }

@app.get("/api/compiler/recent")
def recent_runs(db: Session = Depends(get_db)):
    runs = db.query(CompilerRun).order_by(CompilerRun.created_at.desc()).limit(5).all()
    return [format_run(r) for r in runs]

@app.get("/api/compiler/runs/{run_id}/stream")
def stream_run(run_id: str, db: Session = Depends(get_db)):
    def event_stream():
        local_db = SessionLocal()
        try:
            while True:
                run = local_db.get(CompilerRun, run_id)
                if not run:
                    yield 'data: {"type":"error","message":"Run not found"}\n\n'
                    break
                payload = {"type": "update", "run": format_run(run), "stages": [format_stage(s) for s in run.stages]}
                import json, time
                yield f"data: {json.dumps(payload)}\n\n"
                if run.status in {"completed", "failed"}:
                    yield 'data: {"type":"done"}\n\n'
                    break
                time.sleep(1.5)
        finally:
            local_db.close()
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/api/compiler/eval/prompts")
def eval_prompts():
    return EVAL_PROMPTS

@app.post("/api/compiler/eval/run/{prompt_id}", status_code=201)
def run_eval(prompt_id: str, request: Request, db: Session = Depends(get_db)):
    prompt = next((p for p in EVAL_PROMPTS if p["id"] == prompt_id), None)
    if not prompt:
        raise HTTPException(status_code=404, detail="Eval prompt not found")
    run = create_run_with_stages(db, prompt["prompt"], is_eval=True, eval_prompt_id=prompt_id, ip=client_ip(request))
    launch_pipeline(run.id, prompt["prompt"])
    return format_run(run)

@app.get("/api/compiler/eval/metrics")
def eval_metrics(db: Session = Depends(get_db)):
    runs = db.query(CompilerRun).filter(CompilerRun.is_eval_run == True).order_by(CompilerRun.created_at.desc()).all()
    total = len(runs)
    completed = sum(r.status == "completed" for r in runs)
    failed = sum(r.status == "failed" for r in runs)
    durations = [duration_ms(r.created_at, r.completed_at) for r in runs if r.completed_at]
    durations = [d for d in durations if d is not None]
    token_runs = [r.total_tokens for r in runs if r.total_tokens is not None]
    cost_runs = [r.total_cost_usd for r in runs if r.total_cost_usd is not None]
    failure_breakdown = {}
    for r in runs:
        if r.status == "failed":
            failed_stage = next((s.stage_name for s in r.stages if s.status == "failed"), "Unknown")
            failure_breakdown[failed_stage] = failure_breakdown.get(failed_stage, 0) + 1
    coverage = []
    for prompt in EVAL_PROMPTS:
        prompt_runs = [r for r in runs if r.eval_prompt_id == prompt["id"]]
        coverage.append({"promptId": prompt["id"], "label": prompt["label"], "category": prompt["category"], "runCount": len(prompt_runs), "lastStatus": prompt_runs[0].status if prompt_runs else None})
    return {
        "totalEvalRuns": total,
        "completedEvalRuns": completed,
        "failedEvalRuns": failed,
        "successRate": round((completed / total) * 100) if total else 0,
        "avgDurationMs": round(sum(durations) / len(durations)) if durations else None,
        "avgTokensPerRun": round(sum(token_runs) / len(token_runs)) if token_runs else None,
        "avgCostPerRun": (sum(cost_runs) / len(cost_runs)) if cost_runs else None,
        "failureBreakdown": failure_breakdown,
        "promptCoverage": coverage,
    }

@app.get("/api/admin/users")
def admin_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [format_user(u) for u in users]

@app.get("/api/admin/summary")
def admin_summary(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).all()
    runs = db.query(CompilerRun).all()
    return {
        "totalUsers": len(users),
        "adminUsers": sum(getattr(u, "role", "user") == "admin" for u in users),
        "normalUsers": sum(getattr(u, "role", "user") != "admin" for u in users),
        "totalRuns": len(runs),
        "completedRuns": sum(r.status == "completed" for r in runs),
        "failedRuns": sum(r.status == "failed" for r in runs),
    }

@app.get("/api/billing/status")
def billing_status(request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    stripe_configured = bool(os.getenv("STRIPE_SECRET_KEY") and os.getenv("STRIPE_PREMIUM_PRICE_ID"))
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    runs_today = db.query(CompilerRun).filter(CompilerRun.client_ip == ip, CompilerRun.created_at >= start).count()
    is_premium = ip in premium_ips or not stripe_configured
    return {"plan": "premium" if is_premium else "free", "isStripeConfigured": stripe_configured, "runsToday": runs_today, "freeLimitPerDay": FREE_RUNS_PER_DAY, "remainingFreeRuns": None if is_premium else max(0, FREE_RUNS_PER_DAY - runs_today), "limitReached": (not is_premium and runs_today >= FREE_RUNS_PER_DAY)}

@app.post("/api/billing/check-limit")
def check_limit(request: Request, db: Session = Depends(get_db)):
    status = billing_status(request, db)
    return {"allowed": not status["limitReached"], "plan": status["plan"], "runsToday": status["runsToday"], "remaining": status["remainingFreeRuns"]}

@app.post("/api/billing/create-checkout")
def create_checkout():
    raise HTTPException(status_code=400, detail="Stripe checkout is optional. Add Stripe keys and connect your payment code here.")

@app.post("/api/billing/create-portal")
def create_portal():
    raise HTTPException(status_code=400, detail="Stripe portal is optional. Add Stripe keys and connect your payment code here.")

@app.post("/api/billing/webhook")
def stripe_webhook():
    return {"received": True}

@app.get("/api/compiler/export/zip")
def export_zip():
    memory = io.BytesIO()
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder, _, files in os.walk(root):
            if "node_modules" in folder or "__pycache__" in folder or ".git" in folder:
                continue
            for file in files:
                full = os.path.join(folder, file)
                archive.write(full, os.path.relpath(full, root))
    memory.seek(0)
    return StreamingResponse(memory, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=ai-app-react-fastapi.zip"})
