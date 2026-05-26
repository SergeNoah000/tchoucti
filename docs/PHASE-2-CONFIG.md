# Tchoucti — Phase 2 : Refonte configuration + onboarding admin

> **Mise à jour :** 2026-05-23
> **Statut :** spec validée, à implémenter
> **Prérequis :** commit `dd7da63` (Track 3 modules + auto-planning)

## Vision

Séparer **configuration** (admin uniquement) et **opérationnel** (bureau + membres).
L'admin configure l'association une seule fois via un onboarding guidé puis les autres
rôles n'interagissent qu'avec les séances et les demandes.

> **Principe UX fondamental — Application explicative.**
> Chaque champ de configuration doit être *auto-explicatif*. Aide contextuelle
> toujours visible (pas de tooltip masqué), exemples concrets, preview du
> comportement résultant. L'utilisateur doit comprendre AVANT de remplir.
> Pattern : `<Field label hint example preview>` au lieu de `<Field label>` seul.

## Décisions architecturales

| Question | Décision |
|---|---|
| Séances ↔ tontines | Hybride : 1 série de séances pour l'asso, chaque tontine *pioche* dans les futures |
| Caisses (modèle) | Système (caisse générale + 1 par tontine) + custom illimité |
| Activation prêts / aides | Flag d'activation par module + types catalogués |
| Onboarding admin | Wizard séquentiel à 5 étapes, dashboard verrouillé tant qu'incomplet |
| Migration données | Reseed dev (perte test data OK) ; Alembic pour prod plus tard |
| Participation tontine | Obligatoire pour chaque membre par défaut, opt-out à la création |
| Caisse "épargne perso" | 1 caisse par membre (isolée par membre) |
| Caisse "générale" | Partagée mais tracking contribution par membre via `LedgerEntry.membership_id` |

---

## Phase 0 — Foundation (migration + séparation rôles)

### Nouveaux modèles SQLAlchemy

```text
Caisse
  - id, association_id, name, description, category (system|collective|project|personal)
  - is_system (bool — caisse générale / tontine non supprimable)
  - is_recurring (bool — collectée à chaque séance ?)
  - recurring_amount (int — si is_recurring)
  - has_ceiling (bool), ceiling_amount
  - has_objective (bool), objective_amount, objective_deadline
  - is_member_required (bool — chaque membre doit cotiser ?)
  - member_required_amount, member_required_recurring (bool)
  - fund_id (FK Fund — 1-to-1, créé automatiquement)

LoanType
  - id, association_id, name, description
  - source_caisse_id (FK Caisse — où le prêt est pioché)
  - is_active
  - eligibility_min_seniority_months (int, default 0)
  - eligibility_no_default (bool, default True)
  - max_simultaneous (int, default 1)
  - max_per_year (int, default 1)
  - interest_rate_pct (Decimal)
  - max_duration_months (int)
  - late_fee_pct (Decimal, default 0)

AidType
  - id, association_id, name, description
  - is_active
  - member_contribution_amount (int — combien chaque membre doit donner)
  - is_contribution_recurring (bool — collecte par séance ou one-shot)
  - aid_ceiling_amount (int — plafond versé au bénéficiaire)
  - max_claims_per_member_per_year (int, default 1)
  - declaration_delay_days (int — temps max après l'événement)

MembershipCriterion (conditions d'adhésion)
  - id, association_id, type (age_min|age_max|gender|location|profession|other)
  - label, value (text), is_required (bool)

AssociationDocument (statuts, ROI…)
  - id, association_id, kind (statuts|roi|recepisse|other), name
  - file_url (MinIO), uploaded_by_id, uploaded_at

TontineMeetingLink
  - tontine_round_id, meeting_id (1-to-1 — la séance qui héberge ce round)
  - is_locked (bool — empêche le déplacement isolé)

MemberCaisseBalance (caisse "épargne perso" par membre)
  - membership_id, caisse_id, balance (int)
  - PK composite

TontineParticipation (opt-out par membre par tontine)
  - tontine_cycle_id, membership_id, is_participating (bool, default True)
```

