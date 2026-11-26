# Vélo — Outil CLI d'analyse V'Lille / GBFS

**Vélo** est un outil en ligne de commande écrit en Python permettant de consulter l'état temps réel d'un réseau de vélos en libre-service au format **GBFS** (par défaut **V'Lille**), de suivre ses stations favorites, d'afficher un tableau de bord en continu, d'enregistrer un historique CSV quotidien puis de l'analyser.

> La documentation complète du projet est regroupée dans le dossier [`docs/`](docs/) :
> - [Guide d'installation (`docs/installation.md`)](docs/installation.md)
> - [Référence des commandes (`docs/commands.md`)](docs/commands.md)
> - [Architecture et modules (`docs/architecture.md`)](docs/architecture.md)
> - [Choix techniques et justifications (`docs/decisions.md`)](docs/decisions.md)
> - [Guide Git de l'équipe (`README_Git.md`)](README_Git.md)

---

## Installation rapide avec `uv`

1. Installer `uv` (voir [docs/installation.md](docs/installation.md)) puis cloner le dépôt.
2. Depuis le dossier `VELO/`, installer l'outil en ligne de commande :
   ```bash
   uv tool install .
   ```
3. Initialiser la configuration et télécharger les premières données V'Lille :
   ```bash
   velo init
   ```

---

## Commandes disponibles (socle obligatoire)

| Commande | Rôle |
| :--- | :--- |
| `velo init [--force]` | Crée `config.yaml`, les dossiers de données et teste la connexion GBFS |
| `velo refresh` | Met à jour `system_information`, `station_information` et `vehicle_types` |
| `velo status` | Résumé temps réel du réseau (stations en service/vides/pleines, taux de remplissage) |
| `velo station search \| list \| show` | Recherche par regex, liste des stations ou détail temps réel |
| `velo favorites [add \| remove]` | Suivi jusqu'à 10 stations favorites |
| `velo alerts [--low-bikes N] [--low-docks N]` | Liste les stations hors service, vides/presque vides et pleines/presque pleines |
| `velo dashboard [--refresh S]` | Tableau de bord temps réel Rich (rafraîchissement min. 60s) |
| `velo collect [--interval S] [--duration D \| --until "..." \| --once]` | Collecte périodique vers des fichiers CSV quotidiens (`AAAA-MM-JJ.csv`) |
| `velo history [--from AAAA-MM-JJ] [--to AAAA-MM-JJ]` | Affiche les périodes continues enregistrées |
| `velo query --metric ... [filtres] [--by ...] [--top N]` | Analyse statistique de l'historique collecté |

---

## Résumé des choix techniques

Les justifications détaillées sont disponibles dans [`docs/decisions.md`](docs/decisions.md) :

- **États d'une station** : une station est *hors service* si `is_installed`, `is_renting` ou `is_returning` est faux (elle n'est jamais signalée en double comme vide/pleine). Les seuils *presque vide* et *presque pleine* s'appliquent aux stations en service.
- **Expressions régulières (`velo station search`)** : recherche partielle (`re.search`), insensible à la casse (`re.IGNORECASE`) et insensible aux accents (normalisation Unicode NFD).
- **Détection des périodes (`velo history` / `velo query`)** : deux relevés consécutifs appartiennent à une même période si leur écart est `<= 3 × collect.interval_seconds` (soit 6 minutes par défaut), y compris à cheval sur deux fichiers journaliers (minuit).
- **Isolation GBFS & séparation calcul/affichage** : seul `src/velo/gbfs.py` décode les flux GBFS (v2.x et v3.0) ; le tableau de bord réutilise les calculs de `station_state.py` et `favorites.py`.

---

## Tests et qualité du code

```bash
uv run pytest -v
uv run ruff check src tests
```

## Fonctionnalités avancées (section 3.2)

Le socle obligatoire (section 3.1) est complet et testé. Les fonctionnalités avancées bonus de la section 3.2 seront intégrées dans une phase ultérieure.

