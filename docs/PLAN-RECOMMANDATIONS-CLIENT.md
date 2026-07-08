# Plan — recommandations client (juin 2026)

Suivi des recommandations du client, décisions cadrées, et feuille de route.
Légende statut : ✅ fait · 🟡 en cours · ⬜ à faire · 🔎 vérifié (constat).

## Décisions cadrées (validées avec le client)
- **Sortie d'argent = trésorier** : **workflow de validation**. N'importe quel
  membre du bureau PRÉPARE une sortie (décaissement prêt, versement aide, retrait
  caisse, versement tontine) ; elle reste EN ATTENTE tant que le **trésorier**
  ne l'a pas validée/acceptée. C'est lui qui déclenche réellement l'argent.
- **Export** : **les deux** — même format que l'import (classeurs multi-feuilles,
  aller-retour export→édition→ré-import) ET rapports lisibles (Excel/PDF).
- **Pronostics caisse** : rendement par **unité d'argent**, réparti aux
  contributeurs d'un prêt au prorata de leur apport. **Membre = vue locale**
  (son propre rendement selon sa contribution) ; **admin = vue locale + globale**
  (accessible depuis la page détail de la caisse).
- **Priorité** : corrections rapides d'abord.

## Lot 1 — Corrections rapides
- ✅ **Bug approbation de prêt** (`ccdb35a`). Cause : `db.expire_all()` après
  commit expirait aussi l'objet association ; `notify_user` lisait des attributs
  expirés (`assoc.currency`, `user.email`) → MissingGreenlet (lazy-load hors
  async). Fix : `db.expire(objet ciblé)` au lieu de `expire_all()` ; capture des
  attributs user avant commit ; détail construit avant la notif. Reject/repay/
  aides couverts.
- ✅ **Login** : suppression du panneau de comptes de démonstration (`ccdb35a`).
- ✅ **Séances passées (item 3)** : création manuelle / édition / génération
  bloquaient déjà les dates passées. Fix ajouté : `_populate_cycle` crée
  désormais une séance CLÔTURÉE (pas PLANIFIÉE) quand la date du tour est
  passée, + `min=aujourd'hui` sur la date de début du dialog de création de
  tontine. → seules les séances *importées/passées* sont dans le passé.
- ✅ **Domaine dynamique (item 4)** : `rootDomain()` (`lib/utils.ts`) prend
  désormais le **domaine réel** servi (dérivé de `window.location.hostname`,
  sous-domaine retiré) au lieu de fixer `myappsuite.com` ; `NEXT_PUBLIC_ROOT_DOMAIN`
  reste prioritaire. `groupementHost` / `associationLoginUrl` l'utilisent.
- ✅ **Verrou association après connexion + switcher (item 5)** : la session est
  scopée sur UNE association. `associationsApi.list()` remonte l'association
  courante (`current_association_id` en localStorage) en `[0]` → toutes les pages
  faisant `associations[0]` l'utilisent. Un utilisateur régulier avec **plusieurs**
  associations doit **en choisir une après la connexion** (écran de sélection dans
  le Shell) ; il peut **changer depuis le menu profil**. Le verrou est libéré à la
  déconnexion. NB : silo complet (comptes séparés par association) = chantier à part.
- 🔎 **Slug URL de connexion par association** : implémenté
  (`{groupement}.{domaine}/a/{slug}`, `public.py` + route `app/a/[slug]`).
  → à confirmer en live sur le domaine.

## Lot 2 — Sorties d'argent validées par le trésorier ✅
Architecture : **table générique `PayoutRequest`** = file de validation unique
(par `kind`), plutôt que d'ajouter des statuts à chaque domaine.
- ✅ Modèle `PayoutRequest` (pending/validated/rejected/cancelled) + RBAC
  `user_can_validate_payout` (trésorier OU admin). Flag `has_treasurer_role`
  exposé sur `/auth/me`.
- ✅ **Décaissement prêt / versement aide / versement tontine (argent) / retrait
  caisse** : le bouton **PRÉPARE** une demande EN ATTENTE ; l'argent ne sort
  qu'à la **validation du trésorier**. Tontine en avoir physique = pas de
  validation (aucun argent). Mouvement manuel OUT = réservé au trésorier
  (exécuté immédiatement).
- ✅ Routeur `/payouts` (liste + validate/reject/cancel) + notifications
  (préparation → trésoriers ; décision → préparateur).
