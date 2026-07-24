"""System issues and validation agent API."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.session import get_db
from db.models import SystemIssue
from agent.validator import run_validation, get_issues_summary

router = APIRouter(prefix="/api/issues", tags=["issues"])


@router.get("")
def list_issues(db: Session = Depends(get_db)):
    """Open issues, validation history, and health scores."""
    return get_issues_summary(db)


@router.post("/validate")
def trigger_validation(db: Session = Depends(get_db)):
    """Manually run the validation agent."""
    result = run_validation(db)
    return result


@router.post("/{issue_id}/resolve")
def resolve_issue(issue_id: int, db: Session = Depends(get_db)):
    """Dismiss issue — removes from DB immediately."""
    issue = db.query(SystemIssue).filter(SystemIssue.id == issue_id).first()
    if not issue:
        return {"message": "Issue not found"}
    db.delete(issue)
    db.commit()
    return {"message": "Issue dismissed", "id": issue_id}
