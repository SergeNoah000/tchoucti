# Tchoucti — déploiement VPS (Traefik + Docker)

Pipeline simple, git-based : tu pousses sur GitHub, tu te connectes au VPS,
tu lances `deploy.sh`. CI à venir plus tard.

## 0. Vue d'ensemble

```
Internet ─┬─► 80/443 ──► Traefik ──┬─► myappsuite.com           → frontend (Next.js)
          │                        ├─► www.myappsuite.com       → redirect → apex
          │                        ├─► api.myappsuite.com       → backend (FastAPI)
          │                        ├─► storage.myappsuite.com   → MinIO (S3 public)
          │                        ├─► minio.myappsuite.com     → MinIO console
          │                        └─► traefik.myappsuite.com   → dashboard (basic-auth)
          │
          └─► 22       ──► SSH (root)

Internal: postgres · redis · worker (Celery) · beat (Celery beat) — pas de port exposé.
```

Tout vit sur **un seul VPS** (`207.180.231.56`, domaine `myappsuite.com`).
Pour scaler plus tard : sortir Postgres et Redis sur du managé, basculer
MinIO vers S3 réel.

---

## 1. Préparer le poste local (déjà fait ✅)

```bash
# Clé SSH de déploiement (ed25519, sans passphrase)
ssh-keygen -t ed25519 -f ~/.ssh/tchoucti_deploy -N "" -C "tchoucti-deploy@myappsuite.com"

# Publique ajoutée au compte GitHub via gh
gh ssh-key add ~/.ssh/tchoucti_deploy.pub --title "tchoucti-vps-myappsuite"
```

La **publique** vit déjà sur GitHub. La **privée** (`~/.ssh/tchoucti_deploy`)
doit être copiée sur le VPS pour que `git clone/pull` fonctionne.

---

## 2. DNS — pointer le domaine sur le VPS

Chez le registrar / hébergeur DNS de `myappsuite.com`, créer ces A-records
pointant vers `207.180.231.56` :

| Nom                 | Type | Cible             | TTL   |
|---------------------|------|-------------------|-------|
| `@`                 | A    | 207.180.231.56    | 300   |
| `www`               | A    | 207.180.231.56    | 300   |
| `api`               | A    | 207.180.231.56    | 300   |
| `storage`           | A    | 207.180.231.56    | 300   |
| `minio`             | A    | 207.180.231.56    | 300   |
| `traefik`           | A    | 207.180.231.56    | 300   |

> Les futurs groupements (sous-domaines clients) seront des `A` ou des
> `CNAME` vers l'apex. Ils sont déjà capturés par le router Traefik
> `HostRegexp` (voir compose).

Attendre que la propagation soit OK :
```bash
dig +short api.myappsuite.com    # doit renvoyer 207.180.231.56
```

---

## 3. Copier la clé privée sur le VPS

Depuis ton poste local :

```bash
# 3a) Pose la clé sur le VPS
scp ~/.ssh/tchoucti_deploy root@207.180.231.56:/root/.ssh/id_ed25519
ssh root@207.180.231.56 'chmod 600 /root/.ssh/id_ed25519'
```

> On utilise `id_ed25519` (nom par défaut) côté serveur pour que `git`
> trouve la clé sans config supplémentaire.

---

## 4. Bootstrap du VPS

```bash
# 4a) SSH
ssh root@207.180.231.56

# 4b) Bootstrap (récupère le script bootstrap-only, qui fera ensuite git clone)
curl -fsSL https://raw.githubusercontent.com/SergeNoah000/tchoucti/main/deploy/init-server.sh \
  | REPO_URL=git@github.com:SergeNoah000/tchoucti.git bash
```

Ce script :
- met à jour les paquets, installe Docker + plugin compose, ufw, fail2ban
- ouvre `22/80/443` et active ufw
- met le fuseau sur `Africa/Douala`
- clone le repo dans `/opt/tchoucti`
- affiche les prochaines étapes

> Si le repo est privé et que le clone échoue : vérifie que `/root/.ssh/id_ed25519`
> existe (étape 3) et que la clé publique est bien sur GitHub.

---

## 5. Renseigner les secrets

```bash
ssh root@207.180.231.56
cd /opt/tchoucti
cp deploy/.env.example deploy/.env
nano deploy/.env
```

