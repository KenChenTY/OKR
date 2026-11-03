"""Separate Windows service. At-least-once jobs; no scheduler inside API workers."""

import hashlib
import csv
import json
import logging
import shutil
import subprocess
import time
import uuid
from datetime import date, timedelta

from sqlalchemy import or_, select

from .config import settings
from .business_time import today
from .db import session_factory
from .models import Audit, Evidence, Export, Job, KeyResult, Notification, Objective, ScoreSnapshot, User, now
from .services import lock, objective_query, objective_view

logger = logging.getLogger("okr.worker")


def schedule_reminders(db):
    lock(db, "schedule-reminders")
    rows = db.execute(
        select(KeyResult, Objective).join(Objective, KeyResult.objective_id == Objective.id).where(Objective.status == "Active", KeyResult.next_due < today())
    ).all()
    for kr, obj in rows:
        key = f"reminder:{kr.id}:{today()}"
        if not db.scalar(select(Job.id).where(Job.dedupe_key == key)):
            db.add(
                Job(
                    kind="notify",
                    dedupe_key=key,
                    payload=json.dumps({"user_id": obj.owner_id, "objective_id": obj.id, "message": f"关键结果「{kr.name}」已到更新日期"}, ensure_ascii=False),
                )
            )
    for oid in db.scalars(select(Objective.id).where(Objective.status.in_(["Approved", "Active", "Completed"]))):
        key = f"snapshot:{oid}:{today()}"
        if not db.scalar(select(Job.id).where(Job.dedupe_key == key)):
            db.add(Job(kind="snapshot", dedupe_key=key, payload=json.dumps({"objective_id": oid, "date": str(today())})))


def csv_safe(value):
    result = str(value if value is not None else "")
    return "'" + result if result.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else result


def export_file(db, record):
    user = db.get(User, record.user_id)
    if not user or not user.active or user.role not in ("Manager", "Division Head", "PMO", "Audit"):
        record.status = "Denied"
        return
    query = objective_query(db, user)
    if record.cycle_id:
        query = query.where(Objective.cycle_id == record.cycle_id)
    objects = list(db.scalars(query.order_by(Objective.id).limit(2001)))
    if len(objects) > 2000:
        raise RuntimeError("Export exceeds 2000 objectives; select a narrower cycle")
    directory = settings().storage_root.resolve() / "exports"
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / (record.storage_key + ".tmp")
    started = time.monotonic()
    try:
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["目标编号", "目标", "负责人", "部门", "状态", "战略主题", "达成率", "截止日期"])
            for obj in objects:
                if time.monotonic() - started > 180:
                    raise RuntimeError("Export exceeded execution budget")
                view = objective_view(db, obj)
                writer.writerow([csv_safe(view[k]) for k in ("code", "title", "owner_name", "org_name", "status", "theme", "progress", "end_date")])
        temporary.replace(directory / record.storage_key)
    finally:
        temporary.unlink(missing_ok=True)
    record.object_ids = json.dumps([o.id for o in objects])
    record.status = "Completed"
    db.add(
        Audit(
            actor_id=user.id,
            action="GenerateExport",
            objective_id=None,
            detail=json.dumps({"export_id": record.id, "count": len(objects)}),
            request_id=f"export:{record.id}",
        )
    )


def claim():
    with session_factory()() as db, db.begin():
        # Global short lock only around claiming; work executes outside it.
        lock(db, "job-claim")
        job = db.scalar(
            select(Job)
            .where(or_((Job.status == "Pending") & (Job.next_run <= now()), (Job.status == "Running") & (Job.locked_until < now())))
            .order_by(Job.id)
            .limit(1)
        )
        if not job:
            return None
        token = uuid.uuid4().hex
        job.status, job.lock_token = "Running", token
        job.locked_until = now() + timedelta(minutes=5)
        job.attempts += 1
        return job.id, token


