"""API v1 — aggregates all routers under /api."""
from fastapi import APIRouter

from app.api.v1 import (
    auth,
    groupements,
    associations,
    memberships,
    roles,
    meetings,
    activities,
    users,
    invitations,
    tontines,
    finance,
    social_aid,
    loans,
    setup,
    caisses,
    loan_types,
    aid_types,
    public,
    notifications,
)

api_router = APIRouter()

# Auth
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])

# Phase 1 — Core CRUD
api_router.include_router(groupements.router, prefix="/groupements", tags=["groupements"])
api_router.include_router(associations.router, prefix="/associations", tags=["associations"])
api_router.include_router(memberships.router, prefix="/memberships", tags=["memberships"])

# Invitations (no prefix — routes are /invitations, /invitations/accept, etc.)
api_router.include_router(invitations.router, tags=["invitations"])

# Roles & Permissions (no prefix — routes are /roles, /permissions, /me/permissions)
api_router.include_router(roles.router, tags=["roles"])

# Phase 2 — Meetings & Activities
api_router.include_router(meetings.router, prefix="/meetings", tags=["meetings"])
api_router.include_router(activities.router, prefix="/activities", tags=["activities"])

# Tontine
api_router.include_router(tontines.router, prefix="/tontines", tags=["tontines"])

# Finance
api_router.include_router(finance.router, prefix="/finance", tags=["finance"])

# Social aid
api_router.include_router(social_aid.router, prefix="/social-aid", tags=["social-aid"])

# Loans
api_router.include_router(loans.router, prefix="/loans", tags=["loans"])

# Setup wizard + association adhesion config (config-v2, admin only)
api_router.include_router(setup.router, prefix="/associations", tags=["setup"])

# Caisses (config-v2 wrapper around Fund)
api_router.include_router(caisses.router, prefix="/caisses", tags=["caisses"])

# LoanType catalogue (config-v2)
api_router.include_router(loan_types.router, prefix="/loan-types", tags=["loan-types"])

# AidType catalogue (config-v2)
api_router.include_router(aid_types.router, prefix="/aid-types", tags=["aid-types"])

# Public (no auth) — shareable branded pages
api_router.include_router(public.router, prefix="/public", tags=["public"])

# In-app notifications
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])

