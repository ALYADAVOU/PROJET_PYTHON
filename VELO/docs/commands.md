# Guide d'utilisation des commandes (`commands.md`)

Toutes les commandes s'exécutent via `velo <commande> [options]`.  
En cas d'erreur (configuration invalide, réseau indisponible, identifiant inconnu, sélection vide), l'outil affiche un message explicite sans traceback et retourne un code de sortie non nul.

---

## 1. `velo init [--force]`

Prépare l'outil après l'installation :
1. Crée `~/.config/velo/config.yaml` avec les valeurs par défaut (réseau **V'Lille**). Sans `--force`, une configuration existante est conservée.
2. Crée le dossier de données (`~/.local/share/velo/vlille/history/`).
3. Télécharge les trois fichiers statiques (`system_information`, `station_information`, `vehicle_types`). Si le réseau est inaccessible, les dossiers et la configuration sont tout de même créés avec un avertissement.

```bash
velo init
velo init --force
```

---

## 2. `velo refresh`

Retélécharge les trois fichiers qui changent rarement (`system_information`, `station_information`, `vehicle_types`) et affiche la date de mise à jour ainsi que le nombre de stations.

```bash
velo refresh
```

---

## 3. `velo status`

Télécharge l'état temps réel (`station_status`) et affiche le résumé du réseau :
- nom du réseau et date/heure des données (`last_updated`) ;
- stations en service / total, hors service, vides et pleines ;
- vélos disponibles, places libres et taux de remplissage (`%`).

Si les fichiers statiques locaux dépassent `refresh.max_age_days`, un avertissement invite à exécuter `velo refresh`.

```bash
velo status
```

---

## 4. `velo station`

Permet de chercher, lister ou consulter une station à partir des données locales :

```bash
velo station search gare        # Recherche par expression régulière (casse/accents ignorés)
velo station list               # Liste toutes les stations avec ID et capacité
velo station show 42            # Détail et état temps réel de la station 42
```

---

## 5. `velo favorites`

Gère jusqu'à **10** stations favorites (stockées dans `favorites.json`, hors `config.yaml`) :

```bash
velo favorites                  # Affiche l'état temps réel des favorites (ou aide si vide)
velo favorites add 42           # Ajoute la station 42 aux favoris
velo favorites remove 42        # Retire la station 42 des favoris
```

---

## 6. `velo alerts [--low-bikes N] [--low-docks N]`

Liste les stations posant problème, classées en trois catégories sans doublon :
- **Hors service** ;
- **Vide ou presque** (`bikes <= low_bikes`) ;
- **Pleine ou presque** (`docks <= low_docks`).

```bash
velo alerts
velo alerts --low-bikes 5 --low-docks 3
```

---

## 7. `velo dashboard [--refresh SECONDES]`

Affiche un tableau de bord temps réel (via `Rich`) regroupant l'en-tête avec compte à rebours, les statistiques réseau, les favoris et les alertes.
- Intervalle minimum : **60 secondes**.
- En cas d'erreur réseau, les dernières données connues restent affichées avec un bandeau d'erreur.
- Fermeture propre avec `Ctrl+C`.

```bash
velo dashboard
velo dashboard --refresh 90
```

---

## 8. `velo collect`

Enregistre périodiquement l'état de toutes les stations dans `history/AAAA-MM-JJ.csv` :

```bash
velo collect                                  # Jusqu'à Ctrl+C (intervalle de config.yaml)
velo collect --interval 60 --duration 3h      # Toutes les 60s pendant 3 heures
velo collect --until "2026-11-18 19:00"       # Jusqu'à une date/heure précise
velo collect --once                           # Un seul relevé immédiat puis arrêt
```

- Intervalle minimum : **60 secondes**.
- Déduplique les relevés dont `last_updated` est identique au précédent.
- Continue sans s'arrêter en cas d'erreur réseau temporaire et affiche un bilan final même après `Ctrl+C`.

---

## 9. `velo history [--from AAAA-MM-JJ] [--to AAAA-MM-JJ]`

Affiche les périodes continues détectées dans l'historique (numérotées de la plus ancienne à la plus récente), avec début, fin, durée et nombre de relevés.

```bash
velo history
velo history --from 2026-11-18 --to 2026-11-20
```

---

## 10. `velo query`

Analyse l'historique collecté à l'aide d'une ou plusieurs métriques (`avg_bikes`, `avg_docks`, `empty_rate`, `full_rate`).

### Options de sélection
- `--date AAAA-MM-JJ` : un jour précis ;
- `--from` / `--to` : intervalle (`AAAA-MM-JJ` ou `"AAAA-MM-JJ HH:MM"`) ;
- `--period N [N ...]` : un ou plusieurs numéros de périodes issus de `velo history` ;
- `--days` : `weekdays`, `weekend` ou liste de jours (`lundi,mercredi`) ;
- `--hours` : plage horaire (ex. `7-9`) ;
- `--station <id>` : restreint à une station.

### Regroupement et classement
- `--by` : `station`, `hour`, `weekday` ou `day` ;
- `--top N` : affiche uniquement les `N` premiers résultats.

```bash
velo query --metric empty_rate --days weekdays --hours 7-9 --by station --top 3
velo query --metric avg_bikes avg_docks --period 1 --by hour
```

