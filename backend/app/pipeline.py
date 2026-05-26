from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.orm import Session
from openai import OpenAI
from .models import CompilerRun, CompilerStage

STAGE_NAMES = [
    "Lexer / Parser",
    "System Architect",
    "Code Generator",
    "Self-Healing Validator",
]

COST_PER_PROMPT_TOKEN = 2.5 / 1_000_000
COST_PER_COMPLETION_TOKEN = 10.0 / 1_000_000

STAGE_1_SYSTEM = """You are the Lexer/Parser stage of a software generation compiler. Convert user requirements into valid JSON only with keys: appName, coreDomain, featuresRequested, impliedFeatures, userRoles, dataEntities, assumptions, requiresClarification."""
STAGE_2_SYSTEM = """You are the Lead Software Architect pass. Return valid JSON only with architecture.entities, architecture.rbacMatrix, architecture.workflows, architecture.premiumGating."""
STAGE_3_SYSTEM = """You are the Code Generation backend. Return valid JSON only with databaseSchema, supabaseSchema, apiSchema, uiSchema, paymentSchema."""

def stage_4_system(stage3_output: str) -> str:
    return f"""You are the Verification and Self-Healing Optimization pass. Repair mismatches in this generated schema and return valid JSON only. Original Generated Schema: {stage3_output}"""


def mock_stage_output(stage_number: int, requirements: str, previous: Any = None) -> dict:
    app_name = "generated_app"
    words = [w.strip(".,!?()").lower() for w in requirements.split() if len(w) > 3]
    features = list(dict.fromkeys(words[:8])) or ["dashboard", "authentication", "reports"]
    if stage_number == 1:
        return {
            "appName": app_name,
            "coreDomain": "Business Application",
            "featuresRequested": features,
            "impliedFeatures": ["Authentication", "Database", "Admin dashboard", "Audit logs"],
            "userRoles": ["admin", "user"],
            "dataEntities": ["User", "Profile", "Record", "Payment"],
            "assumptions": ["Responsive web UI", "Supabase/PostgreSQL compatible schema", "Stripe-ready premium plan"],
            "requiresClarification": False,
        }
    if stage_number == 2:
        return {
            "architecture": {
                "entities": [
                    {"name": "User", "description": "Authenticated account", "relationships": [{"targetEntity": "Record", "type": "1:N", "foreignKey": "user_id"}]},
                    {"name": "Record", "description": "Main business object", "relationships": [{"targetEntity": "User", "type": "N:1", "foreignKey": "user_id"}]},
                ],
                "rbacMatrix": {"roles": ["admin", "user"], "permissions": [
                    {"role": "admin", "entity": "Record", "actions": ["CREATE", "READ", "UPDATE", "DELETE"], "rowLevelSecurity": "Full access"},
                    {"role": "user", "entity": "Record", "actions": ["CREATE", "READ", "UPDATE"], "rowLevelSecurity": "Own rows only"},
                ]},
                "workflows": [{"name": "Create record", "trigger": "User submits form", "steps": ["Validate", "Store", "Notify", "Render dashboard"]}],
                "premiumGating": {"freeFeatures": ["Basic CRUD"], "premiumFeatures": ["Advanced analytics", "Exports"], "gatingLogic": "Check subscription before premium endpoints"},
            }
        }
    if stage_number == 3:
        return {
            "databaseSchema": {"tables": [
                {"name": "profiles", "columns": [{"name": "id", "type": "UUID", "constraints": ["PRIMARY KEY"]}, {"name": "email", "type": "TEXT", "constraints": ["NOT NULL", "UNIQUE"]}]},
                {"name": "records", "columns": [{"name": "id", "type": "UUID", "constraints": ["PRIMARY KEY DEFAULT gen_random_uuid()"]}, {"name": "user_id", "type": "UUID", "constraints": ["REFERENCES profiles(id) ON DELETE CASCADE"]}, {"name": "title", "type": "TEXT", "constraints": ["NOT NULL"]}]},
            ]},
            "supabaseSchema": {
                "sqlDdl": "create table profiles (id uuid primary key, email text not null unique); create table records (id uuid primary key default gen_random_uuid(), user_id uuid references profiles(id) on delete cascade, title text not null);",
                "rlsPolicies": [{"table": "records", "policy": "Users manage own records", "operation": "ALL", "role": "authenticated", "using": "auth.uid() = user_id", "withCheck": "auth.uid() = user_id"}],
                "authTriggers": "create or replace function public.handle_new_user() returns trigger as $$ begin insert into profiles(id,email) values(new.id,new.email); return new; end; $$ language plpgsql security definer;",
                "storageBuckets": [],
                "migrations": [{"filename": "001_initial_schema.sql", "sql": "-- see sqlDdl"}],
            },
            "apiSchema": {"endpoints": [{"path": "/records", "method": "GET", "rolesAllowed": ["user", "admin"], "requestBody": [], "responseBody": [{"field": "records", "type": "array"}], "supabaseQuery": "supabase.from('records').select('*')"}]},
            "uiSchema": {"pages": [{"name": "Dashboard", "path": "/", "allowedRoles": ["user", "admin"], "layout": "DASHBOARD", "components": [{"id": "records-table", "type": "DATATABLE", "props": {}, "bindsToApiEndpoint": "/records", "supabaseHook": "useRecords"}]}], "authPages": {"loginPage": {"path": "/login", "providers": ["email"]}, "signupPage": {"path": "/signup"}, "resetPasswordPage": {"path": "/reset-password"}}, "adminDashboard": {"path": "/admin", "allowedRoles": ["admin"], "analyticsWidgets": ["Usage", "Revenue"]}},
            "paymentSchema": {"provider": "stripe", "plans": [{"name": "Premium", "price": "$19", "interval": "month", "features": ["Exports", "Analytics"], "stripePriceId": "price_PLACEHOLDER"}], "webhookEvents": ["customer.subscription.created", "customer.subscription.deleted"]},
        }
    repaired = dict(previous or {})
    repaired["validationReport"] = {"issuesFound": [], "issuesFixed": [], "crossLayerConsistencyScore": 96, "supabaseReadiness": True, "executionReadiness": True}
    return repaired


