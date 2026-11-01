---
name: ecrire
description: Ecrire une video liste de Bounce de A a Z - choix du sujet, structure en six chapitres, script sur src/sim/listkit.py, regles d'image, de son et de rythme apprises des videos precedentes, reglage jusqu'a ce que le controle automatique ne trouve plus rien. A suivre avant la skill juger.
---

# Écrire une vidéo liste

Une liste est une vidéo d'une minute : une accroche, six situations courtes jouées en
simulation physique réelle, chacune avec sa chute, et la sixième qui retourne la série.
Cette skill dit comment l'écrire pour qu'elle passe les juges du premier coup. Elle ne
dit pas quel sujet choisir. Chaque règle ci-dessous vient d'un défaut qui a fait recaler
une vidéo ou partir des spectateurs ; le contrôle automatique (`src/tools/controle.py`)
en vérifie la plupart, la skill `juger` le reste.

## 1. Le sujet

- Une liste de six situations du même genre, que Bounce essaie l'une après l'autre ;
  les cinq premières ratent à cause de ses rebonds, la sixième réussit grâce à eux.
- Le test de nouveauté : le sujet ne doit décrire aucune liste sortie dans les 14
  derniers jours (`themes[]` de ce dépôt), et aucune situation ne doit reprendre un thème
  de simulation sorti dans les 14 derniers jours (`themes[]` de `bouncefactory`).
- Le retournement ne doit pas être celui que les commentaires de la liste précédente ont
  deviné ou réclamé : s'ils l'ont écrit, le spectateur l'attend.
- L'accroche : une question de deux à six mots qui nomme Bounce, jamais déjà utilisée
  (le contrôle la cherche dans les historiques des deux dépôts).

## 2. La structure et le rythme

| règle | valeur |
|---|---|
| durée totale | 60 à 66 s |
| première chute | avant 6 s : la moitié des spectateurs partent dans les six premières secondes |
| un chapitre | 5,5 à 12,5 s ; la chute au moins 2 s après la coupe |
| répliques du narrateur par chapitre | le titre dès la coupe, au plus une phrase de mécanique avant la chute, une phrase après |
| titre de chapitre à l'écran | le rang et le nom, en capitales (la progression retient) |

- **Rien avant l'action.** L'image 0 montre Bounce déjà en l'air et l'objet du premier
  chapitre déjà menacé. Pas de phrase de présentation : l'accroche nomme Bounce, l'image
  montre qui il est.
- **La voix annonce, l'image tranche.** Le titre est dit avant la chute ; la phrase de
  chute vient après le tampon, jamais à sa place.
- **Une phrase ne déborde jamais sur le chapitre suivant**, et la coupe attend la fin de
  la phrase et de la réplique de Bounce (le moteur le fait ; ne pas le contourner).
- **Les chutes ne tombent pas toutes au même instant** de leur chapitre : trois de suite
  au même moment, et le spectateur apprend la recette (le contrôle le mesure).
- **La phrase du milieu ne dévoile pas la chute** et ne décrit pas l'image : elle installe
  une ironie que la chute retourne. Le titre seul dit le lieu.
- **Chaque chapitre a sa mécanique.** Deux chapitres d'une même vidéo ne tombent pas de
  la même façon : deux tours qui s'effondrent sont une seule mécanique.
- **Le gag se comprend sans le son.** La cause (ses rebonds) et la conséquence se voient.
  Si la chute repose sur une règle que l'image ne montre pas d'elle-même (un score, un
  camp, une limite), un élément visible la montre : un tableau, une couleur, une ligne.
- **La réplique de Bounce** : une par vidéo au plus, en réponse à une question explicite
  du narrateur (la phrase finit par « ? »), dans la scène de la question, avant la coupe,
  seule : aucun autre mot de Bounce autour (le moteur réserve sa place). Ailleurs il ne dit son nom
  qu'à ses rebonds.
- **Après la chute, la scène vit** : Bounce continue de rebondir (plus bas, sous le
  tampon), les débris roulent et s'arrêtent, un personnage réagit. Jamais 1,5 s d'image
  immobile : un Bounce posé sur un décor fixe, c'est une image morte.

## 3. L'image

- **Nuit partout**, fond sombre, une source de lumière par scène autant que possible. Un
  éclair (flash, explosion) reste bref et gris, jamais un plein écran blanc.
- **Formes primitives**, personnages sans visage, rien d'illustré : si une chose a besoin
  de détails pour se lire, c'est le mauvais objet.
- **Bounce grand et franc** : rayon d'au moins 60 px, sauts d'au moins deux diamètres,
  dans le tiers inférieur de l'image mais jamais sous les sous-titres au moment d'une chute.
