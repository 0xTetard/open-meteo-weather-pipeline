---
title: "Mon projet météo : un premier pipeline de données"
subtitle: "Notes de conception et d'apprentissage — Python, PostgreSQL et Docker"
author: "Projet personnel"
date: "23 novembre 2026"
lang: fr-FR
geometry: margin=2.1cm
fontsize: 10pt
colorlinks: true
linkcolor: blue
urlcolor: blue
toc-title: "Sommaire"
---

\thispagestyle{empty}
\newpage

# Comment lire ce guide

J'ai écrit ces notes pour expliquer ce que j'ai construit et ce que j'ai appris en le faisant. Elles décrivent le dépôt tel qu'il existe, pas une architecture idéale ni un système prêt pour la production. Les noms de fichiers renvoient au code de `weather_pipeline/`, aux tests et à `compose.yaml`. Les extraits JSON sont illustratifs; la réponse réelle varie selon le lieu, la période et les mises à jour du fournisseur.

Le fil conducteur est le trajet d'une journée météo : les options données à la commande définissent le lieu et la période; le client HTTP demande les archives Open-Meteo; le programme transforme et contrôle la réponse; PostgreSQL garde la réponse brute ainsi qu'une table quotidienne facile à interroger. Docker fournit le même environnement à chaque lancement manuel.

Les chapitres séparent les faits présents dans le code des limites ou évolutions possibles. Le projet ne contient aucune planification automatique : une mise à jour n'a lieu que lorsqu'une personne relance la commande. Il est volontairement une première version locale.

\newpage

# 1. Objectif du projet

J'ai réalisé ce projet pour pratiquer les étapes principales d'un pipeline de données : récupérer une source publique, vérifier et transformer les données, puis les enregistrer dans une base. J'ai aussi ajouté des tests et une exécution locale reproductible.

Le sujet choisi est la météo quotidienne d'un point géographique. Open-Meteo expose une API d'archives sans jeton d'accès pour cet usage. Paris est le défaut, mais latitude, longitude et fuseau sont configurables. Les champs suivis sont la température maximale et minimale, la somme des précipitations et la vitesse maximale du vent.

Ce projet m'a donné l'occasion de comparer quelques approches simples : conserver le JSON reçu ou ne garder que les données propres, utiliser PostgreSQL ou un fichier, et rendre les chargements répétables. Il m'a aussi appris ce qu'il faudrait encore améliorer avant de parler d'un vrai service de production.

**Ce qui est réalisé :** un chargement déclenché manuellement par CLI; une base PostgreSQL; une image applicative non-root; un compose local; des tests unitaires et un test d'intégration prêt pour une base.

**Ce qui n'est pas revendiqué :** haute disponibilité, alertes, reprise garantie après panne, traitement de flux, orchestration distribuée, cloud, tableau de bord ou niveau de service. La simplicité permet de fiabiliser d'abord les étapes de base, comme le demandait le cadrage.

\newpage

# 2. Vocabulaire et architecture générale

Un **pipeline** est une séquence d'opérations qui fait passer une donnée d'une source à une destination en appliquant des règles explicites. Ici, le parcours est souvent résumé par ETL : *Extract* (extraire), *Transform* (transformer), *Load* (charger). Le projet conserve également le payload source, ce qui se rapproche d'une zone d'atterrissage brute (« bronze ») suivie d'une table métier (« silver »).

```text
Options de la commande
          |
          v
CLI -> pipeline.run -> API Open-Meteo
                 |         |
                 |         v
                 |    JSON source
                 |         |
                 |   transform.py -> qualité.py
                 |                       |
                 +-----------------------v
                              PostgreSQL
                      raw_weather_payloads
                              |
                         daily_weather
```

`__main__.py` est la porte d'entrée et lit les options de commande; `pipeline.py` coordonne les étapes. `source.py`, `transform.py`, `quality.py` et `db.py` isolent les responsabilités. `schema.sql` décrit les tables. Les fichiers Docker et Compose décrivent l'exécution, et `tests/` vérifie une partie des contrats.

La séparation est utile : une transformation peut être testée sans réseau ni base; le transport HTTP peut être remplacé ou simulé; la persistance peut évoluer sans réécrire les règles métier. Ce n'est pas une architecture en couches lourde : les modules restent petits et la séquence reste lisible.

\newpage

# 3. La source de données

La source est l'API d'archives historiques d'Open-Meteo, à l'adresse `https://archive-api.open-meteo.com/v1/archive`. Le projet demande quatre séries quotidiennes. Il n'utilise ni scraping HTML, ni compte, ni clé secrète.

Pourquoi cette source? Elle est publique et assez simple pour se concentrer sur le pipeline. Elle permet une véritable requête réseau, mais les tests unitaires ne dépendent pas de sa disponibilité. Une API gouvernementale française aurait été un choix valable, mais aurait demandé de choisir une série précise, d'étudier son format et ses conditions d'accès avant d'avoir une première version.

