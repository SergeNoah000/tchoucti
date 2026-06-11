"""Admin setup wizard endpoints — Phase 1 (config-v2 onboarding).

All endpoints in this module require `association_admin` on the target
association (or higher: groupement_admin / super_admin).
"""
from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_db,
    require_association_admin_for,
)
from app.models.association import Association, MembershipCriterion
from app.models.role import Membership
from app.models.document import Document, DocumentVisibility
from app.models.user import User
from app.schemas.setup import (
    CriterionCreate,
    CriterionOut,
    DocumentOut,
    RegistrationFeeUpdate,
    SetupAdvanceRequest,
    SetupStateOut,
)
from app.services.storage import upload_bytes

router = APIRouter()


async def _get_assoc(db: AsyncSession, association_id: UUID) -> Association:
    res = await db.execute(select(Association).where(Association.id == association_id))
    assoc = res.scalar_one_or_none()
    if not assoc:
        raise HTTPException(404, "Association introuvable")
    return assoc


# ── Setup state ────────────────────────────────────────────────────────────


@router.get("/{association_id}/setup", response_model=SetupStateOut)
async def get_setup_state(
    association_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Read where the admin currently is in the wizard. Open to any role with
    access to the association (so the dashboard can render the right widgets)."""
    assoc = await _get_assoc(db, association_id)
    if not current_user.is_super_admin and current_user.groupement_id != assoc.groupement_id:
        raise HTTPException(403, "Forbidden")
    cfg = assoc.config or {}
    return SetupStateOut(
        setup_complete=bool(cfg.get("setup_complete", False)),
        setup_step=int(cfg.get("setup_step", 0) or 0),
    )


@router.patch("/{association_id}/setup", response_model=SetupStateOut)
async def advance_setup(
    association_id: UUID,
    payload: SetupAdvanceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_association_admin_for),
):
    """Advance the wizard step or mark setup complete. Admin only."""
    assoc = await _get_assoc(db, association_id)
    cfg = dict(assoc.config or {})
    if payload.step is not None:
        # Step can only move forward (avoids accidental re-show of done steps).
        cfg["setup_step"] = max(int(cfg.get("setup_step", 0) or 0), payload.step)
    if payload.complete is not None:
        cfg["setup_complete"] = bool(payload.complete)
        if payload.complete:
            cfg["setup_step"] = 5
    assoc.config = cfg
    await db.commit()
    await db.refresh(assoc)
    return SetupStateOut(
        setup_complete=bool(cfg.get("setup_complete", False)),
        setup_step=int(cfg.get("setup_step", 0) or 0),
    )


@router.patch("/{association_id}/registration-fee", response_model=dict)
async def set_registration_fee(
    association_id: UUID,
    payload: RegistrationFeeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_association_admin_for),
):
    """Persist the membership registration fee on the association config."""
    assoc = await _get_assoc(db, association_id)
    cfg = dict(assoc.config or {})
    cfg["registration_fee"] = int(payload.registration_fee)
    assoc.config = cfg
    await db.commit()
    return {"registration_fee": cfg["registration_fee"]}


# ── Membership criteria CRUD ───────────────────────────────────────────────


@router.get("/{association_id}/criteria", response_model=List[CriterionOut])
async def list_criteria(
    association_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List adhesion criteria (any role with access can read — useful for the
    public invitation page where invitees see what's required of them)."""
    assoc = await _get_assoc(db, association_id)
    if not current_user.is_super_admin and current_user.groupement_id != assoc.groupement_id:
        raise HTTPException(403, "Forbidden")
    res = await db.execute(
        select(MembershipCriterion)
        .where(MembershipCriterion.association_id == association_id)
        .order_by(MembershipCriterion.sort_order, MembershipCriterion.id)
    )
    return list(res.scalars().all())


@router.post(
    "/{association_id}/criteria",
    response_model=CriterionOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_criterion(
    association_id: UUID,
    payload: CriterionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_association_admin_for),
):
    await _get_assoc(db, association_id)
    c = MembershipCriterion(
        association_id=association_id,
        type=payload.type,
        label=payload.label,
        value=payload.value,
        is_required=payload.is_required,
        sort_order=payload.sort_order,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@router.delete(
    "/{association_id}/criteria/{criterion_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_criterion(
    association_id: UUID,
    criterion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_association_admin_for),
):
    res = await db.execute(
        select(MembershipCriterion).where(
            MembershipCriterion.id == criterion_id,
            MembershipCriterion.association_id == association_id,
        )
    )
    c = res.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Critère introuvable")
    await db.delete(c)
    await db.commit()


# ── Legal documents (statuts, ROI, récépissé…) ────────────────────────────


@router.get("/{association_id}/documents", response_model=List[DocumentOut])
async def list_documents(
    association_id: UUID,
    meeting_id: UUID | None = None,
    membership_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc(db, association_id)
    if not current_user.is_super_admin and current_user.groupement_id != assoc.groupement_id:
        raise HTTPException(403, "Forbidden")
    stmt = select(Document).where(Document.association_id == association_id)
    if meeting_id is not None:
        stmt = stmt.where(Document.meeting_id == meeting_id)
    if membership_id is not None:
        stmt = stmt.where(Document.membership_id == membership_id)

    # Confidentialité : un membre non-bureau ne voit pas les pièces jointes
    # rattachées à un AUTRE membre (notes/photos perso d'une séance). Il voit
    # les siennes + les documents généraux (sans membership_id).
    from app.api.deps import _user_has_bureau_role

    if not await _user_has_bureau_role(db, current_user, association_id):
        own = await db.execute(
            select(Membership.id).where(
                Membership.user_id == current_user.id,
                Membership.association_id == association_id,
            )
        )
        own_ids = list(own.scalars().all())
        stmt = stmt.where(
            (Document.membership_id.is_(None))
            | (Document.membership_id.in_(own_ids))
        )

    stmt = stmt.order_by(Document.created_at.desc())
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post(
    "/{association_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    association_id: UUID,
    file: UploadFile = File(...),
    title: str = Form(...),
    kind: str = Form("autre"),
    description: str | None = Form(None),
    visibility: str = Form("members"),
    meeting_id: UUID | None = Form(None),
    membership_id: UUID | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_association_admin_for),
):
    """Upload un document (statut, photo, pièce jointe de séance...). Si
    meeting_id et/ou membership_id sont fournis, le document est rattaché à
    cette séance / ce membre."""
    await _get_assoc(db, association_id)
    contents = await file.read()
    if not contents:
        raise HTTPException(422, "Fichier vide")
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(413, "Fichier trop volumineux (max 20 MB)")

    key_prefix = f"associations/{association_id}/documents"
    if meeting_id:
        key_prefix = f"associations/{association_id}/meetings/{meeting_id}"
    url, _key, size = upload_bytes(
        key_prefix=key_prefix,
        filename=file.filename or "document",
        data=contents,
        content_type=file.content_type,
    )

    try:
        vis = DocumentVisibility(visibility)
    except ValueError:
        vis = DocumentVisibility.MEMBERS

    doc = Document(
        association_id=association_id,
        title=title,
        description=description,
        kind=kind,
        file_url=url,
        file_name=file.filename or "document",
        file_mime=file.content_type or "application/octet-stream",
        file_size=size,
        visibility=vis,
        uploaded_by_id=current_user.id,
        meeting_id=meeting_id,
        membership_id=membership_id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


class LogoOut(BaseModel):
    logo_url: str


@router.post("/{association_id}/logo", response_model=LogoOut)
async def upload_logo(
    association_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_association_admin_for),
):
    """Upload the association logo (image) to MinIO and store its public URL."""
    assoc = await _get_assoc(db, association_id)
    contents = await file.read()
    if not contents:
        raise HTTPException(422, "Fichier vide")
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(413, "Image trop volumineuse (max 5 MB)")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(422, "Le logo doit être une image")

    url, _key, _size = upload_bytes(
        key_prefix=f"associations/{association_id}/logo",
        filename=file.filename or "logo",
        data=contents,
        content_type=file.content_type,
    )
    assoc.logo_url = url
    await db.commit()
    return LogoOut(logo_url=url)


@router.delete(
    "/{association_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_document(
    association_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_association_admin_for),
):
    res = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.association_id == association_id,
        )
    )
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document introuvable")
    # Best-effort: we don't unlink the MinIO object yet (cheaper to keep dev
    # buckets simple). Add S3 delete here in prod hardening.
    await db.delete(doc)
    await db.commit()
