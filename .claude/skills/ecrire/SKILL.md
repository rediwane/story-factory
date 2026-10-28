---
name: ecrire
description: Ecrire une video : le format complet d'une config pour src/engine/render.py (scenes, narration, elements dessines, mouvements, accroche, voix, sous-titres, filigrane), le rendu test, la relecture independante avant publication.
---

# Écrire une vidéo

Cette skill dit comment une histoire devient une config que le moteur rend. Elle ne dit
pas quelle histoire écrire, et ne le dira jamais : l'identité du compte est dans
`CLAUDE.md`, le reste est laissé à celui qui écrit.

## La config

Un fichier `configs/<name>.json`. Toutes les clés ont une valeur par défaut dans
`src/engine/render.py` (`DEFAULTS`) ; seules celles qui changent s'écrivent.

| clé | rôle |
|---|---|
| `name` | nom de la vidéo, celui du mp4 |
| `voice`, `voice_length` | modèle piper du narrateur (`langue_REGION-nom-qualité`), vitesse (1.0 normal, plus grand = plus lent) |
| `hook_text` | l'accroche, écrite en haut de l'image et lue en premier ; vide = pas d'accroche |
| `hook_voice` | `false` pour l'afficher sans la lire |
| `bg` | couleur de fond `[r, g, b]` ; une scène peut avoir la sienne |
| `subtitles`, `sub_words`, `sub_y`, `sub_size` | sous-titres de la narration, nombre de mots par morceau, position, taille |
| `watermark` | nom du compte en filigrane, presque transparent |
| `scene_pause_s`, `end_hold_s` | pause après chaque narration, tenue de la dernière image |
| `persist` | éléments présents pendant toute la vidéo (décor) |
| `scenes` | la suite des scènes |

Une **scène** : `narration` (le texte lu, et sous-titré), `elements` (ce qui est dessiné),
et au besoin `pause_after`, `min_s`, `bg`, `voice`. Sa durée est celle de sa narration
plus la pause ; la première scène commence pendant l'accroche.

Un **élément** :

| clé | rôle |
|---|---|
| `type` | `circle`, `ellipse`, `rect`, `poly`, `line`, `text` |
| `x`, `y` | position, en fraction de la largeur et de la hauteur de l'image |
| `r`, `w`, `h` | taille, en fraction de la largeur |
| `points` | pour `poly` et `line` : sommets relatifs à `(x, y)`, en fraction de la largeur |
| `text`, `size`, `stroke` | pour `text` : le texte, sa taille, son contour |
| `color`, `outline`, `width` | couleur de remplissage, contour, épaisseur |
| `t0`, `t1` | apparition et disparition, en secondes depuis le début de la scène |
| `fade` | durée du fondu d'entrée et de sortie |
| `to`, `move`, `ease` | propriétés à atteindre (`x`, `y`, `r`, `w`, `h`, `size`, `angle`, `scale`), fenêtre du mouvement `[début, fin]`, courbe (`inout`, `in`, `out`, `linear`) |
| `bob`, `bob_s` | petite oscillation verticale, amplitude et période |
| `angle`, `scale` | rotation en degrés, échelle |
| `z` | ordre de dessin |

Un personnage ou un objet composé se fait en plusieurs éléments qui bougent ensemble.
Si le moteur ne sait pas dessiner ce qu'une histoire demande, on l'étend dans
`src/engine/` : une fonction de plus, testée sur `tests/rendu_test.json`, sans casser
les configs existantes.

## La narration et l'accroche

- La narration est lue mot pour mot ; elle s'écrit pour l'oreille : phrases courtes, un
  événement par phrase, pas de parenthèses.
- Les sous-titres découpent la narration aux ponctuations : une ponctuation bien placée
  fait un sous-titre lisible.
- L'accroche est une vraie question ou une promesse que la vidéo tient jusqu'au bout.
  Jamais une accroche déjà utilisée (vérifier `hook_text` dans `history.json`).
- Ce que la voix dit et ce que l'image montre avancent ensemble : une image fixe sous
  une longue narration fait décrocher.

## Rendu test

`--simulate` d'abord : il synthétise les voix et donne la durée de chaque scène, sans
encoder. Puis le rendu, et des images extraites avec ffmpeg (la première, une toutes les
2 à 3 secondes, la fin) : l'accroche ne cache pas la scène, les sous-titres sont lisibles
sur téléphone, rien ne déborde de l'image.

## Relecture

Avant publication, la vidéo est confiée à un agent séparé (outil Agent) qui ne l'a pas
écrite. On ne lui donne ni la config, ni l'intention de l'auteur : seulement l'objectif
du compte (des vues, donc du temps de visionnage), les images extraites et le texte de
la narration dans l'ordre. Sa question décisive : un inconnu qui tombe sur cette vidéo
reste-t-il jusqu'au bout, et a-t-il envie de la commenter ou de la partager ? Il dit à
quel moment il aurait décroché, si l'identité du compte est tenue, et si la fin se
devinait. Verdict : passe ou recalée, avec ses raisons, dans `notes`. Une vidéo recalée
est retravaillée ou remplacée ; un créneau ne reste jamais vide.
