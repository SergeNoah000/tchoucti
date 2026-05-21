# Tchoucti — Fichier de Contexte pour Développeurs

> **Ce fichier est destiné à être lu en début de chaque session par un LLM ou un développeur.**
> Il décrit l'état actuel du projet, les conventions, la stack, et ce qui est fait vs à faire.

---

## 1. Description du Projet

**Tchoucti** est une plateforme SaaS multi-tenant pour la gestion de **réunions d'associations** (type réunions familiales, tontines, mutuelles africaines). 

### Hiérarchie multi-tenant
```
Plateforme (Langeao SARL)
  └── Groupement (sous-domaine : {slug}.tchoucti.cm) — tenant level 1
        └── Association (path : /a/{slug}) — tenant level 2
              └── Membership (User × Association × Roles)
```

### But principal
Le **suivi des séances de réunion** : présences, cotisations, dons, amendes, prêts, tontines, aide sociale — le tout ventilé dans une trésorerie à fonds multiples.

---

## 2. Stack Technique

| Composant | Technologie | Version |
|-----------|-------------|---------|
| **Backend** | FastAPI (async) + SQLAlchemy 2.x + Pydantic v2 | Python 3.11+ |
| **DB** | PostgreSQL 16 (via Docker) | Port: 15432 |
| **Cache** | Redis (via Docker) | Port: 16379 |
| **Storage** | MinIO S3 (via Docker) | Port: 19000 |
| **Frontend** | Next.js 15 (App Router) + React 19 | |
| **CSS** | Tailwind CSS **v3** + tailwindcss-animate | |
| **UI** | shadcn/ui (Radix primitives) | |
| **Icons** | lucide-react | |
| **i18n** | next-intl (FR/EN/DE) | |
| **State** | Zustand (auth + permissions stores) | |
| **HTTP** | Axios (avec intercepteurs refresh token) | |
| **Thèmes** | next-themes (dark/light) | |
| **Auth** | JWT (access + refresh tokens) | |
| **Fonts** | Geist + Geist_Mono (next/font/google) | |

### Ports en développement
- Frontend : `http://localhost:3000`
- Backend : `http://localhost:18000`
- PostgreSQL : `localhost:15432`
- Redis : `localhost:16379`
- MinIO : `localhost:19000` (console: 19001)

### Commandes utiles
```bash
make dev          # docker compose up --build (tous les services)
make up           # docker compose up -d
make down         # arrête tout
make shell        # bash dans le container backend
make db-shell     # psql dans PostgreSQL
make seed         # python -m app.db.seed (dans le container backend)
```

---

## 3. Structure du projet

