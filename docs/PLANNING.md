# Tchoucti — Planning Détaillé des Tâches Restantes

> **Lire `docs/CONTEXT.md` avant de commencer toute tâche.**
> Chaque phase est autonome. Un modèle peut prendre 1 phase à la fois.

---

## Phase 1 — CRUD Backend Core (Priorité HAUTE)

Les modèles SQLAlchemy existent déjà. Il faut créer les schemas Pydantic + endpoints CRUD.

### 1.1 Groupements CRUD
- **Fichiers à créer** : `backend/app/schemas/groupement.py`, `backend/app/api/v1/groupements.py`
- **Schemas** : `GroupementCreate`, `GroupementUpdate`, `GroupementOut` (miroir de `Groupement` model)
- **Endpoints** :
  - `GET /api/groupements` — liste (super_admin only ou filtré par user.groupement_id)
  - `GET /api/groupements/{id}` — détail
  - `POST /api/groupements` — créer (super_admin only)
  - `PATCH /api/groupements/{id}` — modifier
- **Inclure le router** dans `backend/app/api/v1/__init__.py`
- **Dépendance** : `get_current_user` de `deps.py`

### 1.2 Associations CRUD
- **Fichiers** : `backend/app/schemas/association.py`, `backend/app/api/v1/associations.py`
- **Schemas** : `AssociationCreate`, `AssociationUpdate`, `AssociationOut`
- **Endpoints** :
  - `GET /api/associations` — liste (filtré par groupement_id du user connecté)
  - `GET /api/associations/{id}` — détail
  - `POST /api/associations` — créer (groupement_admin+)
  - `PATCH /api/associations/{id}` — modifier
- **Logique** : scope par `user.groupement_id` sauf super_admin

### 1.3 Members / Memberships CRUD
- **Fichiers** : `backend/app/schemas/membership.py`, `backend/app/api/v1/memberships.py`
- **Schemas** : `MembershipCreate` (user_id, association_id, role_codes[]), `MembershipOut` (avec user nested + roles)
- **Endpoints** :
  - `GET /api/memberships?association_id=xxx` — liste des membres d'une asso
  - `POST /api/memberships` — inviter un membre (crée User si email inconnu + Membership + MembershipRole)
  - `PATCH /api/memberships/{id}` — modifier statut/rôles
  - `DELETE /api/memberships/{id}` — suspendre

### 1.4 Roles & Permissions (lecture seule)
- **Fichiers** : `backend/app/schemas/role.py`, `backend/app/api/v1/roles.py`
- **Endpoints** :
  - `GET /api/roles` — liste des rôles système
  - `GET /api/permissions` — liste des permissions
  - `GET /api/me/permissions?association_id=xxx` — permissions effectives du user courant

---

## Phase 2 — Séances / Meetings (Priorité HAUTE — cœur du projet)

### 2.1 Backend Meetings API
- **Fichiers** : `backend/app/schemas/meeting.py`, `backend/app/api/v1/meetings.py`
- **Schemas** : `MeetingCreate`, `MeetingOut`, `AttendanceItem`, `ActivityEntryCreate`, `ActivityEntryOut`
- **Endpoints** :
  - `GET /api/meetings?association_id=&status=` — liste
  - `GET /api/meetings/{id}` — détail (avec attendance + entries)
  - `POST /api/meetings` — créer (status=scheduled)
  - `POST /api/meetings/{id}/start` — passer en in_progress
  - `POST /api/meetings/{id}/close` — clôturer (verrouille les entries, crée les mouvements treasury)
  - `PUT /api/meetings/{id}/attendance` — bulk saisie présences
  - `POST /api/meetings/{id}/entries` — ajouter une activité financière
  - `DELETE /api/meetings/{id}/entries/{entry_id}` — supprimer une entrée (si meeting pas clôturée)

### 2.2 Backend Activities API
- **Fichiers** : `backend/app/schemas/activity.py`, `backend/app/api/v1/activities.py`
- **Endpoints** :
  - `GET /api/activities?association_id=` — liste des types d'activité
  - `POST /api/activities` — créer un type d'activité custom
