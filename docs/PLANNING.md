# Tchoucti — Planning

> Lire `docs/CONTEXT.md` pour la stack et les conventions.
> Ce fichier = feuille de route vivante. Mise à jour : 2026-05-23.

---

## ✅ Acquis (fait & vérifié)

- **Auth & RBAC** — JWT (access + refresh), 7 rôles système, 36 permissions
- **Multi-tenant** — middleware sous-domaine, Groupement → Association
- **Dashboards role-aware** — 4 vues distinctes (super-admin / admin groupement / admin association / membre), couleur primaire par rôle
- **Groupements** — CRUD, page détail à onglets, équipe d'admins, propriétaire + transfert, suspension
- **Associations** — CRUD, page détail à onglets, liste hiérarchique
- **Membres** — invitation par e-mail, liste, suspension/réactivation, rôles
- **Invitations** — moteur générique (tokens hashés, expir 7j, renvoi, révocation), e-mail via Mailpit
- **Infra** — `docker compose up` lance tout + auto-seed si base vide

## ✅ Track 1 — Paramètres d'association (v1)

7 sections (général, tontine, caisse sociale, paiements, réunions, notifications, membres) — stockage `Association.config` JSONB. Sera **refactoré** en Phase 2 (config-v2).

## ✅ Track 3 — Modules métier opérationnels

- **Tontine** — cycles + tours + **multi-bénéficiaires** (`share_parts`), payout vers trésorerie
- **Finance** — trésorerie + fonds + mouvements (IN/OUT/XFER), invariant `Σ fonds = trésorerie`
- **Caisse sociale** — déclaration → approbation → versement
- **Prêts** — échéancier (intérêt mensuel simple), approbation, déboursement, remboursement
- **Séances** — refonte collapsible par membre, save bulk sur fermeture du collapse, clôture poste vers trésorerie

## ✅ Auto-planning séances + Celery rappels

- `POST /meetings/generate` pré-crée N séances futures selon cadence asso
- Auto-extension après clôture (rolling window)
- Worker Celery + beat (toutes les 15 min) envoie rappels e-mail à J-N configurables
- Templates de rappel FR/EN/DE
- Settings UI : horizon, titre par défaut, lieu, rappels enabled + délais

---

## 🟡 Phase 2 — Refonte configuration + onboarding admin ⟵ EN COURS

**Voir [docs/PHASE-2-CONFIG.md](PHASE-2-CONFIG.md) pour le plan détaillé.**

Retour client après tests : la configuration actuelle n'est pas assez fine ni
explicite. Refonte majeure :

- **Séparation rôle admin** — seul l'admin configure, les autres rôles opèrent
- **Wizard d'onboarding** à 5 étapes, dashboard verrouillé tant qu'incomplet
- **Multi-tontines** par association (chacune avec config indépendante)
- **Caisses hybrides** — système (générale + tontine) + custom (épargne perso, collective, projet) avec config riche (récurrence, plafond, objectif, cotisation obligatoire)
- **Prêts catalogués** — flag d'activation + types (éligibilité, taux, durée, caisse source)
- **Aides sociales catalogués** — flag d'activation + types (cotisation membre, plafond, délai)
- **Critères d'adhésion multiples** — âge, sexe, localisation, profession, autres + frais d'inscription
- **Documents légaux** — statuts, ROI, récépissé via MinIO
- **Séance dynamique** — actions listées selon ce qui est configuré
- **Séances flexibles** — déplacement individuel, annulation sans casser le cycle
- **Historiques aides** — par membre (sienne) ou bureau (toutes)

> **Principe UX directeur :** application *explicative*. Chaque champ a une aide
> visible + exemple concret + preview du comportement. Pas de tooltip caché.

---

## 🟠 Phase 6 — Réalignement modèle métier + devise + silo ⟵ EN COURS

**Voir [docs/PHASE-6-DOMAIN-REALIGN.md](PHASE-6-DOMAIN-REALIGN.md).**

Suite à un cadrage métier (2026-05-29), le modèle Phase 2 était partiellement
faux. Corrections validées :

- **Tontine → Cycles → séances** : une tontine est durable et a *plusieurs
  cycles* ; un cycle = une rotation ; **1 séance = 1 tour**. Mon `TontineCycle`
  était traité comme racine → il faut un parent `Tontine`.
- **Séances créées d'office** pour tout le cycle à sa création (plus de bouton
  "générer", sauf séances extraordinaires). Pas de tontine = pas de séance régulière.
- **Cycle suivant hérite de tout** (config + participants + activités).
- **Distribution** : plusieurs gagnants/tour, 1 fois chacun → `nb_tours =
  participants / bénéf_par_tour`. `beneficiary_pays` configurable.
- **Caisses ↔ tontines** : indépendance totale (tontine possède sa caisse).
- **Devise** : `<Select>` ISO + conversion via API libre (frankfurter) au
  changement, exemples i18n dynamiques (plus de « 5 000 XAF » en dur).
- **Silo login** (Track 2 absorbé ici) : `{grp}.myappsuite.com/a/{slug}`, fix
  invitation (email admin de N assos), Open Graph + logo asso.
- **Fix UI** : modal d'invitation qui déborde (lien tronqué + copier).

> ⚠️ La mémoire `domain-model-tontine.md` fait foi sur le modèle métier.

---

## 🔵 Track 2 — Refonte « silo association » (absorbé dans Phase 6D)

Décision client : chaque association = silo fermé, un compte = une association,
e-mail unique par scope, routing `/a/[assoc]/...`. **À planifier en bloc** après
stabilisation Phase 2.

## 🔵 Track 4 — Notifications & communication (partiellement fait)

- ✅ Moteur e-mail (Mailpit dev + SMTP prod)
- ✅ Rappels séance via Celery
- 🔲 Notifications in-app temps réel
- 🔲 Bascules fines depuis 1.7

## 🔵 Track 5 — Documents & exports (partiellement fait)

- ✅ MinIO branché, utilisé pour invitations
- 🔲 Upload documents légaux (Phase 2a)
- 🔲 Export PDF PV de séance via reportlab
- 🔲 Export bilan financier

## 🔵 Track 6 — Production

- Migrations Alembic versionnées (remplacer le drop/create du seed)
- Tests pytest + frontend
- CI/CD, monitoring, déploiement

---

## Ordre recommandé

```
✅ Track 1 (v1) + Track 3 + Auto-planning
         ↓
🟡 Phase 2 (config-v2 + onboarding)   ⟵ EN COURS
         ↓
🔲 Track 2 (silo) en bloc cohérent
         ↓
🔲 Track 6 (production) en continu
```