L'API d'archives ne doit pas être confondue avec une API de prévisions. Le code appelle l'endpoint d'archives pour demander des dates passées. Les quatre champs sont `temperature_2m_max`, `temperature_2m_min`, `precipitation_sum` et `wind_speed_10m_max`; dans la réponse standard, les unités sont respectivement °C, °C, mm et km/h. Les métadonnées `daily_units` permettent de contrôler ces unités dans une inspection réelle.

La source renvoie des données correspondant à un point, mais peut ajuster ou arrondir les coordonnées demandées selon ses modèles. Le pipeline enregistre les coordonnées retournées par la source, pas seulement celles passées à la commande. C'est donc cette paire de coordonnées qui contribue à l'identité des observations dans la table finale.

Avant un usage public ou commercial, il faut vérifier les conditions, limites d'utilisation et règles d'attribution courantes d'Open-Meteo. Une API sans clé n'est pas synonyme d'absence de conditions ni d'absence de quotas.

\newpage

# 4. La requête HTTP en détail

`weather_pipeline/source.py` construit une URL avec `urllib.parse.urlencode`. En concept, la requête ressemble à ceci (les valeurs de dates dépendent de l'exécution) :

```text
GET /v1/archive?
 latitude=48.8566
 &longitude=2.3522
 &start_date=2026-11-07
 &end_date=2026-11-13
 &daily=temperature_2m_max,temperature_2m_min,
        precipitation_sum,wind_speed_10m_max
 &timezone=Europe/Paris
```

`urlencode` s'occupe de l'encodage des caractères réservés, notamment la virgule et les deux-points éventuels. La requête annonce un `User-Agent` descriptif. `urlopen` a une limite d'attente de 30 secondes : un appel bloqué ne doit pas suspendre le processus indéfiniment.

Le corps est lu puis décodé en JSON. Le code exige un objet JSON et vérifie le marqueur `error` utilisé par l'API. Il renvoie deux objets au pipeline : le dictionnaire décodé et l'URL complète. L'URL est conservée avec le payload comme provenance (endpoint, paramètres de période, lieu et fuseau).

`urllib` a été retenu plutôt que d'ajouter `requests` ou `httpx` pour une seule requête synchrone. C'est une dépendance de moins. Un client dédié deviendrait intéressant avec beaucoup d'endpoints, de l'asynchronisme, une configuration TLS avancée ou des middlewares communs.

\newpage

# 5. À quoi ressemble le payload récupéré?

Le payload est un document JSON contenant des métadonnées et des séries parallèles. Exemple raccourci et illustratif :

```json
{
  "latitude": 48.86,
  "longitude": 2.35,
  "timezone": "Europe/Paris",
  "daily_units": {
    "temperature_2m_max": "°C",
    "temperature_2m_min": "°C",
    "precipitation_sum": "mm",
    "wind_speed_10m_max": "km/h"
  },
  "daily": {
    "time": ["2026-11-07", "2026-11-08"],
    "temperature_2m_max": [13.1, 12.4],
    "temperature_2m_min": [7.0, 6.8],
    "precipitation_sum": [0.0, 1.2],
    "wind_speed_10m_max": [18.0, 24.5]
  }
}
```

Le tableau de dates et chacun des tableaux de mesures doivent être de même longueur. L'élément à l'indice `i` dans chaque série décrit la même journée. C'est le contrat implicite que `transform.py` vérifie avant de construire les lignes.

Le JSON peut contenir d'autres métadonnées (altitude, décalage UTC, version ou temps de génération). Le transformateur ne copie que les champs nécessaires au modèle métier; la table brute permet de retrouver les métadonnées écartées. L'exemple n'est pas une réponse figée : valeurs, coordonnées et métadonnées changent selon l'appel.

La réponse entière est stockée sous forme `JSONB` dans PostgreSQL dans `raw_weather_payloads.payload`. `JSONB` facilite la conservation et l'inspection des objets JSON; ce n'est pas un fichier `.json` déposé sur le disque. Le projet n'écrit donc pas de CSV ou de fichier de données local. Les fichiers du dépôt sont le code, la configuration et la documentation; les données runtime sont dans la base.

\newpage

# 6. Fenêtre temporelle et choix du décalage

Dans `pipeline.run`, la date de fin est la date courante dans le fuseau demandé moins cinq jours. La date de début est la date de fin moins `days_to_load - 1`. Par défaut `--days=7`, donc la fenêtre contient sept dates, bornes incluses. Par exemple, si la date dans le fuseau demandé est le 20 novembre, la requête couvre du 8 au 14 novembre inclus.

Le décalage de cinq jours est une marge de prudence pour éviter de demander des observations d'archive trop récentes ou encore incomplètes. Ce n'est pas une garantie formelle du fournisseur ni une mesure calculée par le pipeline; il est codé comme une heuristique simple.

La fenêtre est glissante. Lorsqu'on relance manuellement le pipeline quelques jours plus tard, une partie des dates peut recouper des données déjà chargées. Cela donne une occasion de corriger les valeurs si la source révise une archive, et exerce la logique d'upsert. Le pipeline ne se relance pas de lui-même.

Le fuseau est appliqué lors du calcul de la date courante grâce à `ZoneInfo(timezone)`. Cela évite de dépendre du fuseau système du conteneur. Les transitions heure d'été/hiver restent gérées par la base IANA installée dans Python.

\newpage

# 7. Paramètres à la demande : options CLI

Il n'y a ni fichier `.env.example`, ni module `config.py`, ni configuration persistante à maintenir. Les paramètres sont des options données au lancement dans `weather_pipeline/__main__.py`. Cela rend chaque exécution explicite et évite qu'un fichier de configuration déclenche ou implique une mise à jour périodique.

`argparse` convertit et valide `--latitude`, `--longitude`, `--days` et `--timezone`. Les coordonnées doivent être dans les bornes géographiques, le nombre de jours entre 1 et 90, et le fuseau doit exister dans la base IANA connue de Python. Les valeurs par défaut sont Paris, `Europe/Paris`, sept jours, PostgreSQL local et le niveau `INFO`.

L'URL PostgreSQL se donne avec `--database-url`. Par défaut elle vise PostgreSQL local. Dans Compose, la commande est construite avec une URL utilisant le nom du service `db`, car les conteneurs se joignent via le réseau Compose. `localhost` depuis le conteneur applicatif désignerait le conteneur lui-même, pas PostgreSQL.

Le niveau de logs peut être choisi avec `--log-level`. Les identifiants `weather/weather` utilisés dans les commandes locales sont des valeurs de développement sans secret; ils ne doivent pas être réutilisés pour un service exposé.

\newpage

# 8. Entrée en ligne de commande : `__main__.py`

La commande `python -m weather_pipeline` indique à Python d'exécuter `weather_pipeline/__main__.py`. `argparse` présente les options et rejette les valeurs hors limites avant tout accès réseau ou base.

Le programme configure `logging.basicConfig`, puis appelle une seule fois `pipeline.run(...)`. Le format de journal contient heure, niveau, nom de logger et message. Les logs vont par défaut sur la sortie standard, ce qui est adapté aux conteneurs : Docker peut les collecter sans fichier de log partagé.

La CLI ne contient pas de logique métier. Cette séparation rend l'exécution manuelle, les tests et l'appel des fonctions plus simples. `if __name__ == "__main__"` évite de lancer le programme si le module est importé depuis un test.

Exemples :

```bash
python -m weather_pipeline
python -m weather_pipeline --latitude 45.7640 --longitude 4.8357 --days 14
```

Il n'y a qu'un seul mode : lancer une ingestion puis terminer. Le code ne fournit pas de commande `init-db`, `check` ou `backfill`; le schéma est préparé au début de chaque exécution.

\newpage

# 9. `source.py` : réseau, erreurs et reprises

`fetch_weather()` reçoit le lieu, le fuseau, les deux dates et, optionnellement, un nombre d'essais. Il construit la requête, puis essaie au maximum trois fois. Le délai HTTP maximal est de 30 secondes.

Sont réessayées les erreurs réseau (`URLError`, timeout) et certaines réponses HTTP : 429 (limitation de débit) ou 5xx (erreur côté serveur). L'attente est exponentielle simple : une seconde avant le deuxième essai, puis deux secondes avant le troisième. Après le dernier échec, une `RuntimeError` explique le problème. Une réponse 4xx autre que 429 n'est pas retentée, car elle signale généralement un paramètre invalide. Un JSON non décodable est également considéré comme non récupérable dans cette fonction.

Ce mécanisme est délibérément petit. Il n'implémente pas de jitter aléatoire, circuit breaker, métrique, cache ou respect du header `Retry-After`. Ces protections sont des candidats d'évolution si le volume ou les exigences de disponibilité augmentent.

Un point d'architecture important : la fonction réseau ne touche pas à PostgreSQL. Elle renvoie le payload en mémoire. Cela permet au pipeline de rejeter une réponse avant de l'écrire, et aux tests de remplacer `urlopen` par une fausse réponse déterministe.

\newpage

# 10. `transform.py` : du JSON aux objets métier

`DailyWeather` est un dataclass immuable décrivant une observation quotidienne avec une date, des coordonnées, un fuseau et quatre mesures. Une instance correspond à une ligne logique de `daily_weather`, avant ajout des champs techniques de base de données.

`transform(payload)` lit `latitude`, `longitude`, `timezone` et les cinq tableaux utiles de `payload["daily"]`. Il signale les champs manquants ou de mauvais type avec `TransformationError`. Il vérifie ensuite que les champs sont bien des listes et ont la même longueur. Enfin, chaque date ISO devient `datetime.date`, chaque valeur numérique devient `float`, et `math.isfinite` rejette NaN et l'infini.

Pourquoi produire une liste d'objets au lieu de passer directement le dictionnaire à SQL? Les unités et les noms source sont traduits une fois vers un contrat métier explicite; les règles qualité opèrent sur des attributs lisibles; l'adaptateur SQL ne dépend pas de la structure imbriquée d'Open-Meteo.

Le transformateur ne fait pas de conversion d'unités ni de valeurs par défaut. Il utilise les unités demandées par l'API. Une valeur nulle dans un champ requis provoque un rejet du lot plutôt qu'une substitution arbitraire. C'est une politique stricte et visible; si la source commence à retourner des valeurs absentes de façon normale, il faudra décider explicitement de filtrer, compléter ou modéliser le `NULL`.

\newpage

# 11. `quality.py` : règles et garde-fous

`validate(records)` intervient après transformation et avant toute connexion/écriture en base. Cela évite de charger un lot qui ne respecte pas le contrat métier. Elle rassemble les erreurs afin de donner plusieurs motifs dans un seul message.

Les contrôles actuels sont : lot non vide; unicité des dates; température minimale et maximale dans [-90, 60] °C; minimum inférieur ou égal au maximum; précipitations dans [0, 2000] mm/jour; vitesse maximale du vent dans [0, 400] km/h. Les valeurs non finies et nulles sont déjà rejetées par le transformateur.

Ces seuils sont des bornes grossières de plausibilité, pas des seuils climatiques locaux, ni des garanties scientifiques universelles. Ils sont volontairement larges pour détecter une erreur de schéma, un décalage d'unité ou une corruption évidente sans prétendre décider si une journée est « normale ».

La base reproduit quelques contraintes (`temperature_min <= temperature_max`, précipitations et vent non négatifs). Cette défense en profondeur protège aussi contre un autre client SQL. Les règles métier plus précises vivent en Python, où les messages sont plus faciles à comprendre. Il n'y a pas encore de règle sur le nombre exact de dates attendues, les trous de calendrier ou la cohérence avec la période demandée; ce sont des contrôles utiles à ajouter.

\newpage

# 12. Schéma PostgreSQL : `schema.sql`

Le schéma contient deux tables aux rôles différents :

| Table | Rôle | Clé principale |
|---|---|---|
| `raw_weather_payloads` | Réponse API brute et provenance | `id` identité |
| `daily_weather` | Faits météo quotidiens prêts à requêter | latitude + longitude + date |

La table brute a `fetched_at TIMESTAMPTZ`, l'URL et le JSON `JSONB`. La table métier utilise `DATE`, `NUMERIC` pour éviter de stocker les décimales météo en approximation flottante, un `TEXT` de fuseau, une référence vers le payload source et `loaded_at`.

La clé primaire composite exprime l'unicité attendue : au même lieu et pour une même date, une seule observation courante. `source_payload_id` permet de retrouver quel lot a fourni la valeur actuelle. Un index sur `observation_date` accélère les requêtes chronologiques courantes.

`CREATE TABLE IF NOT EXISTS` et `CREATE INDEX IF NOT EXISTS` rendent l'initialisation répétable. C'est un démarrage pratique, pas un système de migration : modifier une colonne déjà existante ne mettra pas automatiquement le schéma à niveau. Une suite de migrations versionnées serait préférable dès que le schéma évolue.

Les coordonnées sont `NUMERIC(8,5)`, suffisantes pour la précision de point visée ici; températures sont conservées à deux décimales. Le schéma ne stocke pas explicitement l'unité car les colonnes portent leur unité dans leur nom (`_c`, `_mm`, `_kmh`).

\newpage

# 13. `db.py` : chargement transactionnel et idempotence

`initialize(database_url)` ouvre une connexion et exécute le contenu de `schema.sql`. Le fichier est local au module grâce à `Path(__file__).with_name(...)`, ce qui évite de dépendre du répertoire courant. La connexion psycopg utilisée comme gestionnaire de contexte valide la transaction si tout réussit et la ferme ensuite.

`store_batch()` ouvre une autre transaction. Elle insère d'abord le JSON brut dans `raw_weather_payloads` et récupère son identifiant avec `RETURNING id`. Elle fait ensuite un `executemany` des lignes métier avec ce même identifiant.

Pour chaque date, `ON CONFLICT (latitude, longitude, observation_date) DO UPDATE` remplace les mesures, le fuseau, l'identifiant du payload et `loaded_at`. Relancer la même fenêtre ne crée donc pas de lignes métier en double : c'est le sens de l'idempotence côté faits. En revanche, une nouvelle ligne brute est créée à chaque exécution; l'historique brut est un journal des chargements, pas un stockage dédupliqué.

Toutes les insertions du lot brut et métier sont dans une transaction : si une ligne échoue, les écritures de ce lot sont annulées ensemble. `initialize()` est une transaction séparée; la création idempotente du schéma peut donc rester même si le chargement échoue. Il n'y a pas de suppression de l'ancien payload lors d'un upsert, ce qui conserve la traçabilité historique.

`psycopg` paramètre les valeurs SQL (`%s`) au lieu de construire du SQL par concaténation. Cela protège les valeurs, traite correctement le JSON et évite les problèmes de quoting.

\newpage

# 14. `pipeline.py` : l'ordre complet d'une exécution

La fonction `run(...)` est le scénario nominal, dans cet ordre :

1. Déterminer la fin de fenêtre (cinq jours avant la date courante dans le fuseau choisi) puis le début.
2. Écrire un log de démarrage avec les dates et le fuseau.
3. Appeler Open-Meteo via `fetch_weather`.
4. Convertir le JSON avec `transform`.
5. Faire échouer le traitement si `validate` détecte des anomalies.
6. Initialiser les tables et index avec `db.initialize`.
7. Écrire le payload et les lignes quotidiennes avec `db.store_batch`.
8. Journaliser le nombre de lignes chargées et retourner ce nombre.

L'ordre de l'étape qualité avant la base est intentionnel : un payload mal formé ne crée même pas une ligne brute dans la version actuelle. Après la validation, initialisation puis stockage, on ne logue le succès qu'une fois la transaction terminée.

Si le téléchargement ou la transformation échoue, l'échec remonte à la CLI et Python sort avec une erreur; Compose voit un code de sortie non nul. Le pipeline ne masque donc pas un échec comme une réussite. L'utilisateur choisit lui-même quand le relancer.

On pourrait préférer enregistrer aussi les payloads rejetés pour le diagnostic. Ce serait une évolution : elle exige une table d'audit/statut distincte afin de ne pas confondre payloads acceptés et rejetés.

\newpage

# 15. Pourquoi aucune mise à jour automatique?

Le pipeline n'a ni boucle, ni tâche cron, ni ordonnanceur dans Compose. Chaque appel à `python -m weather_pipeline` lance une seule ingestion puis le processus se termine. Démarrer PostgreSQL avec Compose ne déclenche pas le service d'ingestion; il faut demander explicitement le profil `run` ou lancer la commande Python.

Pourquoi retirer l'automatisation? Le besoin actuel est d'avoir un pipeline fiable et de laisser la personne décider quand télécharger/actualiser les données. Une tâche quotidienne introduirait des exécutions sans action explicite, ainsi que des problèmes de supervision, de panne et de reprise qui ne sont pas nécessaires à cette étape.

Lors d'une nouvelle exécution manuelle, la fenêtre glissante peut recouvrir les dates précédentes. L'upsert met alors à jour les lignes métier existantes au lieu de les dupliquer. En revanche, le JSON brut reçoit une nouvelle ligne par chargement : cela garde la trace des appels, même si l'utilisateur décide de relancer plusieurs fois.

Un ordonnanceur ou orchestrateur pourra être ajouté ultérieurement si le besoin change, mais il ne fait pas partie de la version actuelle.

\newpage

# 16. `compose.yaml` : services et profils

Compose décrit trois services :

* `db` démarre PostgreSQL 16 Alpine, initialise une base/un utilisateur de développement, expose le port 5432 et persiste les fichiers de base dans `postgres_data`.
* `pipeline` construit l'image applicative et est activé par le profil `run`. Il attend le healthcheck `pg_isready`, exécute une seule fois la commande, puis s'arrête. Aucun redémarrage automatique n'est configuré.
* `tests`, profil `test`, construit `Dockerfile.test`, fournit `TEST_DATABASE_URL` et attend la base pour le test d'intégration.

Le profil `run` permet d'expliciter l'ingestion; un simple `docker compose up` ne lance que PostgreSQL. Le service `db` n'a pas de profil et peut tourner seul. Les paramètres lieu/période sont des options CLI, pas des variables d'environnement Compose.

Le healthcheck est important : « conteneur lancé » ne veut pas dire « PostgreSQL accepte les connexions ». `depends_on: condition: service_healthy` évite de lancer l'application trop tôt. Il ne couvre pas une panne future de la base après le démarrage; l'application n'a pas de mécanisme de reconnexion durable.

Le volume survit à `docker compose down`. `docker compose down -v` l'efface. Le mot de passe et le port publiés sont adaptés au développement local, pas à une exposition réseau publique.

\newpage

# 17. Dockerfile applicatif et reproductibilité

`Dockerfile` part de `python:3.12-slim`, fixe deux variables pour ne pas écrire de bytecode et envoyer les logs immédiatement, crée `/app`, installe `requirements.txt`, copie le paquet puis crée l'utilisateur non privilégié UID 10001. L'absence de `USER root` pour le processus applicatif réduit les privilèges en cas de problème.

Le `CMD` lance un chargement manuel par défaut. Le paquet inclut `schema.sql` car le dossier `weather_pipeline/` entier est copié.

`Dockerfile.test` est séparé : il installe aussi les dépendances de test, copie `tests/` et `pytest.ini`, puis lance pytest. Copier `pytest.ini` permet à pytest de trouver `weather_pipeline` sur le chemin Python dans l'image, comme lors de `python -m pytest` localement.

`requirements.txt` fixe `psycopg[binary]` à la version 3.3.9. Le driver binaire évite de compiler l'extension PostgreSQL dans cette petite image. `requirements-dev.txt` inclut cette dépendance et épingle pytest. Les versions fixes rendent les installations comparables, mais ne remplacent pas un lockfile complet avec hash cryptographiques.

Le build utilise la version de base par tag, pas un digest immuable; l'image peut donc évoluer au fil du temps. Le projet ne comprend pas encore de scan de vulnérabilités, de SBOM ou de publication dans un registre.

\newpage

# 18. Inventaire de tous les fichiers du dépôt

| Fichier | Fonction |
|---|---|
| `README.md` | Démarrage rapide, commandes et résumé d'architecture |
| `.gitignore` | Exclut le venv, le bytecode et le cache pytest |
| `requirements.txt` | Dépendance de production : psycopg |
| `requirements-dev.txt` | Dépendances runtime et pytest |
| `pytest.ini` | Répertoire des tests et chemin d'import pytest |
| `Makefile` | Raccourcis `test`, `run`, `up`, `down` |
| `Dockerfile` | Image du service applicatif |
| `Dockerfile.test` | Image destinée à la suite de tests |
| `compose.yaml` | PostgreSQL, pipeline ponctuel, tests et volume |
| `.dockerignore` | Évite d'inclure caches, environnement virtuel et documentation dans les images |
| `weather_pipeline/__init__.py` | Marque le paquet Python |
| `weather_pipeline/__main__.py` | Options CLI et lancement manuel |
| `weather_pipeline/source.py` | Construction requête API, HTTP, reprises et JSON |
| `weather_pipeline/transform.py` | Dataclass et conversion JSON vers objets typés |
| `weather_pipeline/quality.py` | Contrôles métier avant le stockage |
| `weather_pipeline/pipeline.py` | Séquence d'ingestion exécutée une fois |
| `weather_pipeline/db.py` | Initialisation et écritures transactionnelles |
| `weather_pipeline/schema.sql` | Tables, clés, contraintes et index PostgreSQL |
| `tests/` | Fixtures, tests CLI/source/transform/qualité/PostgreSQL |
| `docs/GUIDE_COMPLET.md` | Source modifiable de ce guide PDF |
| `docs/GUIDE_COMPLET_PIPELINE_METEO.pdf` | Version PDF du guide |

`.venv/` et les caches ne doivent pas être versionnés. Il n'y a pas de fichier `.env.example` ni de `config.py`; les paramètres sont donnés au lancement. Les données téléchargées ne sont pas des fichiers de dépôt : elles sont dans PostgreSQL, et la réponse source est dans la colonne JSONB de la table brute.

\newpage

# 19. La stratégie de test

Les tests unitaires sont indépendants d'Internet et de PostgreSQL. `tests/conftest.py` fournit un payload déterministe de deux journées. Cela rend les résultats reproductibles même si l'API publique est indisponible ou change temporairement.

`test_transform_quality.py` vérifie la conversion, le nombre de lignes, les valeurs, les séries de longueurs différentes, les valeurs nulles, l'acceptation d'un lot correct, le rejet d'une température incohérente et le rejet d'un lot vide. `test_cli.py` teste les valeurs par défaut et le rejet d'options hors limites. `test_source.py` remplace `urlopen` par une fausse réponse et vérifie la construction de l'URL; le test ne part pas sur le réseau.

`test_db_integration.py` est le test d'intégration : si `TEST_DATABASE_URL` existe, il initialise le schéma, insère une observation, la recharge avec une température modifiée, puis vérifie que la clé n'a qu'une ligne et que l'upsert a modifié la valeur. L'observation et le payload de test sont supprimés à la fin. Sans variable, pytest l'ignore explicitement.

Commande locale : `python -m pytest -q`. Avec Docker : `docker compose --profile test run --build --rm tests`. Le test touche brièvement à la base configurée puis nettoie ses données; une base de test reste préférable à une base importante.

La suite actuelle vérifie aussi les validations CLI. Le test PostgreSQL est ignoré quand aucune base n'est disponible. Une récupération Open-Meteo réelle avait précédemment passé transformation et contrôles; ce test réseau manuel n'est pas une suite automatisée stable.

\newpage

# 20. Démarrer, exécuter, interroger

Avec Docker installé :

```bash
docker compose up -d db
docker compose --profile run run --build --rm pipeline
```

Le profil `run` effectue exactement un chargement puis le conteneur applicatif ponctuel est supprimé; PostgreSQL continue de fonctionner. Pour modifier le lieu ou la longueur de fenêtre dans Docker, lancer PostgreSQL puis passer les options au conteneur applicatif :

```bash
docker compose up -d db
docker compose --profile run run --rm pipeline python -m weather_pipeline \
  --database-url postgresql://weather:weather@db:5432/weather \
  --latitude 45.7640 --longitude 4.8357 --days 14
```

Pour exécuter les tests avec une base :

```bash
docker compose --profile test run --build --rm tests
```

Interroger quelques observations et les payloads bruts :

```sql
SELECT observation_date, latitude, longitude,
       temperature_min_c, temperature_max_c,
       precipitation_mm, wind_speed_max_kmh
FROM daily_weather
ORDER BY observation_date DESC
LIMIT 10;

SELECT id, fetched_at, source_url, payload->'daily' AS daily_data
FROM raw_weather_payloads
ORDER BY fetched_at DESC
LIMIT 3;
```

Directement en Python, créer un environnement virtuel, installer `requirements-dev.txt`, démarrer PostgreSQL et lancer `python -m weather_pipeline` (ajouter `--database-url` si nécessaire). La base doit déjà être accessible. La commande `make run` raccourcit le démarrage ponctuel; `make up` démarre seulement la base.

\newpage

# 21. Logs, erreurs et diagnostic

Les logs sont des lignes texte horodatées avec le niveau, le module et un message. Le scénario nominal produit au minimum un message de démarrage et un message de fin avec le nombre de lignes. Le client API émet un avertissement à chaque nouvelle tentative. Une erreur remonte au processus appelant, qui sort avec un code non nul.

Quelques diagnostics :

* **Connection refused PostgreSQL** : vérifier `docker compose ps`, l'état `healthy`, le port 5432 et le fait d'utiliser `db` depuis un conteneur mais `localhost` depuis l'hôte.
* **Open-Meteo ne répond pas** : vérifier DNS/réseau; la fonction fait trois tentatives réseau, puis échoue.
* **HTTP 400 / réponse API error** : inspecter latitude, longitude, dates, fuseau et paramètres; les erreurs de requête ne sont pas réessayées automatiquement.
* **TransformationError** : la forme ou une valeur du payload ne correspond pas au contrat attendu; le lot n'est pas écrit.
* **QualityError** : les données sont convertibles mais violent une règle de plage ou cohérence; comparer l'erreur aux unités source.
* **Erreur de contrainte SQL** : examiner le schéma, le payload et l'intégrité du lot; la transaction de `store_batch` est annulée.

Une observation rejetée n'est actuellement pas conservée dans `raw_weather_payloads`, puisque la qualité précède la connexion à la base. Pour investiguer durablement des réponses mauvaises, il faudrait enregistrer une tentative avec statut `received/rejected/loaded` et le motif, en séparant cet audit des faits validés.

Il n'y a pas encore d'indicateurs numériques, alertes, dashboards ou corrélation par identifiant d'exécution.

\newpage

# 22. Choix faits et alternatives écartées

| Choix actuel | Alternative | Pourquoi ce choix au départ? |
|---|---|---|
| API Open-Meteo sans clé | Source publique avec compte ou scraping | Démarrage rapide, pas de secret; un contrat JSON stable pour l'exercice |
| `urllib` synchrone | `requests` / `httpx` async | Une requête simple; limiter les dépendances et la complexité |
| Python + dataclass | Pandas / Spark | Quelques dizaines de lignes; pas de calcul distribué nécessaire |
| PostgreSQL | SQLite ou fichiers CSV | Besoin explicite d'une vraie base relationnelle, clés, contraintes, JSONB et transactions |
| Tables brut + métier | Une seule table finale | Garder la réponse originale pour audit/retransformation et une table propre pour SQL |
| Clé composite + upsert | Ajouter sans contrôle ou tout supprimer | Rejouer la fenêtre sans lignes métier doublonnées, tout en conservant les reprises brutes |
| Exécution manuelle, sans scheduler | Cron / Airflow / Prefect | Pas de mise à jour périodique demandée; garder le déclenchement explicite |
| Docker Compose local | Cloud/Kubernetes | Reproductible sur une machine, sans coût ni configuration de compte |
| Tests unitaires + un test DB | Tester uniquement par exécution manuelle | Valider les règles rapidement; prévoir un chemin d'intégration avec PostgreSQL |

Ces choix ne signifient pas que les alternatives sont mauvaises. Ils répondent à la taille actuelle. Si le nombre de sources, dépendances entre tâches, destinations et besoins d'observabilité augmente, il devient rationnel de réévaluer l'architecture.

\newpage

# 23. Limites et risques à connaître

1. **La base n'a pas été validée ici en conteneur.** Docker était absent pendant la réalisation. Le test d'intégration existe, mais doit être exécuté dans un environnement disposant de Docker ou PostgreSQL.
2. **Schéma sans migrations.** `IF NOT EXISTS` n'applique pas les changements de colonnes sur une table existante.
3. **Secrets de développement.** Compose contient un mot de passe fixe et publie PostgreSQL sur l'hôte. Ne pas utiliser tel quel sur un serveur partagé.
4. **Déclenchement manuel.** Le pipeline ne se met pas à jour seul; l'utilisateur doit décider quand relancer la commande.
5. **Aucun enregistrement des lots rejetés.** Utile pour l'audit et le support, mais pas encore implémenté.
6. **Couverture partielle.** Tests d'échecs HTTP, migrations, dates manquantes et rollback transactionnel à ajouter.
7. **Dépendance externe et unités.** La disponibilité, les conditions et le schéma d'API sont à surveiller; confirmer `daily_units` lors d'une évolution.

Être capable de nommer ces limites est une force en entretien : on montre une compréhension du niveau de maturité plutôt que de présenter un petit pipeline comme une plateforme haute disponibilité.

\newpage

# 24. Feuille de route : fiabiliser avant d'orchestrer/cloud

**Étape 1 — robustesse locale.** Lancer Compose manuellement plusieurs fois; valider les données, volumes et relances. Ajouter une base dédiée aux tests, migrations versionnées, tests de rollback, contrôle des dates attendues et unités explicites.

**Étape 2 — opérations.** Persister un registre des exécutions (début, fin, statut, dates, nombre de lignes, erreur), améliorer les retries HTTP avec `Retry-After` et jitter, ajouter une politique de rétention des payloads, des logs structurés JSON et une alerte sur échec ou retard. Empêcher les runs concurrents si nécessaire.

**Étape 3 — orchestrateur, si le besoin le justifie.** Un orchestrateur comme Prefect devient utile avec plusieurs flux, dépendances, reprises, historique, paramètres et notifications. Il faut lui confier l'ordonnancement et la visibilité, pas réécrire inutilement les transformations déjà testées.

**Étape 4 — cloud, après preuve locale.** Choisir d'abord un service managé adapté (base, conteneur, secrets, réseau, logs). Déplacer les identifiants vers un gestionnaire de secrets, restreindre les accès et sauvegarder PostgreSQL. Déployer l'image avec version/tag immuable et définir une stratégie de restauration. Le cloud ajoute des responsabilités; il ne corrige pas à lui seul un pipeline incorrect.

Le critère de passage n'est pas « le code marche sur mon poste une fois », mais des exécutions répétées et vérifiables, des échecs compris, des données contrôlées et une procédure de reprise documentée.

\newpage

# 25. Comment présenter et prendre en main le projet

Présentation possible : « Pour un projet personnel, j'ai créé un petit pipeline Python qui récupère à la demande des données météo publiques, les vérifie et les charge dans PostgreSQL. J'ai séparé les étapes pour pouvoir les tester, et j'utilise Docker Compose pour lancer la base localement. C'est une première version : elle n'a pas encore d'ordonnanceur ni de déploiement cloud. »

Pour l'apprendre, suis cet ordre dans le code : 1) `README.md` pour les commandes; 2) `__main__.py` pour les options CLI; 3) `pipeline.py` pour le scénario; 4) `source.py`; 5) `transform.py` puis `quality.py`; 6) `schema.sql` et `db.py`; 7) tests; 8) `compose.yaml` et Dockerfiles. Lance les tests unitaires, lis ensuite un payload simulé, puis observe une requête SQL.

Questions à te poser : que se passe-t-il si une colonne manque? Si la source révise une journée? Si PostgreSQL tombe entre l'insertion brute et le chargement métier? Pourquoi une nouvelle ligne brute apparaît à chaque run alors que la table finale garde une ligne? Quelles observations faudrait-il pour décider de Prefect?

Formulation CV possible : **« Projet personnel — réalisation d'un pipeline météo en Python avec PostgreSQL et Docker : récupération d'une API publique, transformation et vérification des données, tests et chargement rejouable. »** Je ne mentionne que les fonctions réellement présentes dans le projet.

\newpage

# 26. Glossaire et références

**API** : interface HTTP permettant à un programme de demander des données. **Payload** : corps de réponse transportant ces données. **ETL** : extraction, transformation, chargement. **JSON** : format texte structuré; **JSONB** : représentation JSON interrogeable de PostgreSQL. **Dataclass** : classe Python concise pour des objets de données. **Idempotence** : répéter une opération produit le même état métier final. **Upsert** : insertion ou mise à jour en cas de conflit. **Transaction** : groupe d'écritures validées ou annulées ensemble. **Healthcheck** : vérification qu'un service est prêt à répondre. **Orchestrateur** : outil qui planifie, suit et relie les exécutions de tâches.

Références utiles (les contrats externes peuvent évoluer) :

* Documentation API Open-Meteo, archives historiques : <https://open-meteo.com/en/docs/historical-weather-api>
* Documentation PostgreSQL, types JSON : <https://www.postgresql.org/docs/current/datatype-json.html>
* Documentation PostgreSQL, transactions : <https://www.postgresql.org/docs/current/tutorial-transactions.html>
* Documentation Docker Compose : <https://docs.docker.com/compose/>
* Documentation Python `zoneinfo` : <https://docs.python.org/3/library/zoneinfo.html>
* Documentation psycopg 3 : <https://www.psycopg.org/psycopg3/docs/>

**Résumé final :** la donnée suit le trajet source publique → JSON conservé → objets typés → contrôles métier → transaction PostgreSQL → requête SQL. Chaque fichier a une responsabilité identifiable; les tests vérifient les contrats locaux et le service Compose fournit la base. Le prochain travail utile est de lancer le test PostgreSQL dans un environnement Docker, puis d'observer plusieurs exécutions réelles avant d'ajouter des outils d'orchestration ou d'hébergement.
