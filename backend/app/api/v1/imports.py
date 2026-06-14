"""Endpoints d'import en masse via templates Excel (.xlsx).

Flux : télécharger le template → le remplir → l'uploader pour APERÇU (dry-run,
rien n'est créé) → confirmer pour COMMIT (création réelle, ligne par ligne avec
points de sauvegarde pour qu'une ligne en erreur n'annule pas les autres).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_association_admin_for
from app.models.user import User
from app.services.imports import get_importer, list_importers

router = APIRouter()

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MAX_BYTES = 10 * 1024 * 1024


# ── Schemas de sortie ────────────────────────────────────────────────────────
class EntityOut(BaseModel):
    entity: str
    label: str
    description: str


class ColumnOut(BaseModel):
    key: str
    header: str
    required: bool


class RowOut(BaseModel):
    index: int
    values: dict
    errors: list[str]
    ok: bool


class PreviewOut(BaseModel):
    entity: str
    columns: list[ColumnOut]
    rows: list[RowOut]
    total: int
    valid: int
    invalid: int


class CommitOut(BaseModel):
    entity: str
    created: int
    failed: int
    errors: list[RowOut]


def _require_importer(entity: str):
    imp = get_importer(entity)
    if imp is None:
        raise HTTPException(404, f"Type d'import inconnu : {entity}")
    return imp


async def _read_xlsx(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(422, "Fichier vide.")
    if len(data) > _MAX_BYTES:
        raise HTTPException(413, "Fichier trop volumineux (max 10 Mo).")
    name = (file.filename or "").lower()
    if not name.endswith(".xlsx"):
        raise HTTPException(422, "Format attendu : .xlsx (le template fourni).")
    return data


@router.get("/entities", response_model=list[EntityOut])
async def list_entities(current_user: User = Depends(get_current_user)):
    """Liste les types d'entités importables (tout utilisateur connecté)."""
    return [
        EntityOut(entity=i.entity, label=i.label, description=i.description)
        for i in list_importers()
    ]


@router.get("/{entity}/template")
async def download_template(
    entity: str,
    association_id: UUID = Query(...),
    current_user: User = Depends(require_association_admin_for),
):
    imp = _require_importer(entity)
    data = imp.build_template()
    filename = f"template-{entity}.xlsx"
    return StreamingResponse(
        iter([data]),
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{entity}/preview", response_model=PreviewOut)
async def preview_import(
    entity: str,
    association_id: UUID = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_association_admin_for),
):
    """Dry-run : valide chaque ligne sans rien créer."""
    imp = _require_importer(entity)
    data = await _read_xlsx(file)
    raw_rows = imp.parse(data)
    ctx = await imp.new_ctx(db, association_id)

    rows: list[RowOut] = []
    valid = 0
    for idx, values in enumerate(raw_rows, start=1):
        if imp._is_example_row(values):
            continue
        _payload, errs = await imp.validate_row(db, association_id, values, ctx)
        ok = not errs
        valid += 1 if ok else 0
        rows.append(RowOut(index=idx, values=values, errors=errs, ok=ok))

    return PreviewOut(
        entity=entity,
        columns=[ColumnOut(key=c.key, header=c.header, required=c.required) for c in imp.columns],
        rows=rows,
        total=len(rows),
        valid=valid,
        invalid=len(rows) - valid,
    )


@router.post("/{entity}/commit", response_model=CommitOut)
async def commit_import(
    entity: str,
    association_id: UUID = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_association_admin_for),
):
    """Crée réellement les lignes valides. Une ligne en erreur est ignorée et
    rapportée, sans annuler les lignes déjà créées."""
    imp = _require_importer(entity)
    data = await _read_xlsx(file)
    raw_rows = imp.parse(data)
    ctx = await imp.new_ctx(db, association_id)

    created = 0
    errors: list[RowOut] = []
    for idx, values in enumerate(raw_rows, start=1):
        if imp._is_example_row(values):
            continue
        payload, errs = await imp.validate_row(db, association_id, values, ctx)
        if errs:
            errors.append(RowOut(index=idx, values=values, errors=errs, ok=False))
            continue
        try:
            async with db.begin_nested():
                await imp.create_row(db, association_id, payload, ctx)
            created += 1
        except Exception as exc:  # noqa: BLE001 — on rapporte l'erreur par ligne
            errors.append(
                RowOut(index=idx, values=values, errors=[str(exc)], ok=False)
            )

    await db.commit()
    # Hook post-commit (ex. envoi des mails de bienvenue/activation pour les
    # membres). Les erreurs d'envoi ne doivent pas faire échouer l'import.
    try:
        await imp.after_commit(db, ctx)
    except Exception:  # noqa: BLE001
        pass
    return CommitOut(entity=entity, created=created, failed=len(errors), errors=errors)
