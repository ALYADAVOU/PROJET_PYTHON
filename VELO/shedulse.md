# Ordre de création des fichiers VELO

## Étape 1 --- Fondations du projet

Ce sont les premiers fichiers à créer. Ils permettent d'avoir un projet
Python propre, fonctionnel et prêt à accueillir le code.

1.  **`pyproject.toml`**\
    Configuration du projet, dépendances, outils, commande
    d'installation.
2.  **`README.md`**\
    Présentation du projet, installation, fonctionnement et
    documentation.
3.  **`.gitignore`**\
    Empêche Git de suivre les fichiers inutiles ou générés.
4.  **`src/velo/__init__.py`**\
    Déclare le package Python principal velo.
5.  **`src/velo/cli.py`**\
    Point d'entrée de l'application : gestion des commandes utilisateur.
6.  **`src/velo/commands/__init__.py`**\
    Prépare le sous-package des commandes (init, status, station, etc.).
7.  **`uv.lock`**\
    Verrouillage des versions exactes des dépendances, généré par uv
    après la configuration.

`<text color="success" weight="medium">`{=html}À ce stade : le projet
doit pouvoir être installé et la commande velo doit commencer à
fonctionner, même si les fonctionnalités ne sont pas encore
implémentées.`</text>`{=html}

------------------------------------------------------------------------

## Étape 2 --- Les fichiers centraux nécessaires à presque tout le projet

Ils sont très importants car plusieurs développeurs vont les utiliser.

8.  **`src/velo/models.py`**\
    Définir les structures des données : stations, vélos, docks,
    relevés, etc.
9.  **`src/velo/logging_config.py`**\
    Configuration des logs et messages d'erreurs du programme.
10. **`src/velo/config.py`**\
    Lecture et gestion de la configuration du projet.
11. **`src/velo/network.py`**\
    Connexion réseau, requêtes HTTP, récupération des données et gestion
    des erreurs réseau.
12. **`src/velo/gbfs.py`**\
    Lecture et transformation des données provenant de l'API GBFS.

**Pourquoi cet ordre ?** `models.py` définit les objets utilisés par les
autres fichiers. `network.py` et `gbfs.py` permettent ensuite aux
commandes d'accéder aux données du réseau de vélos.

------------------------------------------------------------------------

## Étape 3 --- Les fonctionnalités de base (Partie 1 et 2)

On commence par les fonctionnalités les plus simples qui permettent de
vérifier que le programme fonctionne.

13. **`src/velo/commands/init.py`**\
    Initialisation du projet et création des données/configurations
    nécessaires.
14. **`src/velo/commands/refresh.py`**\
    Actualisation des données statiques du réseau.
15. **`src/velo/station_state.py`**\
    Détermination de l'état d'une station (vide, pleine, hors service,
    etc.).
16. **`src/velo/commands/status.py`**\
    Afficher les statistiques générales du réseau.
17. **`src/velo/commands/station.py`**\
    Lister, rechercher et consulter les stations.
18. **`src/velo/commands/favorites.py`**\
    Ajouter, afficher et supprimer des stations favorites.
19. **`src/velo/commands/alerts.py`**\
    Afficher les alertes de stations : vides, presque vides, pleines,
    etc.

------------------------------------------------------------------------

## Étape 4 --- Le dashboard

Ces fichiers permettent de construire le tableau de bord en temps réel.

20. **`src/velo/dashboard/__init__.py`**\
    Initialise le sous-package dashboard.
21. **`src/velo/dashboard/dashboard_view.py`**\
    Affichage visuel du tableau de bord : statistiques, favoris,
    alertes.
22. **`src/velo/commands/dashboard.py`**\
    Gestion du lancement, rafraîchissement, boucle et arrêt du
    dashboard.

`<text color="warning" weight="medium">`{=html}Attention
:`</text>`{=html} `dashboard_view.py` est un fichier partagé entre
plusieurs membres. Il faut se mettre d'accord sur les fonctions
d'affichage avant que plusieurs personnes le modifient.

------------------------------------------------------------------------

## Étape 5 --- Collecte et sauvegarde des données historiques (Partie 4)

On construit les fichiers qui vont permettre d'enregistrer l'évolution
des stations au fil du temps.

