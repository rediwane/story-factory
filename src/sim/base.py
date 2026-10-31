"""
Base commune des thèmes.

Un thème = un module sous src/mechanics/ qui définit :

    DEFAULTS = {...}                      # paramètres propres au thème
    class Sim:
        def __init__(self, cfg, rng): ...
        def step(self, dt) -> list        # avance d'un pas ; renvoie les événements du pas
        def snapshot(self) -> object      # ce qu'il faut pour dessiner cette frame
        def draw(self, dr, snap, t, S): ...  # dessine snap ; S = facteur de supersampling
        done: bool                        # la simulation est finie
        payoff: bool                      # le payoff a eu lieu (vidéo valide)
        counter(self, snap) -> str|None  # texte du compteur (facultatif)
        scene_top: float                  # fraction de la hauteur où commence la scène (défaut 0.24)

        hero_mood(self) -> str|None      # après le payoff : "win", "lose" ou None (facultatif)

Événements renvoyés par step(), des tuples :
    ("hit", data)     collision -> Bounce dit son nom (voix grave) ; son visage encaisse le choc
    ("event", data)   moment marquant : repère de simulation, aucun son ajouté
    ("payoff", data)  la fin : repère de simulation (la vidéo est valide) ; Bounce réagit selon hero_mood()
`data` est libre.

Bounce, le personnage : la balle du héros est dessinée par `ball()` (couleur fixe,
visage, expressions) ; les autres balles d'un thème par `extra_ball()` ; un héros qui
n'est pas une balle reçoit son visage par `hero_face()`. Il n'y a pas d'autre son que
sa voix, la voix de l'accroche et le silence : c'est l'identité du compte.

Le thème est lancé par :
    python3 src/mechanics/<theme>.py configs/<name>.json              # rend output/<name>.mp4
    python3 src/mechanics/<theme>.py configs/<name>.json --simulate   # durée + payoff, sans encodage

La config porte les clés communes ci-dessous (COMMON) et celles du thème (DEFAULTS).
"""
import os, sys, json, math, colorsys, subprocess, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
import audio_kit as ak
sys.path.insert(0, os.path.join(ROOT, "src", "engine"))
import voice as narr_voice  # noqa: E402  (Kokoro, voix du narrateur)

COMMON = {
    "name": "untitled",
    "width": 1080, "height": 1920, "fps": 60, "supersample": 2,
    "bg_color": [8, 8, 12],
    "seed": 1,
    # durée : le thème s'arrête sur son payoff ; ces bornes protègent le run
    "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 1.4,
    # palette : teinte de départ et pas par événement, en 0..1
    "hue_start": 0.55, "hue_step": 0.07, "saturation": 0.85, "value": 1.0,
    # Bounce : sa couleur (fixe, c'est le décor qui change), ce qu'il dit à chaque
    # rebond, sa voix (grave : transposée vers le bas, dite lentement) et ses réactions
    "hero_color": [255, 20, 200],
    "hero_name": "Bounce",
    "hero_min_gap_s": 0.45,         # deux mots jamais plus rapprochés : les rebonds trop serrés restent muets
    "hero_voice_pitch": 0.72, "hero_voice_length": 1.25, "hero_gain": 0.9,
    "hero_win": "Yes!", "hero_lose": "Oh no.",
    "hero_shock_s": 0.3,            # durée du visage de choc après un rebond
    # filigrane : le nom du compte, presque transparent, en bas de l'image
    "watermark": "@bouncefactory0", "watermark_y": 0.94, "watermark_alpha": 0.15,
    # accroche : en haut de l'image, lue par la voix
    "hook_text": "", "hook_text_s": 3.2, "hook_top": 0.09, "hook_width": 0.86,
    "hook_font_size": 96, "hook_voice": True,
    # compteur (si le thème en propose un) : caché pendant l'accroche
    "show_counter": True, "counter_font_size": 84, "counter_y": 0.19,
    # le narrateur : ses répliques sont données par le thème (sim.lines), calées sur les
    # événements de la simulation ; Bounce se tait pendant qu'il parle
    "narrator_voice": "am_fenrir", "narrator_length": 1.0, "narr_gap_s": 0.35,
    "sub_y": 0.80, "sub_font_size": 56, "sub_words": 6, "narr_tail_s": 1.2,
}

FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]


