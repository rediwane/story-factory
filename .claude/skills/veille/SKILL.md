---
name: veille
description: Une fois par semaine (history.json veille.last_check > 7 jours). Relever les hashtags du moment et la frontiere des formats satures dans la niche des histoires racontees. Ecrire dans history.json veille. Ne consigne jamais de liste d'histoires a reprendre.
---

# Veille

Les stats disent ce que nos vidéos ont fait ; la veille dit ce que TikTok pousse en ce
moment. Elle donne au run les hashtags du moment, et dit **de quoi s'écarter**. Elle ne
dit jamais quoi faire : une liste de formats dans un fichier que le run relit devient un
menu, et le run cesse de chercher.

## Sources

1. **Hashtags** : le TikTok Creative Center d'abord ; s'il ne répond pas, une recherche
   web croisée sur au moins deux sources. Noter la confiance.
2. **Formats de la niche** : ce qui tourne en ce moment dans les histoires racontées par
   une voix de synthèse. On en rapporte une **frontière** : ce qui se voit partout est
   saturé.

Se méfier des articles d'outils marketing qui recopient les mêmes chiffres sans source.

## Ce qu'on écrit

Dans `history.json → veille`, en remplaçant le contenu précédent :

```json
{
  "last_check": "AAAA-MM-JJ",
  "hashtags": ["..."],
  "formats_satures": "une ou deux phrases qui décrivent la frontière, sans énumérer d'histoires",
  "sources": ["url"],
  "confiance": "haute | moyenne | basse"
}
```

## Ce qu'on ne fait pas

- Copier un compte concurrent, ou en suivre un en particulier.
- Changer une règle de `CLAUDE.md` sur la foi d'un article : une trouvaille de fond se
  propose au propriétaire.