23. **`src/velo/collection/__init__.py`**\
    Initialise le sous-package de collecte.
24. **`src/velo/collection/storage.py`**\
    Définit le stockage des relevés et leur format CSV.
25. **`src/velo/collection/collector.py`**\
    Récupère périodiquement les données et prépare leur enregistrement.
26. **`src/velo/commands/collect.py`**\
    Commande utilisateur qui déclenche la collecte, la durée et
    l'intervalle.
27. **`src/velo/commands/history.py`**\
    Consultation de l'historique : périodes, évolutions, données
    enregistrées.

------------------------------------------------------------------------

## Étape 6 --- Analyse des données (Partie 5)

Cette partie dépend principalement de la collecte et du stockage
historique.

28. **`src/velo/analysis/__init__.py`**\
    Initialise le sous-package d'analyse.
29. **`src/velo/analysis/metrics.py`**\
    Calcul des métriques : moyennes, taux de stations vides/pleines,
    etc.
30. **`src/velo/analysis/analysis.py`**\
    Regroupement, analyse et classement des données.
31. **`src/velo/commands/query.py`**\
    Commande de recherche des données historiques selon les dates,
    périodes, stations, etc.

------------------------------------------------------------------------

## Étape 7 --- Tous les fichiers de tests

Les tests ne doivent pas être créés uniquement à la fin. Il faut les
créer au fur et à mesure de l'implémentation de chaque fonctionnalité.
Mais voici l'ordre conseillé pour créer leurs fichiers.

32. **`tests/__init__.py`**
33. **`tests/test_config.py`**
34. **`tests/test_init.py`**
35. **`tests/test_gbfs.py`**
36. **`tests/test_refresh.py`**
37. **`tests/test_station_state.py`**
38. **`tests/test_status.py`**
39. **`tests/test_station.py`**
40. **`tests/test_favorites.py`**
41. **`tests/test_alerts.py`**
42. **`tests/test_dashboard.py`**
43. **`tests/test_storage.py`**
44. **`tests/test_collect.py`**
45. **`tests/test_history.py`**
46. **`tests/test_metrics.py`**
47. **`tests/test_query.py`**
48. **`tests/test_analysis.py`**

------------------------------------------------------------------------

## Étape 8 --- Documentation finale du projet

49. **`docs/decisions.md`**\
    Journal des décisions techniques : choix de formats, organisation,
    règles communes et justifications.

------------------------------------------------------------------------

# Liste complète condensée (49 fichiers)

`<text color="success" weight="medium">`{=html}Voici la liste dans
l'ordre que vous pouvez suivre pour la création des fichiers et dossiers
:`</text>`{=html}

``` text
01. pyproject.toml
02. README.md
03. .gitignore
04. src/velo/__init__.py
05. src/velo/cli.py
06. src/velo/commands/__init__.py
07. uv.lock

08. src/velo/models.py
09. src/velo/logging_config.py
10. src/velo/config.py
11. src/velo/network.py
12. src/velo/gbfs.py

13. src/velo/commands/init.py
14. src/velo/commands/refresh.py
15. src/velo/station_state.py
16. src/velo/commands/status.py
17. src/velo/commands/station.py
18. src/velo/commands/favorites.py
19. src/velo/commands/alerts.py

20. src/velo/dashboard/__init__.py
21. src/velo/dashboard/dashboard_view.py
22. src/velo/commands/dashboard.py

23. src/velo/collection/__init__.py
24. src/velo/collection/storage.py
25. src/velo/collection/collector.py
26. src/velo/commands/collect.py
27. src/velo/commands/history.py

28. src/velo/analysis/__init__.py
29. src/velo/analysis/metrics.py
30. src/velo/analysis/analysis.py
31. src/velo/commands/query.py

32. tests/__init__.py
33. tests/test_config.py
34. tests/test_init.py
35. tests/test_gbfs.py
36. tests/test_refresh.py
37. tests/test_station_state.py
38. tests/test_status.py
39. tests/test_station.py
40. tests/test_favorites.py
41. tests/test_alerts.py
42. tests/test_dashboard.py
43. tests/test_storage.py
44. tests/test_collect.py
45. tests/test_history.py
46. tests/test_metrics.py
47. tests/test_query.py
48. tests/test_analysis.py

49. docs/decisions.md
```