```
dengoh/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entrypoint + router mount
│   │   ├── api/
│   │   │   ├── deps.py          # get_db, get_current_user (OAuth2)
│   │   │   └── v1/
│   │   │       ├── __init__.py  # api_router (agrège tous les routers)
│   │   │       └── auth.py      # ✅ login, me, refresh, logout, activate
│   │   ├── core/
│   │   │   ├── config.py        # Settings (pydantic-settings, .env)
│   │   │   ├── security.py      # JWT (create/decode tokens), bcrypt
│   │   │   ├── tenant.py        # TenantContext dataclass
│   │   │   └── middleware.py     # TenantMiddleware (parse Host header)
│   │   ├── db/
│   │   │   ├── base.py          # DeclarativeBase
│   │   │   ├── session.py       # AsyncEngine + AsyncSessionLocal
│   │   │   └── seed.py          # ✅ Create tables + 4 demo users + groupement + association
│   │   ├── models/              # ✅ 30+ tables SQLAlchemy (toutes définies)
│   │   │   ├── user.py, groupement.py, association.py
│   │   │   ├── role.py (Permission, Role, Membership, MembershipRole, UserPermission)
│   │   │   ├── finance.py (Treasury, Fund, TreasuryMovement, LedgerEntry)
│   │   │   ├── meeting.py (Meeting, Activity, MeetingAttendance, MeetingActivityEntry)
│   │   │   ├── tontine.py, loan.py, social_aid.py, project.py
│   │   │   ├── document.py, audit_log.py, notification.py
│   │   │   └── __init__.py (importe tout)
│   │   ├── schemas/
│   │   │   └── auth.py          # ✅ TokenPair, UserPublic, RefreshRequest, ActivateRequest
│   │   └── seeds/
│   │       └── rbac.py          # ✅ Catalogue permissions + rôles système (7 rôles, 35+ permissions)
│   ├── migrations/
│   │   ├── env.py               # Alembic async config
│   │   └── versions/            # (vide — on utilise seed.py drop+create pour le dev)
│   ├── alembic.ini              # script_location = migrations
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx       # ✅ Geist fonts + next-intl + Providers + Toaster
│   │   │   ├── page.tsx         # ✅ Landing page (hero + features + roles)
│   │   │   ├── login/page.tsx   # ✅ Login + panneau comptes démo cliquables
│   │   │   ├── activate/page.tsx# ✅ Activation de compte (token + password)
│   │   │   ├── admin/page.tsx   # ✅ Super admin dashboard (stats, groupements)
│   │   │   └── dashboard/
│   │   │       ├── layout.tsx   # ✅ AppShell wrapper (sidebar + topbar)
│   │   │       ├── page.tsx     # ✅ Dashboard role-aware (super_admin/groupement_admin/member)
│   │   │       └── meetings/page.tsx # ✅ Meetings list (vide, avec EmptyState)
│   │   ├── components/
│   │   │   ├── ui/              # ✅ 16 composants shadcn (button, card, input, dialog, tabs, etc.)
│   │   │   ├── common/          # ✅ brand-mark, theme-toggle, language-toggle, stat-card, empty-state
│   │   │   └── layout/app-shell.tsx # ✅ Sidebar + topbar + user dropdown + association switcher
│   │   ├── i18n/
│   │   │   ├── config.ts        # locales: fr/en/de
│   │   │   ├── request.ts       # getRequestConfig
│   │   │   └── locales/         # ✅ FR/EN/DE complets (brand, common, landing, nav, login, activate, dashboard, admin, meeting, roles, errors)
│   │   ├── lib/
│   │   │   ├── api.ts           # ✅ Axios + intercepteurs refresh + namespaces (auth, meetings, members, etc.)
│   │   │   ├── types.ts         # ✅ Types TS (User, Meeting, Membership, Fund, etc.)
│   │   │   ├── utils.ts         # cn() + initials()
│   │   │   └── store/
│   │   │       ├── auth.ts      # ✅ Zustand persist (user, tokens, login/logout)
│   │   │       └── permissions.ts # ✅ Zustand (permissions cache)
│   │   └── middleware.ts        # ✅ Next.js middleware (tenant resolution, locale)
│   ├── tailwind.config.ts       # ✅ Palette brand (teal), fonts Geist, animations
│   ├── globals.css              # ✅ CSS variables (light/dark), brand utilities
│   └── package.json
│
├── docs/
│   ├── ARCHITECTURE.md          # ✅ Architecture complète documentée
│   ├── CONTEXT.md               # ← CE FICHIER
│   └── PLANNING.md              # ← Planning détaillé des tâches restantes
│
├── docker-compose.yml           # ✅ postgres + redis + minio + backend (uvicorn :18000)
├── Makefile                     # ✅ dev, up, down, shell, seed, migrate, etc.
└── .env.example                 # ✅ Variables d'environnement
```

---

## 4. Ce qui est FAIT ✅

### Backend
- [x] Tous les modèles SQLAlchemy (30+ tables) — finances, meetings, tontines, prêts, aide sociale, projets, documents, audit
- [x] Seed script (`python -m app.db.seed`) — drop/create tables + 4 comptes démo + groupement + association
- [x] Auth API : `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/refresh`, `POST /api/auth/logout`, `POST /api/auth/activate`
- [x] JWT (access + refresh), bcrypt password hashing
- [x] TenantMiddleware (parse sous-domaine depuis Host header)
- [x] RBAC catalogue complet (35+ permissions, 7 rôles système)
- [x] Docker compose fonctionnel (PostgreSQL, Redis, MinIO, Backend)

### Frontend
- [x] Next.js 15 + Tailwind v3 + shadcn/ui + Geist font
- [x] i18n complet FR/EN/DE (all keys defined)
- [x] Auth flow : login → JWT → store Zustand → redirect dashboard/admin
- [x] Landing page (hero, features, roles)
- [x] Login page avec panneau comptes démo cliquables
- [x] Activation de compte
- [x] Dashboard role-aware (super_admin, groupement_admin, member)
- [x] Admin page (super admin only)
- [x] AppShell (sidebar + topbar + dropdown user + association switcher placeholder)
- [x] Meetings list page (empty state)
- [x] Dark/light theme toggle
- [x] Language toggle (FR/EN/DE, sans drapeaux)

### Comptes démo seedés
| Rôle | Email | Password |
|------|-------|----------|
| Super Admin | `admin@tchoucti.cm` | `admin123` |
| Admin Groupement | `admin@demo.tchoucti.cm` | `groupement123` |
| Admin Association | `secretaire@demo.tchoucti.cm` | `assoc123` |
| Membre | `membre@demo.tchoucti.cm` | `membre123` |

