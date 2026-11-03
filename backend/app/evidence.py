import hashlib
import json
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Evidence, Job, User
from .schemas import LinkInput
from .security import current_user, require_owner
from .services import audit, get_objective

router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])
ALLOWED = {".xlsx", ".pptx", ".pdf", ".png", ".jpg", ".jpeg"}
MAX_SIZE = 25 * 1024 * 1024


def validate_content(path: Path, suffix: str):
    with path.open("rb") as stream:
        header = stream.read(16)
    if suffix == ".pdf":
        return header.startswith(b"%PDF-")
    if suffix == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in (".jpg", ".jpeg"):
        return header.startswith(b"\xff\xd8\xff")
    if suffix in (".xlsx", ".pptx"):
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                names = {e.filename for e in entries}
                prefix = "xl/" if suffix == ".xlsx" else "ppt/"
                return (
                    "[Content_Types].xml" in names
                    and any(n.startswith(prefix) for n in names)
                    and not any("vbaproject" in n.lower() for n in names)
                    and len(entries) < 10000
                    and sum(e.file_size for e in entries) < 200 * 1024 * 1024
                )
        except zipfile.BadZipFile:
            return False
    return False


def ensure_editable(db, user, objective_id, previous_id):
    obj = get_objective(db, user, objective_id, True)
    require_owner(user, obj)
    if obj.status not in ("Draft", "Active"):
        raise HTTPException(409, "仅草稿或执行中目标可添加证据")
    if previous_id:
        previous = db.get(Evidence, previous_id)
        if not previous or previous.objective_id != obj.id:
            raise HTTPException(422, "历史版本不属于当前目标")
    return obj


@router.post("/uploads", status_code=201)
def upload(
    request: Request,
    objective_id: int = Form(...),
    previous_id: int | None = Form(None),
    file: UploadFile = File(...),
    user: User = Depends(current_user, scope="function"),
    db: Session = Depends(get_db, scope="function"),
):
    ensure_editable(db, user, objective_id, previous_id)
    name = (file.filename or "").replace("\\", "/").split("/")[-1]
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED or len(name) > 255:
        raise HTTPException(422, "仅支持xlsx、pptx、pdf、png、jpg；旧Office格式暂不开放")
    expected_mime = {
        ".pdf": {"application/pdf"},
        ".png": {"image/png"},
        ".jpg": {"image/jpeg"},
        ".jpeg": {"image/jpeg"},
        ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/zip"},
        ".pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation", "application/zip"},
    }
    if file.content_type not in expected_mime[suffix] | {"application/octet-stream", None}:
        raise HTTPException(422, "文件MIME类型与扩展名不匹配")
    root = settings().storage_root.resolve() / "quarantine"
    root.mkdir(parents=True, exist_ok=True)
    key = uuid.uuid4().hex + suffix
    path, size, hash_ = root / key, 0, hashlib.sha256()
    try:
        with path.open("xb") as output:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_SIZE:
                    raise HTTPException(413, "文件不能超过25MB")
                hash_.update(chunk)
                output.write(chunk)
        if not size or not validate_content(path, suffix):
            raise HTTPException(422, "文件内容与格式不匹配或包含不允许的宏")
        evidence = Evidence(
            objective_id=objective_id,
            previous_id=previous_id,
            name=name,
            kind="file",
            storage_key=key,
            sha256=hash_.hexdigest(),
            size=size,
            status="PendingScan",
            uploaded_by=user.id,
        )
        db.add(evidence)
        db.flush()
        db.add(Job(kind="scan", payload=json.dumps({"evidence_id": evidence.id}), dedupe_key=f"scan:{evidence.id}"))
        audit(db, user, request, "UploadEvidence", objective_id, {"evidence_id": evidence.id, "sha256": evidence.sha256, "previous_id": previous_id})
        # Commit before returning so failed transactions can remove the orphan file.
        db.commit()
        return {"id": evidence.id, "status": evidence.status}
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()


@router.post("/links", status_code=201)
def add_link(body: LinkInput, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    ensure_editable(db, user, body.objective_id, body.previous_id)
    url = urlparse(body.url)
    allowed = {s.strip().lower() for s in settings().link_hosts.split(",") if s.strip()}
    if url.scheme != "https" or url.hostname not in allowed or url.username or url.password:
        raise HTTPException(422, "仅允许配置白名单中的HTTPS证据链接")
    e = Evidence(**body.model_dump(), kind="link", status="Available", uploaded_by=user.id)
    db.add(e)
    db.flush()
    audit(db, user, request, "AddEvidenceLink", body.objective_id, {"evidence_id": e.id, "url": body.url})
    return {"id": e.id}


@router.get("/versions/{evidence_id}/download")
def download(evidence_id: int, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    e = db.get(Evidence, evidence_id)
    if not e:
        raise HTTPException(404)
    get_objective(db, user, e.objective_id)
    if e.kind != "file" or e.status != "Available":
        raise HTTPException(409, "文件尚未通过扫描或不可下载")
    path = settings().storage_root.resolve() / "evidence" / e.storage_key
    if not path.is_file():
        raise HTTPException(503, "证据文件暂不可用")
    audit(db, user, request, "DownloadEvidence", e.objective_id, {"evidence_id": e.id})
    db.commit()
    return FileResponse(
        path, filename=e.name, media_type="application/octet-stream", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    )