def call_openai_stage(system: str, user_content: str) -> tuple[Any, int, int, int, float]:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        max_tokens=4096,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user_content}],
    )
    content = response.choices[0].message.content or "{}"
    try:
        output = json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        output = json.loads(content[start : end + 1])
    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    total_tokens = usage.total_tokens if usage else 0
    cost = prompt_tokens * COST_PER_PROMPT_TOKEN + completion_tokens * COST_PER_COMPLETION_TOKEN
    return output, prompt_tokens, completion_tokens, total_tokens, cost


def run_pipeline(run_id: str, requirements: str, session_factory) -> None:
    db: Session = session_factory()
    try:
        run = db.get(CompilerRun, run_id)
        if not run:
            return
        stages = db.query(CompilerStage).filter(CompilerStage.run_id == run_id).order_by(CompilerStage.stage_number).all()
        run.status = "running"
        run.current_stage = 1
        db.commit()

        use_mock = os.getenv("MOCK_PIPELINE", "true").lower() == "true" or not os.getenv("OPENAI_API_KEY")
        previous_output: Any = None
        total_tokens = 0
        total_cost = 0.0

        for stage in stages:
            stage.status = "running"
            stage.started_at = datetime.now(timezone.utc)
            run.current_stage = stage.stage_number
            db.commit()
            time.sleep(0.7 if use_mock else 0.1)
            try:
                if use_mock:
                    output = mock_stage_output(stage.stage_number, requirements, previous_output)
                    prompt_tokens = 250 + stage.stage_number * 40
                    completion_tokens = 650 + stage.stage_number * 85
                    total = prompt_tokens + completion_tokens
                    cost = prompt_tokens * COST_PER_PROMPT_TOKEN + completion_tokens * COST_PER_COMPLETION_TOKEN
                else:
                    if stage.stage_number == 1:
                        output, prompt_tokens, completion_tokens, total, cost = call_openai_stage(STAGE_1_SYSTEM, requirements)
                    elif stage.stage_number == 2:
                        output, prompt_tokens, completion_tokens, total, cost = call_openai_stage(STAGE_2_SYSTEM, f"Input IR JSON:\n{json.dumps(previous_output, indent=2)}")
                    elif stage.stage_number == 3:
                        output, prompt_tokens, completion_tokens, total, cost = call_openai_stage(STAGE_3_SYSTEM, f"Input Architecture:\n{json.dumps(previous_output, indent=2)}")
                    else:
                        output, prompt_tokens, completion_tokens, total, cost = call_openai_stage(stage_4_system(json.dumps(previous_output, indent=2)), "Validate and repair.")
                previous_output = output
                total_tokens += total
                total_cost += cost
                stage.status = "completed"
                stage.output = output
                stage.prompt_tokens = prompt_tokens
                stage.completion_tokens = completion_tokens
                stage.total_tokens = total
                stage.estimated_cost_usd = cost
                stage.completed_at = datetime.now(timezone.utc)
                db.commit()
            except Exception as exc:
                stage.status = "failed"
                stage.error = str(exc)
                stage.completed_at = datetime.now(timezone.utc)
                for remaining in [s for s in stages if s.stage_number > stage.stage_number]:
                    remaining.status = "failed"
                    remaining.error = "Upstream stage failed"
                run.status = "failed"
                run.completed_at = datetime.now(timezone.utc)
                run.total_tokens = total_tokens
                run.total_cost_usd = total_cost
                db.commit()
                return

        run.status = "completed"
        run.current_stage = None
        run.completed_at = datetime.now(timezone.utc)
        run.total_tokens = total_tokens
        run.total_cost_usd = total_cost
        db.commit()
    finally:
        db.close()