Variables critiques (à générer puis coller) :

```bash
# Mots de passe forts
openssl rand -base64 24    # POSTGRES_PASSWORD
openssl rand -base64 24    # MINIO_ROOT_PASSWORD
openssl rand -hex 48       # JWT_SECRET_KEY

# Auth basique pour le dashboard Traefik (DOUBLE les $ !)
docker run --rm httpd:alpine htpasswd -nbB admin 'TON_MOT_DE_PASSE' \
  | sed -e 's/\$/\$\$/g'
# Colle la sortie dans TRAEFIK_AUTH=…
```

Fournis aussi :
- `ACME_EMAIL` : ton adresse pour les avis Let's Encrypt
- `SMTP_*` : un vrai fournisseur (Brevo, Postmark, OVH, SES…)

> Vérifie qu'aucun `CHANGE-ME` ne traîne avant de déployer.

---

## 6. Premier déploiement

```bash
bash /opt/tchoucti/deploy/deploy.sh
```

Le script :
1. `git fetch && git pull`
2. `docker compose build` (images backend + frontend)
3. `docker compose up -d`
4. `docker image prune -f`

Au **premier** lancement, Traefik demande les certs Let's Encrypt à la
**première requête** sur chaque host. Ouvre `https://myappsuite.com` dans
ton navigateur — le cert apparaît en ~10 s. Surveille :

```bash
docker logs -f tchoucti_traefik | grep -i acme
```

Si tu vois `Unable to obtain ACME certificate` : vérifie le DNS, ouvre les
ports 80/443, et que `ACME_EMAIL` n'est pas vide.

---

## 7. Cycle de déploiement courant

Local :
```bash
git push origin main
```

VPS :
```bash
ssh root@207.180.231.56 'bash /opt/tchoucti/deploy/deploy.sh'
```

Une ligne. Bonne pour ~95 % des déploiements (code-only). Les déploiements
qui modifient `docker-compose.prod.yml` ou un Dockerfile re-créent les
conteneurs concernés ; pas d'action manuelle requise.

---

## 8. Comptes par défaut

Au premier démarrage, `app.db.init_db` seed la base si elle est vide. Les
6 comptes démo sont créés (voir `backend/app/db/seed.py`). **Tu dois
changer leurs mots de passe en production**, ou mieux : passer
`SEED_DEMO=0` (à câbler) et créer un vrai admin.

---

## 9. Sauvegardes

Volumes nommés à snapshotter régulièrement :

| Volume                       | Contenu                          |
|------------------------------|----------------------------------|
| `tchoucti_postgres_data`     | base de données                  |
| `tchoucti_minio_data`        | fichiers (docs légaux, PV, etc.) |
| `tchoucti_traefik_letsencrypt` | certs Let's Encrypt            |
| `tchoucti_redis_data`        | cache + Celery broker            |

Backup minimal (à mettre dans un cron quotidien) :

```bash
# /etc/cron.daily/tchoucti-backup
set -e
DST=/var/backups/tchoucti && mkdir -p "$DST"
TS=$(date +%Y%m%d-%H%M)

# Postgres
docker exec tchoucti_postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip > "$DST/pg-$TS.sql.gz"

# MinIO data (raw volume tar)
docker run --rm -v tchoucti_minio_data:/data -v "$DST":/backup alpine \
  tar czf "/backup/minio-$TS.tar.gz" -C /data .

# Garde 14 jours
find "$DST" -mtime +14 -delete
```

---

## 10. Dépannage rapide

| Symptôme | Vérifier |
|---|---|
| 502 sur l'URL | `docker ps` (le service est-il up ?), `docker logs tchoucti_backend` |
| Cert TLS non émis | DNS pointe-t-il bien ? ports 80/443 ouverts ? `docker logs tchoucti_traefik` |
| Email non envoyé | `SMTP_*` corrects ? `docker logs tchoucti_worker` |
| DB invalide après update | `docker exec -it tchoucti_backend python -m app.db.init_db` |
| Tout casser proprement | `docker compose -f deploy/docker-compose.prod.yml down` (volumes intacts) |
| Reset complet (⚠️ perte data) | `docker compose -f deploy/docker-compose.prod.yml down -v` |
