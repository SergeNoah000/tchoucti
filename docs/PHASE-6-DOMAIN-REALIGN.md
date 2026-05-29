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

## Phase 6B — Devise (dropdown + verrou + exemples dynamiques) ✅ FAIT

> **Décision client (2026-05-29)** : option **« verrouiller dès qu'il y a de
> l'historique »** retenue (≠ conversion auto). Choix libre de la devise tant
> qu'aucun mouvement de trésorerie n'existe ; figée ensuite. « Zéro risque
> comptable » — pas de conversion des montants stockés (l'option « convertir la
> config » a été explicitement écartée). Pas de service forex nécessaire.

### Sélecteur
- `frontend/src/components/common/currency-select.tsx` : `<Select>` ISO 4217
  (liste curée `src/lib/currencies.ts`), libellés localisés via `Intl.DisplayNames`.
- Remplace les inputs texte dans onboarding, association-detail, association-settings.

### Verrou
- Backend `AssociationOut.currency_locked` calculé : `True` dès qu'un
  `TreasuryMovement` existe pour l'association (`_has_financial_history`).
- `PATCH /associations/{id}` : refuse (409 `currency_locked`) si la devise change
  alors que `currency_locked`.
- Validation des codes devise (`ALLOWED_CURRENCIES`) en create + update.
- Frontend : `<CurrencySelect disabled={currency_locked}>` + hint explicatif.

### Exemples hardcodés → dynamiques
- Hints/preview i18n « Ex : 5 000 XAF » → clés paramétrées `{ amount }` calculées
  via `fmt.currency(N)` (onboarding fee/caisses, aid contribution/ceiling/preview).

### Commit
- `Phase 6B — devise : dropdown ISO + verrou si historique financier + exemples dynamiques`

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

### 6D-1 — Bug invitation ✅ FAIT (commit c0689d6)
- Symptôme : un email déjà admin d'une autre asso du groupement n'a pas reçu
  l'invitation comme admin d'une nouvelle asso.
- Cause : dans `create_membership`, l'email n'était envoyé que pour un compte
  tout neuf (`created_new_user`). Compte existant → ajouté en silence.
- Fix : envoi d'invitation dès qu'on invite par email (neuf OU existant).
  `accept` : mot de passe optionnel (requis seulement si compte sans password) ;
  un actif rejoignant une 2e asso garde son mot de passe. `peek` expose
  `existing_active` + `association_name` → la page d'activation saute l'étape
  mot de passe et propose « Rejoindre ».

### 6D-2 — Upload logo ✅ FAIT (commit ea05149)
- `POST /associations/{id}/logo` (image ≤ 5 Mo → MinIO → `logo_url`).
- Composant `LogoUpload` dans onboarding (profil) + paramètres (Général).

### 6D-3/4 — Login brandé par association + Open Graph ✅ FAIT
- Backend : `GET /public/association-branding?groupement={sub|slug}&association={slug}`
  (sans auth) → branding public (nom, logo, couleur) groupement + asso.
- Frontend : route serveur `app/a/[slug]/page.tsx` — résout le groupement via
  `x-tenant-slug` (sous-domaine, posé par le middleware tenant) ou `?g=` en dev ;
  `generateMetadata` → `og:title/description/image` (= logo asso) + twitter card ;
  `BrandedLogin` (client) affiche logo + couleur de l'asso. 404 si introuvable.
- CORS : `CORS_ORIGIN_REGEX` autorise `https://{grp}.${DOMAIN}`.

#### Infra (à appliquer sur le VPS — voir aussi le guide de déploiement)
1. **DNS** : enregistrement A wildcard `*.${DOMAIN}` → IP du VPS.
2. **Traefik** : le router frontend matche désormais
   `Host(${DOMAIN}) || HostRegexp(^[a-z0-9-]+\.${DOMAIN}$)` en **priority=10**
   (catch-all de dernier recours ; les routers explicites et ceux des autres
   apps gagnent). ⚠️ Vérifier après déploiement que les autres apps du domaine
   (ex. `globalasset.${DOMAIN}`) répondent toujours.
3. **TLS** : Let's Encrypt génère un cert par hôte via HTTP-01 au 1er accès
   (OK avec DNS wildcard). Pour un vrai cert wildcard → challenge DNS-01.
4. **SSR** : `API_INTERNAL_URL` (= `http://backend:8000/api`) pour le fetch de
   branding côté serveur Next (l'OG doit être rendu serveur).

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
