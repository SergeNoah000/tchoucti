# Tchoucti — Architecture

## Vue d'ensemble

Plateforme SaaS multi-tenant pour la gestion des **associations** (réunions, finances, tontine, prêts, assistance sociale, projets).

```
┌──────────────────────────────────────────────────────────┐
│                  Langeao SARL (Platform)                  │
│     admin.tchoucti.com  →  Super-admin (plateforme)       │
└──────────────────────────────────────────────────────────┘
            │
            ├── Groupement « famille-ndong »
            │       famille-ndong.tchoucti.com
            │   ├── Association « Reunions Du Vendredi »
            │   │       (path: /a/reunions-vendredi)
            │   │   ├── 25 membres (Memberships)
            │   │   ├── Treasury → Funds (general/insurance/tontine/savings)
            │   │   ├── Meetings → Activity Entries → Treasury Movements
            │   │   ├── Loans (avec intérêts + échéancier)
            │   │   ├── Tontine cycles
            │   │   ├── Social aid cases
            │   │   └── Projects
            │   └── Association « Tontine 100k »
            │
            └── Groupement « assos-batie »
                    assos-batie.tchoucti.com
                ├── Association « Femmes Solidaires »
                └── Association « Jeunesse 2024 »
```

## Hiérarchie

1. **Plateforme** : Langeao SARL — `admin.tchoucti.com` — super-admins.
2. **Groupement** (tenant level 1) : un sous-domaine `{slug}.tchoucti.com`.
   - Contient N associations, ses propres admins, son abonnement.
3. **Association** (tenant level 2) : sous un groupement, accédée via path `/a/{slug}`.
   - Contient ses membres, ses réunions, sa caisse propre.
4. **Membership** : lien `User ↔ Association` (+ rôles multiples : Président, Trésorier, Censeur, Membre…).

## Identité & autorisation

- **User** : identité globale (email unique sur la plateforme).
- **Membership** : adhésion d'un user à une association (numéro d'adhérent, dates, statut).
- **Role** : bundle de permissions. Système (non supprimables) ou custom (par asso).
- **Permission** : action atomique (`loans.approve`, `treasury.manage`, …).
- **UserPermission** : override granulaire (rare).

Rôles système :

| Rôle | Scope | Description |
|---|---|---|
| `super_admin` | Platform | Langeao SARL |
| `groupement_admin` | Groupement | Admin du sous-domaine |
| `association_admin` | Association | Président par défaut |
| `association_manager` | Association | Anime les séances |
| `treasurer` | Association | Trésorier |
| `censor` | Association | Censeur / audit |
| `member` | Association | Adhérent simple |

## Architecture financière (cœur du projet)

### Modèle hybride : caisse globale + ventilation par fonds

```
Association
   └── Treasury  (1-1, "caisse globale" — solde absolu de l'argent réel)
            ├── Fund GENERAL      ← cotisations, dons, amendes, capital prêts
            ├── Fund INSURANCE    ← cotisation assurance + intérêts prêts + pénalités
            ├── Fund TONTINE      ← pot de la tontine en cours
            ├── Fund SAVINGS      ← épargne libre (suivi par membre)
            └── Fund PROJECT:xxx  ← un fonds par projet voté
```

**Invariant strict :** `Σ Fund.balance == Treasury.balance == Σ TreasuryMovement.signed_amount`.

### Modèle de données financières

- `TreasuryMovement` : un mouvement de cash (IN / OUT / XFER), montant positif, direction signée.
- `LedgerEntry` : ventilation d'un mouvement vers un Fund (CREDIT ou DEBIT).
  - 1 IN simple = 1 ligne CREDIT.
  - 1 OUT simple = 1 ligne DEBIT.
  - Remboursement de prêt avec intérêt = 1 mouvement IN, 2 lignes CREDIT (GENERAL + INSURANCE).
  - Transfert inter-fonds = 1 mouvement XFER (cash net 0), 1 DEBIT source + 1 CREDIT cible.

### Mapping des activités de réunion → fonds

