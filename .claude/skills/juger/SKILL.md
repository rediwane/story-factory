---
name: juger
description: Juger une video liste avant publication - le controle automatique, puis trois juges independants (l'inconnu sans le son, la facture, le rythme et le son), leurs consignes exactes, la regle de verdict, et ce qu'on fait d'un defaut qu'un juge trouve et que le controle n'a pas vu.
---

# Juger une vidéo liste

L'auteur ne juge jamais seul sa vidéo, et le propriétaire ne doit rien trouver à redire
sur une vidéo qui a passé ce circuit. Il a quatre étages ; une vidéo n'est publiable que
si les quatre disent oui.

## 0. Le contrôle automatique

`python3 src/tools/controle.py configs/<name>.json --post` sort en 0. Il a produit dans
`output/controle_<name>/` : `controle.json` (chapitres, débuts, chutes, répliques avec
leurs instants), `planche.png` (une image toutes les 2 s), `ouverture.png` (les trois
premières secondes), `chute_<n>.png` (neuf images autour de chaque chute), `coupe_<n>.png`
(cinq images autour de chaque coupe). Les juges travaillent sur ces fichiers et sur le mp4.

## Les trois juges

Trois agents séparés (outil Agent), lancés **en même temps**, qui n'ont pas écrit la
vidéo. On leur donne l'objectif du compte, l'identité de Bounce en trois lignes (une
balle rose au visage blasé, qui dit son nom à ses rebonds et réagit d'un mot à la fin de
la vidéo, « Yes! » ou « Oh no. » selon l'issue, comme dans toutes les vidéos du compte ;
qui n'arrête jamais de rebondir et se met tout seul dans le pétrin), le chemin du mp4 et
des planches. On ne leur donne pas
l'intention de l'auteur. Chacun rend : PASSE ou RECALÉE, puis ses défauts classés
**bloquant** ou **mineur**, chacun avec son instant et ce qu'il voit.

### Juge 1 : l'inconnu, sans le son

Il reçoit les planches et le mp4 mais **ni la narration, ni le script** ; il ne lit pas
l'audio. Il répond :
- dans les trois premières secondes, qu'est-ce qui lui donne une raison de rester ;
- pour chaque chapitre : le lieu, ce que fait la balle, ce qui rate et pourquoi ; s'il
  ne comprend pas la cause ou la chute sans le son, c'est bloquant ;
- comprend-il qu'il y a une série et que la dernière la retourne ;
- à quel instant il aurait fait défiler, et pourquoi ;
- aurait-il envie de commenter, et quoi ;
- y a-t-il un objet du gag qu'il ne distingue pas sur un téléphone (trop petit, trop
  sombre, sous les boutons de TikTok), ou une forme qui évoque autre chose (un logo, une
  marque, un objet interdit) ?

### Juge 2 : la facture

Il reçoit les planches, le mp4 (il extrait ses propres rafales avec ffmpeg), et **le
script** du sujet. Il vérifie image par image autour de chaque chute et de chaque coupe :
- rien ne traverse un solide, à aucun moment (Bounce, débris, personnages) ;
- tout objet que Bounce peut toucher figure dans `solids()` du script ;
- tout reste dans le cadre, le point d'impact compris ;
- le tampon, les titres et les sous-titres ne couvrent ni Bounce ni l'objet de la chute ;
- aucune image ne fait « bug » : objet qui se téléporte, qui flotte, qui tombe sans
  cause, calque dans le mauvais ordre ;
- nuit partout, formes simples, décors lisibles sur téléphone, aucune ressemblance avec
  du contenu généré à la chaîne ;
- Bounce grand, sauts francs, lisible à chaque chute ;
- les lumières (halos, faisceaux) éclairent : un disque ou un faisceau plus sombre que
  le mur est un défaut ;
- les objets qui tombent se posent comme des objets : rebond, glissade, pile, jamais
  aplatis d'un coup.

### Juge 3 : le rythme et le son

Il reçoit `controle.json` (narration et instants), le mp4 (audio : silencedetect,
niveaux), les planches de coupe. Il vérifie :
- la voix annonce chaque chapitre dès la coupe et avant la chute ;
- aucune phrase ne déborde sur le chapitre suivant, aucune phrase ne tombe sur une image
  qui ne correspond plus ;
- la réplique de Bounce répond à une question, tombe dans sa scène, seule, audible ;
- Bounce ne parle jamais sous le narrateur ; pas de silence de plus de 1,6 s ;
- les tenues après chaque chute : assez pour lire le tampon, jamais une image morte ;
- l'ouverture : la première chute arrive vite et se comprend ;
- chaque phrase du narrateur : drôle ou utile ; une phrase qui décrit l'image, ou qui
  dévoile la chute avant qu'elle arrive, est un défaut ;
- la fin : le dernier son finit avant la dernière image.

## Le verdict, et quand on s'arrête

Trois juges exigeants trouveront toujours quelque chose : le circuit a une fin.

- **Bloquant** = un bug qu'un spectateur verrait ou entendrait (objet qui traverse, se
  téléporte, mot coupé, voix l'une sur l'autre), ou une chute qu'on ne comprend pas sans le
  son. Tout le reste est **mineur**. Un « bloquant » qui contredit l'identité du compte
  (ce que fait `base.py` dans toutes les vidéos) n'en est pas un : la consigne du juge
  est corrigée.
- **Publiable** : contrôle automatique à zéro et aucun défaut bloquant.
- **Un défaut mineur ne fait jamais rerendre.** Il devient, dans le même commit, une
  vérification du contrôle ou une règle de la skill `ecrire`, pour la vidéo suivante.
- **Au plus un rerendu par vidéo**, pour les défauts bloquants. Après ce rerendu, le
  contrôle passe, les juges repassent une fois, et la vidéo part ; ce qui reste est écrit
  dans `notes`.
- Les verdicts et leurs raisons vont dans `notes` de `history.json`.

## Ce qui rend le circuit meilleur à chaque vidéo

Un défaut qu'un juge ou le propriétaire trouve et que le contrôle automatique n'a pas vu
devient, **dans le même commit que sa correction** : soit une vérification de plus dans
`src/tools/controle.py` (s'il se mesure), soit une règle dans la skill `ecrire` ou une
question de plus dans la consigne d'un juge (s'il ne se mesure pas). Ce que l'auteur a
appris ne doit jamais rester dans sa tête : une vidéo faite par un autre run, sans lui,
doit en bénéficier.
