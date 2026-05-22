# Tchoucti — Planning

> Lire `docs/CONTEXT.md` pour la stack et les conventions.
> Ce fichier = feuille de route vivante. Mise à jour : 2026-05-21.

---

## ✅ Acquis (fait & vérifié)

- **Auth & RBAC** — JWT (access + refresh), 7 rôles système, 36 permissions
- **Multi-tenant** — middleware sous-domaine, Groupement → Association
- **Dashboards role-aware** — 4 vues distinctes (super-admin / admin groupement / admin association / membre), couleur primaire par rôle
- **Groupements** — CRUD, page détail à onglets, équipe d'admins, propriétaire + transfert, suspension
- **Associations** — CRUD, page détail à onglets, liste hiérarchique
- **Membres** — invitation par e-mail, liste, suspension/réactivation, rôles
- **Réunions** — liste, détail, présences, saisies d'activités
- **Invitations** — moteur générique (tokens hashés, expir 7j, renvoi, révocation), e-mail via Mailpit
- **Infra** — `docker compose up` lance tout + auto-seed si base vide

---

## 🟡 Track 1 — Paramètres d'association  ⟵ EN COURS

Tout ce que l'admin d'association peut configurer. Stockage : colonnes typées
pour le Général, `Association.config` (JSONB) pour le reste.

### 1.1 Général
- Nom · Type d'association (tontine / mutuelle / coopérative / autre) · Devise · Contact (e-mail, téléphone)

### 1.2 Membres
- Ajout / suppression de membres ✅ *(fait)*
- **Catégories** : actif · honneur · fondateur · suspendu  → `Membership.category`
- **Rôles/permissions** : président · trésorier · secrétaire · commissaire aux comptes · membre simple ✅ *(RBAC en place, assignation via l'onglet Membres)*

### 1.3 Tontine — configuration
- Montant de cotisation · fréquence · durée du cycle · nombre de participants
- Méthode d'attribution : ordre fixe · tirage au sort · enchère · priorité urgence · vote des membres

### 1.4 Caisse sociale — configuration
- Montant de contribution sociale · conditions d'assistance
- Événements couverts + montants : décès · maladie · mariage · naissance

### 1.5 Paiements
- Moyens activables : espèces · MTN Mobile Money · Orange Money · virement bancaire

### 1.6 Réunions — configuration
- Fréquence · mode (physique / virtuel / hybride) · quorum minimal · notifications auto

### 1.7 Notifications
- Bascules : rappel de cotisation · réunion · pénalité · attribution de tour · anniversaire · échéance de prêt

---

## 🔵 Track 2 — Refonte « silo association »

Décision client : chaque association = silo fermé, un compte = une association,
e-mail unique par scope, routing `/a/[assoc]/...`. Chantier fondamental
(auth, modèle `User`, middleware tenant, routing Next, seed). **À planifier en
bloc** quand Track 1 est stabilisé.

---

## 🔵 Track 3 — Modules métier opérationnels

Une fois la configuration en place, les opérations qui la consomment :

- **Tontine** — cycles, tours, attribution selon la méthode choisie, décaissement
- **Caisse sociale** — déclaration de cas, validation, versement selon barème
- **Prêts** — demande, approbation, échéancier, remboursement, pénalités
- **Finances** — trésorerie multi-fonds, mouvements, ventilation, invariant `Σ fonds = trésorerie`
- **Séances** — onglet Résumé (totaux + ventilation), clôture qui poste vers la trésorerie

---

## 🔵 Track 4 — Notifications & communication

- Moteur de notifications (in-app + e-mail) piloté par les bascules de 1.7
- Rappels programmés (cotisation, réunion, échéance)

## 🔵 Track 5 — Documents & exports

- Upload de documents (statuts, PV) vers MinIO
- Export PDF : PV de réunion, bilan financier

## 🔵 Track 6 — Production

- Migrations Alembic versionnées (remplacer le drop/create)
- Tests (pytest + frontend)
- CI/CD, monitoring, déploiement

---

## Ordre recommandé

```
Track 1 (Paramètres)  →  Track 3 (Modules métier)  →  Track 4/5
        ↓
Track 2 (Silo) en parallèle quand Track 1 est stable
        ↓
Track 6 (Production) en continu
```
