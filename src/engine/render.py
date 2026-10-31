"""
Moteur de rendu des histoires : une config JSON -> une vidéo verticale 1080x1920.

    python3 src/engine/render.py configs/<name>.json --simulate   # durées, sans encodage
    python3 src/engine/render.py configs/<name>.json              # -> output/<name>.mp4

Une histoire est une suite de scènes. Chaque scène a une narration (lue par la voix du
narrateur, et affichée en sous-titres) et des éléments dessinés (formes simples, texte),
qui peuvent apparaître, disparaître, se déplacer et changer de taille. La durée d'une
scène est celle de sa narration, plus une pause. Une accroche facultative est écrite en
haut de l'image et lue en premier.

Le format complet d'une config est décrit dans .claude/skills/ecrire/SKILL.md.
Ce moteur ne choisit rien à la place de l'histoire : ni style, ni personnage, ni
couleurs. Il dessine ce que la config demande.
"""
import os
import sys
import json
import math
import tempfile
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voice as vk  # noqa: E402
import bounce as hero  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULTS = {
    "width": 1080, "height": 1920, "fps": 30,
    "bg": [12, 12, 18],
    "voice": vk.DEFAULT_VOICE, "voice_length": 1.0,
    "hook_text": "", "hook_voice": True, "hook_gap_s": 0.3, "hook_extra_s": 0.6,
    "hook_size": 0.075, "hook_y": 0.07, "hook_color": [255, 255, 255],
    "subtitles": True, "sub_size": 0.062, "sub_y": 0.80, "sub_words": 5,
    "sub_color": [255, 255, 255], "sub_stroke": [0, 0, 0],
    "watermark": "", "watermark_y": 0.95, "watermark_alpha": 0.15,
    "scene_pause_s": 0.35, "end_hold_s": 0.8,
    "hero_gain": 0.95, "hero_min_gap_s": 0.9, "hero_shock_s": 0.3,
    "persist": [],
    "scenes": [],
}

FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
_font_cache = {}


def font(px):
    px = max(8, int(px))
    if px not in _font_cache:
        f = None
        for p in FONTS:
            if os.path.exists(p):
                f = ImageFont.truetype(p, px)
                break
        _font_cache[px] = f or ImageFont.load_default()
    return _font_cache[px]


def load_config(path):
    with open(path, encoding="utf-8") as fh:
        user = json.load(fh)
    cfg = dict(DEFAULTS)
    cfg.update(user)
    cfg.setdefault("name", os.path.splitext(os.path.basename(path))[0])
    return cfg


# ------------------------------------------------------------------ timeline

