# Tchoucti — Phase 6 : Réalignement du modèle métier + devise + silo login

> **Mise à jour :** 2026-05-29
> **Statut :** spec validée (4 décisions client), à implémenter
> **Contexte :** le modèle actuel traite `TontineCycle` comme racine — FAUX.
> Voir le modèle corrigé : mémoire `domain-model-tontine.md`.

## Décisions client (verrouillées)

1. **Distribution** : plusieurs gagnants/tour, chacun gagne **1 fois** par cycle.
   `nb_tours = nb_participants / bénéficiaires_par_tour`.
2. **Séances hors tontine** : non — les séances régulières sont **portées par les
   cycles**. Pas de tontine = uniquement séances extraordinaires.
3. **Héritage cycle suivant** : **tout** (config + participants + activités).
4. **Caisses ↔ tontines** : indépendance totale. La tontine crée sa caisse auto ;
   les caisses de tontine ne sont jamais source de prêt/aide.

---

## Phase 6A — Refactor du modèle Tontine → Cycles → Séances

### Modèle de données

**Nouveau** `Tontine` (entité durable, parent) :
```
Tontine
  id, association_id, name, slug, is_active
  # config par défaut héritée par chaque cycle
  round_amount, frequency (weekly|biweekly|monthly|bimonthly|custom),
  custom_interval_days, beneficiaries_per_round, beneficiary_pays (bool),
  selection_method (manual|random|seniority|vote|auction)
```

**Modifié** `TontineCycle` (devient enfant) :
```
TontineCycle
  id, tontine_id (FK), cycle_number (1,2,3…)
  round_amount (snapshot), start_date, end_date, status
  is_mandatory
  # le fonds dédié reste 1 par cycle (historique isolé)
```

`TontineRound` inchangé sauf : lié au cycle, 1 round ↔ 1 séance via
`TontineMeetingLink` (déjà là).

`TontineParticipation` : passe au niveau **cycle** (chaque cycle re-liste ses
participants, copiés depuis le cycle précédent à la génération).

### Création d'une tontine (1er cycle)
1. Crée `Tontine` + `TontineCycle` #1 + sa caisse système dédiée.
2. Calcule `nb_tours = ceil(nb_participants / beneficiaries_per_round)`.
3. **Crée d'office TOUTES les séances du cycle** selon la fréquence (à partir de
   start_date). Chaque séance = 1 round, lié via `TontineMeetingLink`.
4. Assigne les bénéficiaires aux tours (selon `selection_method`).

### Génération du cycle suivant
- Action `POST /tontines/{id}/cycles` : crée le cycle N+1, **hérite tout**
  (montant, fréquence, bénéf/tour, beneficiary_pays, participants, activités
  collectées), recalcule les tours, crée les nouvelles séances après la fin du
  cycle précédent. Admin peut ajuster avant validation.

### UI explicative (CRUCIAL)
À la création tontine, montrer clairement :
> « 10 participants, 2 bénéficiaires par tour → **5 séances**, une toutes les 4
> semaines à partir du 01/06. Chaque membre reçoit la cagnotte une seule fois. »

### Suppression du "générer des séances" automatique
- Retirer le bouton `POST /meetings/generate` du flux normal.
- Le remplacer par **"Ajouter une séance extraordinaire"** (one-shot, hors cycle).
- L'auto-extension Celery (`_auto_extend_planning`) : supprimée ou reliée à la
  génération de cycle, pas au calendrier asso.

### Séances tab
- **Passées** (closed) : contribution par membre + récap des totaux (déjà ~OK).
- **Futures** (planned) : infos préventives (tontine, montant attendu) + bouton
  **Décaler** (déjà là) + **Annuler** (déjà là).

### Commits estimés
1. `Phase 6A-1 — modèle Tontine parent + Cycle enfant + migration reseed`
2. `Phase 6A-2 — création cycle = séances d'office + assignation bénéficiaires`
3. `Phase 6A-3 — génération cycle suivant (héritage total)`
4. `Phase 6A-4 — retrait generate-séances, ajout séance extraordinaire`
5. `Phase 6A-5 — frontend : config tontine + preview + onglet cycles`

---

## Phase 6B — Devise (dropdown + conversion + exemples dynamiques)

### Sélecteur
- Remplacer l'input texte devise par un **`<Select>`** ISO 4217 (liste curée :
  XAF, XOF, EUR, USD, GBP, CAD, CHF, NGN, GHS, MAD, …).

### Conversion
- API libre **frankfurter.app** (sans clé, taux BCE) :
  `GET https://api.frankfurter.app/latest?from=XAF&to=EUR`.
