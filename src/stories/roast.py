"""
Prototype « le roast » : Bounce rebondit, et le narrateur passe la minute à l'insulter,
à lui ordonner d'arrêter, puis à lui jeter dessus tout ce qu'il trouve (enclume, piano,
tapette, botte, seize tonnes). Bounce encaisse, dit son nom, et repart. Il ne s'arrête
qu'au moment où on lui permet de continuer.

Les gros mots sont écrits étoilés (sous-titres, accroche) et remplacés à l'oral par un
bip de synthèse (sinusoïde ~1 kHz) : décision du propriétaire pour cette vidéo. Le bip
est fabriqué ici, en code : aucun fichier audio. La voix du narrateur passe par
`voice.say`, que ce module enveloppe : base.py n'est pas modifié.

Toute la chorégraphie (rebonds, répliques, chutes d'objets) est calculée d'avance sur une
seule horloge, à partir de la durée réelle des répliques : chaque réplique tombe dans
l'arc d'un rebond, entre deux « Bounce ».

    python3 src/stories/roast.py configs/<name>.json [--simulate]
"""
import math, sys, os, re
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim
from listkit import Chapter, glow, mix
import voice as narr_voice
import audio_kit as ak

SR = narr_voice.SR

# ------------------------------------------------------------------ le bip
_orig_say = narr_voice.say
_bleep_memo = {}
STAR = re.compile(r"[A-Za-z]*\*[A-Za-z*]*")


