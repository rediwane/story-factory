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

**Phase 2 : le format liste est trouvé ; on industrialise sa fabrication.**

- 28/10/2026 : dépôt créé pour un second compte d'histoires sans lien avec Bounce.
- 31/10/2026, décidé par le propriétaire : pas de second compte, les histoires ont Bounce
  pour héros et sortent sur @bouncefactory0. Narrateur : Kokoro `am_fenrir`. Trois
  prototypes rejetés (des formes déplacées comme des diapositives, puis une simulation
  commentée : « le même format en moins bien »).
- 31/10/2026 : **le format liste**, choisi par le propriétaire : une accroche, six
  situations courtes en simulation physique réelle, chacune avec sa chute, la sixième qui
  retourne la série, une minute. Première vidéo publiée le soir même : bien au-dessus de
  la médiane du compte, 41 % de durée moyenne regardée, 29 % de visionnage complet, et la
  seule vidéo du compte à recevoir l'« Additional Reward » de TikTok (RPM environ dix fois
  celui des autres). Défaut mesuré : 43 % des spectateurs partent avant 6 s.
- 01/11/2026 : deuxième liste publiée ; décidé par le propriétaire : **ce que l'auteur
  apprend ne reste pas dans sa tête**. Les règles vont dans les skills `ecrire` et
  `juger`, les vérifications mesurables dans `src/tools/controle.py`, pour qu'un run sans
  session produise une vidéo que le propriétaire n'a rien à reprendre. Le circuit : le
  contrôle automatique avant et après rendu, puis trois juges indépendants.

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
- **Le format liste** : une accroche, six situations courtes en simulation physique
  réelle, chacune avec sa chute, la sixième qui retourne la série, 60 à 66 secondes, la
  première chute avant 6 secondes. Le détail est dans la skill `ecrire`.
- **Rien d'immobile** : jamais 1,5 seconde sans mouvement, aucune présentation avant
  l'action.
- **La mémoire de l'auteur ne compte pas** : tout défaut trouvé par un juge ou par le
  propriétaire devient, dans le même commit que sa correction, une vérification dans
  `src/tools/controle.py` ou une règle dans une skill.

À trancher par le propriétaire :
1. **La part des créneaux** : combien de listes par jour sur les cinq créneaux du compte.
2. **L'automatisation** : la routine qui écrit, contrôle, fait juger et publie une liste
   chaque nuit (architecture à plusieurs routines décrite en session le 31/10 : un
   gérant qui attribue les créneaux, une routine par format, un juge commun).
3. **YouTube Shorts et Instagram Reels** : comptes à créer et relier à Metricool.

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
| `src/engine/` | `voice.py` (narrateur Kokoro, mixage), `bounce.py` (le personnage, repris de bouncefactory) ; `render.py`, le premier moteur à diapositives, n'est plus utilisé | — |
| `src/sim/` | `base.py` (simulation, voix, rendu, repris de bouncefactory et étendu au narrateur), `chapters.py` (les chapitres enchaînés), `listkit.py` (la base d'un chapitre et son contrat) | — |
| `src/stories/` | une liste par fichier | le run |
| `src/tools/controle.py` | le juge automatique, avant et après rendu | — |
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
| `ecrire` | écrire | le sujet, la structure, les règles d'image, de son et de rythme, le script, le réglage |
| `juger` | juger | le contrôle automatique, les trois juges, le verdict, l'apprentissage du circuit |
| `publier` | publier | hébergement du mp4, post Metricool, créneaux |
| `mesure` | mesurer | champs Metricool, rapprochement avec `history.json`, `daily` |
| `veille` | hebdo | hashtags du moment, frontière des formats saturés de la niche |

Ce fichier suffit à mener un run ; les skills ajoutent le détail technique, jamais une
règle nouvelle.
