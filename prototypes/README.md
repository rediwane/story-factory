# Prototypes

Scripts autonomes de la phase 0, faits en session avec le propriétaire pour trouver
l'identité du compte. Ce ne sont ni des modèles d'histoire ni des configs : le run ne
les relit pas et ne s'en inspire pas. Ils servent de référence technique (personnage,
caméra, transitions, texte cinétique, bruitages, musique générée) pour l'extension du
moteur `src/engine/`.

- `v1_fixe.py` : premier test, personnage fixe qui parle. Jugé trop monotone.
- `v2_monte.py` : même test en montage rythmé, un plan par phrase. Validé comme
  direction par le propriétaire le 28/10.

Rendu : `python3 -I prototypes/v2_monte.py <sortie.mp4>` (Kokoro, cairosvg, ffmpeg).
