# Phase 7 — Modèle Fred : caisse de prêts à rendement partagé

> **Cible :** compléter le modèle de prêts actuel par un **mode optionnel sur la
> Caisse** qui redistribue les intérêts perçus aux cotisants au prorata de leur
> apport, comme dans le modèle Excel de Fred ([docs/Modell_Fred.xlsx](Modell_Fred.xlsx)).
>
> Ce mode ne remplace pas le LoanType actuel. Il **complète** : une caisse
> peut être en mode **« conservé »** (comportement actuel, intérêts dans le
> fonds INSURANCE) ou en mode **« partagé au prorata »** (intérêts redistribués
> aux cotisants par périodes).

## Décisions verrouillées avec le client (2026-06-03)

1. **Greffe sur la Caisse** (pas sur le LoanType). Une caisse COLLECTIVE peut
   activer le mode partagé ; ses LoanTypes l'héritent automatiquement.
2. **Période d'agrégation** configurable : `per_meeting | monthly | quarterly | annually`.
3. **Snapshot des soldes** : fin de la période précédente (look-back d'une période,
   comme Fred). Pas de pondération par jour.
4. **Pas de capitalisation** : `interest_cum` n'entre pas dans la base de calcul
   du mois suivant (conforme à Fred). On reste sur `apport_cum` comme base.
5. **Destination des intérêts** redistribués : **sous-solde dans la même caisse**.
   Chaque membre voit deux compteurs sur la caisse : `apport_cum` (capital versé)
   et `interest_cum` (intérêts reçus, distincts).
6. **Retraits** : 3 modes proposés à l'admin :
   - `anytime_if_liquid` : retrait possible si la caisse a la liquidité
     disponible (= solde caisse − encours prêts non remboursés).
   - `never` : pas de retrait (modèle Fred strict).
   - `end_of_period_only` : retrait uniquement après une clôture de période.

## Modèle de données

### Caisse — colonnes ajoutées

```python
class InterestDistribution(str, Enum):
    KEPT = "kept"                       # actuel : l'intérêt reste dans INSURANCE
    SHARED_PRO_RATA = "shared_pro_rata" # nouveau : redistribué aux cotisants

class DistributionPeriod(str, Enum):
    PER_MEETING = "per_meeting"
    MONTHLY     = "monthly"
    QUARTERLY   = "quarterly"
    ANNUALLY    = "annually"

class WithdrawalMode(str, Enum):
    ANYTIME_IF_LIQUID   = "anytime_if_liquid"
    NEVER               = "never"
    END_OF_PERIOD_ONLY  = "end_of_period_only"

# Sur Caisse :
interest_distribution: InterestDistribution = KEPT
distribution_period:   DistributionPeriod   = PER_MEETING
withdrawal_mode:       WithdrawalMode       = NEVER
last_distribution_at:  Date | None
```

### `caisse_contributor_balance` — sous-soldes par membre

```
(caisse_id, membership_id) UNIQUE
apport_cum     bigint  -- cumul du capital versé (base de calcul du prorata)
interest_cum   bigint  -- cumul des intérêts redistribués (informatif)
updated_at     timestamptz
```

Invariant attendu : `Σ apport_cum + Σ interest_cum ≈ Fund.balance` (à la
liquidité prêtée près).

### `caisse_distribution` — historique des clôtures

```
caisse_id          uuid
period_start       date
period_end         date
period_label       string   -- ex. "2026-Q1", "2026-04", "séance #2026-06-12"
interest_pool      bigint   -- intérêts perçus sur la période (à redistribuer)
total_base         bigint   -- somme des apport_cum au début de la période
closed_at          timestamptz
closed_by_id       uuid → users
```

### `caisse_distribution_share` — détail par membre

```
distribution_id   uuid → caisse_distribution
membership_id     uuid → memberships
base              bigint   -- apport_cum du membre au début de la période
share_amount      bigint   -- (base / total_base) × interest_pool
```

## Logique métier

### Mise à jour de `apport_cum` (L2)

- À la **clôture d'une séance** (`POST /meetings/{id}/close`), pour chaque
  `MeetingActivityEntry` non-voided ciblant une caisse à `interest_distribution`
  ∈ {KEPT, SHARED_PRO_RATA} (en pratique, toutes les caisses concernées) :
  - upsert `caisse_contributor_balance(caisse_id, membership_id)`,
    `apport_cum += entry.amount`.
- Idem pour les mouvements manuels IN attribués à un membre (rare).

