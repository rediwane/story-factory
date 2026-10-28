---
name: publier
description: Publier une video : hebergement du mp4 (uguu, repli litterbox, verification de l'URL), post TikTok via Metricool sur les creneaux du jour, verification getScheduledPosts, consignation dans history.json.
---

# Publier

**Le `brandId` Metricool de ce compte n'est pas encore connu** : le propriétaire crée la
marque dans Metricool, puis il s'écrit ici et dans la skill `mesure`. Sans lui, rien ne
se publie.

## Créneaux (Europe/Paris)

La cadence et les créneaux se décident avec le propriétaire au démarrage, et s'écrivent
ici. La première semaine d'un compte neuf : une ou deux vidéos par jour au plus.
Attribution des créneaux **au hasard**, tirage noté dans `notes`, pour que l'effet de
l'heure se lise dans les stats.

Avant toute création : `getScheduledPosts` sur la journée. Un créneau déjà occupé → la
vidéo prévue dessus passe `generated_not_selected`, raison dans `notes`.

## Hébergement du mp4

Metricool copie le fichier sur son CDN à la création du post : quelques heures
d'hébergement suffisent. Dans cet ordre, en passant au suivant dès qu'une réponse n'est
pas une URL `https://` directe vers un `.mp4` :

1. **uguu**
   ```bash
   curl -s -F "files[]=@output/<name>.mp4" "https://uguu.se/upload?output=text"
   ```
2. **litterbox** (24 h) ; Metricool en a refusé les URL sur l'autre compte, c'est un repli
   ```bash
   curl -s -F "reqtype=fileupload" -F "time=24h" -F "fileToUpload=@output/<name>.mp4" \
     https://litterbox.catbox.moe/resources/internals/api.php
   ```
3. Les deux échouent, ou Metricool refuse l'URL → `publication_failed`, raison dans `notes`.

Ne jamais créer un post avec une URL non vérifiée.

## Le post Metricool

`createScheduledPost`, réseau TikTok :

- `text` : la caption de `captions/<name>.md`, courte, 3 à 4 hashtags dont ceux du
  moment (`history.json → veille.hashtags`) ;
- média : l'URL vérifiée ; `publicationDate` : le créneau, en Europe/Paris ;
- `tiktokData.title` : **obligatoire** (Metricool refuse le post sans lui) : l'accroche ;
- `privacyOption: PUBLIC_TO_EVERYONE`, commentaires, duet et stitch activés ;
- l'étiquette de contenu généré par IA, si Metricool la propose ; sinon le noter dans
  `notes` et le signaler au propriétaire.

Réponse : `status: "scheduled"`, `metricool_post_id`, `scheduled_time`, `slot`,
`media_url` dans l'entrée `history.json`, écrits avant de passer à la vidéo suivante.
Le lendemain, l'étape de nettoyage passe les entrées `scheduled` en `published` dès que
`getScheduledPosts` renvoie `PUBLISHED`, avec `publicUrl` dans `post_url` ; sinon
`abandoned`.

## Panne

Metricool refuse ou ne répond pas : réessayer une fois après 30 s, puis
`publication_failed` avec la réponse dans `notes`. Les autres vidéos partent quand même.
