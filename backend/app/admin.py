from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Export, Job, User, now
from .security import current_user
from .services import audit, lock

router = APIRouter(prefix="/api/v1/admin", tags=["operations"])


def require_admin(user):
    if user.role != "System Admin":
        raise HTTPException(403, "仅系统管理员可执行此操作")


@router.get("/jobs")
def jobs(user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    require_admin(user)
    return [
        {"id": j.id, "kind": j.kind, "status": j.status, "attempts": j.attempts, "next_run": j.next_run, "locked_until": j.locked_until, "error": j.error}
        for j in db.scalars(select(Job).order_by(Job.id.desc()).limit(200))
    ]


@router.post("/jobs/{job_id}/retry")
def retry(job_id: int, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    import json

    require_admin(user)
    lock(db, "job-claim")
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404)
    if job.status != "Failed":
        raise HTTPException(409, "只能重放失败的任务")
    job.status, job.attempts, job.next_run, job.locked_until, job.error = "Pending", 0, now(), None, ""
    if job.kind == "export":
        record = db.get(Export, json.loads(job.payload)["export_id"])
        if not record or record.expires_at < now():
            raise HTTPException(409, "导出已过期，请重新创建")
        record.status = "Pending"
    audit(db, user, request, "RetryJob", None, {"job_id": job_id})
    return {"ok": True}
