# Journal des décisions techniques (`decisions.md`)

Ce document consigne et justifie les choix de conception réalisés pour l'outil **Vélo**, conformément aux exigences du cahier des charges.

---

## 1. Définition des états d'une station

Les règles ci-dessous sont implémentées de façon centralisée dans [`src/velo/station_state.py`](../src/velo/station_state.py) et réutilisées par `status`, `favorites`, `alerts` et `dashboard` :

| État | Condition retenue | Justification |
| :--- | :--- | :--- |
| **Hors service** | `not (is_installed and is_renting and is_returning)` | Dès qu'une station n'est plus installée, ne loue plus ou n'accepte plus les retours, elle n'est pas exploitable normalement par l'usager. |
| **Vide** | Station en service et `bikes == 0` | Aucun vélo disponible à l'emprunt. |
| **Presque vide** | Station en service et `0 < bikes <= low_bikes` | Nombre de vélos inférieur ou égal au seuil configuré (`alerts.low_bikes`, défaut `2`). |
| **Pleine** | Station en service et `docks == 0` | Aucune place libre pour déposer un vélo. |
| **Presque pleine** | Station en service et `0 < docks <= low_docks` | Nombre de places libres inférieur ou égal au seuil configuré (`alerts.low_docks`, défaut `2`). |

### Règles complémentaires
- **Exclusion mutuelle avec « hors service »** : une station hors service affiche souvent `0` vélo et `0` place dans le flux GBFS ; elle n'est donc **jamais** comptée dans les vides/pleines ni signalée deux fois dans `velo alerts`.
- **Taux de remplissage du réseau** (`velo status`) : calculé sur les stations en service uniquement :
  $$\text{taux} = \text{round}\left(\frac{\sum \text{bikes}}{\sum (\text{bikes} + \text{docks})} \times 100\right)$$
  Si la somme vaut `0`, le taux retourné est `0 %`.

---

## 2. Recherche par expressions régulières (`velo station search`)

Implémentée dans `search_stations()` ([`src/velo/station_state.py`](../src/velo/station_state.py)) :

- **Recherche partielle** (`re.search`) : taper `gare` trouve `Gare Lille Flandres` et `Gare Lille Europe` sans devoir écrire `.*gare.*`, tout en permettant les motifs avancés (`^gare`, `europe$`, etc.).
- **Insensible à la casse** (`re.IGNORECASE`) : `vauban` trouve `Vauban`.
- **Insensible aux accents** : le motif saisi et les noms de stations sont normalisés en Unicode NFD puis débarrassés des marques diacritiques (`Mn`), afin que `chateau` trouve `Château`.
- **Validation** : une expression régulière invalide (ex. `[abc`) lève une `DataError` affichée proprement sans traceback.

---

## 3. Stockage CSV et détection des périodes (`velo collect` & `velo history`)

### Format des fichiers CSV
Implémenté dans [`src/velo/collection/storage.py`](../src/velo/collection/storage.py) :
- Un fichier par jour nommé `AAAA-MM-JJ.csv` selon la date locale du relevé.
- Colonnes exactes : `timestamp,station_id,bikes,docks,is_installed,is_renting,is_returning,last_reported`.
- Horodatages au format **ISO 8601 en heure locale avec décalage horaire** (ex. `2026-11-18T08:14:00+01:00`), permettant l'échange et l'analyse inter-groupes.
- Ouverture systématique avec `encoding="utf-8"` et `newline=""` pour la compatibilité Windows/Linux.
- Tolérance aux pannes : les lignes CSV corrompues sont journalisées en `WARNING` puis ignorées sans arrêter la lecture.

### Déduplication lors de la collecte
`collect_loop()` ([`src/velo/collection/collector.py`](../src/velo/collection/collector.py)) mémorise le `last_updated` du dernier relevé enregistré et n'écrit pas un nouveau relevé si le flux GBFS n'a pas changé.

### Seuil de détection des périodes
Implémenté dans `detect_periods()` :
- Deux relevés consécutifs appartiennent à la **même période** si leur écart temporel vérifie :
  $$\Delta t \le 3 \times \text{collect.interval\_seconds}$$
- Avec l'intervalle par défaut de `120` secondes, le seuil vaut **360 secondes (6 minutes)**.
- **Justification** : cela tolère jusqu'à deux échecs réseau ou retards de rafraîchissement consécutifs sans fragmenter artificiellement une collecte continue, tout en détectant nettement une vraie interruption (arrêt de `velo collect`, coupure réseau prolongée).
- La détection travaille sur la chronologie globale des relevés (et non fichier par fichier), ce qui permet à une même période de traverser minuit entre deux fichiers `AAAA-MM-JJ.csv`.

---

## 4. Métriques et requêtes analytiques (`velo query`)

Implémentées dans [`src/velo/analysis/metrics.py`](../src/velo/analysis/metrics.py) et [`src/velo/analysis/analysis.py`](../src/velo/analysis/analysis.py) :

- `avg_bikes` : moyenne arithmétique de `bikes` sur les relevés sélectionnés.
- `avg_docks` : moyenne arithmétique de `docks` sur les relevés sélectionnés.
- `empty_rate` : proportion (en `%`) des relevés où la station est **en service** et `bikes == 0`.
- `full_rate` : proportion (en `%`) des relevés où la station est **en service** et `docks == 0`.
- **Plage horaire `--hours A-B`** : sélectionne les heures locales telles que `A <= hour < B` (ex. `7-9` couvre de `07:00` à `08:59`, soit la tranche horaire du matin). Si `A == B`, l'heure `A` complète (`AA:00`–`AA:59`) est retenue.
- **Données manquantes** : les trous ne sont jamais interpolés ; le nombre exact de relevés utilisés est affiché, un avertissement apparaît si la sélection comporte des interruptions, et une erreur (code de sortie `1`) avec la liste des périodes disponibles est renvoyée si la sélection est vide.

---

## 5. Règles d'architecture et priorités de configuration

- **Isolation GBFS** : seul [`src/velo/gbfs.py`](../src/velo/gbfs.py) connaît le schéma GBFS (v2.x et v3.0) et aucune URL secondaire n'est codée en dur (`gbfs.json` sert de point d'entrée unique).
- **Séparation calcul / affichage** : [`src/velo/dashboard/dashboard_view.py`](../src/velo/dashboard/dashboard_view.py) ne réalise ni requête réseau ni calcul ; il affiche les résultats produits par `station_state.py` et `commands/favorites.py`.
- **Priorité des réglages** : `option CLI > config.yaml > valeur par défaut du code`.
- **Favoris séparés** : enregistrés dans `<data.folder>/<reseau>/favorites.json` (max `10` stations), jamais dans `config.yaml`.