def process(job_id, token):
    # Each task is bounded below the five-minute lease (scanner timeout=120s).
    with session_factory()() as db, db.begin():
        lock(db, f"job-execute:{job_id}")
        job = db.get(Job, job_id)
        if not job or job.status != "Running" or job.lock_token != token:
            return
        payload = json.loads(job.payload)
        if job.kind == "notify":
            if not db.scalar(select(Notification.id).where(Notification.dedupe_key == job.dedupe_key)):
                db.add(Notification(**payload, dedupe_key=job.dedupe_key))
        elif job.kind == "export":
            record = db.get(Export, payload["export_id"])
            if record and record.status == "Pending":
                export_file(db, record)
        elif job.kind == "snapshot":
            obj = db.get(Objective, payload["objective_id"])
            snapshot_date = date.fromisoformat(payload["date"])
            # A delayed job must not label today's values as historical data.
            if (
                obj
                and snapshot_date == today()
                and not db.scalar(select(ScoreSnapshot.id).where(ScoreSnapshot.objective_id == obj.id, ScoreSnapshot.snapshot_date == snapshot_date))
            ):
                db.add(
                    ScoreSnapshot(
                        objective_id=obj.id, snapshot_date=snapshot_date, payload=json.dumps(objective_view(db, obj, True), default=str, ensure_ascii=False)
                    )
                )
        elif job.kind == "scan":
            e = db.get(Evidence, payload["evidence_id"])
            if e.status == "PendingScan":
                scanner = settings().scanner_executable
                if not scanner:
                    raise RuntimeError("Scanner is not configured; evidence remains quarantined")
                root = settings().storage_root.resolve()
                source, destination = root / "quarantine" / e.storage_key, root / "evidence" / e.storage_key
                # A previous attempt may have copied the file before its DB commit failed.
                source = source if source.is_file() else destination
                with source.open("rb") as f:
                    hash_ = hashlib.file_digest(f, "sha256").hexdigest()
                if hash_ != e.sha256:
                    e.status = "Rejected"
                else:
                    result = subprocess.run([scanner, str(source)], timeout=120, capture_output=True, check=False)
                    if result.returncode not in (0, 1):
                        raise RuntimeError("Scanner unavailable; evidence remains quarantined")
                    e.status = "Available" if result.returncode == 0 else "Rejected"
                    if e.status == "Available" and source != destination:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(source, destination)
                db.add(
                    Audit(
                        actor_id=e.uploaded_by,
                        action="ScanEvidence",
                        objective_id=e.objective_id,
                        detail=json.dumps({"evidence_id": e.id, "result": e.status, "source": "worker"}),
                        request_id=f"job:{job.id}",
                    )
                )
        else:
            raise RuntimeError("Unsupported job type")
        job.status, job.locked_until = "Completed", None
        job.error = ""


def fail(job_id, token, error):
    with session_factory()() as db, db.begin():
        job = db.get(Job, job_id)
        if job and job.lock_token == token:
            job.error = str(error)[:1000]
            job.status = "Failed" if job.attempts >= 3 else "Pending"
            job.next_run = now() + timedelta(minutes=[1, 5, 15][min(job.attempts - 1, 2)])
            job.locked_until = None
            if job.status == "Failed" and job.kind == "export":
                record = db.get(Export, json.loads(job.payload)["export_id"])
                if record:
                    record.status = "Failed"


def main():
    logging.basicConfig(level=logging.INFO)
    last_schedule = 0.0
    while True:
        try:
            if time.monotonic() - last_schedule > 60:
                with session_factory()() as db, db.begin():
                    schedule_reminders(db)
                last_schedule = time.monotonic()
            item = claim()
            if item:
                try:
                    process(*item)
                except Exception as exc:
                    logger.error("Job %s failed (%s)", item[0], type(exc).__name__)
                    fail(*item, exc)
            else:
                time.sleep(2)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            logger.error("Worker unavailable (%s)", type(exc).__name__)
            time.sleep(5)


if __name__ == "__main__":
    main()