### Changements modèles existants

- `Fund.kind` → reste enum mais on ajoute `CUSTOM`. Toutes les nouvelles caisses utilisent `CUSTOM`.
- `Association.config` ajout : `{ setup_complete: bool, setup_step: int, registration_fee: int|null }`
- `TontineCycle` : déjà supporte N par asso techniquement, juste UI à débloquer.

### Séparation rôles (frontend + backend)

**Backend**
- Décorateur `@require_association_admin` à appliquer sur tous les endpoints config :
  - `POST/PATCH /caisses`, `/loan-types`, `/aid-types`, `/tontines`, `/associations/{id}/config`, `/membership-criteria`
- Endpoints opérationnels (read/saisie séance/demandes) restent ouverts aux rôles métier.

**Frontend**
- Nouveau hook `useCanConfigure()` qui retourne `true` ssi `detectRole(user) === "association_admin"`.
- Route guards : `/dashboard/config/**` redirige vers `/dashboard` si `!canConfigure`.
- Sidebar : section "Configuration" visible uniquement pour admin.
- `detectRole` à raffiner : ne plus dire "manager pour tout non-membre" — distinguer `association_admin` du reste.

### Migration

```bash
docker compose down -v && docker compose up -d
# reseed inclut maintenant : caisse générale auto-créée par asso ;
# Association.config.setup_complete = false → forcera l'onboarding
```

### Commits attendus
1. `Phase 0a — Modèles config (Caisse, LoanType, AidType, criteria, docs)`
2. `Phase 0b — Séparation rôle admin (require_admin + canConfigure)`

---

## Phase 1 — Wizard d'onboarding (5 étapes)

### Route et flux

- Nouvelle route : `/dashboard/onboarding`
- Middleware : si user est `association_admin` ET `!association.config.setup_complete` → redirect vers `/dashboard/onboarding`
- Layout dédié `<WizardLayout>` avec `<StepIndicator>` (5 étapes, progression visible)
- Stockage progression : `association.config.setup_step` (0..5)
- Bouton "Passer pour l'instant" sur étapes 3-4-5 (tontines, prêts, aides — optionnels)
- Étape 1-2 (asso + caisses) obligatoires

### Les 5 étapes

| # | Étape | Obligatoire | Contenu |
|---|---|---|---|
| 1 | Association | ✓ | Nom, type légal, devise, contact, adresse, statut légal, conditions d'adhésion (critères + frais), upload documents |
| 2 | Caisses | ✓ | Caisse générale auto, possibilité d'ajouter custom (au moins 0 custom OK) |
| 3 | Tontines | optionnel | 0..N tontines avec mapping séances |
| 4 | Prêts | optionnel | Activer/non + types |
| 5 | Aides sociales | optionnel | Activer/non + types |

À la fin : `setup_complete = true`, redirect vers dashboard avec toast de bienvenue.

### Commit attendu
3. `Phase 1 — Wizard onboarding admin`

---

## Phase 2 — Sections de configuration

### 2a. Association (incl. critères d'adhésion + docs)

**Critères d'adhésion** — l'admin ajoute autant de critères qu'il veut :
- Âge minimum / maximum
- Sexe (M / F / mixte)
- Localisation (ville, région, pays)
- Profession
- Autre (label libre)