> Les caisses en mode `KEPT` ne calculent pas de distribution, mais on tient
> quand même le `apport_cum` pour faciliter une bascule ultérieure.

### Clôture de période + redistribution (L3)

Endpoint **`POST /caisses/{id}/close-distribution`** (admin) :

1. **Période** :
   - `period_start = last_distribution_at` (ou `caisse.created_at` si aucune).
   - `period_end = today`.
2. **Pool d'intérêts** : somme des `LedgerEntry` IN sur le fund de la caisse
   dans la période, dont `source_type = "loan_repayment"` et la part est un
   intérêt (cf. L5 — pour le routing).
3. **Base totale** : `total_base = Σ apport_cum` snapshot au début de la période.
   En pratique, on snapshote la valeur actuelle (les apports d'une période ne
   comptent qu'au suivant, comme Fred — il faut donc soustraire les apports
   reçus pendant la période courante).

   Implémentation : on garde `apport_cum_at_period_start` mis à jour à chaque
   distribution (cf. ci-dessous).
4. **Pour chaque membre** ayant `base > 0` : créer
   `caisse_distribution_share(base, share = round(base × pool / total_base))`.
   Reliquat de l'arrondi → dernier membre, ou au pool reste.
5. Incrémente `caisse_contributor_balance.interest_cum += share_amount`.
6. Snapshot `last_distribution_at = period_end` et set
   `apport_cum_at_period_start = apport_cum` (sur la table balances).
7. Crée la `caisse_distribution` + ses `caisse_distribution_share`.

**Auto-trigger** : à chaque clôture de séance, si la caisse est en mode
SHARED_PRO_RATA :
- `PER_MEETING` → déclenche close-distribution.
- `MONTHLY` → si la date de la séance ≥ fin du mois en cours et qu'on n'a pas
  déjà clos ce mois.
