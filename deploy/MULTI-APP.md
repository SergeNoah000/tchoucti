# Héberger plusieurs apps sur le même VPS

Le `docker-compose.prod.yml` fourni embarque sa propre instance Traefik —
c'est l'option **mono-app**, idéale pour démarrer. Dès que tu veux poser
une 2ᵉ application sur le même serveur, il faut :

- **Extraire Traefik** dans une stack dédiée (sinon conflit sur 80/443).
- Faire **rejoindre** chaque app au réseau partagé `proxy`.

Ce document explique cette bascule, puis comment ajouter n'importe quelle
app derrière le même Traefik. Deux modes de clone Git sont documentés :
**SSH** (clé déploiement) et **HTTPS** (PAT ou repo public), sans
dépendance à `gh`.

---

## A. Bascule mono-app → multi-app (à faire une fois)

### A1. Démarrer le Traefik partagé

Sur le VPS :

```bash
mkdir -p /opt/traefik
cp /opt/tchoucti/deploy/traefik/docker-compose.yml /opt/traefik/
cp /opt/tchoucti/deploy/traefik/.env.example      /opt/traefik/.env
nano /opt/traefik/.env   # renseigne ACME_EMAIL, TRAEFIK_HOST, TRAEFIK_AUTH
```

> `TRAEFIK_HOST` peut désormais être indépendant du domaine de Tchoucti.
> Par ex : `traefik.myappsuite.com` ou `traefik.tonautre-domaine.com`.

```bash
cd /opt/traefik
docker compose up -d
docker network ls | grep proxy   # confirme la création du réseau `proxy`
```

> **Migration des certs déjà émis** : ils étaient stockés dans le volume
> `tchoucti_traefik_letsencrypt`. Pour les réutiliser (éviter le rate limit
> Let's Encrypt) :
>
> ```bash
> # Copier acme.json depuis l'ancien volume vers le nouveau
> docker run --rm \
>   -v tchoucti_traefik_letsencrypt:/from \
>   -v traefik_letsencrypt:/to \
>   alpine sh -c "cp /from/acme.json /to/acme.json && chmod 600 /to/acme.json"
> ```

### A2. Désactiver le Traefik bundle de Tchoucti

```bash
cd /opt/tchoucti
# Arrêter le Traefik embarqué (sans toucher au reste de la stack)
docker compose -f deploy/docker-compose.prod.yml rm -sf traefik
```

Puis éditer `deploy/docker-compose.prod.yml` :

1. **Supprimer** (ou commenter) tout le bloc `services.traefik:` — Traefik
   vit maintenant dans `/opt/traefik`.
2. **Remplacer** la section `networks:` en bas du fichier par :

   ```yaml
   networks:
     web:
       name: proxy
       external: true
   ```

3. (Optionnel) Renommer chaque `networks: [web]` en `networks: [proxy]` ;
   ce n'est cosmétique que.

Puis relancer la stack :

```bash
bash deploy/deploy.sh
```

Les containers de Tchoucti rejoindront le réseau `proxy` ; Traefik
auto-découvre les labels et continue de router `myappsuite.com`,
`api.myappsuite.com`, etc.

---

## B. Ajouter une 2ᵉ app derrière le Traefik partagé

Trois choses à préparer :
- Un **repo Git** clonable depuis le VPS
- Un **docker-compose** avec les bons labels Traefik
- Des **enregistrements DNS** pointant sur le VPS

### B1. Clone du repo — choisir SSH ou HTTPS

#### Option 1 — SSH (recommandé pour les repos privés)

Sur le VPS, depuis le compte qui hébergera l'app (par ex. `root`) :

```bash
# Génère une paire dédiée (sans passphrase pour les pull auto)
ssh-keygen -t ed25519 -f ~/.ssh/app2_deploy -N "" -C "app2-deploy@<hostname>"

# Affiche la clé publique
cat ~/.ssh/app2_deploy.pub
```

Ajoute cette clé publique côté hébergeur Git :

- **GitHub (deploy key, recommandé)** : repo → *Settings* → *Deploy keys*
  → *Add deploy key*. Coller la `.pub`. Ne coche pas *Allow write access*
  sauf si tu en as besoin. **Avantage** : limité à un seul repo.
- **GitHub (compte perso)** : *Settings → SSH and GPG keys → New SSH key*.
  La clé peut alors pull n'importe quel repo où le compte a accès.
- **GitLab** : repo → *Settings → Repository → Deploy Keys*.
- **Bitbucket** : repo → *Repository settings → Access keys*.
- **Forgejo / Gitea** : repo → *Settings → Deploy keys*.

Configure `ssh` côté VPS pour utiliser cette clé spécifique :

```bash
cat >> ~/.ssh/config <<'EOF'

Host github-app2
  HostName github.com
  User git
  IdentityFile ~/.ssh/app2_deploy
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
ssh-keyscan -t ed25519,rsa github.com >> ~/.ssh/known_hosts 2>/dev/null
```

Clone via l'alias :

```bash
mkdir -p /opt/app2
git clone git@github-app2:OWNER/REPO.git /opt/app2
```

> Pourquoi un alias `github-app2` ? Pour éviter le conflit avec la clé
> déjà installée pour Tchoucti (`~/.ssh/id_ed25519`). L'alias force `ssh`
> à utiliser la bonne clé pour cet hébergeur uniquement.

#### Option 2 — HTTPS (repo public, ou repo privé via PAT)

**Repo public** : aucun secret nécessaire.

```bash
git clone https://github.com/OWNER/REPO.git /opt/app2
```

**Repo privé** : il faut un Personal Access Token (PAT).

GitHub :

1. *Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token*.
2. Repository access : choisir *Only select repositories* → le repo de l'app.
3. Permissions : *Contents: Read-only* suffit pour `git pull`.
4. Génère → copie le token (visible une seule fois).

Sur le VPS, configurer un helper qui injecte le token automatiquement :

```bash
# Stocker le token côté serveur, lisible uniquement par root
mkdir -p /root/.config/git
cat > /root/.config/git/credentials <<EOF
https://OWNER:ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx@github.com
EOF
chmod 600 /root/.config/git/credentials

git config --global credential.helper "store --file=/root/.config/git/credentials"

git clone https://github.com/OWNER/REPO.git /opt/app2
```

> Pour un repo GitLab : remplacer `github.com` par `gitlab.com`,
> `OWNER:PAT` par `oauth2:PAT`.
> Pour Bitbucket : `https://x-token-auth:PAT@bitbucket.org/…`.

Rotation : régénérer le PAT régulièrement (90 j par défaut côté GitHub).

### B2. Compose minimal de la nouvelle app

Voici un squelette qu'il suffit d'adapter (`/opt/app2/docker-compose.yml`) :

```yaml
name: app2

services:
  app2:
    build: .                       # ou: image: ghcr.io/owner/app:tag
    container_name: app2
    restart: unless-stopped
    environment:
      DATABASE_URL: postgres://...
      # ...
    networks:
      - proxy
    labels:
      - traefik.enable=true
      # Domaine principal
      - traefik.http.routers.app2.rule=Host(`app2.example.com`)
      - traefik.http.routers.app2.entrypoints=websecure
      - traefik.http.routers.app2.tls.certresolver=le
      # Port interne du conteneur
      - traefik.http.services.app2.loadbalancer.server.port=3000

networks:
  proxy:
    name: proxy
    external: true
```

Points-clés :

| Ligne | Pourquoi |
|---|---|
| `network: proxy` (external) | partage le réseau du Traefik standalone |
| `traefik.enable=true` | sans ce flag, Traefik ignore le service |
| `Host(\`app2.example.com\`)` | route HTTP en fonction du Host header |
| `tls.certresolver=le` | demande automatiquement un cert Let's Encrypt |
| `loadbalancer.server.port=3000` | port **interne** du conteneur, pas du host |

> Tu peux router plusieurs domaines : `Host(\`a.x.com\`) || Host(\`b.x.com\`)`.
> Tu peux router par chemin : `PathPrefix(\`/api\`)`.

Une fois ces fichiers en place :

```bash
cd /opt/app2
docker compose up -d
docker compose logs -f
```

### B3. DNS

Créer un A-record pour chaque domaine routé, pointant sur le même VPS :

```
app2.example.com    A    207.180.231.56
```

Patiente la propagation, puis ouvre l'URL : Traefik négocie le cert
Let's Encrypt à la première requête.

### B4. Cycle de redéploiement pour la 2ᵉ app

Mets en place le même pattern que Tchoucti :

```bash
cat > /opt/app2/deploy.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd /opt/app2
git pull --ff-only
docker compose build --pull
docker compose up -d --remove-orphans
docker image prune -f >/dev/null
EOF
chmod +x /opt/app2/deploy.sh
```

Côté local : `git push` puis `ssh root@vps 'bash /opt/app2/deploy.sh'`.

---

## C. Bonnes pratiques quand le VPS héberge N apps

- **Volumes & noms de containers** : préfixe-les par l'app (déjà fait avec
  `name:` dans le compose). Évite `postgres` tout court, préfère
  `app2_postgres`.
