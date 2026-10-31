# story-factory

Le **format histoire** du compte TikTok **@bouncefactory0** (Metricool `brandId 7069324`,
fuseau Europe/Paris) : des histoires courtes racontées par une voix off, sur des dessins
simples animés, dont le héros est Bounce, le personnage du compte. Il tourne **en
parallèle** du format de simulation physique du dépôt `rediwane/bouncefactory`, sur le
même compte, et partage ses créneaux.

La méthode vient de ce premier dépôt, qui tourne déjà seul. Ce qui est propre à ce
format est ici ; ce qui est au personnage (son dessin, sa voix, son mot unique) est
repris à l'identique de `bouncefactory` dans `src/engine/bounce.py`, jamais réinventé.

## État du projet — à lire en premier

**Phase 1 : prototypes en session, rien n'est encore publié par ce dépôt.**

- 28/10/2026 : dépôt créé pour un second compte d'histoires sans lien avec Bounce ;
  moteur de rendu écrit et testé (`src/engine/`), règles et skills en place.
- 31/10/2026, décidé par le propriétaire : **le dépôt change de but**. Pas de second
  compte : les histoires ont Bounce pour héros et sortent sur @bouncefactory0, comme
  nouveau format à côté des simulations. Raisons : partir de 10 000 abonnés et d'un
  visage connu plutôt que de zéro ; la narration est le format de rétention le plus
  solide ; le personnage est l'actif à construire (attachement, commentaires, suite).
  **Voix du narrateur : Kokoro, voix `am_fenrir`** (`src/engine/voice.py`). Langue :
  l'anglais, celle du compte. Premier prototype rendu le jour même
  (`configs/lighthouse_20261031.json`), relu, montré au propriétaire, non publié : jugé trop lent, Bounce trop fort dans le
  mix, histoire pas assez intéressante. Deuxième prototype choisi par le propriétaire
  parmi trois pitchs : le championnat de bowling (`configs/bowling_20261031.json`).

Décidé, et qui ne se rediscute pas sans le propriétaire :
- **Bounce ne dit jamais que son nom**, de sa voix du premier compte ; le narrateur
  parle, lui répond « Bounce ». C'est le gag qui traverse toutes les histoires.
- **Le visuel reste celui du compte** : géométrie simple sur fond sombre, Bounce dessiné
  par le code commun, les autres personnages sans visage, le nom du compte en filigrane,
  aucun détail illustratif (tout ce qui n'est pas Bounce se fait en formes primitives).
- **Bounce se met lui-même dans le pétrin** : l'histoire part d'une situation qu'il
  suffirait de régler en restant assis, et il ne reste jamais assis.
- **Une accroche** écrite en haut et lue en premier ; sous-titres de la narration.
- **Aucun son hors les deux voix** : ni musique, ni bruitage. Sous la narration, Bounce
  se tait ; ses répliques sont rares et pleines, ses mots de saut discrets.
- **La chute change d'une histoire à l'autre.** Le mot unique en réponse à une question
  est un ressort, pas la fin obligée : certaines histoires finissent sur une image, un
  geste, une conséquence, sans qu'il parle. Deux histoires qui tombent sur la même chute
  apprennent la recette au spectateur.
- **Rien d'immobile** : aucun plan de plus de trois secondes sans mouvement, quelque chose
  bouge à chaque seconde, les histoires visent 40 à 45 secondes.

À trancher par le propriétaire, après les prototypes :
1. **Le ton du narrateur** (conte qui prend Bounce au sérieux, ou commentateur agacé)
   et **le monde** des histoires (celui des thèmes de simulation, ou le sien).
2. **La part des créneaux** : le compte ne distribue pas plus de 5 vidéos par jour ;
   combien reviennent aux histoires, et à partir de quand.
3. **Le protocole du test** : combien d'histoires, comparées à quoi (la médiane M du
   compte, lue dans le `history.json` de `bouncefactory`), et le seuil qui dira si le
   format entre dans la routine quotidienne.
4. Quand il y entre : la routine du matin de ce dépôt (ou son intégration dans celle de
   `bouncefactory`), et le juge.

Une session qui reprend le projet commence par cette section, propose, et laisse le
propriétaire trancher. Quand une décision est prise, elle s'écrit ici et la liste se
met à jour.

## Objectif

**Faire des vues.** Tout le reste est un moyen. **Ce qui fait les vues, c'est le temps
de visionnage** : TikTok pousse ce que les gens regardent longtemps. Tout se juge à
cette question : pourquoi quelqu'un resterait jusqu'à la fin, et pourquoi il ne
partirait pas dans les premières secondes ? Une vidéo indistinguable de dix autres de
la niche est un échec, quels que soient ses chiffres.

## Identité

