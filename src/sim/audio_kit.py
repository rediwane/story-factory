"""
Brique audio partagée par les mécaniques : sound design percussif, voix d'accroche
(TTS), et lit musical optionnel.

Rien ici ne modifie un script existant — c'est un module neuf que les nouvelles
mécaniques importent.

Trois briques :

- `pluck()` / `kick()` / `riser()` / `impact()` : sons de synthèse. Le compte a pour
  identité un son *généré par les collisions* ; l'enjeu n'est pas d'y coller une
  musique, c'est que ces sons claquent au lieu de faire "bip".
- `hook_voice()` : une phrase d'accroche dite par une voix TTS, posée sur les
  premières secondes. piper (voix naturelle) si son modèle est disponible, sinon
  espeak-ng (voix robotique, style "TikTok TTS"), sinon rien — jamais d'échec bloquant.
- `sfx()` : charge un son réel de la bibliothèque `assets/audio/` par tag (verre
  brisé, impact métal, whoosh…). Un vrai bruit de verre porte mieux qu'un kick de
  synthèse sur l'évènement fort d'une vidéo. Renvoie None si la bibliothèque est vide
  ou si aucun son ne correspond : la mécanique retombe alors sur la synthèse.
- `load_music_bed()` : lit musical optionnel, chargé depuis un fichier local fourni
  par l'utilisateur via la clé de config `music_file`. Aucune piste n'est téléchargée
  ni intégrée par défaut : ce qu'on publie doit être libre de droits ou vous
  appartenir (voir CLAUDE.md, section Audio).
"""
import numpy as np
import json, os, subprocess, shutil, wave, tempfile

SR = 44100

VOICE_DIR = os.environ.get("PIPER_VOICE_DIR", os.path.expanduser("~/.cache/piper"))
VOICE_NAME = "en_US-amy-medium"             # la voix de l'accroche
HERO_VOICE_NAME = "en_US-hfc_male-medium"   # la voix de Bounce (grave, transposée plus bas par base.py)
VOICE_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def _voice_url(name):
    """en_US-amy-medium -> .../en/en_US/amy/medium (l'arborescence du dépôt piper-voices)."""
    lang, speaker, quality = name.split("-", 2)
    return f"{VOICE_BASE_URL}/{lang.split('_')[0]}/{lang}/{speaker}/{quality}"


# ---------------------------------------------------------------- sons de synthèse

def _env(n, attack=0.004, decay=6.0, sr=SR):
    """Enveloppe percussive : attaque très courte, décroissance exponentielle."""
    t = np.arange(n) / sr
    a = np.clip(t / max(attack, 1e-6), 0, 1)
    return a * np.exp(-t * decay)


def pluck(freq, dur=0.5, sr=SR, detune=0.004, decay=6.0, bright=1.0):
    """Note percussive : harmoniques + léger détune + attaque nette.

    Remplace la sinusoïde additive d'origine, qui sonnait creux une fois la vidéo
    ré-encodée par TikTok.
    """
    n = int(dur * sr)
    t = np.arange(n) / sr
    out = np.zeros(n)
    for k, amp in ((1, 1.0), (2, 0.45 * bright), (3, 0.22 * bright), (4, 0.11 * bright)):
        out += amp * np.sin(2 * np.pi * freq * k * t)
        out += amp * 0.6 * np.sin(2 * np.pi * freq * k * (1 + detune) * t)
    out *= _env(n, decay=decay, sr=sr)
    # petit clic d'attaque : c'est lui qui rend l'impact lisible sur un haut-parleur
    click = np.random.default_rng(int(freq)).normal(0, 1, min(n, int(0.004 * sr)))
    out[:len(click)] += click * 0.35 * np.exp(-np.arange(len(click)) / (0.0015 * sr))
    return out / (np.max(np.abs(out)) + 1e-9)


def kick(dur=0.35, sr=SR, f0=120.0, f1=45.0):
    """Kick : sweep de fréquence descendant, pour marquer un évènement fort."""
    n = int(dur * sr)
    t = np.arange(n) / sr
    f = f1 + (f0 - f1) * np.exp(-t * 22)
    ph = 2 * np.pi * np.cumsum(f) / sr
    return np.sin(ph) * _env(n, attack=0.001, decay=9.0, sr=sr)


