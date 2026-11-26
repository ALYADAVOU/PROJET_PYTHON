# Projet Python

Ce guide explique comment récupérer le dépôt et travailler sur une branche personnelle.

## Prérequis

- Installer [Git](https://git-scm.com/downloads).
- Avoir accès au dépôt GitHub : <https://github.com/ALYADAVOU/PROJET_PYTHON>.

## Cloner le dépôt

Dans un terminal, exécutez :

```bash
git clone https://github.com/ALYADAVOU/PROJET_PYTHON.git
cd PROJET_PYTHON
```

Le dossier du projet s'appelle `VELO`. Si GitHub le crée sous ce nom, entrez plutôt dans ce dossier avec `cd VELO`.

## Créer sa branche de travail

Avant de commencer, récupérez les dernières modifications de la branche principale, puis créez une branche dédiée à votre tâche :

```bash
git switch main
git pull
git switch -c feature/nom-de-votre-tache
```

Remplacez `feature/nom-de-votre-tache` par un nom court et explicite, par exemple `feature/ajout-statistiques`. Pour un correctif, vous pouvez utiliser le préfixe `fix/`.

Vérifiez que vous êtes sur votre branche :

```bash
git branch
git status
```

La branche courante est marquée par `*`. Faites vos modifications et vos commits sur cette branche, pas directement sur `main`.

## Enregistrer et publier son travail

Quand vos modifications sont prêtes :

```bash
git add .
git commit -m "Décrire brièvement la modification"
git push -u origin feature/nom-de-votre-tache
```

Pour les prochaines publications de cette même branche, utilisez simplement `git push`.

Une fois la branche publiée, ouvrez GitHub et créez une **pull request** vers `main` afin que le groupe puisse relire et intégrer votre travail.

## Reprendre un projet déjà cloné

Si le dépôt est déjà présent sur votre ordinateur, ne le clonez pas une deuxième fois. Ouvrez son dossier, mettez `main` à jour, puis créez votre branche :

```bash
git switch main
git pull
git switch -c feature/nom-de-votre-tache
```