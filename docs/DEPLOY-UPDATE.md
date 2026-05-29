# Mise à jour du déploiement — Phase 6 + correctifs

> **Date :** 2026-05-29 · **HEAD visé :** voir `git log` (lot « Phase 6A→6D + correctifs »)
> **Cible :** VPS `207.180.231.56`, domaine `myappsuite.com` (Traefik + Docker).
> Procédure de déploiement de base : voir [deploy/README.md](../deploy/README.md).

Ce document liste **ce qui a changé** depuis le dernier déploiement et **les
actions** pour mettre la prod à jour (DNS, base de données, redéploiement,
vérifications).

---

## 1. État — ce qui a changé

| Commit | Changement | Impact déploiement |
|--------|-----------|--------------------|
| `d827da5` / `e41c98c` | **Phase 6A** : refonte Tontine → Cycles → séances | **Schéma DB cassé** (tables tontine) |
| `dfe2d2d` | **Phase 6B** : devise dropdown ISO + verrou + exemples dynamiques | Code only |
| `c0689d6` | **6D-1** : fix invitation (email déjà membre d'une autre asso) | Code only |
| `ea05149` | **6D-2** : upload logo association | Code only (MinIO déjà en place) |
| `df77cf0` | **6D-3/4** : login brandé `{grp}.myappsuite.com/a/{slug}` + Open Graph | **DNS wildcard + Traefik** |
| `f4dc88e` | fix domaine groupement codé en dur + message login trompeur | Code only |
| `acf7f7d` | tontine : montant explicite + création sans membres | Code only |
| `79ffea9` | aide sociale : **caisse temporaire** ouverte à l'approbation | **Migration DB additive** (aid_types) |
| `9c75731` | sidebar (doublon tontine), type de prêt à la demande, pages Documents/Paramètres opérationnelles, bouton « créer asso » | Code only (+ 2 endpoints auth) |

Deux postes nécessitent une action manuelle en prod : **le DNS/Traefik** (§2) et
**la base de données** (§3). Le reste est pris en charge par `deploy.sh`.

---

## 2. Hébergeur / DNS — sous-domaine wildcard

Pour activer le login par association `{groupement}.myappsuite.com/a/{slug}`,
ajouter chez l'**hébergeur DNS** de `myappsuite.com` :

| Nom | Type | Cible            | TTL |
|-----|------|------------------|-----|
| `*` | A    | `207.180.231.56` | 300 |

Vérifier la propagation :
```bash
dig +short demo.myappsuite.com    # doit renvoyer 207.180.231.56
```

Côté Traefik (déjà dans `deploy/docker-compose.prod.yml`, rien à faire) : le
router frontend matche `Host(myappsuite.com) || HostRegexp(^[a-z0-9-]+\.myappsuite\.com$)`
en **priority=10** (catch-all de dernier recours).

⚠️ **À surveiller après déploiement** :
- Le domaine est **partagé** avec d'autres apps (ex. `globalasset.myappsuite.com`).
  Leur router explicite a une priorité par défaut > 10 et garde la main —
  **mais le vérifier** (cf. §5).
- **TLS** : Let's Encrypt émet un certificat **par hôte** au 1er accès HTTPS
  (challenge HTTP-01, fonctionne grâce au wildcard DNS). Pour un **vrai certificat
  wildcard**, basculer le resolver `le` en challenge **DNS-01** (nécessite les
  identifiants API du fournisseur DNS dans la config Traefik) — optionnel.

---

## 3. Base de données

`deploy.sh` ne lance **aucune migration** (le projet n'a pas de migrations
Alembic actives ; `init_db` ne fait que peupler une base vide). Les changements
de schéma doivent donc être appliqués à la main.

> Adapter `POSTGRES_USER` / `POSTGRES_DB` aux valeurs de `deploy/.env`.
> Préfixe des commandes :
> ```bash
> cd /opt/tchoucti
> DC="docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env"
> ```

### Cas A — la prod n'a PAS encore de données réelles (recommandé)

La refonte tontine (Phase 6A) **casse le schéma** des tables `tontines` /
`tontine_cycles` (anciennes colonnes supprimées, `tontine_id` ajouté). Sans
migration, le plus simple et le plus sûr est de **recréer la base** :

```bash
$DC down                     # arrête (NE PAS oublier -v ci-dessous)
$DC down -v                  # ⚠️ SUPPRIME les volumes = efface la base !
$DC up -d                    # recrée tables + seed démo (init_db)
```

> ⚠️ `down -v` **efface toutes les données** (postgres + MinIO). À n'utiliser que
> si la prod ne contient que des données de démo/test.

### Cas B — la prod CONTIENT des données réelles à conserver

1. **Sauvegarder d'abord** (cf. deploy/README §9) :
   ```bash
   $DC exec -T postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB | gzip > ~/backup-$(date +%F).sql.gz
   ```
2. **Aides sociales** — migration additive sûre :
   ```bash
   $DC exec -T postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -c "
     ALTER TABLE aid_types ALTER COLUMN source_caisse_id DROP NOT NULL;
     ALTER TABLE aid_types ADD COLUMN IF NOT EXISTS auto_create_caisse boolean NOT NULL DEFAULT false;
   "
   ```
3. **Tontines (Phase 6A)** — la transformation des anciennes données tontine vers
   le nouveau modèle (Tontine durable → cycles) **n'a pas de migration
   automatique**. S'il existe des tontines réelles, écrire une migration de
   données dédiée *avant* de déployer (ou les recréer manuellement après un
   `down -v`). Tant que ce point n'est pas traité, ne pas déployer 6A sur une base
   contenant des tontines réelles.

---

## 4. Déploiement du code

Aucune nouvelle variable `.env` à renseigner : `CORS_ORIGIN_REGEX`,
`API_INTERNAL_URL` et le router wildcard sont déjà dans
`deploy/docker-compose.prod.yml`.

```bash
ssh root@207.180.231.56
bash /opt/tchoucti/deploy/deploy.sh      # git pull → build → up -d → prune
```

Puis appliquer la mise à jour DB du §3 (Cas A ou B).

---

## 5. Vérifications post-déploiement

```bash
DC="docker compose -f /opt/tchoucti/deploy/docker-compose.prod.yml --env-file /opt/tchoucti/deploy/.env"
$DC ps                                   # tous les services Up
```

- [ ] **Autres apps intactes** : `https://globalasset.myappsuite.com` répond
      toujours (pas intercepté par Tchoucti).
- [ ] **App principale** : `https://myappsuite.com` et `https://api.myappsuite.com/api/health` OK.
- [ ] **Login brandé** : `https://demo.myappsuite.com/a/<slug-asso>` affiche la
      page brandée (logo + nom de l'asso) et le login fonctionne.
- [ ] **Open Graph** :
      ```bash
      curl -s https://demo.myappsuite.com/a/<slug> | grep -i 'og:image'
      ```
- [ ] **Devise** : le sélecteur ISO s'affiche ; verrou actif si historique financier.
- [ ] **Tontine** : création sans membre → cycle brouillon ; ajout participants → démarrage.
- [ ] **Aide** : type « caisse temporaire » → caisse ouverte à l'approbation.
- [ ] **Pages Documents & Paramètres** opérationnelles ; sélection du type de prêt à la demande.

---

## 6. Rollback

```bash
cd /opt/tchoucti && git log --oneline -5
git checkout <commit-précédent> && bash deploy/deploy.sh
```
Si la base a été recréée (`down -v`) ou migrée, restaurer le dump du §3-B.
