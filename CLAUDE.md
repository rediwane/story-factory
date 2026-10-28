# story-factory

Deuxième système autonome du propriétaire : un compte TikTok qui publiera chaque jour
des histoires racontées par une voix, sur des dessins simples animés, produites,
publiées, mesurées et améliorées sans intervention humaine, via Metricool.

La méthode vient d'un premier compte du propriétaire, qui tourne déjà seul (dépôt
`rediwane/bouncefactory`). Ce compte-ci est aussi **un test de cette méthode** : savoir
si elle trouve un format qui marche quand on part de zéro, dans une autre niche. Rien
de l'autre compte ne s'utilise ici : ni son personnage, ni ses thèmes, ni son nom.

## État du projet — à lire en premier

**Phase 0 : la base est posée, rien n'est publié.** Le 28/10/2026 : dépôt créé, moteur
de rendu écrit et testé (`src/engine/`), règles et skills en place. Aucun compte
TikTok n'est encore branché, aucune routine planifiée n'existe.

Décidé par le propriétaire :
- le genre : des **histoires**, racontées par une voix de synthèse, sur des dessins
  simples animés ;
- à terme, la même routine que l'autre compte : des vidéos générées chaque matin et
  programmées via Metricool ;
- aucun lien public avec l'autre compte ;
- (28/10) l'identité repose sur **un personnage récurrent**, simple et reconnaissable
  d'un coup d'œil, qui raconte des histoires et peut aussi expliquer des choses réelles
  (faits vérifiés), avec **une signature formelle forte** et constante (palette, mise
  en scène, ton). Le personnage lui-même reste à choisir ;
- (28/10) **la langue : l'anglais.** Une version dans une autre langue, plus tard, serait
  un autre compte.

À trancher par le propriétaire, dans cet ordre, avant toute routine :
1. **L'identité** (direction choisie, voir plus haut ; reste le personnage, son ton et sa signature) : ce qui rend le compte reconnaissable au premier coup d'œil, en plus
   du genre (qui raconte, ce qui revient d'une vidéo à l'autre, le ton, le style visuel,
   la voix). C'est la décision la plus importante : un compte d'histoires sans identité
   est indistinguable de mille autres.
2. ~~La langue~~ : tranchée, l'anglais.
3. **La voix** : les voix piper gratuites suffisent pour un prototype ; une voix plus
   naturelle peut demander un service payant.
4. **Le nom du compte** (filigrane) et sa création sur TikTok, à la main ; la nouvelle
   marque dans Metricool (son `brandId` va dans les skills `publier` et `mesure`).
5. **Le protocole du test** : sa durée (cinq à six semaines) et le seuil qui dira si la
   méthode a marché, fixés **avant** la première vidéo.

Ensuite, dans l'ordre :
1. cinq ou six vidéos prototypes faites en session avec le propriétaire, qu'il valide ;
2. l'écriture de l'identité retenue dans ce fichier, et `era_start` dans `history.json` ;
3. les premières publications, une ou deux par jour la première semaine (un compte
   neuf qui publie en rafale par un outil tiers est freiné plus facilement), puis la
   cadence pleine ;
4. la tâche planifiée du matin, puis, quand l'historique le permet, un juge à part.

Une session qui reprend le projet commence par cette section, propose, et laisse le
propriétaire trancher. Quand une décision est prise, elle s'écrit ici et la liste se
met à jour.

## Objectif

**Faire des vues.** Tout le reste est un moyen. **Ce qui fait les vues, c'est le temps
de visionnage** : TikTok pousse ce que les gens regardent longtemps. Tout se juge à
cette question : pourquoi quelqu'un resterait jusqu'à la fin, et pourquoi il ne
partirait pas dans les premières secondes ? Une vidéo indistinguable de dix autres de
la niche est un échec, quels que soient ses chiffres.

## Identité — à écrire quand le propriétaire l'aura choisie

Vide pour l'instant, volontairement. Rien ne s'y écrit sans décision du propriétaire.

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
| `src/engine/` | le moteur : `render.py` (rendu), `voice.py` (voix, mixage) | — |
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

- **Une seule langue** pour tout le compte, celle que le propriétaire aura choisie.
- **Rien qui tombe sous les règles communautaires TikTok** (argent, jeux d'argent,
  armes, drogues, actes dangereux, sexe, désinformation). Une vidéo retirée passe
  `removed` et son thème est revu avant toute nouvelle vidéo.
- **Contenu généré par IA** : le compte respecte les règles de TikTok sur l'étiquetage
  du contenu généré par IA.
- **Aucune musique ni son sous droits** dans le dépôt ou dans les vidéos.
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
