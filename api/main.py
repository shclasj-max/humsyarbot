"""🏥 هامزیار Mini App — FastAPI Backend v2.0"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import db
from api.routers import (
    dashboard, questions, schedule, resources,
    profile, notifications, references, faq,
    tickets, reports, grades, subscription,
    admin_panel, content_admin,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.ensure_indexes()
    yield
    db.client.close()

app = FastAPI(title="Humsyar API", version="2.0.0", lifespan=lifespan)
WEBAPP_URL = os.getenv("WEBAPP_URL", "*")
app.add_middleware(CORSMiddleware,
    allow_origins=[WEBAPP_URL] if WEBAPP_URL != "*" else ["*"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(dashboard.router,     prefix="/api/dashboard")
app.include_router(questions.router,     prefix="/api/questions")
app.include_router(schedule.router,      prefix="/api/schedule")
app.include_router(resources.router,     prefix="/api/resources")
app.include_router(profile.router,       prefix="/api/profile")
app.include_router(notifications.router, prefix="/api/notifications")
app.include_router(references.router,    prefix="/api/references")
app.include_router(faq.router,           prefix="/api/faq")
app.include_router(tickets.router,       prefix="/api/tickets")
app.include_router(reports.router,       prefix="/api/reports")
app.include_router(grades.router,        prefix="/api/grades")
app.include_router(subscription.router,  prefix="/api/subscription")
app.include_router(content_admin.router, prefix="/api/content")
app.include_router(admin_panel.router,   prefix="/api/admin")

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
