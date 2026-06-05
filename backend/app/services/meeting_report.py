"""Génération du PV de séance — Document structuré + PDF stocké sur MinIO.

Appelé à la clôture d'une séance. Visible à TOUS les membres de l'association
(DocumentVisibility.MEMBERS). Remplace tout PV précédent du même meeting.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.association import Association
from app.models.document import Document, DocumentVisibility
from app.models.meeting import Activity, Meeting, MeetingActivityEntry, MeetingAttendance
from app.models.role import Membership
from app.models.user import User
from app.services.storage import upload_bytes

logger = logging.getLogger(__name__)


_ATTENDANCE_FR = {
    "present": "Présent",
    "absent": "Absent",
    "excused": "Excusé",
    "late": "En retard",
}


def _slugify_basic(text: str) -> str:
    safe = "".join(c if c.isalnum() else "-" for c in text.lower())
    return "-".join(p for p in safe.split("-") if p) or "rapport"


def _render_pdf(
    meeting: Meeting,
    association: Association,
    activities: dict[UUID, Activity],
    memberships: dict[UUID, Membership],
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"PV {meeting.title}",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=colors.HexColor("#0F766E"))
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=colors.HexColor("#0F766E"))
    body = styles["BodyText"]
    small = ParagraphStyle("Small", parent=body, fontSize=8, textColor=colors.HexColor("#666"))

    story: list = []

    # ── 1. TITRE ───────────────────────────────────────────────────────────
    story.append(Paragraph(association.name, h2))
    story.append(Paragraph(f"PV — {meeting.title}", h1))
    story.append(
        Paragraph(
            f"Séance du {meeting.scheduled_on.strftime('%d/%m/%Y')}"
            + (f" — clôturée le {meeting.closed_at.strftime('%d/%m/%Y à %H:%M')}" if meeting.closed_at else ""),
            small,
        )
    )

    # ── 2. RÉSUMÉ ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("Résumé", h2))

    by_status: dict[str, int] = {}
    for a in meeting.attendances:
        key = a.status.value if hasattr(a.status, "value") else str(a.status)
        by_status[key] = by_status.get(key, 0) + 1
    present_n = by_status.get("present", 0) + by_status.get("late", 0)
    absent_n = by_status.get("absent", 0)
    excused_n = by_status.get("excused", 0)
    total_collected = sum(
        e.amount for e in meeting.entries
        if (e.status.value if hasattr(e.status, "value") else str(e.status)) != "voided"
    )
    summary_rows = [
        ["Présents (incl. en retard)", str(present_n)],
        ["Excusés", str(excused_n)],
        ["Absents", str(absent_n)],
        ["Total encaissé", f"{total_collected:,}".replace(",", " ") + f" {association.currency}"],
    ]
    summary_t = Table(summary_rows, colWidths=[8 * cm, 5 * cm])
    summary_t.setStyle(_table_style())
    story.append(summary_t)

    if meeting.description:
        story.append(Spacer(1, 0.35 * cm))
        story.append(Paragraph("<b>Ordre du jour :</b> " + meeting.description, body))

    if meeting.notes:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph("Compte-rendu / Notes de séance", h2))
        for paragraph in meeting.notes.replace("\r\n", "\n").split("\n\n"):
            if paragraph.strip():
                story.append(Paragraph(paragraph.replace("\n", "<br/>"), body))
                story.append(Spacer(1, 0.15 * cm))

    # ── Détail par membre ──────────────────────────────────────────────────
    member_ids: set[UUID] = set()
    for a in meeting.attendances:
        member_ids.add(a.membership_id)
    for e in meeting.entries:
        member_ids.add(e.membership_id)

    if member_ids:
        story.append(Spacer(1, 0.6 * cm))
        story.append(Paragraph("3. Actions par membre", h2))

    att_by_member: dict[UUID, MeetingAttendance] = {a.membership_id: a for a in meeting.attendances}
    entries_by_member: dict[UUID, list[MeetingActivityEntry]] = {}
    for e in meeting.entries:
        if (
            (e.status.value if hasattr(e.status, "value") else str(e.status)) == "voided"
        ):
            continue
        entries_by_member.setdefault(e.membership_id, []).append(e)

    # Tri par nom de membre.
    ordered = sorted(
        member_ids,
        key=lambda mid: (
            getattr(getattr(memberships.get(mid), "user", None), "full_name", "") or ""
        ).lower(),
    )

    total_in = 0
    for mid in ordered:
        mem = memberships.get(mid)
        name = getattr(getattr(mem, "user", None), "full_name", None) or "(inconnu)"
        att = att_by_member.get(mid)
        att_label = _ATTENDANCE_FR.get(att.status.value, "—") if att else "—"
        entries = entries_by_member.get(mid, [])
        member_total = sum(e.amount for e in entries)
        total_in += member_total

        story.append(Spacer(1, 0.3 * cm))
        header_text = f"<b>{name}</b> &nbsp;&nbsp; <font color='#666'>{att_label}</font>"
        story.append(Paragraph(header_text, body))
        if att and att.notes:
            for paragraph in att.notes.replace("\r\n", "\n").split("\n\n"):
                if paragraph.strip():
                    story.append(
                        Paragraph(
                            "<i>Notes :</i> " + paragraph.replace("\n", "<br/>"),
                            small,
                        )
                    )
        if att and att.excuse_reason:
            story.append(Paragraph(f"<i>Motif d'excuse :</i> {att.excuse_reason}", small))

        if entries:
            rows = [["Activité", "Montant", "Notes"]]
            for e in entries:
                act = activities.get(e.activity_id)
                rows.append([
                    act.name if act else "(activité)",
                    f"{e.amount:,}".replace(",", " "),
                    e.notes or "",
                ])
            rows.append(["Total membre", f"{member_total:,}".replace(",", " "), ""])
            t = Table(rows, colWidths=[7 * cm, 3 * cm, 6 * cm])
            t.setStyle(_table_style(total_row=True))
            story.append(t)

    # ── Total séance ───────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * cm))
    story.append(
        Paragraph(
            f"<b>Total encaissé : {total_in:,}".replace(",", " ")
            + f" {association.currency}</b>",
            body,
        )
    )

    # ── Journal des éditions ───────────────────────────────────────────────
    edits = list(meeting.edit_history or [])
    if edits:
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("Journal des éditions", h2))
        for entry in edits:
            who = entry.get("by_name") or entry.get("by") or "?"
            when = entry.get("at") or ""
            member_name = entry.get("member_name") or "?"
            story.append(
                Paragraph(
                    f"• <b>{member_name}</b> — modifié par {who} <font color='#666'>{when}</font>",
                    small,
                )
            )

    story.append(Spacer(1, 0.6 * cm))
    story.append(
        Paragraph(
            f"<font color='#999'>Rapport généré automatiquement à la clôture de la séance — {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}</font>",
            small,
        )
    )

    doc.build(story)
    return buffer.getvalue()


def _table_style(total_row: bool = False) -> TableStyle:
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6F2EF")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0F766E")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if total_row:
        cmds += [
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F5F5F5")),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ]
    return TableStyle(cmds)


async def generate_meeting_report(
    db: AsyncSession,
    *,
    meeting: Meeting,
    association: Association,
    activities: Iterable[Activity],
    recorded_by: User,
) -> Document | None:
    """Génère le PV PDF de la séance et la rend disponible comme Document visible
    à tous les membres. Remplace un PV précédent s'il existe. Renvoie le Document
    créé, ou None en cas d'échec non bloquant (loggé)."""
    try:
        member_ids: set[UUID] = set()
        for att in meeting.attendances:
            member_ids.add(att.membership_id)
        for entry in meeting.entries:
            member_ids.add(entry.membership_id)

        memberships: dict[UUID, Membership] = {}
        if member_ids:
            res = await db.execute(
                select(Membership)
                .options(selectinload(Membership.user))
                .where(Membership.id.in_(member_ids))
            )
            memberships = {m.id: m for m in res.scalars().all()}

        act_map = {a.id: a for a in activities}
        pdf_bytes = _render_pdf(meeting, association, act_map, memberships)

        filename = f"PV-{_slugify_basic(meeting.title)}-{meeting.scheduled_on.isoformat()}.pdf"
        url, _key, size = upload_bytes(
            key_prefix=f"associations/{association.id}/meeting-reports",
            filename=filename,
            data=pdf_bytes,
            content_type="application/pdf",
        )

        # Remplace un PV précédent (idempotent en cas de re-clôture / regénération).
        prev_res = await db.execute(
            select(Document).where(
                Document.meeting_id == meeting.id,
                Document.kind == "meeting_report",
            )
        )
        for prev in prev_res.scalars().all():
            await db.delete(prev)
        await db.flush()

        doc = Document(
            association_id=association.id,
            meeting_id=meeting.id,
            title=f"PV — {meeting.title}",
            description=f"Procès-verbal généré à la clôture de la séance du {meeting.scheduled_on.strftime('%d/%m/%Y')}.",
            kind="meeting_report",
            file_url=url,
            file_name=filename,
            file_mime="application/pdf",
            file_size=size,
            visibility=DocumentVisibility.MEMBERS,
            uploaded_by_id=recorded_by.id,
        )
        db.add(doc)
        meeting.report_url = url
        meeting.report_generated_at = datetime.now(timezone.utc)
        await db.flush()
        return doc
    except Exception:  # pragma: no cover — la clôture ne doit pas échouer.
        logger.exception("Échec de génération du PV — la séance reste clôturée.")
        return None