- Service backend `app/services/forex.py` : `convert(amount, from, to)` avec
  cache Redis (TTL 24h) des taux.
- Au **changement de devise** d'une association : convertir les **montants de
  config** (registration_fee, recurring_amount des caisses, member_required,
  loan/aid amounts, round_amount des tontines) via l'API + arrondi.
  ⚠️ Ne PAS convertir les soldes de trésorerie historiques (mouvements passés
  restent dans leur devise d'origine) — afficher un avertissement clair.

### Exemples hardcodés → dynamiques
- Les hints i18n du type « Ex : 5 000 XAF » doivent utiliser la devise de l'asso.
  Remplacer par des clés paramétrées : `t("feeExample", { currency })` avec
  `fmt.currency(5000)`. Auditer tous les `XAF` en dur dans les locales + composants.

### Commits estimés
6. `Phase 6B-1 — Select devise ISO + service forex (frankfurter + cache Redis)`
7. `Phase 6B-2 — conversion config au changement de devise + warning`
8. `Phase 6B-3 — exemples i18n dynamiques (devise de l'asso)`

---

## Phase 6C — Corrections caisses / prêts / aides

- **Caisse ne choisit jamais de tontine** : vérifier qu'aucun form caisse ne
  demande de tontine (la tontine possède sa caisse, pas l'inverse).
- **Source prêt/aide** : exclure les caisses de tontine (kind=TONTINE) de la
  liste des sources — déjà exclu `project`, ajouter l'exclusion tontine.
- **Remplissage hors séance** : confirmer qu'un mouvement direct
  (`/finance/movements`) peut créditer n'importe quelle caisse custom.

### Commit estimé
9. `Phase 6C — caisses indépendantes + sources prêt/aide filtrées`

---

## Phase 6D — Login par association (silo) + invitation + Open Graph

> Gros chantier = Track 2 différé. À découper.

### Bug invitation (prioritaire)
- Symptôme : un email déjà admin d'une autre asso du groupement n'a pas reçu
  l'invitation comme admin d'une nouvelle asso.
- Cause probable : dédoublonnage de l'utilisateur/invitation par email **global**.
- Fix : invitation + membership scopées à **(email, association)**. Un même email
  peut exister comme **comptes séparés** par association (décision silo déjà prise).
  → revoir `memberships.invite` + `invitations.accept` pour ne pas court-circuiter
  quand l'email existe ailleurs.

### Login par association
- URL : `{groupement}.myappsuite.com/a/{slug-asso}` (login scopé).
- Lien partageable → page de login/adhésion de l'association.
- Implique : middleware tenant (sous-domaine groupement + path slug asso),
  refonte du modèle `User` (un compte par scope), refresh du flux de login.

### Open Graph (lien partageable)
- Meta sociales (`og:title`, `og:description`, `og:image`) sur la page
  login/adhésion, avec le **logo de l'association** (champ `logo_url`, upload à
  ajouter dans la config asso — oublié jusqu'ici).
- `generateMetadata` dynamique côté Next.js selon l'asso.

### Commits estimés
10. `Phase 6D-1 — fix invitation scopée (email peut être admin de N assos)`
11. `Phase 6D-2 — upload logo association + champ logo_url`
12. `Phase 6D-3 — login par sous-domaine groupement + slug asso`
13. `Phase 6D-4 — Open Graph dynamique (logo asso) sur lien partageable`

---

## Phase 6E — Fix UI rapide : modal d'invitation déborde

- Le lien d'invitation affiché en entier pousse les bords au-delà du modal
  (input compris).
- Fix : input readonly avec `truncate` / `overflow-x-auto`, bouton "Copier"
  à côté, largeur contrainte (`max-w-full`, `min-w-0`). Ne pas afficher le lien
  brut en pleine largeur.

### Commit estimé
14. `Phase 6E — fix débordement modal invitation (lien tronqué + copier)`

---

## Ordre recommandé

```
6E (quick UI fix)  →  6C (corrections caisses, petit)  →  6A (refactor cœur)
   →  6B (devise)  →  6D (silo login + invitation + OG, gros bloc final)
```

6A est le plus structurant et casse le schéma → reseed dev (perte data test OK).
6D peut être démarré en parallèle par le sous-bug invitation (6D-1) qui est
indépendant et urgent.

## Risques

- **6A migration** : `TontineCycle` existant n'a pas de `tontine_id`. Reseed
  complet en dev. Alembic propre nécessaire avant prod.
- **6B conversion** : ne jamais convertir l'historique financier — uniquement la
  config. Sinon corruption comptable.
- **6D silo** : touche l'auth → tester login/refresh/logout de bout en bout sur
  les 6 comptes démo + un nouvel email multi-asso.