- `QUARTERLY` / `ANNUALLY` → idem (fin de trimestre / d'année).

Manuel toujours possible côté admin (bouton « clôturer la période »).

### Routing des intérêts à la perception (L5)

Aujourd'hui, dans `loans.repay_loan` (`backend/app/api/v1/loans.py:478-489`),
**l'intérêt va systématiquement vers le fonds INSURANCE**.

→ À modifier : si le **prêt remboursé** a une `source_caisse` avec
`interest_distribution = SHARED_PRO_RATA`, l'intérêt est alloué au **fonds de
cette caisse** (pas INSURANCE). C'est ensuite ce qui sera redistribué à la
clôture de période.

Pour les caisses en mode `KEPT` (= la majorité), comportement inchangé →
INSURANCE.

### Retraits (L4)

Endpoint **`POST /caisses/{id}/withdraw`** (membre ou admin selon le mode) :

```json
{ "membership_id": "...", "amount": 5000 }
```

Validations :
- `mode = NEVER` → 409.
- `mode = END_OF_PERIOD_ONLY` et `now > last_distribution_at + 1 jour` →
  409 (à raffiner : on accepte tant que pas de nouveaux apports depuis la
  distribution).
- `mode = ANYTIME_IF_LIQUID` → vérifier
  `liquidity_available ≥ amount`, où :

  ```
  liquidity_available = Fund.balance − Σ(loan.principal_remaining for loans
                                         dont source_caisse_id = this)
  ```
- `caisse_contributor_balance.apport_cum ≥ amount` (on ne peut retirer que ce
  qu'on a apporté ; les `interest_cum` ne sont **pas** retirables — restent
  comme rendement « papier » jusqu'à la dissolution, conforme à Fred).
- Effet :
  - `apport_cum -= amount`.
  - Crée un mouvement OUT depuis le fund vers le compte du membre (cash-out).

## UI (L6)

- **Config caisse** : nouveau bloc dans `aid-types-manager` / form caisse :
  - Switch « Mode rendement partagé » (toggle `interest_distribution`).
  - Si activé : sélecteur `distribution_period` + sélecteur `withdrawal_mode`.
  - Phrase explicative claire (« explicative UX »).
- **Détail caisse** (nouvelle page ou onglets sur la page caisses) :
  - Onglet « Cotisants » : table membres × (apport_cum, interest_cum, % du pot).
  - Onglet « Distributions » : historique des clôtures (date, intérêt distribué,
    nombre de membres, taux de rendement implicite). Bouton « Clôturer
    maintenant » pour l'admin.
  - Onglet « Ma part » (vue membre) : ses apports, ses intérêts cumulés, sa
    fraction du pot, l'historique de ses parts.
- **Bouton Retirer** sur l'onglet « Ma part » selon le `withdrawal_mode`.

## Schéma SQL (résumé)

```sql
-- Sur caisses :
ALTER TABLE caisses ADD COLUMN IF NOT EXISTS interest_distribution
  VARCHAR(30) NOT NULL DEFAULT 'kept';
ALTER TABLE caisses ADD COLUMN IF NOT EXISTS distribution_period
  VARCHAR(30) NOT NULL DEFAULT 'per_meeting';
ALTER TABLE caisses ADD COLUMN IF NOT EXISTS withdrawal_mode
  VARCHAR(30) NOT NULL DEFAULT 'never';
ALTER TABLE caisses ADD COLUMN IF NOT EXISTS last_distribution_at DATE;

-- Nouvelle table balances :
CREATE TABLE IF NOT EXISTS caisse_contributor_balances (
  id            UUID PRIMARY KEY,
  caisse_id     UUID NOT NULL REFERENCES caisses(id) ON DELETE CASCADE,
  membership_id UUID NOT NULL REFERENCES memberships(id) ON DELETE RESTRICT,
  apport_cum                   BIGINT NOT NULL DEFAULT 0,
  apport_cum_at_period_start   BIGINT NOT NULL DEFAULT 0,
  interest_cum                 BIGINT NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(caisse_id, membership_id)
);

-- Historique des distributions :
CREATE TABLE IF NOT EXISTS caisse_distributions (
  id              UUID PRIMARY KEY,
  caisse_id       UUID NOT NULL REFERENCES caisses(id) ON DELETE CASCADE,
  period_start    DATE NOT NULL,
  period_end      DATE NOT NULL,
  period_label    VARCHAR(50) NOT NULL,
  interest_pool   BIGINT NOT NULL,
  total_base      BIGINT NOT NULL,
  closed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_by_id    UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS caisse_distribution_shares (
  id               UUID PRIMARY KEY,
  distribution_id  UUID NOT NULL REFERENCES caisse_distributions(id) ON DELETE CASCADE,
  membership_id    UUID NOT NULL REFERENCES memberships(id) ON DELETE RESTRICT,
  base             BIGINT NOT NULL,
  share_amount     BIGINT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(distribution_id, membership_id)
);
```

## Découpage en commits

| # | Commit | Périmètre |
|---|--------|-----------|
| L1 | `Fred L1 — modèle Caisse (3 modes) + 3 nouvelles tables` | Modèles + DB ALTER + schemas Pydantic |
| L2 | `Fred L2 — mise à jour apport_cum à la clôture des séances` | Hook dans `close_meeting` |
| L3 | `Fred L3 — clôture/redistribution + auto-trigger` | Endpoint + service de calcul + auto sur meeting close |
| L4 | `Fred L4 — retraits (3 modes configurables)` | Endpoint + validations |
| L5 | `Fred L5 — routing intérêts vers caisse source si partagé` | `repay_loan` ajusté |
| L6 | `Fred L6 — UI config + onglets Cotisants/Distributions/Ma part + bouton Retirer` | Frontend |
| L7 | `Fred L7 — doc déploiement` | DEPLOY-UPDATE.md mis à jour |

## Limites assumées du modèle

- Pas de pondération **par jour** des apports (mois entier, comme Fred).
- Pas de capitalisation des intérêts (Fred).
- Les `interest_cum` ne sont **pas retirables** comme cash (rendement « papier »
  visible à la dissolution / report).
- Un membre rejoint en cours d'année : sa part démarre à 0 et croît normalement.
  Pas de re-calibrage rétroactif.
- Si la caisse a **0 prêt** sur une période, `interest_pool = 0` → distribution
  vide (mais on log quand même).

## Invariants comptables à tester

- À tout instant : `Σ caisse_contributor_balances.apport_cum + Σ caisse_contributor_balances.interest_cum ≤ Fund.balance + Σ encours_prêts_caisse`.
- Après distribution : `Σ shares.share_amount = interest_pool` (avec reliquat).
- `total_base` au moment de la clôture = `Σ apport_cum_at_period_start`.

## Prochaines questions à se poser plus tard

- Affichage des **intérêts à recevoir** estimés (= rentabilité × apport_cum sur
  la période en cours) — utile pour la transparence.
- **Dissolution** d'une caisse : conversion `interest_cum` en cash ?
- **Multi-année** : labels de période plus riches (Q1 2026, etc.).