def beep(dur, sr=SR, f=1000.0, amp=0.42, fade=0.012):
    n = max(1, int(dur * sr))
    t = np.arange(n) / sr
    x = amp * np.sin(2 * np.pi * f * t)
    k = min(int(fade * sr), n // 2)
    if k > 0:
        ramp = np.linspace(0.0, 1.0, k)
        x[:k] *= ramp
        x[-k:] *= ramp[::-1]
    return x


def _trim(x, thr=0.02, keep=0.03):
    idx = np.where(np.abs(x) > thr)[0]
    if not len(idx):
        return np.zeros(0)
    a = max(0, idx[0] - int(keep * SR))
    b = min(len(x), idx[-1] + int(keep * SR))
    return x[a:b]


def bleep_len(word):
    """La durée du bip : à peu près celle du mot qu'il cache (lettres, étoiles comprises)."""
    letters = len(re.sub(r"[^A-Za-z*]", "", word))
    return float(min(0.55, max(0.28, 0.08 + 0.045 * letters)))


def roast_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    """`voice.say`, avec les mots étoilés remplacés par un bip. Une phrase sans étoile
    passe telle quelle."""
    if not text or "*" not in text:
        return _orig_say(text, voice, length_scale, sr)
    key = (text, voice, length_scale, sr)
    if key in _bleep_memo:
        return _bleep_memo[key]
    parts, pos = [], 0
    for m in STAR.finditer(text):
        before = text[pos:m.start()].strip()
        if before and re.search(r"[A-Za-z]", before):
            parts.append(("say", before))
        parts.append(("beep", m.group(0)))
        pos = m.end()
    after = text[pos:].strip()
    if after and re.search(r"[A-Za-z]", after):
        parts.append(("say", after))
    out = [np.zeros(int(0.02 * sr))]
    for kind, s in parts:
        if kind == "say":
            x = _orig_say(s, voice, length_scale, sr)
            if x is None:
                continue
            out.append(_trim(np.asarray(x, dtype=np.float64)))
            out.append(np.zeros(int(0.025 * sr)))
        else:
            out.append(beep(bleep_len(s), sr))
            out.append(np.zeros(int(0.035 * sr)))
    x = np.concatenate(out)
    _bleep_memo[key] = x
    return x


narr_voice.say = roast_say

# ------------------------------------------------------------------ le mot de Bounce
# piper ne rend pas « Bounce » deux fois à la même longueur (0,67 à plus de 0,9 s) : la
# chorégraphie est calée sur WL, on garde donc un tirage qui tient dedans, une fois par
# processus. Même voix, même mot : seul le tirage est choisi.
_orig_hero_word = base.hero_word
_hero_memo = {}
WORD_MAX = 0.78


def steady_hero_word(text, cfg):
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    if key not in _hero_memo:
        best = None
        for _ in range(12):
            v = _orig_hero_word(text, cfg)
            if v is None:
                break
            if best is None or len(v) < len(best):
                best = v
            if len(v) / ak.SR <= WORD_MAX:
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word


# ------------------------------------------------------------------ le décor
W, H = 1080, 1920
R = 180.0                      # Bounce : 360 px de diamètre
G = 1350.0
FLOOR = 1640.0
YC = FLOOR - R                 # centre de Bounce posé au sol
H_MAX = 920.0                  # le plus haut rebond : il reste sous les sous-titres
TMAX = 2 * math.sqrt(2 * H_MAX / G)
WL = 0.82                      # le « Bounce » le plus long que piper rend (0,67 à 0,80 s mesurés)
PRE = 0.12                     # fin du « Bounce » -> début de la réplique (base.py écarte ses mots de 0,1 s de la voix)
POST = 0.14                    # fin de la réplique -> retombée suivante
SQ_A, SQ_B, SQ_AFTER = 0.2, 0.05, 0.1    # écrasement d'un rebond ordinaire
WALL = (24, 24, 36)
FLOORC = (40, 36, 50)
STEEL = (82, 86, 102)
BLOCK = (112, 112, 122)
WOODP = (92, 50, 40)
SWAT = (66, 150, 86)
LEATHER = (90, 58, 38)
IRON = (66, 68, 82)


def shape_rect(w, h):
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


# la forme convexe de chaque objet qui tombe, autour de son centre
SHAPES = {
    "block": shape_rect(230, 110),
    "anvil": [(-175, -75), (150, -75), (150, -35), (118, 75), (-118, 75), (-175, -45)],
    "piano": shape_rect(430, 330),
    "weight": [(-190, -180), (190, -180), (280, 180), (-280, 180)],
}
SHAKE = {"block": 10.0, "anvil": 16.0, "piano": 20.0, "weight": 30.0, "boot": 14.0, "swatter": 12.0}


# ------------------------------------------------------------------ le plan
class Plan:
    """Toute la vidéo sur une horloge : les morceaux de trajectoire de Bounce, ses
    contacts, les répliques, les objets, les chapitres, la caméra."""

    def __init__(self, cfg):
        self.cfg = cfg
        hv = base.hook_audio(cfg)
        self.hook_end = 0.15 + (len(hv) / ak.SR if hv is not None else 2.0)
        self.segs = []          # (t0, t1, kind, data)
        self.contacts = []      # dict(t, x, kind, voiced, amp)
        self.lines = []         # dict(start, end, text, key, ch)
        self.objs = []
        self.chapters = []      # dict(start, chute)
        self.cracks = []        # (t, x, seed)
        self.shakes = []        # (t, amplitude)
        self.zooms = []         # (t0, t1, z0, z1, cx, cy)
        self.t, self.x = 0.0, 420.0
        self.last_voiced = False
        self.tv = -9.0
        self.n_line = 0
        self.end = None
        self.rng = np.random.default_rng(int(cfg["seed"]) + 7)

    def dur(self, text):
        x = narr_voice.say(text, self.cfg["narrator_voice"], self.cfg["narrator_length"])
        return (len(x) / SR) if x is not None else 0.8

    # ---- Bounce
    def arc(self, t1, x1=None, kind="floor", voiced=True, amp=SQ_A):
        x1 = self.x if x1 is None else x1
        self.segs.append((self.t, t1, "arc", (self.x, x1)))
        self.t, self.x = t1, x1
        self.contacts.append({"t": t1, "x": x1, "kind": kind, "voiced": voiced, "amp": amp})
        self.last_voiced = voiced
        if voiced:
            self.tv = t1
        return t1

    def wander(self):
        """Où retombe le prochain rebond : il dérive d'un côté à l'autre."""
        lo, hi = 300.0, 640.0
        x = self.x + float(self.rng.uniform(0.45, 1.0)) * 170.0 * (1 if self.rng.random() < 0.5 else -1)
        if x < lo or x > hi:
            x = 2 * self.x - x
        return float(min(hi, max(lo, x)))

    def hop(self, T=0.95, x1=None, **kw):
        return self.arc(self.t + T, self.wander() if x1 is None else x1, **kw)

    def to(self, t1, x1=None, voiced=True, **kw):
        """Retombe à t1 ; un arc trop long pour le cadre passe par un rebond
        intermédiaire, sous la voix (muet)."""
        T = t1 - self.t
        if T > TMAX:
            self.arc(self.t + T / 2, self.wander(), voiced=False)
        return self.arc(t1, self.wander() if x1 is None else x1, voiced=voiced, **kw)

    def dwell(self, t1, profile):
        self.segs.append((self.t, t1, "dwell", (self.x, profile)))
        self.t = t1

    # ---- la voix
    def line(self, text, title=False, after=None):
        if after is not None:
            start = after
        elif self.last_voiced:
            start = self.tv + WL + PRE
        else:
            start = max(self.t, self.tv + WL) + 0.25
        d = self.dur(text)
        if title:
            if len(self.chapters) > 1:
                self.chapters[-1]["start"] = start - 0.2
            key = "title"
        else:
            self.n_line += 1
            key = f"l{self.n_line}"
        self.lines.append({"start": start, "end": start + d, "text": text, "key": key, "ch": len(self.chapters) - 1})
        return start + d

    def say(self, text, title=False, x1=None, extra=0.0):
        """Une réplique dans l'arc d'un rebond : Bounce retombe juste après."""
        e = self.line(text, title)
        return self.to(e + POST + extra, x1)

    def chapter(self):
        self.chapters.append({"start": None, "chute": None})

    def chute(self, t=None):
        self.chapters[-1]["chute"] = self.t if t is None else t


def impact(p, kind, out=1, big=False):
    """L'objet tombe sur Bounce au moment où il touche le sol (la retombée qu'on vient de
    poser), l'écrase un instant et repart en l'air, éjecté hors du cadre ; Bounce, lui,
    rebondit."""
    tc = p.t
    comp, decomp = 0.1, 0.14
    p.objs.append({"kind": kind, "x": p.x, "tc": tc, "launch": tc + comp, "vx": out * (520 if big else 700),
                   "vy": -2400.0, "w": out * (3.0 if big else 6.0)})
    p.contacts[-1]["amp"] = 0
    p.dwell(tc + comp + decomp, ("impact", tc, comp, decomp, 0.5))
    p.cracks.append((tc, p.x, len(p.cracks)))
    p.shakes.append((tc, SHAKE[kind]))
    p.chute(tc)


def pin(p, kind, lines, tremble=0.0, zoom=None):
    """L'objet l'écrase et reste sur lui ; le narrateur jubile ; Bounce ressort d'un coup
    (et l'objet part au ciel)."""
    tc = p.t
    p.contacts[-1]["amp"] = 0
    e = None
    for k, txt in enumerate(lines):
        e = p.line(txt) if k == 0 else p.line(txt, after=e + 0.5)
    tp = e + POST + tremble
    p.objs.append({"kind": kind, "x": p.x, "tc": tc, "launch": tp - 0.05, "vx": 240.0, "vy": -2450.0,
                   "w": 0.0 if kind == "weight" else 2.2, "tremble": (tp - tremble, tp) if tremble else None})
    p.dwell(tp + 0.16, ("pin", tc, tp, 0.45))
    p.cracks.append((tc, p.x, len(p.cracks)))
    p.shakes.append((tc, SHAKE[kind]))
    p.contacts.append({"t": tp, "x": p.x, "kind": "floor", "voiced": True, "amp": 0})
    p.last_voiced, p.tv = True, tp
    if zoom:
        p.zooms.append((tc + 0.5, tp - 0.05, 1.0, zoom, p.x, FLOOR))
        p.zooms.append((tp - 0.05, tp + 0.25, zoom, 1.0, p.x, FLOOR))
    p.chute(tc)
    return tp


def swat(p):
    """La tapette géante arrive de la droite et le cueille en l'air, quand son « Bounce »
    est fini : il part contre le mur de gauche, puis retombe."""
    tc, x0 = p.t, p.x
    T = 2.1
    v0 = G * T / 2
    u = WL + 0.1
    ts = tc + u
    ys = YC - (v0 * u - 0.5 * G * u * u)
    vy_s = -(v0 - G * u)
    p.segs.append((tc, ts, "arc_part", (x0, x0, T)))
    vx = -800.0
    vy = vy_s * 0.4 - 260.0
    tw = ts + (x0 - R) / -vx
    yw = ys + vy * (tw - ts) + 0.5 * G * (tw - ts) ** 2
    vyw = vy + G * (tw - ts)
    p.segs.append((ts, tw, "free", (x0, ys, vx, vy)))
    p.contacts.append({"t": ts, "x": x0, "kind": "swat", "voiced": True, "amp": 0})
    p.contacts.append({"t": tw, "x": R, "kind": "wall", "voiced": False, "amp": 0.2})
    vx2 = 300.0
    a, b, c = 0.5 * G, vyw, yw - YC
    tf = (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)
    p.segs.append((tw, tw + tf, "free", (R, yw, vx2, vyw)))
    p.t, p.x = tw + tf, R + vx2 * tf
    p.contacts.append({"t": p.t, "x": p.x, "kind": "floor", "voiced": True, "amp": SQ_A})
    p.last_voiced, p.tv = True, p.t
    p.objs.append({"kind": "swatter", "ts": ts, "xs": x0 + R, "ys": ys})
    p.shakes.append((ts, SHAKE["swatter"]))
    p.chute(ts)


def stomp(p, n):
    """La botte : elle l'écrase à chaque retombée, n fois ; il rebondit entre deux."""
    p.contacts[-1]["amp"] = 0
    times, xs = [p.t], [p.x]
    comp, hold, decomp = 0.08, 0.04, 0.12
    p.chute(p.t)
    for k in range(n):
        t0 = times[-1]
        p.dwell(t0 + comp + hold + decomp, ("impact", t0, comp + hold, decomp, 0.45))
        p.cracks.append((t0, p.x, len(p.cracks)))
        p.shakes.append((t0, SHAKE["boot"]))
        if k < n - 1:
            times.append(p.arc(p.t + 0.95, p.x + 14.0, amp=0))
            xs.append(p.x)
    p.objs.append({"kind": "boot", "times": times, "xs": xs, "dwell": comp + hold + decomp})


def build(cfg):
    p = Plan(cfg)
    p.chapter()
    p.chapters[-1]["start"] = 0.0
    # 0 s : il tombe déjà ; il claque le sol sous l'accroche et repart
    p.segs.append((0.0, 0.32, "free", (420.0, YC - 0.5 * G * 0.32 ** 2 - 420 * 0.32, 0.0, 420.0)))
    p.t = 0.32
    p.contacts.append({"t": 0.32, "x": 420.0, "kind": "floor", "voiced": False, "amp": SQ_A})
    p.arc(p.hook_end + 0.22, 470.0)
    # 1. le parpaing
    p.say("Stop bouncing.", title=True, x1=520.0)
    impact(p, "block", out=1)
    p.say("You little sh*t.")
    p.hop()
    # 2. l'enclume
    p.chapter()
    p.say("Right. Anvil.", title=True)
    p.hop(1.0, 430.0)
    pin(p, "anvil", ["Stop saying your f*cking name!"], zoom=1.12)
    p.say("Oh, f*ck off.")
    p.hop()
    # 3. le piano
    p.chapter()
    p.say("Piano, d*ckhead.", title=True)
    p.hop(1.05)
    p.hop(1.05, 560.0)
    impact(p, "piano", out=-1, big=True)
    p.say("What the f*ck?")
    p.say("Nobody likes you.")
    p.hop()
    # 4. la tapette
    p.chapter()
    p.say("Hold still, a**hole.", title=True, x1=600.0)
    swat(p)
    p.say("Why won't you stop?")
    p.say("Useless sh*t.")
    # 5. la botte
    p.chapter()
    p.say("Boot.", title=True)
    p.hop(1.3, 470.0)
    stomp(p, 3)
    p.say("Why are you still round?")
    p.say("F*ck you.")
    # 6. seize tonnes
    p.chapter()
    p.say("Sixteen tons.", title=True)
    p.hop(1.0)
    p.hop(1.1, 450.0)
    pin(p, "weight", ["Finally.", "Peace and f*cking quiet."], tremble=0.5, zoom=1.16)
    p.say("Oh, f*ck me.")
    # 7. il abandonne
    p.chapter()
    p.say("Fine. Bounce forever.", title=True)
    e = p.line("See if I care.")
    ts = p.arc(e + POST + 0.05, 440.0, kind="stop", voiced=False, amp=0.12)
    e = p.line("...Bounce?", after=ts + 1.1)
    p.zooms.append((ts + 0.05, e + 0.1, 1.0, 1.5, 440.0, FLOOR, "lin"))
    p.segs.append((ts, e + 0.12, "still", (p.x,)))
    p.t = e + 0.12
    tc = p.arc(e + 0.12 + 0.72, 445.0)
    p.chute(tc)
    p.chapters[-1]["smug"] = tc
    p.zooms.append((tc + 0.5, tc + 0.9, 1.5, 1.0, 440.0, FLOOR))
    e = p.line("Mother-f*cker.")
    p.arc(e + POST + 0.05, 470.0)
    p.end = p.t
    # après la fin : il repart, la vidéo boucle sur son premier rebond
    p.segs.append((p.t, p.t + 3.0, "arc", (p.x, p.x)))
    return p


# ------------------------------------------------------------------ l'état à un instant
def lin(u):
    return max(0.0, min(1.0, u))


def ease(u):
    u = lin(u)
    return u * u * (3 - 2 * u)


class World:
    """Lit le plan : où est Bounce, comment il est écrasé, où sont les objets, la caméra."""

    def __init__(self, plan):
        self.p = plan
        self.segs = sorted(plan.segs, key=lambda s: s[0])
        for o in plan.objs:
            if o["kind"] == "swatter":
                continue
            tc = o["tc"] if "tc" in o else o["times"][0]
            vb = 0.0
            for (t0, t1, k, d) in self.segs:
                if k == "arc" and abs(t1 - tc) < 1e-6:
                    vb = G * (t1 - t0) / 2
            o["vc"] = min(2450.0, vb + 650.0)    # il tombe un peu plus vite que Bounce : il le rattrape au sol

    def seg(self, T):
        for s in self.segs:
            if s[0] <= T < s[1]:
                return s
        return self.segs[-1] if T >= self.segs[-1][0] else self.segs[0]

    def bounce(self, T):
        """(x, y, sx, sy) : le centre de Bounce et son écrasement."""
        t0, t1, k, d = self.seg(T)
        tau = T - t0
        sx = sy = 1.0
        if k in ("arc", "arc_part"):
            x0, x1 = d[0], d[1]
            Tt = (t1 - t0) if k == "arc" else d[2]
            v0 = G * Tt / 2
            h = max(0.0, v0 * tau - 0.5 * G * tau * tau)
            x, y = x0 + (x1 - x0) * min(1.0, tau / Tt), YC - h
        elif k == "free":
            x0, y0, vx, vy = d
            x, y = x0 + vx * tau, y0 + vy * tau + 0.5 * G * tau * tau
        elif k == "dwell":
            x, prof = d
            sy = self.profile(prof, T)
            sx = 1.0 + (1.0 - sy) * 0.9
            return x, FLOOR - R * sy, sx, sy
        else:
            x, y = d[0], YC
        for c in self.p.contacts:
            if c["amp"] <= 0 or not (c["t"] - SQ_B <= T <= c["t"] + SQ_AFTER):
                continue
            kk = lin(1 - (c["t"] - T) / SQ_B if T < c["t"] else 1 - (T - c["t"]) / SQ_AFTER)
            if c["kind"] == "wall":
                sx = 1 - c["amp"] * kk
                sy = 1 + 0.6 * c["amp"] * kk
                x = max(0.0, x - R) + R * sx
            else:
                sy = 1 - c["amp"] * kk
                sx = 1 + 0.8 * c["amp"] * kk
                y = min(FLOOR, y + R) - R * sy
        return x, y, sx, sy

    def profile(self, prof, T):
        if prof[0] == "impact":
            _, tc, comp, decomp, smin = prof
            u = T - tc
            if u < comp:
                return 1 - (1 - smin) * lin(u / comp)
            return smin + (1 - smin) * lin((u - comp) / decomp)
        _, tc, tp, smin = prof
        if T < tp:
            s = 1 - (1 - smin) * lin((T - tc) / 0.1)
            if T > tc + 0.1:
                s += 0.035 * math.sin(2 * math.pi * 1.6 * (T - tc - 0.1))   # il respire là-dessous
            return s
        return smin + (1 - smin) * lin((T - tp) / 0.16)

    def top(self, T):
        x, y, sx, sy = self.bounce(T)
        return y - R * sy

    def objects(self, T):
        """[(id, kind, x, y, a)] ; y est le bas de la semelle pour la botte, le centre sinon."""
        out = []
        for i, o in enumerate(self.p.objs):
            st = self.obj(o, T)
            if st is not None:
                out.append((i, o["kind"]) + st)
        return out

    def obj(self, o, T):
        k = o["kind"]
        if k == "swatter":
            ts, xs, ys = o["ts"], o["xs"], o["ys"]
            # elle passe la tête par la droite, recule pour prendre son élan, et frappe
            if T < ts - 0.9:
                return None
            if T < ts - 0.5:
                xl = W + 20 - (W + 20 - 920) * ease((T - ts + 0.9) / 0.4)
            elif T < ts - 0.12:
                xl = 920 + 60 * ease((T - ts + 0.5) / 0.38)
            elif T < ts:
                xl = 980 + (xs - 980) * (T - ts + 0.12) / 0.12
            else:
                xl = xs + 1100.0 * (T - ts)
            if xl > W + 40:
                return None
            return (xl, ys, 0.0)
        if k == "boot":
            return self.boot(o, T)
        hb = max(dy for dx, dy in SHAPES[k])
        tc, vc = o["tc"], o["vc"]
        if T < tc:
            tau = tc - T
            if tau > vc / G:
                return None
            yb = (FLOOR - 2 * R) - vc * tau + 0.5 * G * tau * tau
            return (o["x"], min(yb, self.top(T)) - hb, 0.0)
        if T < o["launch"]:
            dx = 0.0
            tr = o.get("tremble")
            if tr and tr[0] <= T:
                dx = 7.0 * math.sin(70.0 * (T - tr[0]))
            return (o["x"] + dx, self.top(T) - hb, 0.0)
        u = T - o["launch"]
        y = self.top(o["launch"]) - hb + o["vy"] * u
        x = o["x"] + o["vx"] * u
        if y + hb + 60 < 0 or x < -450 or x > W + 450:
            return None
        return (x, y, o["w"] * u)

    def boot(self, o, T):
        times, dw = o["times"], o["dwell"]
        t0 = times[0]
        if T < t0:
            tau = t0 - T
            if tau > o["vc"] / G:
                return None
            yb = (FLOOR - 2 * R) - o["vc"] * tau + 0.5 * G * tau * tau
            return (o["xs"][0], min(yb, self.top(T)), 0.0)
        for k, tk in enumerate(times):
            if tk <= T < tk + dw:
                return (o["xs"][k], self.top(T), 0.0)
            if k + 1 < len(times) and tk + dw <= T < times[k + 1]:
                u = (T - tk - dw) / (times[k + 1] - tk - dw)
                x = o["xs"][k] + (o["xs"][k + 1] - o["xs"][k]) * u
                return (x, self.top(T) - 240.0 * math.sin(math.pi * u), 0.0)
        te = times[-1] + dw
        yb = self.top(te) - 2300.0 * (T - te)
        if yb < -10:
            return None
        return (o["xs"][-1], yb, 0.0)

    def camera(self, T):
        """(cx, cy, z, ox, oy) : le point fixe du zoom, le zoom, le tremblement."""
        cx, cy, z = W / 2, H / 2, 1.0
        for zm in self.p.zooms:
            t0, t1, z0, z1, zx, zy = zm[:6]
            if t0 <= T:
                f = lin if len(zm) > 6 else ease
                z = z0 + (z1 - z0) * f((T - t0) / max(1e-6, t1 - t0))
                cx, cy = zx, zy
        ox = oy = 0.0
        for (t, a) in self.p.shakes:
            u = T - t
            if 0 <= u < 0.45:
                k = a * math.exp(-u / 0.11)
                ox += k * math.sin(2 * math.pi * 17 * u)
                oy += k * math.cos(2 * math.pi * 13 * u)
        return cx, cy, z, ox, oy


def rot(pts, x, y, a):
    ca, sa = math.cos(a), math.sin(a)
    return [(x + dx * ca - dy * sa, y + dx * sa + dy * ca) for dx, dy in pts]


BOOT_HULL = [(-185, 0), (190, 0), (190, -720), (-30, -720), (-185, -230)]
SWAT_HEAD = 400.0


def obj_polys(kind, x, y, a):
    """Les formes d'un objet dans l'image (le premier polygone sert de corps)."""
    if kind == "swatter":
        hh = SWAT_HEAD / 2
        head = [(x, y - hh), (x + SWAT_HEAD, y - hh), (x + SWAT_HEAD, y + hh), (x, y + hh)]
        mx = x + SWAT_HEAD / 2
        handle = [(mx - 22, y - hh - 1400), (mx + 22, y - hh - 1400), (mx + 22, y - hh), (mx - 22, y - hh)]
        return [head, handle]
    if kind == "boot":
        return [[(x + dx, y + dy) for dx, dy in BOOT_HULL]]
    return [rot(SHAPES[kind], x, y, a)]


# ------------------------------------------------------------------ dessin
class View:
    """Coordonnées du monde -> image : supersampling, zoom, tremblement."""

    def __init__(self, S, cam):
        self.S = S
        self.cx, self.cy, self.z, self.ox, self.oy = cam

    def X(self, x):
        return (self.cx + (x - self.cx) * self.z + self.ox) * self.S

    def Y(self, y):
        return (self.cy + (y - self.cy) * self.z + self.oy) * self.S

    def L(self, l):
        return l * self.z * self.S

    def pts(self, pts):
        return [(self.X(x), self.Y(y)) for x, y in pts]

    def box(self, x0, y0, x1, y1):
        return [self.X(x0), self.Y(y0), self.X(x1), self.Y(y1)]


def draw_bounce(dr, V, x, y, sx, sy):
    hc = base.HERO["color"]
    rx, ry = R * sx, R * sy
    dr.ellipse(V.box(x - rx * 1.5, y - ry * 1.5, x + rx * 1.5, y + ry * 1.5), fill=mix(WALL, dim(hc, 0.6), 0.3))
    dr.ellipse(V.box(x - rx, y - ry, x + rx, y + ry), fill=hc)
    base.hero_face(dr, V.X(x), V.Y(y), V.L(R * min(sx, sy, 1.0)))
    if base.HERO["pos"] is None:
        base.HERO["pos"] = (V.X(x), V.Y(y))


def draw_obj(dr, V, kind, x, y, a):
    w5 = max(1, int(V.L(5)))
    if kind == "block":
        dr.polygon(V.pts(rot(SHAPES["block"], x, y, a)), fill=BLOCK, outline=dim(BLOCK, 0.6), width=w5)
        for hx in (-58, 58):
            cx, cy = rot([(hx, 0)], x, y, a)[0]
            dr.polygon(V.pts(rot(shape_rect(64, 52), cx, cy, a)), fill=dim(BLOCK, 0.42))
    elif kind == "anvil":
        body = [(-175, -75), (150, -75), (150, -35), (70, -12), (70, 30), (118, 75), (-118, 75), (-70, 30), (-70, -12), (-175, -45)]
        dr.polygon(V.pts(rot(body, x, y, a)), fill=STEEL, outline=dim(STEEL, 0.55), width=w5)
        dr.polygon(V.pts(rot([(-170, -75), (150, -75), (150, -62), (-170, -62)], x, y, a)), fill=(150, 156, 172))
    elif kind == "piano":
        dr.polygon(V.pts(rot(shape_rect(430, 330), x, y, a)), fill=WOODP, outline=dim(WOODP, 0.55), width=w5)
        dr.polygon(V.pts(rot([(-215, -165), (215, -165), (215, -138), (-215, -138)], x, y, a)), fill=dim(WOODP, 1.4))
        dr.polygon(V.pts(rot([(-200, -10), (200, -10), (200, 40), (-200, 40)], x, y, a)), fill=(228, 224, 216))
        for k in range(14):
            if k % 7 in (2, 6):
                continue
            kx = -200 + 400 * (k + 0.75) / 14
            dr.polygon(V.pts(rot([(kx - 7, -10), (kx + 7, -10), (kx + 7, 18), (kx - 7, 18)], x, y, a)), fill=(20, 18, 22))
        dr.polygon(V.pts(rot([(-160, 70), (160, 70), (160, 140), (-160, 140)], x, y, a)), fill=dim(WOODP, 0.75))
    elif kind == "weight":
        dr.ellipse(V.box(x - 70, y - 180 - 100, x + 70, y - 180 + 12), outline=IRON, width=max(2, int(V.L(26))))
        dr.polygon(V.pts(rot(SHAPES["weight"], x, y, a)), fill=IRON, outline=dim(IRON, 0.55), width=w5)
        dr.text((V.X(x), V.Y(y + 14)), "16 T", fill=(196, 198, 210), anchor="mm", font=base.font(V.L(150)))
    elif kind == "swatter":
        head, handle = obj_polys("swatter", x, y, 0.0)
        dr.polygon(V.pts(handle), fill=dim(SWAT, 0.7))
        dr.polygon(V.pts(head), fill=SWAT, outline=dim(SWAT, 0.5), width=max(1, int(V.L(10))))
        for k in range(1, 6):
            gx = x + SWAT_HEAD * k / 6
            gy = y - SWAT_HEAD / 2 + SWAT_HEAD * k / 6
            dr.line([(V.X(gx), V.Y(y - SWAT_HEAD / 2 + 12)), (V.X(gx), V.Y(y + SWAT_HEAD / 2 - 12))], fill=dim(SWAT, 0.55), width=w5)
            dr.line([(V.X(x + 12), V.Y(gy)), (V.X(x + SWAT_HEAD - 12), V.Y(gy))], fill=dim(SWAT, 0.55), width=w5)
    elif kind == "boot":
        shaft = [(-20, -220), (190, -220), (190, -720), (-20, -720)]
        foot = [(-185, -40), (190, -40), (190, -240), (-20, -240), (-185, -170)]
        sole = [(-185, 0), (190, 0), (190, -44), (-185, -44)]
        for part in (shaft, foot):
            dr.polygon(V.pts([(x + a_, y + b_) for a_, b_ in part]), fill=LEATHER, outline=dim(LEATHER, 0.6), width=w5)
        dr.polygon(V.pts([(x + a_, y + b_) for a_, b_ in sole]), fill=(34, 26, 24))
        for k in range(5):
            ly = y - 270 - k * 72
            dr.line([(V.X(x + 10), V.Y(ly)), (V.X(x + 64), V.Y(ly - 30))], fill=(200, 186, 150), width=max(1, int(V.L(8))))


def draw_crack(dr, V, x, seed):
    rng = np.random.default_rng(1000 + seed)
    for k in range(5):
        px, py = x + float(rng.uniform(-40, 40)), FLOOR + 3
        sgn = 1 if k % 2 else -1
        slope = float(rng.uniform(0.15, 0.5))
        L = float(rng.uniform(110, 240))
        pts = [(V.X(px), V.Y(py))]
        for j in range(4):
            px += sgn * L / 4 * float(rng.uniform(0.7, 1.2))
            py += slope * L / 4 * float(rng.uniform(0.6, 1.3))
            pts.append((V.X(px), V.Y(min(py, FLOOR + 140))))
        dr.line(pts, fill=(20, 18, 26), width=max(1, int(V.L(5))))


def draw_dust(dr, V, T, impacts):
    for (t, x, a) in impacts:
        u = T - t
        if not (0 <= u < 1.0):
            continue
        for k in range(6):
            side = -1 if k % 2 == 0 else 1
            dx = side * (R * 1.2 + (60 + 40 * (k // 2)) * (1 - math.exp(-u * 4)))
            r = (24 + 10 * (k // 2)) * (1 + 1.6 * u)
            col = mix(FLOORC, (96, 92, 110), (1 - u) * 0.8)
            dr.ellipse(V.box(x + dx - r, FLOOR - 10 - r * 0.8 - 30 * u, x + dx + r, FLOOR - 10 + r * 0.6 - 30 * u), fill=col)


def draw_scene(world, dr, T, S, smug_t=None):
    V = View(S, world.camera(T))
    full = View(S, (W / 2, H / 2, 1.0, 0.0, 0.0))
    dr.rectangle(full.box(0, 0, W, H), fill=WALL)
    # la lumière de scène, derrière lui
    for k in range(6, 0, -1):
        r = 760 * k / 6
        dr.ellipse(V.box(470 - r, 1080 - r, 470 + r, 1080 + r), fill=mix(WALL, (64, 58, 88), 0.5 * (7 - k) / 6))
    dr.rectangle(V.box(-400, FLOOR - 30, W + 400, FLOOR), fill=dim(WALL, 0.7))
    dr.rectangle(V.box(-400, FLOOR, W + 400, H + 400), fill=FLOORC)
    dr.rectangle(V.box(-400, FLOOR, W + 400, FLOOR + 8), fill=dim(FLOORC, 1.4))
    for (t, x, seed) in world.p.cracks:
        if T >= t:
            draw_crack(dr, V, x, seed)
    x, y, sx, sy = world.bounce(T)
    objs = world.objects(T)
    hgt = max(0.0, FLOOR - (y + R * sy))
    k = max(0.25, 1 - hgt / 1300)
    dr.ellipse(V.box(x - R * 1.05 * k * sx, FLOOR + 6, x + R * 1.05 * k * sx, FLOOR + 30), fill=dim(FLOORC, 0.55))
    for (i, kind, ox, oy, a) in objs:
        if kind == "swatter":
            continue
        bottom = oy if kind == "boot" else oy + max(dy for dx, dy in SHAPES[kind])
        kk = max(0.0, 1 - (FLOOR - bottom) / 1700)
        hw = (190 if kind == "boot" else max(abs(dx) for dx, dy in SHAPES[kind])) * (0.35 + 0.65 * kk)
        if kk > 0.05:
            dr.ellipse(V.box(ox - hw, FLOOR + 10, ox + hw, FLOOR + 34), fill=mix(FLOORC, (12, 10, 16), 0.3 + 0.5 * kk))
    draw_dust(dr, V, T, world.p.dust)
    if smug_t is not None and T >= smug_t + 0.35:
        base.HERO["expr"] = "win"
    draw_bounce(dr, V, x, y, sx, sy)
    for (i, kind, ox, oy, a) in objs:
        draw_obj(dr, V, kind, ox, oy, a)


# ------------------------------------------------------------------ les chapitres
PLAN = {}


def plan_for(cfg):
    if "p" not in PLAN:
        p = build(cfg)
        p.dust = [(t, x, 1.0) for (t, x, s) in p.cracks]
        PLAN["p"], PLAN["w"] = p, World(p)
    return PLAN["p"], PLAN["w"]


class Part(Chapter):
    """Un chapitre : une fenêtre sur le plan commun, de son titre au suivant."""
    idx = 0
    exit_ok = True            # le cadre est tenu par le plan (H_MAX), pas par la règle des listes
    bodies_exit_ok = True     # les objets arrivent du ciel et y repartent

    def setup(self):
        p, w = plan_for(self.cfg)
        self.P, self.Wd = p, w
        ch = p.chapters[self.idx]
        self.c_start = ch["start"]
        self.chute_abs = ch["chute"]
        nxt = p.chapters[self.idx + 1]["start"] if self.idx + 1 < len(p.chapters) else p.end + 0.05
        self.hold_s = nxt - self.chute_abs
        self.plan_lines = [l for l in p.lines if l["ch"] == self.idx]
        self.lines = [(l["start"] - self.c_start, l["text"], l["key"]) for l in self.plan_lines]
        self.smug = ch.get("smug")
        self.abs0 = self.c_start
        self.prevT = None
        self.title = None
        self.R = R
        self.bx, self.by, self.on = 420.0, YC, "air"
        x, y, _, _ = w.bounce(self.chute_abs)
        self.focus_xy = (min(640.0, max(250.0, x)), y)

    def step(self, dt):
        self.t += dt
        T = self.abs0 + self.t
        evs = []
        lo = self.prevT if self.prevT is not None else T - dt
        for c in self.P.contacts:
            if lo < c["t"] <= T:
                evs.append(("event", "stop") if c["kind"] == "stop" else ("hit", "floor"))
        self.prevT = T
        if T >= self.chute_abs - 1e-9:
            self.finish("CHUTE")
        return evs

    def snapshot(self):
        T = self.abs0 + self.t
        x, y, sx, sy = self.Wd.bounce(T)
        return {"T": T, "t": self.t, "bx": x, "by": y, "sx": sx, "sy": sy, "end": self.end_t, "on": "air"}

    def hero(self, s):
        return (s["bx"], s["by"], R * min(s["sx"], s["sy"]))

    def solids(self, s):
        out = [("rect", 0.0, FLOOR, float(W), float(H))]
        for (i, kind, x, y, a) in self.Wd.objects(s["T"]):
            for pg in obj_polys(kind, x, y, a):
                out.append(("poly", pg))
        return out

    def bodies(self, s):
        return [(i, x, y, a, obj_polys(kind, x, y, a)[0]) for (i, kind, x, y, a) in self.Wd.objects(s["T"])]

    def focus(self, s):
        x, y = self.focus_xy
        return (x - 250, y - 250, x + 250, min(FLOOR, y + 250))

    def draw(self, dr, s, t, S):
        draw_scene(self.Wd, dr, s["T"], S, self.smug)


def make(i):
    class P_(Part):
        pass
    P_.idx = i
    P_.__name__ = f"Part{i + 1}"
    return P_


CHAPTERS = [(make(i), {}) for i in range(7)]

DEFAULTS = {
    "ball_r": R, "gravity": G,
    "chapter_max_s": 13.0,
    "narrator_length": 0.9,
    "hook_narrator": True, "hook_text_s": 2.6, "hook_top": 0.06, "hook_font_size": 92,
    "sub_y": 0.155, "sub_font_size": 60, "sub_words": 4,
    "watermark_y": 0.95, "end_hold_s": 0.85, "narr_tail_s": 0.6, "narr_gap_s": 0.3,
    "scene_top": 0.215, "min_duration_s": 30.0,
}


class Sim(StorySim):
    def __init__(self, cfg, rng):
        PLAN.clear()
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)

    def _open(self, i):
        s = self.sims[i]
        s.abs0 = self.t
        s.lines = [(l["start"] - self.t, l["text"], l["key"]) for l in s.plan_lines]
        super()._open(i)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
