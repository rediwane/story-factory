---
name: mesure
description: Mesurer : lire les vues des videos publiees via Metricool, ecrire stats.views_24h / views_48h / views dans history.json, et les metriques de compte dans daily. Rapprochement par heure de publication, conduite en cas de panne.
---

# Mesurer

Remplir `stats` de chaque vidéo `published` et `daily` du jour. Ne pas juger : les
verdicts sont une autre étape.

**Le `brandId` Metricool de ce compte n'est pas encore connu** : il s'écrit ici quand le
propriétaire a créé la marque.

## Appel

`getAnalyticsDataByMetrics`, période du plus ancien post sans `views_48h` jusqu'à
aujourd'hui. Dates en UTC ; le compte est en Europe/Paris.

| champ | contenu |
|---|---|
| `TKPO02` | date-heure de publication, `YYYYMMDDhhmmss`, UTC |
| `TKPO03` | URL de la vidéo |
| `TKPO06` | durée en secondes |
| `TKPO07` | **vues** |
| `TKPO08` / `TKPO09` / `TKPO10` | likes / commentaires / partages |

Sur un compte TikTok personnel, le temps de visionnage (`TKPO13` à `TKPO15`) et la
portée (`TKPO11`) remontent vides. Les re-tester une fois par mois ; ne rien bâtir dessus.

## Rapprochement

Une ligne Metricool se rattache à l'entrée dont `scheduled_time` (en UTC) est à moins de
10 minutes de `TKPO02` et dont `duration_s` est à moins de 2 s de `TKPO06`. Une ligne sans
entrée : publication hors routine, notée dans `notes`, jamais inventée dans `videos[]`.

## Écriture

`age_h` = heures depuis `TKPO02` :
- `stats.views` = `TKPO07`, toujours écrasé ;
- `stats.views_24h` = `TKPO07` si `age_h ≥ 24` et encore absent ;
- `stats.views_48h` = `TKPO07` si `age_h ≥ 48` et encore absent ;
- `likes`, `comments`, `shares`, `measured_at`.

Une valeur à 24 h ou 48 h écrite une fois ne bouge plus.

## Compte

`TKEV02` (vues du jour), `TKEV07` (abonnés), pour chaque date manquante de `daily`.

## Panne

Metricool en échec : l'écrire dans `notes`, continuer avec les stats connues, ne jamais
inventer une valeur.