- ✅ Écran **Validation des sorties** (`/dashboard/finance/validations`) :
  en attente + historique ; boutons Valider/Refuser (valideurs) ou Annuler
  (préparateur). Lien de nav injecté pour le bureau/trésorier.
- ✅ Anti-doublon par source ; `pending_payout` exposé sur prêts/aides (badge
  « En attente du trésorier »). Testé E2E sur le flux prêt (prépare → file →
  refus membre 403 → validation trésorier → prêt en remboursement).
- ⏳ Reste mineur : relabel boutons tontine/caisse (« préparer ») — le workflow
  fonctionne déjà, seul le libellé du bouton reste à ajuster.

## Lot 3 — Page détail membre (admin) ✅
- ✅ Endpoint `GET /memberships/{id}/activity?since=&until=` → cotisations
  (tontine/caisse/aide, via `MeetingActivityEntry` typé par préfixe d'activité),
  demandes (prêts + aides), revenus (mouvements OUT reçus : versement tontine /
  décaissement prêt / versement aide), + totaux et ventilations par famille.
- ✅ RBAC : bureau/admin = **vue globale** (n'importe quel membre) ; simple
  membre = **vue locale** (403 sur autrui). Testé E2E.
- ✅ Composant `MemberActivityView` : filtre de **période** + **2 formats**
  (groupé par activité / chronologique) + 3 totaux (cotisé/demandé/reçu).
  Intégré dans la page détail membre (bureau) + page **« Mon activité »**
  (`/dashboard/my-activity`, lien nav membre). i18n FR/EN/DE.
- Limite connue : tours de tontine à **bénéficiaires multiples**
  (related_membership_id=None) non rattachés aux revenus (cas courant = 1
  bénéficiaire, couvert). À compléter via `TontineRoundBeneficiary` si besoin.

## Lot 4 — Séances (réunions) ✅
- ✅ **Réordonner l'ordre de passage** (A) : `PUT /tontines/cycles/{id}/reorder`
   permute les bénéficiaires des tours PAS ENCORE servis (brouillon = tous ;
   cycle actif = tours futurs ; tours servis/en cours figés). Dialog
   monter/descendre `ReorderPassageDialog`. Testé E2E.
- ✅ **Obligation d'action tontine** (B, frontend) : section tontine dédiée en
   séance — chaque tontine exige une décision explicite (toggle « a tout
   donné », montant partiel, ou « rien » = 0 confirmé par modal). Un membre
   présent ne peut être enregistré tant qu'une tontine reste « à décider ».
- ✅ **Prêts + aides** (C) : déjà présents sur la page séance (agenda : sections
   Prêts / Aides). Ajout d'une **synthèse par type d'activité** (tontines /
   caisses / prêts / aides) dans le **PV** (rapport PDF de clôture).

## Lot 5 — Pronostics caisse ✅
- ✅ `GET /caisses/{id}/projections` : prêts financés par la caisse (statut
   disbursed/repaying) → **rentabilité par prêt** (intérêt total ÷ capital, %),
   **intérêts à venir** par échéance (`interest_part - paid_interest` des
   échéances non payées), et **part projetée** de chaque contributeur au prorata
   de l'apport (formule identique à `close_distribution_period`). `kept` →
   part membre = 0 (intérêts conservés).
- ✅ RBAC : `my` (vue LOCALE) pour tous ; `contributors` (vue GLOBALE) réservé
   aux admins (`is_admin_view`). Testé E2E (prorata 3500/6000 = 58,33% ; membre
   voit sa part, contributeurs masqués).
- ✅ Frontend : onglet **Pronostics** sur la page détail caisse (admin = local +
   global) ; **membre** = dialog Pronostics depuis « Mes cotisations »
   (vue locale, sa part projetée). i18n FR/EN/DE.

## Lot 6 — Imports (vérif complète) + Export
⬜ Vérifier à fond les imports **prêts / aides / caisses** (mouvements/actions).
⬜ **Export** : classeurs multi-feuilles (même format que l'import, ré-importable)
   ET rapports lisibles.

## Rappel infra
Le backend reperd `openpyxl` et le frontend `geist`/`next@15.5.19` à chaque
recréation de conteneur (volumes anonymes réinitialisés depuis l'image d'origine).
Faire **`docker compose build backend frontend && docker compose up -d`** dès que
le réseau le permet pour figer les dépendances dans les images.
