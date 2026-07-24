"""LLM usage and budget API."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.session import get_db
from agent.llm_usage import get_usage_summary, test_openai_connection

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/usage")
def llm_usage(db: Session = Depends(get_db)):
    """OpenAI/LLM status, current month spend, and 4-month history."""
    return get_usage_summary(db)


@router.post("/test")
def test_llm_connection():
    """Test OpenAI API connection."""
    return test_openai_connection()