def build_timeline(cfg):
    """Synthétise les voix et place chaque scène dans le temps.
    Renvoie (audio_clips, scenes_t, total) : clips = [(t, array)], scenes_t = [(t0, t1, scene)]."""
    clips = []
    t = 0.0
    hook_end = 0.0
    if cfg["hook_text"] and cfg["hook_voice"]:
        x = vk.say(cfg["hook_text"], cfg["voice"], cfg["voice_length"])
        if x is not None:
            clips.append((0.0, x))
            t = len(x) / vk.SR + cfg["hook_gap_s"]
            hook_end = t
    scenes_t = []
    for i, sc in enumerate(cfg["scenes"]):
        start = 0.0 if i == 0 else t
        narr_at = t
        x = vk.say(sc.get("narration", ""), sc.get("voice", cfg["voice"]),
                   sc.get("voice_length", cfg["voice_length"]))
        dur = (len(x) / vk.SR) if x is not None else 0.0
        if x is not None:
            clips.append((narr_at, x))
        end = narr_at + dur + sc.get("pause_after", cfg["scene_pause_s"])
        end = max(end, start + sc.get("min_s", 0.0))
        sc["_narr"] = (narr_at, narr_at + dur)
        scenes_t.append((start, end, sc))
        t = end
    total = t + cfg["end_hold_s"]
    # les mots de Bounce : aux retombées de ses sauts (`hops`) et aux instants `say`
    w = hero.word()
    times = []
    for (a, b, sc) in scenes_t:
        for el in sc.get("elements", []):
            if el.get("type") != "bounce":
                continue
            for tl in hero_landings(el, b - a):
                times.append(a + tl)
            for ts in el.get("say", []):
                times.append(a + ts)
    for el in cfg["persist"]:
        if el.get("type") == "bounce":
            times += hero_landings(el, total) + list(el.get("say", []))
    # ses mots de saut se taisent sous la narration ; ses répliques (`say`) passent toujours, pleines
    narr = [sc.get("_narr", (0, 0)) for (_, _, sc) in scenes_t]
    says = set()
    for (a, b, sc) in scenes_t:
        for el in sc.get("elements", []):
            if el.get("type") == "bounce":
                says.update(round(a + ts, 3) for ts in el.get("say", []))
    said, last = 0, -9.0
    for tt in sorted(times):
        if w is None or tt - last < cfg["hero_min_gap_s"]:
            continue
        is_say = round(tt, 3) in says
        if not is_say and any(na - 0.1 <= tt <= nb + 0.1 for (na, nb) in narr):
            continue
        clips.append((tt, w * (1.0 if is_say else cfg["hero_gain"])))
        said += 1
        last = tt
    cfg["_hero_said"] = said
    cfg["_hook_until"] = max(hook_end + cfg["hook_extra_s"], cfg.get("hook_min_s", 0.0)) if cfg["hook_text"] else 0.0
    return clips, scenes_t, total


# ------------------------------------------------------------------ dessin

def ease(u, kind="inout"):
    u = min(1.0, max(0.0, u))
    if kind == "linear":
        return u
    if kind == "in":
        return u * u
    if kind == "out":
        return 1 - (1 - u) ** 2
    return u * u * (3 - 2 * u)


def lerp(a, b, u):
    return a + (b - a) * u


def element_state(el, ts, scene_len):
    """Propriétés de l'élément à l'instant ts (secondes depuis le début de sa scène),
    ou None s'il n'est pas visible."""
    t0 = el.get("t0", 0.0)
    t1 = el.get("t1", None)
    t1 = scene_len if t1 is None else t1
    if ts < t0 or ts > t1:
        return None
    p = {k: el.get(k) for k in ("x", "y", "r", "w", "h", "size", "angle", "scale")}
    p["angle"] = p["angle"] or 0.0
    p["scale"] = p["scale"] if p["scale"] is not None else 1.0
    to = el.get("to")
    if to:
        m0, m1 = el.get("move", [t0, t1])
        u = ease((ts - m0) / max(1e-6, m1 - m0), el.get("ease", "inout"))
        for k, v in to.items():
            if p.get(k) is not None:
                p[k] = lerp(p[k], v, u)
    bob = el.get("bob")
    if bob:
        p["y"] = p["y"] + bob * math.sin(2 * math.pi * ts / el.get("bob_s", 1.2))
    sw = el.get("swing")
    if sw:
        p["angle"] = p["angle"] + sw * math.sin(2 * math.pi * ts / el.get("swing_s", 1.2))
    fade = el.get("fade", 0.2)
    a = 1.0
    if fade > 0:
        a = min(1.0, (ts - t0) / fade, (t1 - ts) / fade) if el.get("t1") is not None else min(1.0, (ts - t0) / fade)
    p["alpha"] = max(0.0, min(1.0, a))
    return p


def hero_landings(el, scene_len):
    """Instants (depuis le début de la scène) où Bounce retombe, d'après `hops` :
    {"h": hauteur en fraction de la largeur, "period": durée d'un saut, "t0", "t1"}."""
    hp = el.get("hops")
    if not hp:
        return []
    t0 = hp.get("t0", el.get("t0", 0.0))
    t1 = hp.get("t1", el.get("t1", scene_len))
    t1 = scene_len if t1 is None else t1
    per = max(0.15, hp.get("period", 0.6))
    out, t = [], t0 + per
    while t <= t1 + 1e-6:
        out.append(t)
        t += per
    return out


