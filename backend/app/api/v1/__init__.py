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

