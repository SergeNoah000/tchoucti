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

## Lot 2 — Sorties d'argent validées par le trésorier
⬜ Workflow prépare → EN ATTENTE → le trésorier valide, pour : décaissement prêt,
versement aide, retrait caisse, versement tontine. Statut « en attente de
validation trésorier » + écran de validation + notifications. Rôle `treasurer`.

## Lot 3 — Page détail membre (admin)
⬜ Résumé d'activité d'un membre sur une **période** :
- Cotisations (tontine, caisse, aides), Demandes (prêts, aides), Revenus
  (tontine, prêts, aides).
- **2 formats** : chronologique (période) / groupé par activité (tontines,
  caisses, aides, prêts).
- **Vue locale** (le membre voit la sienne) + **vue globale** (admin).

## Lot 4 — Séances (réunions)
⬜ Bouton **réordonner l'ordre de passage** des membres.
⬜ **Obligation d'action tontine** en séance : cocher « a tout donné » ou saisir
   clairement 0 / le montant cotisé.
⬜ Ajouter **prêts + aides** sur la page séance et dans les **rapports**.

## Lot 5 — Pronostics caisse
⬜ Page détail caisse : intérêts à venir des prêts (par échéance/date) +
   **rentabilité par unité prêtée** (intérêt total ÷ capital) pour chaque prêt,
   répartie aux contributeurs au prorata. Vue membre locale, admin locale+globale.

## Lot 6 — Imports (vérif complète) + Export
⬜ Vérifier à fond les imports **prêts / aides / caisses** (mouvements/actions).
⬜ **Export** : classeurs multi-feuilles (même format que l'import, ré-importable)
   ET rapports lisibles.

## Rappel infra
Le backend reperd `openpyxl` et le frontend `geist`/`next@15.5.19` à chaque
recréation de conteneur (volumes anonymes réinitialisés depuis l'image d'origine).
Faire **`docker compose build backend frontend && docker compose up -d`** dès que
le réseau le permet pour figer les dépendances dans les images.
