# Import multi-feuilles (classeurs par domaine) — plan validé

But : passer d'un import **mono-feuille / config seule** à des **classeurs Excel
par domaine** contenant config **et** mouvements/actions des membres.

## Décisions (validées avec le client)
- **Un classeur par domaine** : Membres, Caisses, Tontines, Prêts, Aides.
- **Feuille 1 = Membres** dans chaque classeur (mêmes colonnes que l'import
  membres) → crée/relie les membres ; chaque classeur est **autonome**.
  Clé de liaison = **N° d'adhérent** (member_number).
- **Feuilles à plat + référence** (pas de format groupé entête+sous-lignes).
  Une « référence » texte (ex. `PRT-2024-012`) lie entête ↔ détails.
- **Rejouer l'historique** : chaque mouvement importé **régénère** son
  mouvement de trésorerie → soldes reconstruits.
- **Ordre d'import** : Membres → Caisses → Tontines → Prêts → Aides.
  À l'intérieur d'un classeur : feuilles traitées **de haut en bas**.
- **Idempotence** : n° d'adhérent / référence déjà présents → ligne ignorée +
  rapportée.

## Socle technique
- `Importer` actuel = une « feuille » (colonnes + validate_row + create_row).
- Nouveau `DomainImporter` : `entity`, `label`, `description`, `sheets`
  (liste ordonnée de feuilles), **ctx partagé** entre feuilles (caches :
  `membership_by_number`, `caisse_by_name`, `ref → entité`…).
- Endpoints `/imports` deviennent multi-feuilles : template = 1 onglet/feuille ;
  preview valide toutes les feuilles ; commit crée feuille par feuille (ordre),
  point de sauvegarde par ligne, ctx accumulé.

## Domaines & feuilles

Légende : 🟢 existe (réutilisé) · 🟡 à ajouter.

### CAISSES (1er chantier)
- F1 Membres 🟡(réutilise import membres)
- F2 Caisses (config) 🟢
- F3 Mouvements 🟡 : `caisse`, `n° adhérent` (si perso/cotisant), `sens`
  (depot/retrait), `montant`, `date`, `libellé`. → mouvement trésorerie + solde.

### TONTINES
- F1 Membres · F2 Tontines (config) 🟢
- F3 Séances/Tours 🟡 : tontine, n° tour, date, statut, montant attendu.
- F4 Participations 🟡 : tontine, n° tour, n° adhérent, montant, date, retard?
- F5 Gagnants 🟡 : tontine, n° tour, n° adhérent, libellé part, montant reçu, date.

### PRÊTS
- F1 Membres · F2 Types de prêt (config) 🟢
- F3 Prêts 🟡 : référence, n° adhérent, type, montant, dates (demande/accord/
  décaissement), statut, motif.
- F4 Remboursements 🟡 : référence prêt, date, montant (ou capital/intérêt), notes.

### AIDES
- F1 Membres · F2 Types d'aide (config) 🟢
- F3 Demandes 🟡 : référence, n° adhérent (bénéficiaire), type, date événement,
  montant demandé/approuvé, statut, date décision.
- F4 Cotisations 🟡 (surtout mode « cotisation ponctuelle ») : référence demande,
  n° adhérent, montant, date.

## Avancement
- [ ] Socle multi-feuilles (DomainImporter + endpoints)
- [ ] Caisses : F3 Mouvements + rejeu trésorerie
- [ ] Frontend : aperçu multi-feuilles (onglets par feuille)
- [ ] Tontines / Prêts / Aides : feuilles mouvements
