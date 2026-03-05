# AI-Recruiter-Agentic · Pydantic schemas (profile, job, application)
# app/state.py
"""Pydantic schemas shared across the platform."""
from typing import Literal

from pydantic import BaseModel


class CandidateProfile(BaseModel):
    name: str
    skills: list[str]
    years_experience: float
    locations: list[str]
    seniority: str


class JobPosting(BaseModel):
    job_id: str
    title: str
    company: str
    location: str
    description: str
    url: str


class Application(BaseModel):
    job_id: str
    resume_version: str
    cover_letter: str
    status: Literal["draft", "awaiting_approval", "applied", "skipped"] = "draft"
