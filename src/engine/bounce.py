"""
Bounce, le personnage : son dessin et sa voix, repris à l'identique du premier compte
(dépôt bouncefactory, `src/mechanics/base.py` et `audio_kit.py`), pour qu'il soit le
même partout.

- `draw(dr, x, y, r, expr, tilt)` : halo, disque dans sa couleur fixe, visage
  (`calm` au repos, `shock` au choc, `win`, `lose`).
- `word(text)` : un mot dit par lui, voix grave (piper, transposée vers le bas), coupé au
  plus près du son ; None si piper n'est pas disponible (le rendu ne casse pas).

Il ne dit que son nom. Sa couleur, sa voix et son visage ne se règlent pas par vidéo.
"""
import os
import sys
import math
import tempfile
import subprocess

import numpy as np

SR = 44100
COLOR = (255, 20, 200)
INK = (16, 14, 20)
EYE_WHITE = (245, 243, 248)
VOICE_NAME = "en_US-hfc_male-medium"
VOICE_LENGTH = 1.25
VOICE_PITCH = 0.72
NAME = "Bounce"
VOICE_DIR = os.environ.get("PIPER_VOICE_DIR", os.path.expanduser("~/.cache/piper"))
VOICE_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

_cache = {}


def dim(col, k):
    return tuple(max(0, min(255, int(c * k))) for c in col)


def _circle(dr, x, y, r, fill):
    dr.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def face(dr, x, y, r, expr="calm", tilt=0.0):
    ca, sa = math.cos(tilt), math.sin(tilt)

    def P(u, v):
        return (x + (u * ca - v * sa) * r, y + (u * sa + v * ca) * r)

    def stroke(pts, w):
        dr.line([P(u, v) for u, v in pts], fill=INK, width=max(2, int(w * r)), joint="curve")

    def blob(u, v, ru, rv, fill=INK):
        pts = [P(u + ru * math.cos(k * math.pi / 12), v + rv * math.sin(k * math.pi / 12)) for k in range(24)]
        dr.polygon(pts, fill=fill)

    if expr == "shock":
        stroke([(-0.6, -0.62), (-0.2, -0.62)], 0.12); stroke([(0.2, -0.62), (0.6, -0.62)], 0.12)
        blob(-0.36, -0.2, 0.2, 0.22, EYE_WHITE); blob(0.36, -0.2, 0.2, 0.22, EYE_WHITE)
        blob(-0.36, -0.2, 0.09, 0.1); blob(0.36, -0.2, 0.09, 0.1)
        blob(0.0, 0.4, 0.16, 0.2)
    elif expr == "win":
        stroke([(-0.6, -0.5), (-0.2, -0.56)], 0.12); stroke([(0.2, -0.56), (0.6, -0.5)], 0.12)
        blob(-0.36, -0.2, 0.12, 0.12); blob(0.36, -0.2, 0.12, 0.12)
        stroke([(-0.4, 0.3), (-0.2, 0.48), (0.2, 0.48), (0.4, 0.3)], 0.11)
    elif expr == "lose":
        stroke([(-0.6, -0.36), (-0.2, -0.5)], 0.12); stroke([(0.2, -0.5), (0.6, -0.36)], 0.12)
        blob(-0.36, -0.2, 0.12, 0.12); blob(0.36, -0.2, 0.12, 0.12)
        stroke([(-0.3, 0.5), (0.0, 0.4), (0.3, 0.5)], 0.11)
    else:
        stroke([(-0.6, -0.44), (-0.2, -0.44)], 0.12); stroke([(0.2, -0.44), (0.6, -0.44)], 0.12)
        blob(-0.36, -0.2, 0.12, 0.12); blob(0.36, -0.2, 0.12, 0.12)
        stroke([(-0.16, 0.42), (0.2, 0.42)], 0.1)


def draw(dr, x, y, r, expr="calm", tilt=0.0, alpha=1.0, bg=(0, 0, 0)):
    col = tuple(int(bg[i] + (COLOR[i] - bg[i]) * alpha) for i in range(3))
    halo = tuple(int(bg[i] + (dim(COLOR, 0.22)[i] - bg[i]) * alpha) for i in range(3))
    _circle(dr, x, y, r * 1.6, halo)
    _circle(dr, x, y, r, col)
    if alpha > 0.5:
        face(dr, x, y, r, expr, tilt)


# ------------------------------------------------------------------ voix

def _voice_url(name):
    lang, speaker, quality = name.split("-", 2)
    return f"{VOICE_BASE_URL}/{lang.split('_')[0]}/{lang}/{speaker}/{quality}"


def ensure_voice(name=VOICE_NAME, timeout=240):
    onnx = os.path.join(VOICE_DIR, name + ".onnx")
    cfg = onnx + ".json"
    if os.path.exists(onnx) and os.path.exists(cfg):
        return onnx
    os.makedirs(VOICE_DIR, exist_ok=True)
    base = _voice_url(name)
    for url, dest in ((f"{base}/{name}.onnx?download=true", onnx),
                      (f"{base}/{name}.onnx.json?download=true", cfg)):
        try:
            subprocess.run(["curl", "-sSL", "--fail", "-o", dest, url], check=True, timeout=timeout)
        except Exception:
            return None
    return onnx if os.path.exists(onnx) and os.path.exists(cfg) else None


def _read_wav(path, sr=SR):
    import wave
    with wave.open(path) as w:
        n, fr, sw, ch = w.getnframes(), w.getframerate(), w.getsampwidth(), w.getnchannels()
        raw = w.readframes(n)
    if ch != 1 or sw != 2:
        return None
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if fr != sr:
        x = np.interp(np.arange(int(len(x) * sr / fr)) / sr, np.arange(len(x)) / fr, x)
    return x


def pitch(x, factor):
    factor = max(0.5, min(2.0, factor))
    idx = np.arange(0, len(x) - 1, factor)
    return np.interp(idx, np.arange(len(x)), x)


def word(text=NAME, sr=SR):
    """Un mot de Bounce, dans sa voix, ou None."""
    if text in _cache:
        return _cache[text]
    out = None
    onnx = ensure_voice()
    if onnx:
        tmp = tempfile.mktemp(suffix=".wav")
        try:
            subprocess.run([sys.executable, "-m", "piper", "--model", onnx, "--output_file", tmp,
                            "--length_scale", str(VOICE_LENGTH)],
                           input=text.encode(), check=True, timeout=180,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            v = _read_wav(tmp, sr)
            if v is not None and len(v):
                v = v / (np.max(np.abs(v)) + 1e-9)
                v = pitch(v, VOICE_PITCH)
                idx = np.where(np.abs(v) > 0.02)[0]
                if len(idx):
                    v = v[max(0, idx[0] - 150):idx[-1] + int(0.03 * sr)].copy()
                    n = min(int(0.03 * sr), len(v))
                    v[-n:] *= np.linspace(1, 0, n)
                    out = v
        except Exception as e:
            print(f"[bounce] voix indisponible : {e}", file=sys.stderr)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    if out is None:
        print("[bounce] aucune voix pour Bounce : il reste muet", file=sys.stderr)
    _cache[text] = out
    return out