| Activité | Direction | Fonds crédité / débité |
|---|---|---|
| Cotisation mensuelle | IN | + GENERAL |
| Cotisation assurance | IN | + INSURANCE |
| Versement tontine | IN | + TONTINE |
| Décaissement tontine (au bénéficiaire) | OUT | − TONTINE |
| Remboursement de prêt | IN | + GENERAL (capital) + INSURANCE (intérêt + pénalité) |
| Octroi de prêt | OUT | − GENERAL |
| Amende | IN | + GENERAL |
| Épargne libre | IN | + SAVINGS (tracké par membre) |
| Don exceptionnel | IN | + GENERAL |
| Contribution projet | IN | + PROJECT:xxx |
| Aide sociale (décès, maladie…) | OUT | − INSURANCE |

## Prêts

Système complet (cf. validation utilisateur) :
- Taux d'intérêt **configurable** par association (`config.loan_interest_rate_pct`)
- **Échéancier auto-calculé** à l'approbation (`LoanInstallment` × N)
- **Pénalités de retard** (`late_fee_pct`) accumulées sur les échéances en retard
- **Intérêts + pénalités → fonds INSURANCE** (renforce l'auto-assurance)
- Plafond : `principal ≤ multiplier × cumulative_contributions` du membre

## Tontine

Tontine **fixe** (rotation classique) — 1 cycle actif à la fois :
- `TontineCycle` : nb de tours = nb de participants, `round_amount` fixe.
- `TontineRound` : chaque tour a 1 bénéficiaire prédéfini (ordre manuel / aléatoire / ancienneté).
- `TontineContribution` : trace de versement de chaque membre par tour (lié à un `MeetingActivityEntry`).
- À la clôture du tour : 1 OUT vidant le fonds TONTINE vers le bénéficiaire.

## Assistance sociale

Fonds **collectif** (cf. validation utilisateur) :
- Cotisation fixe par réunion (configurable, `config.insurance_contribution`).
- Barème pré-défini (`config.social_aid_amounts`) :
  - décès parent / conjoint / enfant / membre, hospitalisation, sinistre…
- `SocialAidCase` (demande → review → approved → paid) avec `SocialAidPayout`.
- Décaissement depuis le fonds INSURANCE.

## Réunions (séance)

Suit la maquette `Idee_Page_gestion_Seance-Reunion.pdf` :
1. Manager crée une `Meeting`, statut PLANNED.
2. Au lancement → ONGOING. Saisie des présences (`MeetingAttendance`).
3. Pour chaque membre, sélection et saisie des activités → `MeetingActivityEntry` (DRAFT).
4. Validation → RECORDED : crée `TreasuryMovement` + `LedgerEntry`(s), met à jour
   `Membership.cumulative_contributions`, échéances de prêts, contributions tontine, etc.
5. Correction d'une saisie RECORDED → contre-passation + nouvelle saisie (audit-friendly).
6. Clôture → CLOSED, génération PV PDF, snapshots des totaux.

## Stack technique

- **Backend** : FastAPI (async), SQLAlchemy 2.x, Pydantic v2, Alembic, JWT.
- **DB** : PostgreSQL 16 (JSONB pour `config` et `data`).
- **Cache / queue** : Redis (+ optionnellement Celery pour notifications/exports).
- **Storage** : MinIO (S3 compatible) pour PV, justificatifs, logos.
- **Frontend** : Next.js 14 (App Router), Tailwind, shadcn/ui, lucide-icons.
- **Charts** : Recharts.
- **i18n** : fr (par défaut) + en + langue locale (extensible).

## Multi-tenancy

- **Niveau 1 (Groupement)** : isolation par sous-domaine → `TenantMiddleware` parse `Host`.
- **Niveau 2 (Association)** : isolation par chemin `/a/{slug}` + filtres SQL systématiques sur `association_id`.
- Toutes les requêtes DB sont scopées par `(groupement_id, association_id)` via dépendances FastAPI.
- L'override d'en-tête `X-Tenant-Slug` est dispo en dev/mobile.