def sub(freq=55.0, dur=0.6, sr=SR):
    """Basse sinus : donne le poids que les petits haut-parleurs traduisent en punch."""
    n = int(dur * sr)
    t = np.arange(n) / sr
    return np.sin(2 * np.pi * freq * t) * _env(n, attack=0.006, decay=4.0, sr=sr)


def riser(dur=3.0, sr=SR, f_start=220.0, f_end=1760.0):
    """Montée de tension : bruit filtré + glissando, volume croissant."""
    n = int(dur * sr)
    t = np.arange(n) / sr
    f = f_start * (f_end / f_start) ** (t / dur)
    ph = 2 * np.pi * np.cumsum(f) / sr
    tone = np.sin(ph) * 0.5 + np.sin(ph * 1.5) * 0.2
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 1, n)
    noise = np.convolve(noise, np.ones(48) / 48, mode="same")  # passe-bas grossier
    ramp = (t / dur) ** 2
    return (tone * 0.6 + noise * 0.4) * ramp


def impact(dur=1.2, sr=SR):
    """Impact final : bruit large + sub, décroissance longue."""
    n = int(dur * sr)
    rng = np.random.default_rng(11)
    noise = rng.normal(0, 1, n) * _env(n, attack=0.001, decay=5.0, sr=sr)
    return noise * 0.5 + sub(48.0, dur, sr) * 0.9


# ------------------------------------------------- sons reels de la bibliotheque

_MANIFEST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "assets", "audio", "manifest.json")
_sfx_cache = {}


def _manifest():
    try:
        with open(_MANIFEST) as f:
            return json.load(f).get("assets", [])
    except Exception:
        return []


