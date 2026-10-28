# story-factory

Système autonome qui publiera chaque jour des histoires racontées par une voix, sur des
dessins simples animés, sur un compte TikTok, via Metricool. Tout est décrit dans
**`CLAUDE.md`**, à commencer par l'état du projet et les décisions qui restent à prendre.

```
src/engine/render.py     moteur : config JSON -> vidéo verticale 1080x1920 (scènes, narration, sous-titres, formes animées)
src/engine/voice.py      voix du narrateur (piper, repli espeak-ng) et mixage
src/tools/coherence.py   détecteur d'incohérences
tests/rendu_test.json    test technique du moteur, sans contenu
history.json             vidéos, thèmes, métriques, veille, journal
```

```bash
pip install -r requirements.txt
python3 src/tools/coherence.py
python3 src/engine/render.py tests/rendu_test.json --simulate
python3 src/engine/render.py tests/rendu_test.json        # -> output/rendu_test.mp4
```