- **La chute se joue hors de l'interface TikTok** : la colonne des boutons à droite et la
  légende en bas recouvrent l'image (`listkit.ZONES_UI`). L'objet de la chute est déclaré
  par `focus()` et le contrôle le place.
- **Ce qui fait le gag se voit sur un téléphone** : objets clairs sur fond de nuit, assez
  grands (une pièce, un oiseau : au moins 80 px), jamais une silhouette noire sur un ciel
  sombre. Rien qui se lise comme un logo ou une marque.
- **La cause se voit.** Si Bounce ne touche pas l'objet, la transmission est montrée : la
  table tremble, la tour vacille dès l'image 0.
- **Tout reste dans le cadre** : Bounce, les objets qui tombent, les éclaboussures, le
  point d'impact. Sortir du cadre n'est permis que si c'est le gag (`exit_ok`).
- **Rien ne se téléporte ni ne pivote d'un coup** : un objet qui tombe rebondit, glisse et
  se couche progressivement (`listkit.settle_body`, avec les sommets réels de sa forme,
  saillies comprises, sinon il s'enfonce dans le sol) ; les objets qui
  bougent sont déclarés par `bodies()` et le contrôle suit chacun d'une image à l'autre.
- **Deux objets libres ne se traversent pas** (cartes, wagons, débris) : `bodies()` donne
  leur polygone, `listkit.separate()` les écarte doucement à chaque pas, le contrôle mesure.
  Leur vitesse latérale est bornée (frottement), sinon les chocs les projettent hors du décor.
- **Rien ne traverse un solide.** Tout objet que Bounce peut toucher a une collision
  réelle **dès la première image**, pas seulement au moment scripté de la chute, et figure
  dans `solids()`. Les personnages en font partie. Un objet qui doit tomber à cause de lui
  tombe parce qu'il le touche ou parce que ses retombées le secouent, jamais parce que le
  temps est écoulé.
- **Le tampon et les sous-titres ne couvrent jamais Bounce ni l'objet de la chute** :
  choisir `stamp_y` pour chaque chapitre selon où se joue sa chute.
- **Rien n'apparaît d'un coup** : un objet qui entre en scène (un tirage, un cadre, un
  personnage) arrive en mouvement ou en fondu, jamais en une image.
- Les décors des chapitres d'une même vidéo se distinguent au premier coup d'œil
  (couleur dominante, lieu).

## 4. Le son

- Les deux voix seulement : le narrateur (Kokoro `am_fenrir`) et Bounce, au même niveau.
- Bounce se tait pendant que le narrateur parle, et un mot n'est dit que s'il tient entier
  avant la phrase suivante et avant la fin (le moteur le garantit, le contrôle le vérifie).
- **On entend Bounce dans chaque chapitre, et sur le rebond qui fait la chute** : la phrase
  qui suit la chute attend que son mot soit fini (environ 0,9 s après la chute ; le
  contrôle le vérifie).
- **Seul l'atterrissage de Bounce le fait parler** : la chute d'un objet est un `event`,
  jamais un `hit`.
- `end_hold_s` laisse à sa réaction finale le temps d'être dite entière.
- Jamais plus de 1,6 s sans voix.

## 5. Le script

- Un fichier `src/stories/<sujet>.py` : un chapitre par classe, sur `src/sim/listkit.py`
  (son en-tête décrit le contrat : `setup`, `on_land`, `after`, `snapshot`, `draw`,
  `solids`, et les attributs `title`, `stamp`, `stamp_y`, `mood`, `hold_s`, `exit_ok`) ;
  `CHAPTERS` et `Sim(StorySim)` en bas, comme les listes existantes.
- Une config `configs/<name>.json` : `name`, `theme`, `seed`, `hook_text`.
- Les réglages qui décident du moment des chutes sont dans `DEFAULTS`, pour pouvoir les
  ajuster sans réécrire les chapitres.

## 6. Le réglage

1. `python3 src/tools/controle.py configs/<name>.json` : il simule, place les voix,
   vérifie les règles mesurables et estime le mouvement de l'image (ouverture, images
   figées) sans rendre. On corrige le script, les réglages ou la graine jusqu'à
   zéro défaut bloquant. On ne rend rien avant.
2. Le rendu : `python3 src/stories/<sujet>.py configs/<name>.json` (environ dix minutes).
3. `python3 src/tools/controle.py configs/<name>.json --post` : mouvement, nuit,
   silences, durée, et les planches pour les juges dans `output/controle_<name>/`.
   Zéro défaut bloquant, sinon retour à l'étape 1.
4. Les juges : skill `juger`.