# ------------------------------------------------------------------ utilitaires
def load_config(path, defaults):
    cfg = dict(COMMON); cfg.update(defaults)
    with open(path) as f:
        user = json.load(f)
    cfg.update(user)      # les clés d'anciennes configs (sons, mélodie) sont ignorées
    return cfg


def font(px):
    for p in FONTS:
        try:
            return ImageFont.truetype(p, max(1, int(px)))
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=max(1, int(px)))
    except TypeError:
        return ImageFont.load_default()


def text_w(f, s):
    bb = f.getbbox(s); return bb[2] - bb[0]


def hsv(h, s=0.85, v=1.0):
    return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h % 1.0, s, v))


def dim(col, k):
    return tuple(max(0, min(255, int(c * k))) for c in col)


def midi_to_freq(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def circle(dr, x, y, r, fill):
    dr.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def ring(dr, x, y, r, width, col):
    dr.ellipse([x - r, y - r, x + r, y + r], outline=col, width=max(1, int(width)))


def extra_ball(dr, x, y, r, col):
    """Une balle qui n'est pas Bounce : halo et reflet, dans la couleur du thème."""
    circle(dr, x, y, r * 1.6, dim(col, 0.22))
    circle(dr, x, y, r, col)
    dr.ellipse([x - r * 0.45, y - r * 0.5, x + r * 0.15, y + r * 0.05],
               fill=tuple(min(255, int(c * 1.6)) for c in col))


# ------------------------------------------------------------------ Bounce
# État du héros pour la frame en cours, posé par render_video avant le dessin du thème :
# expression, inclinaison, position (la première balle dessinée dans la frame).
HERO = {"expr": "calm", "tilt": 0.0, "pos": None, "color": tuple(COMMON["hero_color"])}
INK = (16, 14, 20)
EYE_WHITE = (245, 243, 248)


def hero_face(dr, x, y, r):
    """Le visage de Bounce, centré en (x, y), pour une tête de rayon r : sourcils
    plats et bouche minuscule au repos (il s'en fout), yeux écarquillés au choc,
    sourire ou moue à la fin. S'incline légèrement dans le sens du mouvement."""
    expr, tilt = HERO["expr"], HERO["tilt"]
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


def ball(dr, x, y, r, col=None):
    """Bounce : halo, disque dans sa couleur fixe, visage. `col` est ignoré (gardé pour
    les thèmes écrits avant lui) : Bounce ne change pas de peau, le décor change."""
    hc = HERO["color"]
    circle(dr, x, y, r * 1.6, dim(hc, 0.22))
    circle(dr, x, y, r, hc)
    hero_face(dr, x, y, r)
    if HERO["pos"] is None:
        HERO["pos"] = (x, y)


# ------------------------------------------------------------------ simulation
def simulate(theme, cfg):
    """Fait tourner le thème jusqu'à son payoff (ou la borne max). Renvoie
    (states, events, duration_s) ; states = liste de (t, snapshot)."""
    rng = np.random.default_rng(int(cfg["seed"]))
    sim = theme.Sim(cfg, rng)
    dt = 1.0 / cfg["fps"]
    t, states, events = 0.0, [], []
    hold_until = None
    sim.payoff_t = None
    while True:
        if hold_until is None:
            evs = sim.step(dt)
            for kind, data in evs:
                events.append((t, kind, data))
            if sim.payoff and sim.payoff_t is None:
                sim.payoff_t = t
            if sim.done or t >= cfg["max_duration_s"]:
                hold_until = t + cfg["end_hold_s"]
        else:
            sim.step(dt)     # la scène continue de vivre pendant la tenue finale
        states.append((t, sim.snapshot()))
        t += dt
        if hold_until is not None and t >= hold_until:
            break
    return states, events, t, sim


# ------------------------------------------------------------------ narration
def build_narration(sim, cfg):
    """Synthétise les répliques du narrateur (sim.lines = [(t_declencheur, texte, cle)]) et
    les place dans le temps : jamais deux à la fois, jamais sous l'accroche, au plus tôt
    à leur déclencheur. Renvoie (narr, replies) : narr = [{start, end, text, key, audio}],
    replies = [t] les instants où Bounce répond (sim.replies = [(cle, delai)])."""
    lines = sorted(getattr(sim, "lines", []), key=lambda l: l[0])
    hook = ak.hook_voice(cfg["hook_text"]) if (cfg["hook_voice"] and cfg["hook_text"]) else None
    cfg["_hook_voice"] = hook
    prev_end = (0.15 + len(hook) / ak.SR + 0.3) if hook is not None else 0.3
    narr = []
    for (trig, text, key) in lines:
        x = narr_voice.say(text, cfg["narrator_voice"], cfg["narrator_length"])
        if x is None:
            print(f"[{cfg['name']}] avertissement : pas de voix de narrateur pour « {text} »", file=sys.stderr)
            x = np.zeros(int(0.8 * ak.SR))
        d = len(x) / ak.SR
        start = max(trig, prev_end + cfg["narr_gap_s"])
        narr.append({"start": start, "end": start + d, "text": text, "key": key, "audio": x})
        prev_end = start + d
    by_key = {n["key"]: n for n in narr}
    replies = []
    for (key, delay) in getattr(sim, "replies", []):
        if key in by_key:
            replies.append(by_key[key]["end"] + delay)
    return narr, replies


def in_narration(t, narr, pad=0.1):
    return any(n["start"] - pad <= t <= n["end"] + pad for n in narr)


def sub_chunks(text, n_words):
    words, out, cur = text.split(), [], []
    for w in words:
        cur.append(w)
        if len(cur) >= n_words or w[-1:] in ".!?,;:":
            out.append(" ".join(cur)); cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def subtitle_at(narr, t, n_words):
    for n in narr:
        if n["start"] <= t <= n["end"] + 0.15:
            chunks = sub_chunks(n["text"], n_words)
            total = sum(len(c) for c in chunks) or 1
            acc = n["start"]
            for c in chunks:
                d = (n["end"] - n["start"]) * len(c) / total
                if t <= acc + d:
                    return c
                acc += d
            return chunks[-1]
    return None


# ------------------------------------------------------------------ audio
def pitch(x, factor):
    """Transpose par rééchantillonnage : factor > 1 = plus aigu et plus court."""
    factor = max(0.5, min(2.0, factor))
    idx = np.arange(0, len(x) - 1, factor)
    return np.interp(idx, np.arange(len(x)), x)


def hero_word(text, cfg):
    """Un mot de Bounce : voix grave (transposée vers le bas), dit lentement, coupé au
    plus près du son. None si aucune voix n'est disponible."""
    sr = ak.SR
    v = ak.hero_voice(text, length_scale=cfg["hero_voice_length"])
    if v is None or not len(v):
        return None
    v = pitch(v, cfg["hero_voice_pitch"])
    idx = np.where(np.abs(v) > 0.02)[0]
    if not len(idx):
        return None
    v = v[max(0, idx[0] - 150):idx[-1] + int(0.03 * sr)].copy()
    n = min(int(0.03 * sr), len(v))
    v[-n:] *= np.linspace(1, 0, n)
    return v


def render_audio(events, total_dur, cfg, path, payoff_t=None, mood=None, narr=(), replies=()):
    """Le son vient des collisions : à chaque `hit`, Bounce dit son nom. Deux mots ne
    sont jamais plus rapprochés que hero_min_gap_s : sur une rafale de rebonds, seuls
    certains parlent, le mot reste toujours entier et compréhensible. Au payoff il
    réagit selon `mood` ("win" / "lose"). Rien d'autre, à part la voix de l'accroche."""
    sr = ak.SR
    buf = np.zeros(int((total_dur + 2.0) * sr))
    rng = np.random.default_rng(int(cfg["seed"]))
    name = hero_word(cfg["hero_name"], cfg)
    said = 0
    if name is None:
        print(f"[{cfg['name']}] avertissement : aucune voix pour Bounce, rebonds muets", file=sys.stderr)
    else:
        last = -9.0
        for (t0, kind, data) in events:
            if kind != "hit" or t0 - last < cfg["hero_min_gap_s"]:
                continue
            if in_narration(t0, narr):
                continue                      # il se tait pendant que le narrateur parle
            hv = cfg.get("_hook_voice")
            if hv is not None and t0 < 0.15 + len(hv) / sr + 0.1:
                continue                      # et pendant l'accroche
            ak.add(buf, pitch(name, 1.0 + rng.uniform(-0.03, 0.03)), t0, gain=cfg["hero_gain"])
            last = t0; said += 1
        for tr in replies:                    # ses répliques : pleines, après la phrase
            ak.add(buf, name, tr, gain=cfg.get("hero_reply_gain", 1.4)); said += 1
        if payoff_t is not None and mood in ("win", "lose"):
            w = hero_word(cfg["hero_win"] if mood == "win" else cfg["hero_lose"], cfg)
            if w is not None:
                tw = payoff_t + 0.15
                for n in narr:
                    if n["start"] - 0.1 <= tw <= n["end"] + 0.1:
                        tw = n["end"] + 0.25
                ak.add(buf, w, tw, gain=1.0)
    for n in narr:
        ak.add(buf, n["audio"], n["start"], gain=1.0)

    if cfg["hook_voice"] and cfg["hook_text"]:
        v = cfg.get("_hook_voice")
        if v is None:
            v = ak.hook_voice(cfg["hook_text"])
        if v is not None:
            n = min(len(v), len(buf))
            duck = np.ones(len(buf))
            duck[:n] = 0.42
            duck[n:n + int(0.3 * sr)] = np.linspace(0.42, 1.0, min(int(0.3 * sr), len(buf) - n))
            buf *= duck
            ak.add(buf, v, 0.15, gain=1.0)
        else:
            print(f"[{cfg['name']}] avertissement : aucune voix TTS, rendu sans accroche vocale",
                  file=sys.stderr)

    ak.write_wav(buf, path)
    return {"hero": cfg["hero_name"], "said": said, "reaction": mood}


# ------------------------------------------------------------------ vidéo
def layout_hook(cfg, S, W2, H2, free_until_y):
    """Découpe l'accroche à la largeur mesurée ; réduit la police jusqu'à tenir
    dans la bande libre entre hook_top et free_until_y (le haut de la scène)."""
    hook_top = H2 * cfg["hook_top"]
    band_h = free_until_y - hook_top
    lines, f, lh = [], None, 0
    for size in range(cfg["hook_font_size"], 33, -6):
        f = font(size * cfg["width"] / 1080 * S)
        lines, max_w = [], W2 * cfg["hook_width"]
        for word in (cfg["hook_text"] or "").upper().split():
            if lines and text_w(f, lines[-1] + " " + word) <= max_w:
                lines[-1] += " " + word
            else:
                lines.append(word)
        lh = int(size * 1.25 * cfg["width"] / 1080 * S)
        if len(lines) * lh <= band_h:
            break
    return lines, f, lh, hook_top


def hero_mood(sim):
    """Réaction de Bounce à la fin, si le thème la décrit : "win", "lose" ou None."""
    fn = getattr(sim, "hero_mood", None)
    if fn is None:
        return None
    try:
        m = fn()
    except Exception:
        return None
    return m if m in ("win", "lose") else None


def render_video(theme, sim, states, cfg, audio_path, out_path, events=(), narr=()):
    W, H, fps, S = cfg["width"], cfg["height"], cfg["fps"], cfg["supersample"]
    W2, H2 = W * S, H * S
    bg = tuple(cfg["bg_color"])
    scene_top = getattr(sim, "scene_top", 0.24) * H2     # sous quoi la scène commence
    lines, hf, lh, hook_top = layout_hook(cfg, S, W2, H2, scene_top - 30 * S)
    cf = font(cfg["counter_font_size"] * W / 1080 * S)
    wf = font(30 * W / 1080 * S)
    sf = font(cfg["sub_font_size"] * W / 1080 * S)
    wcol = tuple(int(b + (255 - b) * cfg["watermark_alpha"]) for b in bg)
    hits = [t0 for (t0, kind, _) in events if kind == "hit"]
    payoff_t, mood = getattr(sim, "payoff_t", None), hero_mood(sim)
    HERO["color"] = tuple(cfg["hero_color"])
    hi, last_hit, prev_pos = 0, -9.0, None

    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-i", audio_path,
         "-c:v", "libx264", "-preset", "slow", "-crf", "17",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", out_path],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for (t, snap) in states:
        # l'état de Bounce pour cette frame : choc juste après un rebond, réaction
        # après le payoff, sinon il s'en fout ; incliné dans le sens où il va
        while hi < len(hits) and hits[hi] <= t:
            last_hit = hits[hi]; hi += 1
        if payoff_t is not None and t >= payoff_t and mood:
            HERO["expr"] = mood
        elif t - last_hit < cfg["hero_shock_s"]:
            HERO["expr"] = "shock"
        else:
            HERO["expr"] = "calm"
        HERO["pos"] = None

        img = Image.new("RGB", (W2, H2), bg)
        dr = ImageDraw.Draw(img)
        theme_draw = sim.draw
        theme_draw(dr, snap, t, S)
        if HERO["pos"] is not None and prev_pos is not None:
            HERO["tilt"] = max(-0.35, min(0.35, (HERO["pos"][0] - prev_pos[0]) / S * 0.03))
        prev_pos = HERO["pos"]

        if cfg["watermark"]:
            dr.text((W2 / 2, H2 * cfg["watermark_y"]), cfg["watermark"], fill=wcol, anchor="mm", font=wf)
        if narr:
            line = subtitle_at(narr, t, cfg["sub_words"])
            if line:
                words, rows = line.split(), [""]
                for wd in words:
                    cand = (rows[-1] + " " + wd).strip()
                    if text_w(sf, cand) <= W2 * 0.86 or not rows[-1]:
                        rows[-1] = cand
                    else:
                        rows.append(wd)
                for i, row in enumerate(rows):
                    dr.text((W2 / 2, H2 * cfg["sub_y"] + (i - (len(rows) - 1) / 2) * sf.size * 1.2), row,
                            fill=(255, 255, 255), anchor="mm", font=sf,
                            stroke_width=max(2, int(sf.size * 0.09)), stroke_fill=(0, 0, 0))

        hook_on = bool(lines) and t < cfg["hook_text_s"]
        if cfg["show_counter"] and not hook_on:
            txt = sim.counter(snap) if hasattr(sim, "counter") else None
            if txt:
                dr.text((W2 / 2, H2 * cfg["counter_y"]), txt, fill=(230, 230, 240),
                        anchor="mm", font=cf)
        if hook_on:
            fade_s = 0.5
            a = 1.0 if t < cfg["hook_text_s"] - fade_s else (cfg["hook_text_s"] - t) / fade_s
            a = max(0.0, min(1.0, a))
            fill = tuple(int(255 * a) for _ in range(3))
            for i, line in enumerate(lines):
                dr.text((W2 / 2, hook_top + (i + 0.5) * lh), line, fill=fill, anchor="mm", font=hf)

        if S > 1:
            img = img.resize((W, H), Image.LANCZOS)
        proc.stdin.write(img.tobytes())
    proc.stdin.close(); proc.wait()


# ------------------------------------------------------------------ point d'entrée
def run(theme, argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(f"usage: python3 {theme.__file__} configs/<name>.json [--simulate]", file=sys.stderr)
        return 2
    cfg = load_config(argv[0], theme.DEFAULTS)
    states, events, dur, sim = simulate(theme, cfg)
    summary = {"name": cfg["name"], "duration_s": round(dur, 2), "payoff": bool(sim.payoff),
               "hits": sum(1 for e in events if e[1] == "hit"),
               "events": sum(1 for e in events if e[1] == "event")}
    if not sim.payoff and "--simulate" in argv:
        print(json.dumps(summary)); return 0
    if not sim.payoff:
        print(json.dumps({**summary, "error": "pas de payoff : ajuster la config"}), file=sys.stderr)
        return 1
    if dur < cfg["min_duration_s"]:
        print(json.dumps({**summary, "error": f"trop court (< {cfg['min_duration_s']} s)"}), file=sys.stderr)
        return 1
    narr, replies = build_narration(sim, cfg)
    total = dur
    if narr:
        total = max(dur, narr[-1]["end"] + cfg["narr_tail_s"])
    if total > dur and states:
        # la scène tient sa dernière image le temps que le narrateur finisse
        dt = 1.0 / cfg["fps"]
        t_last, last_snap = states[-1]
        t = t_last + dt
        while t < total:
            states.append((t, last_snap)); t += dt
    summary["narration"] = [{"t": round(n["start"], 2), "s": round(n["end"] - n["start"], 2), "text": n["text"]} for n in narr]
    summary["duration_s"] = round(total, 2)
    if "--simulate" in argv:
        print(json.dumps(summary, ensure_ascii=False)); return 0
    os.makedirs(os.path.join(ROOT, "output"), exist_ok=True)
    out = os.path.join(ROOT, "output", cfg["name"] + ".mp4")
    audio = tempfile.mktemp(suffix=".wav")
    try:
        summary["voice"] = render_audio(events, total, cfg, audio, getattr(sim, "payoff_t", None), hero_mood(sim), narr, replies)
        render_video(theme, sim, states, cfg, audio, out, events, narr)
    finally:
        if os.path.exists(audio):
            os.remove(audio)
    summary["out"] = os.path.relpath(out, ROOT)
    print(json.dumps(summary, ensure_ascii=False))
    return 0