- **Note** : le seed devrait créer les activités par défaut (cotisation, amende, don, etc.)

### 2.3 Frontend — Page Séance Complète
- **Fichier** : `frontend/src/app/dashboard/meetings/[id]/page.tsx`
- **Design** : suivre la maquette `Idee_Page_gestion_Seance-Reunion.pdf`
- **Composants à créer** dans `frontend/src/components/meeting/` :
  - `MeetingHeader.tsx` — titre, statut (badge), date, boutons Start/Close
  - `AttendancePanel.tsx` — liste des membres avec toggle Present/Absent/Excused/Late
  - `ActivityEntryForm.tsx` — sélecteur activité + membre + montant + commentaire
  - `EntryList.tsx` — tableau des entrées saisies (avec suppression)
  - `MeetingSummary.tsx` — totaux (collecté, dépensé, solde net), ventilation par fonds
- **Onglets** (utiliser `<Tabs>` shadcn) : Présence | Activités | Résumé
- **i18n** : les clés `meeting.*` existent déjà dans les 3 locales

### 2.4 Frontend — Créer une Séance
- **Fichier** : `frontend/src/app/dashboard/meetings/new/page.tsx`
- **Formulaire** : titre, date, lieu (optionnel), association (select si admin groupement)
- **Soumet** via `meetingsApi.create()`

---

## Phase 3 — Finance / Trésorerie (Priorité MOYENNE)

### 3.1 Backend Treasury API
- **Fichiers** : `backend/app/schemas/finance.py`, `backend/app/api/v1/finance.py`
- **Endpoints** :
  - `GET /api/treasury?association_id=` — solde global + liste des fonds
  - `GET /api/treasury/movements?fund_id=&from=&to=` — historique mouvements
  - `POST /api/treasury/movements` — mouvement manuel (admin only, ex: ajustement)
- **Logique à la clôture de séance** (dans meetings.close) :
  - Pour chaque `MeetingActivityEntry` validée, créer `TreasuryMovement` + `LedgerEntry`
  - Mettre à jour `Fund.balance`, `Treasury.balance`, `Membership.cumulative_contributions`

### 3.2 Frontend Finance Dashboard
- **Fichier** : `frontend/src/app/dashboard/finance/page.tsx`
- **Afficher** : solde global, liste des fonds avec balances, graphique d'évolution (Recharts)
- **Historique** : tableau de mouvements avec filtres (date, fonds, direction)

---

## Phase 4 — Prêts (Priorité MOYENNE)

### 4.1 Backend Loans API
- **Fichiers** : `backend/app/schemas/loan.py`, `backend/app/api/v1/loans.py`
- **Endpoints** :
  - `GET /api/loans?association_id=&status=` — liste
  - `POST /api/loans` — demande de prêt (membre)
  - `POST /api/loans/{id}/approve` — approuver + générer échéancier `LoanInstallment`
  - `POST /api/loans/{id}/disburse` — décaisser (crée mouvement OUT sur GENERAL)
  - `POST /api/loans/{id}/repay` — enregistrer remboursement (via séance ou manuel)
- **Calcul** : intérêts mensuels, pénalités de retard, split capital/intérêt/pénalité → GENERAL + INSURANCE

### 4.2 Frontend Loans Page
- **Fichier** : `frontend/src/app/dashboard/loans/page.tsx`
- **Vues** : liste des prêts (avec statut), détail prêt (échéancier), formulaire demande

---

## Phase 5 — Tontine (Priorité MOYENNE)

### 5.1 Backend Tontine API
- **Fichiers** : `backend/app/schemas/tontine.py`, `backend/app/api/v1/tontines.py`
- **Endpoints** :
  - `GET /api/tontines?association_id=` — cycle actif
  - `POST /api/tontines` — créer un cycle (nb tours, montant, participants, ordre)
  - `POST /api/tontines/{cycle_id}/rounds/{round_id}/payout` — décaisser au bénéficiaire
- **Logique** : les contributions tontine sont saisies en réunion → `MeetingActivityEntry` → `Fund TONTINE`