Chaque critère a un flag `is_required` (bloque l'invitation) ou indicatif.

**Frais d'inscription** : champ `registration_fee` (XAF par défaut 0). Si > 0,
nouveau membre doit régler avant activation (movement IN vers caisse générale,
visible dans son historique).

**Documents légaux** : statuts, règlement intérieur, récépissé, autres. Upload
vers MinIO, listés sur la page profil de l'asso.

[config/association](frontend/src/app/dashboard/config/association) — 3 onglets : Profil, Adhésion, Documents

### 2b. Caisses — modèle hybride

**Caisses système** (auto-créées, non supprimables)
- "Caisse générale" — fund kind GENERAL
- "Tontine — <nom>" — créée auto à chaque création de tontine

**Caisses custom** (illimité, créées par l'admin)
- Catégorie au choix : *collective* / *projet* / *épargne personnelle*
- **Épargne personnelle** : 1 ligne `MemberCaisseBalance` par membre, balance isolée. La caisse a un seul fund mais son ledger trace `membership_id` à chaque mouvement.
- **Collective** : balance unique partagée. Peut avoir plafond / objectif / cotisation obligatoire.
- **Projet** : variante de collective avec deadline + objective explicite.

**UI explicative — pattern à respecter :**
```
┌─ Catégorie : [Projet ▾]
│  ℹ️  Une caisse "projet" a un objectif et une date limite.
│      Exemple : construire un puits, objectif 500 000 XAF avant 2026-12-31.
├─ Récurrente à chaque séance ? [Oui / Non]
│  ℹ️  Si oui, chaque membre verra une ligne de cotisation à chaque séance.
├─ Cotisation obligatoire par membre ? [Oui / Non]
│  Si oui : montant → [____]
│  ℹ️  Marquera la cotisation comme manquante si un membre absent ne paie pas.
└─ Aperçu : "À chaque séance, chaque membre devra cotiser 2 000 XAF
            jusqu'à atteindre 500 000 XAF (mars 2027 actuellement)."
```

[config/caisses](frontend/src/app/dashboard/config/caisses) — liste + CRUD + drawer detail

### 2c. Tontines (multiples)

- L'admin peut créer N tontines par asso
- À la création : nom, montant cotisation, # bénéficiaires par tour, méthode de sélection (ordre / tirage / vote), # tours
- Mapping séances : "utiliser les N prochaines séances de l'asso" (défaut) OU "choisir séances spécifiques X, Y, Z"
- Reprise du multi-bénéficiaires déjà livré
- Participation par défaut **obligatoire** ; admin peut opt-out un membre à la création

[config/tontines](frontend/src/app/dashboard/config/tontines)

### 2d. Prêts (activation + types)

- Toggle global `Association.config.loans.enabled`
- Si activé : CRUD `LoanType`
  - Nom, description (explicative)
  - Caisse source (sélecteur — uniquement caisses collectives non-projet)
  - Éligibilité : ancienneté min (mois), pas de défaut antérieur
  - Limites : max simultanés, max par an
  - Taux d'intérêt mensuel
  - Durée max
  - Pénalité de retard (%)

L'écran `/dashboard/loans` ne montre les boutons "Demander un prêt" que si activé et au moins 1 type défini.

[config/loans](frontend/src/app/dashboard/config/loans)

### 2e. Aides sociales (activation + types)

- Toggle global `Association.config.aids.enabled`
- Si activé : CRUD `AidType` (naissance, décès parent, mariage, maladie, …)
  - Nom, description
  - Cotisation membre (montant + récurrent oui/non)
  - Plafond aide versée
  - Max demandes par membre / an
  - Délai de déclaration (jours après l'événement)

[config/aids](frontend/src/app/dashboard/config/aids)

### Commits attendus
4. `Phase 2a — Config association (critères adhésion, frais, docs)`
5. `Phase 2b — Config caisses (système + custom)`
6. `Phase 2c — Config tontines multiples`
7. `Phase 2d-e — Config prêts + aides (types catalogués)`

---

## Phase 3 — Refonte page séance (driven by config)

La page séance devient dynamique : elle liste les actions disponibles selon
ce qui est configuré.

Pour chaque membre (collapse) :
- **Présence** (présent/absent/excusé/retard) — déjà OK
- **Tontines actives sur cette séance** : 1 ligne par tontine où ce membre est participant. Bouton "Marquer payé" + montant pré-rempli.
- **Caisses récurrentes** : 1 ligne par caisse `is_recurring=true`. Pré-rempli si `is_member_required`.
- **Caisses non-récurrentes ouvertes** (projet, objectif en cours) : 1 ligne par caisse avec champ libre.
- **Remboursements prêts** : 1 ligne par prêt actif de ce membre. Échéance + montant attendu pré-rempli.
- **Aides sociales en cours** : 1 ligne par `AidCase` au statut APPROVED en cours de collecte. Montant = `aid_type.member_contribution_amount`.

Le `member-save` actuel s'étend pour accepter ces items dynamiques. Le PDF de PV
liste les totaux par module.

### Commit attendu
8. `Phase 3 — Page séance dynamique driven by config`

---

## Phase 4 — Flexibilité des séances

- `PATCH /meetings/{id}` accepte déjà `scheduled_on` → exposer une action "Déplacer" dans l'UI.
- Quand une séance liée à un round tontine est déplacée :
  - Si `tontine_meeting_link.is_locked` → bloquer + suggérer de décaler le cycle entier
  - Sinon : décaler juste cette séance, le round suit
- Bouton "Annuler cette séance" :
  - Statut → CANCELLED
  - Round tontine lié (si existe) : transféré sur la prochaine séance disponible OU repoussé d'1 période
- Pas de cascade auto sur les autres séances (changement individuel)

### Commit attendu
9. `Phase 4 — Déplacement et annulation séance par séance`

---

## Phase 5 — Historiques aides sociales

**Côté membre** — `/dashboard/aids/me`
- Mes cotisations (tableau : date séance, aide, montant)
- Mes demandes (déclarations + statut)

**Côté bureau** — `/dashboard/aids/contributions`
- Tableau pivot : membre × aide × cumul versé
- Filtres : période, type d'aide
- Export CSV

Endpoint : `GET /aids/contributions?membership_id=<uuid?>` — filtré par RBAC
(membre ne voit que son `membership_id`).

### Commit attendu
10. `Phase 5 — Historiques aides (membre + bureau)`

---

## Composants UI réutilisables à créer

Pour incarner le principe "explicative" partout :

```tsx
<HelpField
  label="Cotisation obligatoire"
  hint="Si activée, chaque membre verra cette caisse comme à payer à chaque séance."
  example="Ex : 5 000 XAF par séance pour la caisse projet 'puits'."
>
  <Input ... />
</HelpField>

<ExampleCallout intent="info">
  💡 Une caisse "projet" sert à collecter pour un objectif fini.
     Une fois l'objectif atteint, la caisse se ferme automatiquement.
</ExampleCallout>

<ConfigPreview>
  Voici ce qui se passera : chaque membre devra verser X à chaque séance
  jusqu'à atteindre Y avant Z.
</ConfigPreview>
```

À créer dans [components/config/](frontend/src/components/config/).

---

## Ordre d'exécution

```
Phase 0 (foundation)                ← bloque tout
  ↓
Phase 1 (wizard)  ──┐
                    │ peuvent avancer en parallèle
Phase 2a/2b/2c/2d/2e (sections config)
  ↓
Phase 3 (séance dynamique)         ← dépend des configs
  ↓
Phase 4 + 5 (flexibilité + historiques)  ← polish
```

Estimation : 10 commits, ~3-4 sessions de travail dense.

---

## Risques identifiés

1. **Migration des données existantes** — Reseed accepté, donc OK en dev. Pour prod, prévoir des migrations Alembic propres avant Phase 0 (Track 6).
2. **Complexité UX de l'onboarding** — Risque d'abandon si trop long. Mitigation : étapes 3-4-5 skippables, retour possible plus tard via `/dashboard/config/*`.
3. **Caisse épargne perso × N membres** — Si asso a 100 membres, ça fait 100 lignes `MemberCaisseBalance` par caisse perso. Pas un souci en volume mais à indexer correctement.
4. **Tontines multiples × séances partagées** — Conflits possibles si 2 tontines piochent la même séance. Validation à la création tontine pour signaler les chevauchements.