def hero_state(el, p, ts, scene_len, shock_s):
    """Ajoute à `p` le saut en cours (décalage vertical) et l'expression du visage."""
    expr = el.get("expr", "calm")
    for (ta, e) in el.get("expr_at", []):
        if ts >= ta:
            expr = e
    hp = el.get("hops")
    dy = 0.0
    if hp:
        t0 = hp.get("t0", el.get("t0", 0.0))
        t1 = hp.get("t1", el.get("t1", scene_len))
        t1 = scene_len if t1 is None else t1
        per = max(0.15, hp.get("period", 0.6))
        if t0 <= ts <= t1:
            u = ((ts - t0) % per) / per
            dy = -hp.get("h", 0.06) * 4 * u * (1 - u)
            since = (ts - t0) % per
            k = int((ts - t0) // per)
            if k >= 1 and since < shock_s and expr == "calm":
                expr = "shock"
    for tsay in el.get("say", []):
        if 0 <= ts - tsay < shock_s + 0.2 and expr == "calm":
            expr = "shock"
    p["dy"] = dy
    p["expr"] = expr
    return p


def mix(col, bg, a):
    return tuple(int(bg[i] + (col[i] - bg[i]) * a) for i in range(3))


def rot(pts, cx, cy, deg):
    if not deg:
        return pts
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in pts]


def draw_element(dr, el, p, W, H, bg):
    col = mix(el.get("color", [255, 255, 255]), bg, p["alpha"])
    out = el.get("outline")
    out = mix(out, bg, p["alpha"]) if out else None
    lw = int(el.get("width", 0) * W) if el.get("width") else 0
    x, y, k = p["x"] * W, p["y"] * H, p["scale"]
    typ = el.get("type", "circle")
    if typ == "bounce":
        r = (p["r"] or 0.05) * W * k
        hero.draw(dr, x, y + p.get("dy", 0.0) * W, r, p.get("expr", "calm"),
                  math.radians(p["angle"]), p["alpha"], bg)
        return
    if typ in ("circle", "ellipse"):
        rx = (p["r"] if p["r"] is not None else p["w"] / 2) * W * k
        ry = (p["r"] if p["r"] is not None and typ == "circle" else (p["h"] or p["w"] or 0) / 2) * W * k
        dr.ellipse([x - rx, y - ry, x + rx, y + ry], fill=col, outline=out, width=lw)
    elif typ == "rect":
        w, h = p["w"] * W * k, p["h"] * W * k
        pts = [(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2), (x - w / 2, y + h / 2)]
        dr.polygon(rot(pts, x, y, p["angle"]), fill=col, outline=out, width=lw)
    elif typ == "poly":
        pts = [(x + dx * W * k, y + dy * W * k) for dx, dy in el["points"]]
        dr.polygon(rot(pts, x, y, p["angle"]), fill=col, outline=out, width=lw)
    elif typ == "line":
        pts = [(x + dx * W * k, y + dy * W * k) for dx, dy in el["points"]]
        dr.line(rot(pts, x, y, p["angle"]), fill=col, width=max(1, lw or int(0.006 * W)), joint="curve")
    elif typ == "text":
        f = font((p["size"] or 0.05) * W * k)
        dr.text((x, y), el.get("text", ""), fill=col, anchor="mm", font=f,
                stroke_width=int(el.get("stroke", 0) * W), stroke_fill=out or bg)


def wrap(text, f, maxw, dr):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if dr.textlength(test, font=f) <= maxw or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def sub_chunks(text, n_words):
    """Découpe la narration en morceaux de sous-titres, aux ponctuations ou tous les n mots."""
    words, out, cur = text.split(), [], []
    for w in words:
        cur.append(w)
        if len(cur) >= n_words or w[-1:] in ".!?,;:":
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def subtitle_at(sc, t, n_words):
    a, b = sc.get("_narr", (0, 0))
    text = sc.get("narration", "")
    if not text or t < a or t > b + 0.15:
        return None
    chunks = sub_chunks(text, n_words)
    total = sum(len(c) for c in chunks) or 1
    acc = a
    for c in chunks:
        d = (b - a) * len(c) / total
        if t <= acc + d:
            return c
        acc += d
    return chunks[-1]


