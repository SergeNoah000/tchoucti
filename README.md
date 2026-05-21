# Tchoucti — Dengoh

> Plateforme SaaS multi-tenant de gestion des **Groupements & Associations**
> Inspirée et basée sur l'architecture du projet **akiko** (Langeao SARL).

[![Backend](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square)](https://fastapi.tiangolo.com/)
[![Frontend](https://img.shields.io/badge/Frontend-Next.js%2016-000?style=flat-square)](https://nextjs.org/)
[![Database](https://img.shields.io/badge/Database-PostgreSQL%2015-336791?style=flat-square)](https://postgresql.org/)
[![i18n](https://img.shields.io/badge/i18n-FR%20%7C%20EN%20%7C%20DE-blue?style=flat-square)]()


---

## 🎯 Vision

Une plateforme SaaS multi-tenant pour digitaliser la gestion administrative et
financière des **associations** et de leurs **groupements** (tontines,
cotisations, assistance sociale, projets, réunions, etc.).

**Hiérarchie métier :**

```
SuperAdmin (Plateforme)
   │
   ▼
 Groupement (= tenant, sous-domaine)        ex: groupement-a.tchoucti.com
   ├─ Admin(s) Groupement
   │
   ├──▶ Association A
   │     ├─ Admin Association
   │     ├─ Manager(s)
   │     └─ Membres
   │          → rôles métier : Président, VP, Secrétaire, Trésorier, Censeur…
   │
   └──▶ Association B …
```

---

## 🚀 Quick Start

### Prérequis
- Docker & Docker Compose v2+
- Node.js 20+ & pnpm
- Make (optionnel)

### Installation

```bash
# 1. Cloner
git clone git@github.com:SergeNoah000/tchoucti.git
cd tchoucti

# 2. Démarrer toute la stack (db + redis + minio + mailpit + backend + frontend)
docker compose up -d --build
```

C'est tout. Au premier démarrage, le backend **crée les tables et injecte
les données de démo automatiquement** (rôles RBAC + comptes de démo). Les
démarrages suivants préservent les données.

> 💡 `.env` est **optionnel** — chaque variable a une valeur par défaut de dev.
> Copier `.env.example` → `.env` uniquement pour personnaliser la config locale.

> 💡 Alternative dev local frontend (hot reload natif) :
> ```bash
> cd frontend && pnpm install && pnpm dev
> ```

### Accès

| Service | URL | Identifiants |
|---|---|---|
| 🌐 Frontend | http://localhost:13000 | — |
| 🔌 API | http://localhost:18000 | — |
| 📖 Swagger | http://localhost:18000/docs | — |
| 📊 MinIO Console | http://localhost:19001 | minioadmin / minioadmin123 |
| 📧 Mailpit (e-mails dev) | http://localhost:18025 | — |


**Comptes seed :**

| Rôle | Email | Password |
|---|---|---|
| Super Admin | admin@tchoucti.cm | admin123 |
| Admin Groupement | admin@demo.tchoucti.cm | groupement123 |
| Admin Association | secretaire@demo.tchoucti.cm | assoc123 |
| Membre | membre@demo.tchoucti.cm | membre123 |

> 🌍 Multi-tenant en dev : `http://demo.localhost:13000` et `http://admin.localhost:13000`
> (sur Linux/macOS, `*.localhost` est résolu automatiquement vers 127.0.0.1).


---

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│    Backend      │────▶│  PostgreSQL 15  │
│  (Next.js 16)   │     │   (FastAPI)     │     │                 │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              ┌─────────┐  ┌─────────┐  ┌─────────┐
              │  Redis  │  │  MinIO  │  │  Celery │
              │ (cache) │  │  (S3)   │  │ (tasks) │
              └─────────┘  └─────────┘  └─────────┘
```

### Stack

**Backend** — FastAPI · SQLAlchemy 2 async · Alembic · PostgreSQL 15 · Redis · MinIO · JWT

**Frontend** — Next.js 15 · React 19 · TypeScript · Tailwind CSS 3 · shadcn/ui (Radix) · TanStack Query · Zustand · `next-intl` (FR/EN/DE) · `next-themes` (dark mode)


**Infra** — Docker · Nginx · Let's Encrypt (wildcard `*.tchoucti.com`) · GitHub Actions

---

## 📦 Modules fonctionnels

| Module | Statut |
|---|---|
| 🏛  Multi-tenant (sous-domaines, isolation) | ✅ v0.1 |
| 🔐 Auth JWT + RBAC granulaire (30 tables, 6 rôles seedés) | ✅ v0.1 |
| 🎨 Design system soft + dark mode + FR/EN/DE | ✅ v0.1 |
| 🏠 Landing + Login + Activation + Dashboard shell | ✅ v0.1 |

| 👥 SuperAdmin : gestion groupements & abonnements | 🟡 Sprint 2 |
| 🏢 Admin Groupement : associations, admins | 🟡 Sprint 2 |
| 📋 Admin Association : membres, rôles métier, événements | 🟡 Sprint 3 |
| 📝 **Page Séance de Réunion** (saisie activités par membre) | 🟡 Sprint 4 |
| 💰 Tontine (cycles, tours, bénéficiaires) | 🟡 Sprint 5 |
| 🫱 Assistance sociale (demandes, validation) | 🟡 Sprint 5 |
| 💵 Cotisations & finances | 🟡 Sprint 5 |
| 📄 Documents (statuts, PV, rapports) | 🟡 Sprint 6 |
| 🔔 Notifications | 🟡 Sprint 6 |
| 📱 PWA Offline-first | 🔵 V2 |

---

## 📚 Documentation

- [docs/architecture.md](docs/architecture.md) — Architecture détaillée
- [docs/data-model.md](docs/data-model.md) — Modèle de données
- [docs/rbac.md](docs/rbac.md) — Système de rôles & permissions
- [docs/multi-tenant.md](docs/multi-tenant.md) — Stratégie multi-tenant

---

## 📄 Licence

Propriétaire — © 2026 Langeao SARL