Celle du compte @bouncefactory0, telle que son `CLAUDE.md` la fixe (Bounce, son visage,
sa couleur, sa voix, son mot unique, le fond sombre, la géométrie simple, le filigrane,
l'anglais), plus ce que ce format ajoute : un narrateur (Kokoro `am_fenrir`) qui raconte,
des sous-titres, des scènes qui s'enchaînent. Ce qui reste à choisir est dans l'état du
projet ; rien d'autre ne s'écrit ici sans décision du propriétaire.

## Ce que les instructions ne contiennent jamais

1. **Aucun exemple** — ni histoire, ni accroche, ni personnage, ni hashtag — dans aucun
   fichier que le run relit (ce fichier, les skills). Un exemple écrit devient un aimant :
   on le reprend au lieu de chercher. Même présenté comme contre-modèle.
2. **Aucune description de la forme attendue** d'une histoire : c'est un exemple
   déguisé en critère.
3. **Aucun chiffre d'état du compte** (vues, abonnés). Les seuils sont relatifs à la
   médiane, lue dans `history.json`.

## Le moteur

```bash
which ffmpeg || (apt-get update && apt-get install -y --no-install-recommends ffmpeg)
pip install -r requirements.txt
python3 src/tools/coherence.py                                # sort en 1 si incohérence

python3 src/engine/render.py configs/<name>.json --simulate   # durées, sans encodage
python3 src/engine/render.py configs/<name>.json              # -> output/<name>.mp4
```

Une vidéo = une config `configs/<name>.json` : scènes, narration de chaque scène,
éléments dessinés et leurs mouvements, accroche, voix, couleurs. Le format complet est
dans la skill `ecrire`. Le moteur ne choisit rien à la place de l'histoire. Les voix
piper se téléchargent au premier rendu. `tests/rendu_test.json` est un test technique
du moteur, sans contenu : il ne sert pas de modèle.

## Fichiers

| fichier | contenu | écrit par |
|---|---|---|
| `CLAUDE.md` | l'état du projet, les règles | le propriétaire |
| `.claude/skills/*/SKILL.md` | le détail technique de chaque étape | le propriétaire |
| `history.json` | `_schema`, `era_start`, `videos`, `themes`, `daily`, `veille`, `notes` | le run |
| `configs/`, `captions/` | recettes et captions des vidéos, versionnées | le run |
| `output/` | les mp4, le temps de publier ; **jamais versionnés** | le run |
| `src/engine/` | le moteur : `render.py` (rendu), `voice.py` (narrateur, mixage), `bounce.py` (le personnage, repris de bouncefactory) | — |
| `src/tools/coherence.py` | détecteur d'incohérences | — |

`history.json → videos[]`, une entrée par vidéo produite : `name, date, theme, config,
role, hook_text, duration_s, hashtags, caption, slot, scheduled_time, media_url,
metricool_post_id, post_url, status, stats {views_24h, views_48h, views, likes,
comments, shares, measured_at}`. `themes[]` : une entrée par thème, c'est-à-dire une
forme d'histoire qui se décrit en une phrase (`name, description, state, created`).
`era_start` : la date de la première vidéo publiée ; rien d'antérieur ne compte.

## La méthode, à appliquer quand la routine démarrera

Ce qui a été appris sur l'autre compte, et qui vaut ici sans rien imposer de la forme :

- **La routine du matin** : nettoyer (`coherence.py`, rapprocher les posts de la veille
  avec Metricool), mesurer (skill `mesure`), juger, choisir les vidéos du jour, les
  écrire (skill `ecrire`), les rendre, les relire, les publier (skill `publier`),
  consigner et pousser sur `main`. Une fois par semaine, la veille (skill `veille`).
- **Les seuils** sont relatifs à la médiane M des vues à 48 h depuis `era_start` : une
  vidéo réussit loin au-dessus, échoue loin en dessous. Aucun verdict avant une dizaine
  de vidéos mesurées.
- **La nouveauté est la valeur** : un thème fait ses meilleures vues le jour où il sort.
  Une copie ne se joue que derrière une réussite, et seulement tant qu'elle tient.
- **Le test de nouveauté** ne regarde que les 14 derniers jours.
- **La relecture indépendante** : avant d'être publiée, chaque vidéo est jugée par un
  agent séparé qui ne l'a pas écrite, sur les images et le son seuls d'abord, avec la
  question de l'objectif. L'auteur ne valide jamais seul sa propre vidéo.
- **La fin ne se devine pas** : ni son moment, ni son issue.
- **Le run suit à la lettre ce qui se mesure** et contourne ce qui ne se mesure pas :
  un critère important qui ne se vérifie pas par un chiffre se vérifie par la relecture.
- **Le regard du propriétaire et les commentaires des spectateurs** ont donné les
  meilleures règles de l'autre compte. Ils passent avant toute métrique.
- **Ne pas changer plusieurs règles à la fois** : sinon on ne sait plus laquelle a agi.

## Contraintes

- **Une seule langue** pour tout le compte : l'anglais.
- **Rien qui tombe sous les règles communautaires TikTok** (argent, jeux d'argent,
  armes, drogues, actes dangereux, sexe, désinformation). Une vidéo retirée passe
  `removed` et son thème est revu avant toute nouvelle vidéo.
- **Contenu généré par IA** : le compte respecte les règles de TikTok sur l'étiquetage
  du contenu généré par IA.
- **Aucune musique, aucun bruitage, aucun son sous droits** : les deux voix sont tout l'audio.
- Erreur bloquante : ne rien publier ce jour-là, l'écrire dans `notes`.

## Skills

| skill | étape | contenu |
|---|---|---|
| `ecrire` | écrire | le format d'une config, ce que le moteur sait dessiner, le rendu test, la relecture |
| `publier` | publier | hébergement du mp4, post Metricool, créneaux |
| `mesure` | mesurer | champs Metricool, rapprochement avec `history.json`, `daily` |
| `veille` | hebdo | hashtags du moment, frontière des formats saturés de la niche |

Ce fichier suffit à mener un run ; les skills ajoutent le détail technique, jamais une
règle nouvelle.