def sfx(tags, kind="sfx", sr=SR, index=0):
    """Son de la bibliothèque portant TOUS les tags demandés (chaîne « a,b » ou
    liste). `index` choisit parmi les correspondances, pour varier d'une vidéo à
    l'autre sans changer d'appel.

    Renvoie un tableau numpy normalisé, ou **None** si la bibliothèque est vide, si
    rien ne correspond, ou si le fichier est illisible — l'appelant doit alors
    retomber sur la synthèse. Un son manquant ne casse jamais un rendu.
    """
    want = set(tags.split(",")) if isinstance(tags, str) else set(tags)
    hits = [a for a in _manifest()
            if a.get("kind") == kind and want.issubset(set(a.get("tags", [])))]
    if not hits:
        return None
    a = hits[index % len(hits)]
    key = (a["id"], sr)
    if key in _sfx_cache:
        return _sfx_cache[key]
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), a["file"])
    if not os.path.exists(path):
        return None
    tmp = tempfile.mktemp(suffix=".wav")
    try:
        subprocess.run(["ffmpeg", "-y", "-i", path, "-ac", "1", "-ar", str(sr), tmp],
                       check=True, timeout=60,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        x = _read_wav(tmp, sr)
    except Exception:
        return None
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    if x is None or not len(x):
        return None
    x = x / (np.max(np.abs(x)) + 1e-9)
    _sfx_cache[key] = x
    return x


# ------------------------------------------------------------------- voix (TTS)

def _voice_files(name=VOICE_NAME):
    onnx = os.path.join(VOICE_DIR, name + ".onnx")
    return onnx, onnx + ".json"


def ensure_voice(timeout=240, name=VOICE_NAME):
    """Télécharge le modèle piper si absent. Renvoie le chemin .onnx ou None."""
    onnx, cfg = _voice_files(name)
    if os.path.exists(onnx) and os.path.exists(cfg):
        return onnx
    os.makedirs(VOICE_DIR, exist_ok=True)
    base_url = _voice_url(name)
    for url, dest in ((f"{base_url}/{name}.onnx?download=true", onnx),
                      (f"{base_url}/{name}.onnx.json?download=true", cfg)):
        try:
            subprocess.run(["curl", "-sSL", "--fail", "-o", dest, url],
                           check=True, timeout=timeout)
        except Exception:
            return None
    return onnx if os.path.exists(onnx) and os.path.exists(cfg) else None


def _read_wav(path, sr=SR):
    with wave.open(path) as w:
        n, fr, sw = w.getnframes(), w.getframerate(), w.getsampwidth()
        raw = w.readframes(n)
        if w.getnchannels() != 1 or sw != 2:
            return None
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if fr != sr:   # rééchantillonnage linéaire, suffisant pour de la voix
        t_src = np.arange(len(x)) / fr
        t_dst = np.arange(int(len(x) * sr / fr)) / sr
        x = np.interp(t_dst, t_src, x)
    return x


def piper_say(text, name, sr=SR, length_scale=None, timeout=180):
    """Texte -> tableau numpy par piper avec la voix `name` ; None si indisponible."""
    onnx = ensure_voice(name=name)
    if not onnx:
        return None
    tmp = tempfile.mktemp(suffix=".wav")
    try:
        cmd = ["python3", "-m", "piper", "--model", onnx, "--output_file", tmp]
        if length_scale:
            cmd += ["--length_scale", str(length_scale)]
        subprocess.run(cmd, input=text.encode(), check=True, timeout=timeout,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        x = _read_wav(tmp, sr)
        if x is not None and len(x):
            return x / (np.max(np.abs(x)) + 1e-9)
    except Exception:
        pass
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return None


def hero_voice(text, sr=SR, length_scale=1.25):
    """Un mot de Bounce, dans sa voix. None si piper n'est pas disponible : les rebonds
    sont alors muets, le rendu ne casse pas."""
    if not text:
        return None
    return piper_say(text, HERO_VOICE_NAME, sr, length_scale)


def hook_voice(text, sr=SR, prefer_piper=True):
    """Phrase d'accroche en voix TTS. Renvoie un tableau numpy, ou None si aucun
    moteur n'est disponible — l'absence de voix ne doit jamais casser un rendu."""
    if not text:
        return None
    if prefer_piper:
        x = piper_say(text, VOICE_NAME, sr)
        if x is not None:
            return x
    tmp = tempfile.mktemp(suffix=".wav")
    try:
        if shutil.which("espeak-ng"):
            subprocess.run(["espeak-ng", "-v", "en-us", "-s", "155", "-w", tmp, text],
                           check=True, timeout=60,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            x = _read_wav(tmp, sr)
            if x is not None and len(x):
                return x / (np.max(np.abs(x)) + 1e-9)
    except Exception:
        pass
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return None


# --------------------------------------------------------------- lit musical

def load_music_bed(path, n_samples, sr=SR, gain=0.18):
    """Charge un fichier audio local comme lit musical, bouclé/coupé à la longueur
    voulue. `path` est fourni par la config (`music_file`) : c'est à vous de n'y
    mettre qu'une piste libre de droits ou vous appartenant. Renvoie None si le
    fichier est absent ou illisible."""
    if not path or not os.path.exists(path):
        return None
    tmp = tempfile.mktemp(suffix=".wav")
    try:
        subprocess.run(["ffmpeg", "-y", "-i", path, "-ac", "1", "-ar", str(sr), tmp],
                       check=True, timeout=180,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        x = _read_wav(tmp, sr)
    except Exception:
        return None
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    if x is None or not len(x):
        return None
    reps = int(np.ceil(n_samples / len(x)))
    x = np.tile(x, reps)[:n_samples]
    fade = min(int(1.5 * sr), n_samples // 4)
    if fade > 0:
        x[-fade:] *= np.linspace(1, 0, fade)
    return x * gain


# ------------------------------------------------------------------- mixage

def add(buf, x, at_s, sr=SR, gain=1.0):
    """Ajoute `x` dans `buf` à l'instant `at_s`, en tronquant proprement au bord."""
    if x is None:
        return
    i = max(0, int(at_s * sr))
    n = min(len(x), len(buf) - i)
    if n > 0:
        buf[i:i+n] += x[:n] * gain


def write_wav(buf, path, sr=SR, peak=0.89, headroom_pct=99.5):
    """Écrit le mix, avec limiteur souple.

    Normaliser sur la crête absolue laisse un seul instant très fort fixer l'échelle :
    dans une vidéo dont la fin empile impact + verre + kick + sub, cette crête peut
    valoir 17 fois le reste, et la voix d'accroche retombe à un niveau inaudible.
    Accessoirement le morceau entier sonne faible, ce que TikTok pénalise puisqu'il
    normalise le volume à la lecture.

    On normalise donc sur un percentile haut (le corps du morceau), puis on écrête
    en douceur avec un tanh — les crêtes se tassent au lieu de saturer.
    """
    m = np.percentile(np.abs(buf), headroom_pct)
    if m <= 0:
        m = np.max(np.abs(buf))
    if m > 0:
        buf = buf / m * peak
        buf = np.tanh(buf)          # limiteur souple : |sortie| < 1, sans clipping dur
        buf = buf / max(np.max(np.abs(buf)), 1e-9) * peak
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((buf * 32767).astype(np.int16).tobytes())
