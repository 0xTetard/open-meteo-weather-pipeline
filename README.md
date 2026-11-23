# Pipeline météo — Open-Meteo → PostgreSQL

J'ai réalisé ce petit projet personnel pour mettre en pratique les étapes de base d'un pipeline de données : récupérer des données météo publiques, les transformer, vérifier quelques règles, puis les enregistrer dans PostgreSQL.

C'est une première version locale, lancée à la demande. Elle n'est pas présentée comme un service de production : il n'y a ni mise à jour automatique, ni déploiement cloud, ni outil d'orchestration.

## Architecture

1. **Source** : API publique [Open-Meteo Archive](https://open-meteo.com/en/docs/historical-weather-api), avec une marge de cinq jours pour éviter les observations trop récentes.
2. **Transformation** : normalisation des séries quotidiennes (températures, précipitations, vent) en enregistrements typés.
3. **Qualité** : séries alignées, valeurs présentes et finies, dates uniques, bornes plausibles et température minimale inférieure ou égale à la maximale.
4. **Stockage** : JSON source dans `raw_weather_payloads` et modèle exploitable dans `daily_weather` (`weather_pipeline/schema.sql`). Les chargements sont transactionnels et rejouables sans doublons dans la table métier.
5. **Exécution** : lancement manuel en Python ou avec Docker Compose. Le pipeline se termine après un chargement.

Pour une explication plus détaillée du code et des choix du projet, voir le [guide PDF](docs/GUIDE_COMPLET_PIPELINE_METEO.pdf) ou sa [source Markdown](docs/GUIDE_COMPLET.md).

## Démarrage avec Docker

Prérequis : Docker avec le plugin Compose.

La base est publiée uniquement sur `127.0.0.1`. Le nom d'utilisateur et le mot de passe définis dans `compose.yaml` sont des identifiants de développement; ne les réutilise pas pour un service accessible depuis Internet.

```bash
# Start PostgreSQL, then run the pipeline once
docker compose up -d db
docker compose --profile run run --build --rm pipeline
```

La base reste disponible sur `localhost:5432`, avec le volume `postgres_data`. La commande ci-dessus utilise le lieu par défaut (Paris) et charge les sept jours d'archive disponibles selon la marge de cinq jours.

Pour explorer les données :

```bash
docker compose exec db psql -U weather -d weather \
  -c 'SELECT * FROM daily_weather ORDER BY observation_date DESC LIMIT 10;'
```

`docker compose down` arrête les services sans supprimer les données. `docker compose down -v` supprime aussi le volume PostgreSQL.

## Exécution manuelle avec Python

Prérequis : Python 3.12 ou plus récent et une instance PostgreSQL accessible.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m weather_pipeline --help
python -m weather_pipeline
```

Le pipeline utilise les valeurs par défaut (Paris, fuseau `Europe/Paris`, 7 jours) et PostgreSQL sur `localhost:5432`. Les options se donnent directement en ligne de commande, sans fichier `.env` :

```bash
python -m weather_pipeline \
  --latitude 45.7640 --longitude 4.8357 --timezone Europe/Paris \
  --days 14 \
  --database-url postgresql://weather:weather@localhost:5432/weather
```

`--days` accepte une valeur entre 1 et 90. À chaque lancement manuel, le pipeline recalcule sa fenêtre glissante et recharge les dates demandées; la clé lieu/date met à jour les lignes déjà présentes au lieu de les dupliquer. Il ne se relance pas de lui-même.

## Tests

Tests unitaires sans accès réseau ni PostgreSQL :

```bash
python -m pytest -q
```

Avec Docker, le test d'intégration PostgreSQL est activé :

```bash
docker compose --profile test run --build --rm tests
```

Le test d'intégration insère une observation temporaire, vérifie l'upsert, puis la supprime. Il est quand même préférable d'utiliser une base de test plutôt qu'une base contenant des données importantes.

## Fichiers principaux

| Fichier | Rôle |
|---|---|
| `weather_pipeline/__main__.py` | Options CLI et lancement manuel |
| `weather_pipeline/pipeline.py` | Enchaînement des étapes du pipeline |
| `weather_pipeline/source.py` | Requête HTTP Open-Meteo et reprises réseau |
| `weather_pipeline/transform.py` | Transformation JSON en objets typés |
| `weather_pipeline/quality.py` | Contrôles de qualité |
| `weather_pipeline/db.py` | Initialisation et écriture transactionnelle PostgreSQL |
| `weather_pipeline/schema.sql` | Tables, clés, contraintes et index |
| `compose.yaml` | Services PostgreSQL, pipeline ponctuel et tests |
| `.dockerignore` | Évite d'envoyer l'environnement virtuel et la documentation au build |
| `Dockerfile` / `Dockerfile.test` | Images d'exécution et de tests |
| `docs/GUIDE_COMPLET.md` | Guide détaillé du projet |

## Évolutions possibles

Le projet reste volontairement local et manuel. Avant d'ajouter une planification automatique, un orchestrateur ou un déploiement cloud, il faut éprouver les chargements, les contrôles et la reprise sur erreur. Le guide détaillé décrit les choix, les limites et les étapes possibles.

## Ce que j'ai pratiqué

En réalisant ce projet, j'ai pratiqué les requêtes HTTP en Python, la modélisation de tables PostgreSQL, les tests unitaires et d'intégration, ainsi que l'exécution locale avec Docker Compose. Je souhaite encore améliorer la gestion des erreurs et les migrations de schéma avant d'envisager une automatisation.

Ce dépôt n'a pas encore de licence. Il est consultable sur GitHub, mais aucune autorisation de réutilisation n'est accordée pour le moment.