- **Backups** : tag tes volumes du préfixe app pour les scripter
  facilement (`docker volume ls | grep app2_`).
- **Logs** : `docker compose logs -f --tail=200` par app.
- **Mémoire** : surveille avec `docker stats`. Pour limiter une app
  gourmande, ajoute `deploy.resources.limits` (compose v3) ou `mem_limit`
  (v2).
- **Mise à jour du Traefik** : `cd /opt/traefik && docker compose pull
  && docker compose up -d`. Les apps ne sont pas impactées.
- **Logs Traefik** : `docker logs -f traefik`. Très bavard à `DEBUG`,
  utile au premier déploiement.
- **Si le port 80/443 est déjà pris** par un nginx système : `apt purge
  nginx-*` ou stoppe-le. Une seule chose peut écouter ces ports.
- **Conflits de sous-domaine** : Traefik utilise la règle la plus
  spécifique. `Host(...)` bat `HostRegexp(...)`. Tchoucti déclare un
  `HostRegexp` qui matche tous les sous-domaines de `myappsuite.com` —
  attention si une autre app veut un sous-domaine de `myappsuite.com`,
  il faut le déclarer **avant** dans une règle `Host(...)` plus précise.

---

## D. Récap des fichiers / chemins typiques

```
/opt/
├── traefik/                      # Stack Traefik standalone (partagée)
│   ├── docker-compose.yml
│   └── .env
├── tchoucti/                     # Repo Tchoucti
│   ├── deploy/docker-compose.prod.yml   (sans Traefik après migration)
│   ├── deploy/.env
│   └── deploy/deploy.sh
├── app2/                         # 2ᵉ app
│   ├── docker-compose.yml
│   ├── .env
│   └── deploy.sh
└── app3/...
```

Réseau Docker partagé : `proxy` (external).
Tout ce qui est exposé publiquement traverse Traefik via ce réseau.