# ------------------------------------------------------------------ rendu

def render(cfg, out_path):
    W, H, fps = cfg["width"], cfg["height"], cfg["fps"]
    clips, scenes_t, total = build_timeline(cfg)
    n_frames = int(math.ceil(total * fps))

    buf = np.zeros(int(total * vk.SR) + vk.SR)
    for at, x in clips:
        vk.add(buf, x, at)
    wav = tempfile.mktemp(suffix=".wav")
    vk.write_wav(buf, wav)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
         "-i", wav, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
         "-c:a", "aac", "-b:a", "160k", "-shortest", out_path],
        stdin=subprocess.PIPE)

    hf = font(cfg["hook_size"] * W)
    sf = font(cfg["sub_size"] * W)
    wf = font(0.028 * W)
    for fi in range(n_frames):
        t = fi / fps
        k = next((i for i, (a, b, _) in enumerate(scenes_t) if a <= t < b), len(scenes_t) - 1)
        if not scenes_t:
            break
        s0, s1, sc = scenes_t[k]
        bg = tuple(sc.get("bg", cfg["bg"]))
        img = Image.new("RGB", (W, H), bg)
        dr = ImageDraw.Draw(img)

        layers = [(el, t) for el in cfg["persist"]] + [(el, t - s0) for el in sc.get("elements", [])]
        layers.sort(key=lambda e: e[0].get("z", 0))
        for el, ts in layers:
            sl = total if el in cfg["persist"] else s1 - s0
            p = element_state(el, ts, sl)
            if p:
                if el.get("type") == "bounce":
                    hero_state(el, p, ts, sl, cfg["hero_shock_s"])
                draw_element(dr, el, p, W, H, bg)

        if cfg["watermark"]:
            wcol = mix([255, 255, 255], bg, cfg["watermark_alpha"])
            dr.text((W / 2, H * cfg["watermark_y"]), cfg["watermark"], fill=wcol, anchor="mm", font=wf)

        if cfg["subtitles"]:
            line = subtitle_at(sc, t, cfg["sub_words"])
            if line:
                for i, ln in enumerate(wrap(line, sf, W * 0.86, dr)):
                    dr.text((W / 2, H * cfg["sub_y"] + i * sf.size * 1.2), ln,
                            fill=tuple(cfg["sub_color"]), anchor="mm", font=sf,
                            stroke_width=max(2, int(sf.size * 0.09)), stroke_fill=tuple(cfg["sub_stroke"]))

        if cfg["hook_text"] and t < cfg["_hook_until"]:
            for i, ln in enumerate(wrap(cfg["hook_text"].upper(), hf, W * 0.88, dr)):
                dr.text((W / 2, H * cfg["hook_y"] + (i + 0.5) * hf.size * 1.15), ln,
                        fill=tuple(cfg["hook_color"]), anchor="mm", font=hf,
                        stroke_width=max(2, int(hf.size * 0.08)), stroke_fill=(0, 0, 0))

        proc.stdin.write(img.tobytes())
    proc.stdin.close()
    proc.wait()
    os.remove(wav)
    return total, scenes_t


def summary(cfg, total, scenes_t):
    return {"name": cfg["name"], "duration_s": round(total, 2), "scenes": len(scenes_t),
            "scene_s": [round(b - a, 2) for a, b, _ in scenes_t],
            "hook_until_s": round(cfg.get("_hook_until", 0.0), 2),
            "hero_said": cfg.get("_hero_said", 0)}


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    cfg = load_config(argv[0])
    if "--simulate" in argv:
        _, scenes_t, total = build_timeline(cfg)
        print(json.dumps(summary(cfg, total, scenes_t), ensure_ascii=False))
        return 0
    out = os.path.join(ROOT, "output", cfg["name"] + ".mp4")
    total, scenes_t = render(cfg, out)
    print(json.dumps({**summary(cfg, total, scenes_t), "mp4": out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
