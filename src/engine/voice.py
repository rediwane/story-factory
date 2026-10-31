"""
La voix du narrateur et le mixage.

- `say(text, voice, length_scale)` : texte -> tableau numpy (mono, SR). Le moteur est
  Kokoro (kokoro-onnx, voix choisie par le propriétaire : `am_fenrir`) ; les noms de voix
  piper (`langue_REGION-nom-qualité`) passent par piper ; repli espeak-ng ; None si
  aucun moteur ne répond. L'absence de voix ne casse
  jamais un rendu : elle se signale sur stderr, et le run l'écrit dans ses notes.
- `add`, `write_wav` : poser des sons dans un buffer, écrire le mix avec un limiteur
  souple (normalisation sur le corps du morceau, pas sur la crête).

Les modèles se téléchargent au premier usage : Kokoro dans ~/.cache/kokoro (modèle
et voix, ~350 Mo), piper dans ~/.cache/piper.
"""
import os
import sys
import wave
import shutil
import tempfile
import subprocess

import numpy as np

SR = 44100
VOICE_DIR = os.environ.get("PIPER_VOICE_DIR", os.path.expanduser("~/.cache/piper"))
VOICE_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
DEFAULT_VOICE = "am_fenrir"
KOKORO_DIR = os.environ.get("KOKORO_DIR", os.path.expanduser("~/.cache/kokoro"))
KOKORO_FILES = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}
_kokoro = None


def is_piper_name(name):
    return "-" in name and "_" in name.split("-")[0]


def ensure_kokoro(timeout=600):
    """Charge Kokoro (télécharge le modèle si absent). Renvoie l'objet ou None."""
    global _kokoro
    if _kokoro is not None:
        return _kokoro
    try:
        from kokoro_onnx import Kokoro
    except Exception as e:
        print(f"[voice] kokoro-onnx absent : {e}", file=sys.stderr)
        return None
    os.makedirs(KOKORO_DIR, exist_ok=True)
    for fn, url in KOKORO_FILES.items():
        dest = os.path.join(KOKORO_DIR, fn)
        if not os.path.exists(dest):
            try:
                subprocess.run(["curl", "-sSL", "--fail", "-o", dest, url], check=True, timeout=timeout)
            except Exception as e:
                print(f"[voice] téléchargement Kokoro échoué : {e}", file=sys.stderr)
                return None
    try:
        _kokoro = Kokoro(os.path.join(KOKORO_DIR, "kokoro-v1.0.onnx"), os.path.join(KOKORO_DIR, "voices-v1.0.bin"))
    except Exception as e:
        print(f"[voice] Kokoro ne se charge pas : {e}", file=sys.stderr)
        return None
    return _kokoro


def _voice_url(name):
    """en_US-lessac-medium -> .../en/en_US/lessac/medium"""
    lang_region, speaker, quality = name.split("-", 2)
    lang = lang_region.split("_")[0]
    return f"{VOICE_BASE_URL}/{lang}/{lang_region}/{speaker}/{quality}"


def ensure_voice(name=DEFAULT_VOICE, timeout=240):
    """Télécharge le modèle piper si absent. Renvoie le chemin .onnx ou None."""
    onnx = os.path.join(VOICE_DIR, name + ".onnx")
    cfg = onnx + ".json"
    if os.path.exists(onnx) and os.path.exists(cfg):
        return onnx
    os.makedirs(VOICE_DIR, exist_ok=True)
    base = _voice_url(name)
    for url, dest in ((f"{base}/{name}.onnx?download=true", onnx),
                      (f"{base}/{name}.onnx.json?download=true", cfg)):
        try:
            subprocess.run(["curl", "-sSL", "--fail", "-o", dest, url],
                           check=True, timeout=timeout)
        except Exception:
            return None
    return onnx if os.path.exists(onnx) and os.path.exists(cfg) else None


def _read_wav(path, sr=SR):
    with wave.open(path) as w:
        n, fr, sw, ch = w.getnframes(), w.getframerate(), w.getsampwidth(), w.getnchannels()
        raw = w.readframes(n)
    if ch != 1 or sw != 2:
        return None
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if fr != sr:
        t_src = np.arange(len(x)) / fr
        t_dst = np.arange(int(len(x) * sr / fr)) / sr
        x = np.interp(t_dst, t_src, x)
    return x


def _norm(x):
    return x / (np.max(np.abs(x)) + 1e-9)


def say(text, voice=DEFAULT_VOICE, length_scale=None, sr=SR):
    """Texte -> tableau numpy. Kokoro (voix am_*, af_*, bm_*…), ou piper pour un nom
    piper, puis espeak-ng, puis None. `length_scale` : 1.0 normal, plus grand = plus lent."""
    if not text or not text.strip():
        return None
    if not is_piper_name(voice):
        k = ensure_kokoro()
        if k is not None:
            try:
                x, ksr = k.create(text, voice=voice, speed=1.0 / (length_scale or 1.0), lang="en-us")
                x = np.asarray(x, dtype=np.float64)
                if ksr != sr:
                    x = np.interp(np.arange(int(len(x) * sr / ksr)) / sr, np.arange(len(x)) / ksr, x)
                if len(x):
                    return _norm(x)
            except Exception as e:
                print(f"[voice] Kokoro échec : {e}", file=sys.stderr)
    onnx = ensure_voice(voice) if is_piper_name(voice) else None
    tmp = tempfile.mktemp(suffix=".wav")
    try:
        if onnx:
            cmd = [sys.executable, "-m", "piper", "--model", onnx, "--output_file", tmp]
            if length_scale:
                cmd += ["--length_scale", str(length_scale)]
            subprocess.run(cmd, input=text.encode(), check=True, timeout=180,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            x = _read_wav(tmp, sr)
            if x is not None and len(x):
                return _norm(x)
        if shutil.which("espeak-ng"):
            subprocess.run(["espeak-ng", "-v", "en-us", "-s", "150", "-w", tmp, text],
                           check=True, timeout=60,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            x = _read_wav(tmp, sr)
            if x is not None and len(x):
                return _norm(x)
    except Exception as e:
        print(f"[voice] échec : {e}", file=sys.stderr)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    print("[voice] aucune voix disponible : narration muette", file=sys.stderr)
    return None


def add(buf, x, at_s, sr=SR, gain=1.0):
    """Ajoute `x` dans `buf` à l'instant `at_s`, en tronquant au bord."""
    if x is None:
        return
    i = max(0, int(at_s * sr))
    n = min(len(x), len(buf) - i)
    if n > 0:
        buf[i:i + n] += x[:n] * gain


def write_wav(buf, path, sr=SR, peak=0.89, headroom_pct=99.5):
    """Écrit le mix : normalisation sur un percentile haut, puis limiteur souple (tanh)."""
    m = np.percentile(np.abs(buf), headroom_pct) if len(buf) else 0
    if m <= 0 and len(buf):
        m = np.max(np.abs(buf))
    if m > 0:
        buf = np.tanh(buf / m * peak)
        buf = buf / max(np.max(np.abs(buf)), 1e-9) * peak
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((buf * 32767).astype(np.int16).tobytes())