---

## 5. Conventions de Code

### Backend (Python)
- **Async everywhere** : toutes les fonctions DB sont async
- **SQLAlchemy 2.x** : mapped_column, Mapped[type], relationships typées
- **UUIDs** partout (pas d'auto-increment)
- **Pydantic v2** : `model_config = {"from_attributes": True}`
- **Fichier par domaine** : 1 fichier models par module (finance.py, meeting.py, etc.)
- **Schemas séparés** : `app/schemas/{domain}.py` pour les Pydantic schemas
- **Routes** : `app/api/v1/{domain}.py`, montées avec préfixe `/api` dans `main.py`
- **Dépendances** : `get_db()` et `get_current_user()` dans `app/api/deps.py`

### Frontend (TypeScript)
- **App Router** (pas de pages/)
- **"use client"** explicite sur chaque composant interactif
- **shadcn/ui** pour tous les composants UI de base
- **Tailwind classes** : jamais de CSS custom, sauf dans globals.css
- **i18n** : `useTranslations("namespace")` — toutes les clés dans `locales/{lang}.json`
- **Store Zustand** : `useAuthStore()` pour l'auth, `usePermissionStore()` pour les permissions
- **API** : tout passe par `lib/api.ts` (namespaces `authApi`, `meetingsApi`, etc.)
- **Types** : tout dans `lib/types.ts` — mirroir des Pydantic schemas backend

### Nommage
- Backend routes : `snake_case` (`/api/auth/login`, `/api/meetings/{id}/entries`)
- Frontend paths : `kebab-case` (`/dashboard/social-aid`, `/dashboard/meetings`)
- Models : `PascalCase` (`MeetingActivityEntry`)
- DB tables : `snake_case` (`meeting_activity_entries`)

---

## 6. Comment tester

```bash
# Vérifier que les services tournent
docker compose ps

# Relancer le backend après un changement
docker compose up -d --build backend

# Re-seeder la base (drop + create + insert demo data)
docker compose exec backend python -m app.db.seed

# Tester l'API auth
curl -X POST http://localhost:18000/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@tchoucti.cm&password=admin123" | jq .

# Frontend dev server (en dehors de Docker)
cd frontend && pnpm dev

# Smoke test rapide (Python)
python3 -c "
import urllib.request, urllib.error
for u in ['http://localhost:3000/', 'http://localhost:3000/login', 'http://localhost:18000/api/health']:
    try:
        r = urllib.request.urlopen(u, timeout=5)
        print(f'OK {r.status} {u}')
    except urllib.error.HTTPError as e:
        print(f'OK {e.code} {u}')
    except Exception as e:
        print(f'ERR {u} {e}')
"
```

---

## 7. Architecture financière (important pour l'implémentation)

Chaque association a :
- 1 `Treasury` (solde global = argent physique réel)
- N `Fund` (GENERAL, INSURANCE, TONTINE, SAVINGS, PROJECT:xxx)
- Invariant : `Σ Fund.balance == Treasury.balance`

Chaque opération crée :
1. `TreasuryMovement` (IN/OUT/XFER, montant, référence)
2. N `LedgerEntry` (CREDIT/DEBIT sur un Fund spécifique)

Les entrées de réunion (`MeetingActivityEntry`) créent ces mouvements à la validation.

---

## 8. Endpoints API déjà définis côté frontend (mais PAS encore côté backend)

Le fichier `frontend/src/lib/api.ts` déclare ces namespaces — les appels HTTP sont prêts mais les routes backend n'existent pas encore :

```
groupementsApi.list()       → GET /api/groupements
groupementsApi.get(id)      → GET /api/groupements/{id}
associationsApi.list()      → GET /api/associations
meetingsApi.list(params)    → GET /api/meetings
meetingsApi.get(id)         → GET /api/meetings/{id}
meetingsApi.create(payload) → POST /api/meetings
meetingsApi.start(id)       → POST /api/meetings/{id}/start
meetingsApi.close(id)       → POST /api/meetings/{id}/close
meetingsApi.setAttendance() → PUT /api/meetings/{id}/attendance
meetingsApi.addEntry()      → POST /api/meetings/{id}/entries
meetingsApi.removeEntry()   → DELETE /api/meetings/{id}/entries/{entryId}
activitiesApi.list()        → GET /api/activities
membersApi.list(assocId)    → GET /api/memberships?association_id=xxx
```