### 5.2 Frontend Tontine Page
- **Fichier** : `frontend/src/app/dashboard/tontines/page.tsx`
- **Afficher** : cycle en cours, tableau des tours (bénéficiaire, statut), contributions par membre

---

## Phase 6 — Aide Sociale (Priorité MOYENNE)

### 6.1 Backend Social Aid API
- **Fichiers** : `backend/app/schemas/social_aid.py`, `backend/app/api/v1/social_aid.py`
- **Endpoints** :
  - `GET /api/social-aid?association_id=` — liste des cas
  - `POST /api/social-aid` — déclarer un cas (membre)
  - `POST /api/social-aid/{id}/approve` — approuver
  - `POST /api/social-aid/{id}/payout` — verser (mouvement OUT sur INSURANCE)

### 6.2 Frontend Social Aid Page
- **Fichier** : `frontend/src/app/dashboard/social-aid/page.tsx`

---

## Phase 7 — Projets (Priorité BASSE)

### 7.1 Backend Projects API
- **Fichiers** : `backend/app/schemas/project.py`, `backend/app/api/v1/projects.py`
- **CRUD** : créer, liste, détail, contributions, clôturer

### 7.2 Frontend Projects Page
- **Fichier** : `frontend/src/app/dashboard/projects/page.tsx`

---

## Phase 8 — Admin Plateforme (Priorité MOYENNE)

### 8.1 Backend Admin Endpoints
- `GET /api/admin/stats` — stats globales (nb groupements, users, associations, MRR)
- `GET /api/admin/groupements` — liste complète avec stats par groupement
- `POST /api/admin/groupements/{id}/suspend` — suspendre un groupement
- `POST /api/admin/groupements/{id}/activate` — réactiver

### 8.2 Frontend Admin Enrichi
- Enrichir `frontend/src/app/admin/page.tsx` avec :
  - Tableau de groupements (nom, slug, nb assos, nb users, statut abo, actions)
  - Formulaire création groupement
  - Stats temps réel (si possible graphiques)

---

## Phase 9 — Documents & Exports (Priorité BASSE)

### 9.1 Upload de documents
- Backend : endpoint upload vers MinIO S3
- Frontend : page documents avec upload drag & drop

### 9.2 Export PDF
- PV de réunion auto-généré à la clôture
- Export bilan financier

---

## Phase 10 — Polish & Production (Priorité BASSE)

- [ ] Notifications (email via SMTP + in-app)
- [ ] Audit log (écriture automatique sur chaque action sensible)
- [ ] Alembic migrations propres (remplacer drop/create par migrations versionnées)
- [ ] Tests unitaires backend (pytest)
- [ ] CI/CD (GitHub Actions)
- [ ] Déploiement production (AWS / VPS)
- [ ] Monitoring (Sentry, health checks)

---

## Ordre de priorité recommandé

```
Phase 1 (CRUD core)  →  Phase 2 (Meetings)  →  Phase 3 (Finance)
     ↓                                              ↓
Phase 8 (Admin)       Phase 4 (Prêts) + Phase 5 (Tontine) + Phase 6 (Aide sociale)
                                        ↓
                      Phase 7 (Projets) + Phase 9 (Documents)
                                        ↓
                              Phase 10 (Production)
```

**La Phase 2 (Meetings) est le cœur du projet** — c'est la fonctionnalité principale à livrer en premier.

---

## Template de prompt pour chaque itération

```
Lis le fichier docs/CONTEXT.md pour comprendre le projet.
Lis le fichier docs/PLANNING.md pour voir les tâches restantes.

Je veux implémenter : [Phase X.Y — nom de la tâche]

Conventions :
- Backend : async, SQLAlchemy 2.x, Pydantic v2, fichiers dans app/schemas/ et app/api/v1/
- Frontend : Next.js App Router, "use client", shadcn/ui, useTranslations(), Tailwind v3
- Toujours inclure le router dans app/api/v1/__init__.py
- Toujours ajouter les clés i18n dans les 3 locales (fr/en/de)
- Rebuild backend après changement : docker compose up -d --build backend
- Re-seed si nouveau modèle : docker compose exec backend python -m app.db.seed
```
