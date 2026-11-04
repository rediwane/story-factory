"""
Prototype « Snooze » : le personnage d'un fan (Snooze, une balle grise qui dort) et Bounce,
qui est littéralement son réveil. Une chambre, un lit, une horloge au mur. Chaque fois que
Bounce lui tombe dessus, Snooze roule sur lui sans ouvrir les yeux (il « appuie sur snooze »)
et l'horloge saute de 9 minutes. Les minutes deviennent des heures, le jour passe par la
fenêtre ; quand Snooze ouvre enfin les yeux, il fait nuit : il se rendort, ravi. Bounce : « Oh no. »

Snooze ne dit qu'un mot, « Snooze », avec une intonation différente à chaque fois ; ses
répliques sont des fichiers lus dans cfg["snooze_bank"] (hors dépôt), sans sous-titre.
Bounce ne s'arrête jamais : même écrasé sous Snooze, il tremble ; sur l'oreiller (mou), ses
rebonds ne font pas de bruit.

Tout est calculé d'avance sur une horloge : les contacts de Bounce, les moments où Snooze
l'écrase, et des arcs sous une gravité unique qui relient les uns aux autres.

    python3 src/stories/snooze.py configs/<name>.json [--simulate]
"""
import math, sys, os, wave
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, font
import audio_kit as ak
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import voice as narr_voice

SR = ak.SR
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ------------------------------------------------------------------ la voix de Snooze
LINES = {  # clé -> fichier de la banque
    "marmonne1": "1_marmonne.wav", "marmonne2": "2_marmonne.wav",
    "agace1": "3_agace.wav", "agace2": "4_agace.wav",
    "etouffe": "5_etouffe.wav", "content": "6_content.wav",
}
BANK, ENV = {}, {}
_orig_say = narr_voice.say


def _read(path):
    with wave.open(path) as w:
        n, fr, ch = w.getnframes(), w.getframerate(), w.getnchannels()
        raw = w.readframes(n)
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if fr != SR:
        x = np.interp(np.arange(int(len(x) * SR / fr)) / SR, np.arange(len(x)) / fr, x)
    return x


def load_bank(cfg):
    path = cfg.get("snooze_bank")
    if not path:
        raise SystemExit("[snooze] snooze_bank manquant dans la config")
    for key, fn in LINES.items():
        x = _read(os.path.join(path, fn))
        x /= (np.sqrt(np.mean(x[np.abs(x) > 0.05 * np.abs(x).max()] ** 2)) + 1e-9)
        x *= 0.2 * (0.7 if key == "etouffe" else 1.0)
        BANK["Snooze " + key] = x
        hop = SR // 60
        e = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, len(x), hop)])
        ENV["Snooze " + key] = e / (e.max() + 1e-9)


def snooze_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    if text in BANK:
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = snooze_say
base.subtitle_at = lambda narr, t, n_words: None          # aucun sous-titre

_orig_build = base.build_narration


def build_narration_keep(sim, cfg):
    narr, replies = _orig_build(sim, cfg)
    sim.narr = narr                                         # la bouche de Snooze suit sa voix
    return narr, replies


base.build_narration = build_narration_keep

# ------------------------------------------------------------------ le mot de Bounce
_orig_hero_word = base.hero_word
_hero_memo = {}


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
            if text != cfg["hero_name"] or len(v) / SR <= 0.78:
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

# ------------------------------------------------------------------ le décor
W, H = 1080, 1920
R = 100.0                 # Snooze et Bounce : même taille
RB = 100.0
CEIL = 470.0
FLOOR = 1500.0
YM = 1262.0               # le dessus du matelas
SX0 = 330.0               # Snooze au repos, sur l'oreiller
SY = YM - R + 16
PIN_X = 500.0             # là où Bounce se fait écraser
ROLL_X = 470.0             # Snooze roule franchement sur lui pour l'écraser
WIN = (100, 560, 470, 930)
CLK = (610, 505, 990, 665)
WALL_DAY, WALL_NIGHT = (30, 30, 44), (13, 13, 22)
FLOOR_COL = (22, 18, 20)
BED = (82, 60, 52)
MATT = (210, 210, 222)
PILLOW = (236, 236, 244)
BLANKET = (86, 98, 168)
BLANKET_D = (64, 74, 136)
S_DISC, S_HALO = (192, 192, 192), (42, 42, 44)
S_EYE, S_EDGE, S_LID = (104, 104, 104), (52, 52, 52), (40, 40, 40)
S_MOUTH = (112, 112, 112)
INK = (16, 14, 20)
DIGIT = (255, 70, 60)

G = 2600.0


def lerp(a, b, s):
    return a + (b - a) * s


def ease(s):
    s = max(0.0, min(1.0, s))
    return s * s * (3 - 2 * s)


def mix(a, b, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(lerp(x, y, k)) for x, y in zip(a, b))


def keyed(keys, t):
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            s = ease((t - t0) / (t1 - t0)) if t1 > t0 else 1.0
            if isinstance(v0, tuple):
                return mix(v0, v1, s)
            return lerp(v0, v1, s)
    return keys[-1][1]


SKY = [(420, (196, 118, 112)), (470, (150, 160, 200)), (560, (120, 178, 228)), (900, (112, 172, 232)),
       (1020, (226, 176, 98)), (1130, (214, 98, 70)), (1210, (52, 46, 92)), (1250, (10, 12, 30))]


class Sim:
    scene_top = 0.24

    def __init__(self, cfg, rng):
        self.cfg = cfg
        load_bank(cfg)
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        self.end_s = cfg["end_s"]
        hy = SY - R - RB                       # Bounce posé sur la tête de Snooze
        my = YM - RB                           # Bounce posé sur le matelas
        py = YM - RB + 44                      # Bounce écrasé sous Snooze
        # ---- la piste de Bounce : contacts (c) et écrasements (pin), dans l'ordre
        T = []

        def c(t, x, y, hit=True):
            T.append(("c", t, x, y, hit))

        def pin(t0, t1):
            T.append(("pin", t0, t1, PIN_X, py))

        T.append(("c", -0.4, 1180.0, 760.0, False))
        c(0.95, 640, my)
        c(1.85, SX0, hy)
        c(2.45, PIN_X, my); pin(2.45, 3.25)
        c(4.15, 175, 1000 - RB)                # le haut de la tête de lit
        c(5.10, SX0, hy)
        c(6.10, 1005, 1080 - RB)               # l'abat-jour
        c(7.05, SX0, hy)
        c(7.65, PIN_X, my); pin(7.65, 8.45)
        c(9.45, 470, CEIL + RB)                # le plafond
        c(10.45, SX0, hy)
        # sous la couverture : la bosse
        for tt in (12.0, 12.9, 13.75, 14.6, 15.45):
            c(tt, SX0, hy + 14)
        c(16.45, 760, my)
        c(17.40, 640, FLOOR - RB)              # il tombe du lit
        c(18.30, 820, FLOOR - RB)
        c(19.40, SX0, hy)
        # l'accélération : six fois, tête puis écrasement, l'horloge saute
        self.montage = []
        t0 = 19.40
        for i in range(6):
            tp = t0 + 0.75
            c(tp, PIN_X, my); pin(tp, tp + 0.55)
            self.montage.append(tp)
            te = tp + 0.55 + 1.1
            ex, ey = [(175, 1000 - RB), (1005, 1080 - RB), (470, CEIL + RB)][i % 3]
            c(te, ex, ey)
            t0 = te + 1.0
            c(t0, SX0, hy)
        # t0 ~ 39 : il ne réagit plus ; Bounce monte de plus en plus haut
        tt = max(t0 + 0.2, 39.9)
        for (dt, x, y) in [(1.0, SX0, hy), (1.15, 620, my), (1.2, SX0, hy), (1.35, 470, CEIL + RB),
                           (1.25, SX0, hy), (1.15, 1005, 1080 - RB), (1.2, SX0, hy), (1.45, SX0, hy)]:
            tt += dt
            c(tt, x, y)
        self.t_big = tt                        # le dernier grand rebond
        # sur l'oreiller, mou : de petits rebonds sans bruit, jusqu'à la fin
        tt += 0.95
        for k in range(14):
            c(tt, 520 + (k % 2) * 30, my, hit=False)
            tt += 0.78
            if tt > cfg["t_return"]:
                break
        c(tt + 0.5, SX0, hy)
        tt += 0.5
        c(tt + 1.05, SX0, hy)
        tt += 1.05
        self.t_last_head = tt
        self.track = T
        self.hits = sorted([(e[1], "head" if abs(e[2] - SX0) < 1 else "hit") for e in T if e[0] == "c" and e[4] and e[1] > 0])
        self.hi = 0
        self.head_hits = [e[1] for e in T if e[0] == "c" and e[4] and abs(e[2] - SX0) < 1]
        self.pins = [(e[1], e[2]) for e in T if e[0] == "pin"]
        # ---- l'horloge : (t, minutes depuis minuit)
        clock = [(0.0, 420), (2.95, 429), (7.95, 438), (11.3, 447)]
        jumps = [495, 582, 690, 785, 920, 1030]
        for tp, m in zip(self.montage, jumps):
            clock.append((tp + 0.3, m))
        self.clock = clock
        self.ff = (self.montage[-1] + 2.0, self.t_big + 0.4, 1030, 1252)   # le temps file, de 17:10 à 20:52
        self.clock_end = (cfg["t_final_clock"], 1261)
        # ---- la couverture sur la tête
        self.cover = [(10.75, 0.0), (11.15, 1.0), (16.0, 1.0), (16.4, 0.0)]
        # ---- les yeux de Snooze : ouverts à la fin, le temps de voir qu'il fait nuit
        self.t_open = self.t_big + 1.25
        self.t_close = self.t_open + 3.6
        # ---- ses répliques : (déclencheur, texte, clé)
        L = [(2.55, "marmonne1"), (7.75, "agace1"), (11.25, "etouffe")]
        for tp, key in zip(self.montage, ["marmonne2", None, "agace2", None, "marmonne1", None]):
            if key:
                L.append((tp + 0.05, key))
        L.append((self.t_open + 2.4, "content"))
        L.append((self.t_last_head + 0.55, "marmonne2"))
        self.lines = [(t, "Snooze " + k, f"s{i}") for i, (t, k) in enumerate(L)]
        self.payoff_at = self.t_open + 3.6 + 0.3

    # ---- la trajectoire de Bounce
    def bounce_at(self, t):
        T = self.track
        prev = None
        for e in T:
            if e[0] == "pin":
                if e[1] <= t <= e[2]:
                    return e[3] + 5 * math.sin(t * 70), e[4] + 3 * math.sin(t * 53), True
                prev = (e[2], e[3], e[4])
                continue
            if e[1] >= t:
                if prev is None:
                    return e[2], e[3], False
                t0, x0, y0 = prev
                t1, x1, y1 = e[1], e[2], e[3]
                d = t1 - t0
                s = (t - t0) / d if d > 0 else 1.0
                h = min(0.5 * G * (d / 2) ** 2, 760.0)
                top = min(y0, y1) - h
                # arc qui passe par top, sans dépasser le plafond
                top = max(top, CEIL + RB)
                a0, a1 = y0 - top, y1 - top
                # parabole par morceaux : monte de y0 à top, redescend à y1
                sm = math.sqrt(a0) / (math.sqrt(a0) + math.sqrt(a1) + 1e-9)
                if s <= sm:
                    u = s / sm if sm > 0 else 1
                    y = top + a0 * (1 - u) ** 2
                else:
                    u = (s - sm) / (1 - sm) if sm < 1 else 1
                    y = top + a1 * u ** 2
                return lerp(x0, x1, s), y, False
            prev = (e[1], e[2], e[3])
        # après le dernier contact : il repart vers le haut, coupé en l'air
        t0, x0, y0 = prev
        s = t - t0
        return x0 + 60 * s, y0 - 1500 * s + 0.5 * G * s * s, False

    def step(self, dt):
        evs = []
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= self.t:
            evs.append(("hit", self.hits[self.hi][1]))
            self.hi += 1
        if not self.payoff and self.t >= self.payoff_at:
            self.payoff = True
            evs.append(("payoff", "nuit"))
        if self.t >= self.end_s:
            self.done = True
        return evs

    def hero_mood(self):
        return "lose"

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    # ---- l'état de Snooze
    def snooze_x(self, t):
        for (a, b) in self.pins:
            if a - 0.05 <= t <= b + 0.35:
                k = ease((t - (a - 0.05)) / 0.22) if t < a + 0.17 else (1.0 if t <= b else 1 - ease((t - b) / 0.35))
                return lerp(SX0, ROLL_X, k)
        return SX0

    def minutes(self, t):
        m = self.clock[0][1]
        for (tc, mm) in self.clock:
            if t >= tc:
                m = mm
        a, b, m0, m1 = self.ff
        if t >= a:
            m = int(lerp(m0, m1, min(1.0, (t - a) / (b - a)) ** 1.15))
        if t >= self.clock_end[0]:
            m = self.clock_end[1]
        return m

    def talking(self, t):
        for n in self.narr:
            if n["start"] <= t <= n["end"]:
                e = ENV.get(n["text"])
                if e is None:
                    return 0.0, n["text"]
                i = int((t - n["start"]) * 60)
                return float(e[min(i, len(e) - 1)]), n["text"]
        return 0.0, None

    # ---- le dessin
    def draw(self, dr, snap, t, S):
        m = self.minutes(t)
        sky = keyed(SKY, m)
        night = max(0.0, min(1.0, (m - 1120) / 120.0))
        wall = mix(WALL_DAY, WALL_NIGHT, night)
        P = lambda x, y: (x * S, y * S)

        def rect(x0, y0, x1, y1, col):
            dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)

        # la chambre
        rect(0, CEIL, W, FLOOR, wall)
        rect(0, CEIL - 8, W, CEIL, dim(wall, 0.6))
        rect(0, FLOOR, W, H, FLOOR_COL)
        # la fenêtre et son ciel
        x0, y0, x1, y1 = WIN
        rect(x0 - 14, y0 - 14, x1 + 14, y1 + 14, (60, 52, 50))
        rect(x0, y0, x1, y1, sky)
        if m < 1180:      # le soleil traverse la fenêtre
            sp = (m - 420) / (1180 - 420)
            sx_, sy_ = lerp(x0 + 40, x1 - 30, sp), y1 - 40 - 300 * math.sin(math.pi * sp)
            sc = mix((255, 236, 170), (255, 150, 90), max(0.0, (m - 1000) / 180))
            dr.ellipse([(sx_ - 32) * S, (sy_ - 32) * S, (sx_ + 32) * S, (sy_ + 32) * S], fill=sc)
        if night > 0.6:   # la lune, les étoiles
            a = (night - 0.6) / 0.4
            mc = mix(sky, (236, 236, 214), a)
            dr.ellipse([(x1 - 120) * S, (y0 + 50) * S, (x1 - 60) * S, (y0 + 110) * S], fill=mc)
            dr.ellipse([(x1 - 106) * S, (y0 + 44) * S, (x1 - 50) * S, (y0 + 100) * S], fill=sky)
            for (sx_, sy_) in [(150, 610), (230, 700), (320, 600), (180, 820), (300, 760), (400, 860), (260, 880)]:
                dr.ellipse([(sx_ - 3) * S, (sy_ - 3) * S, (sx_ + 3) * S, (sy_ + 3) * S], fill=mix(sky, (230, 230, 240), a))
        # le dessin du chassis par-dessus le ciel
        cx_ = (x0 + x1) / 2; cy_ = (y0 + y1) / 2
        rect(cx_ - 6, y0, cx_ + 6, y1, (60, 52, 50))
        rect(x0, cy_ - 6, x1, cy_ + 6, (60, 52, 50))
        # la lumière de la fenêtre au sol
        if night < 0.9:
            lc = mix(dim(sky, 0.35), wall, night)
            dr.polygon([P(x0 + 60, FLOOR), P(x1 + 40, FLOOR), P(x1 + 180, H - 140), P(x0 + 160, H - 140)], fill=mix(FLOOR_COL, lc, 0.5))
        # l'horloge
        cx0, cy0, cx1, cy1 = CLK
        dr.rounded_rectangle([cx0 * S, cy0 * S, cx1 * S, cy1 * S], radius=18 * S, fill=(18, 12, 14), outline=(70, 60, 64), width=int(5 * S))
        txt = f"{m // 60}:{m % 60:02d}"
        ft = font(118 * S)
        dr.text(((cx0 + cx1) / 2 * S, (cy0 + cy1) / 2 * S + 4 * S), txt, fill=DIGIT, anchor="mm", font=ft)
        for (tc, mm) in self.clock[1:4]:
            if 0 <= t - tc < 0.9:
                k = (t - tc) / 0.9
                col = mix((120, 255, 140), wall, k)
                dr.text((cx1 * S - 10 * S, (cy0 - 30 - 50 * k) * S), "+9", fill=col, anchor="rm", font=font(64 * S))
        # la table de nuit et la lampe
        rect(940, 1250, 1070, FLOOR, (70, 52, 46))
        rect(995, 1160, 1012, 1250, (150, 140, 120))
        dr.polygon([P(955, 1160), P(1055, 1160), P(1035, 1080), P(975, 1080)], fill=(220, 200, 150))
        # le lit
        rect(150, 980, 205, FLOOR, BED)                   # la tête de lit
        dr.ellipse([(145) * S, 960 * S, 210 * S, 1010 * S], fill=BED)
        rect(150, YM + 70, 930, YM + 120, BED)
        rect(170, YM + 120, 200, FLOOR, BED); rect(890, YM + 120, 920, FLOOR, BED)
        rect(205, YM, 920, YM + 72, MATT)
        dr.rounded_rectangle([215 * S, (YM - 52) * S, 445 * S, (YM + 6) * S], radius=26 * S, fill=PILLOW)

        # Bounce écrasé passe sous Snooze ; sinon par-dessus
        bx, by, pinned = self.bounce_at(t)
        if pinned:
            base.ball(dr, bx * S, by * S, RB * S)
        self.draw_snooze(dr, t, S)
        self.draw_blanket(dr, t, S)
        if not pinned:
            base.ball(dr, bx * S, by * S, RB * S)

    def squash(self, t):
        sq = 0.0
        for th in self.head_hits:
            d = t - th
            if 0 <= d < 0.5:
                sq = max(sq, 0.13 * math.exp(-d * 8) * math.cos(d * 24))
        return sq

    def draw_snooze(self, dr, t, S):
        x = self.snooze_x(t)
        phi = (x - SX0) / R                       # il roule
        sq = self.squash(t)
        sx, sy = 1 + sq, 1 - sq
        y = YM + 16 - R * sy
        r = R
        dr.ellipse([(x - 1.6 * r * sx) * S, (y - 1.6 * r * sy) * S, (x + 1.6 * r * sx) * S, (y + 1.6 * r * sy) * S], fill=S_HALO)
        dr.ellipse([(x - r * sx) * S, (y - r * sy) * S, (x + r * sx) * S, (y + r * sy) * S], fill=S_DISC)
        ca, sa = math.cos(phi), math.sin(phi)

        def Pp(u, v):
            return ((x + (u * ca - v * sa) * r * sx) * S, (y + (u * sa + v * ca) * r * sy) * S)

        w = max(2, int(0.05 * r * S))
        talk, key = self.talking(t)
        open_k = 0.0
        if self.t_open <= t <= self.t_close:
            open_k = min(1.0, (t - self.t_open) / 0.25, (self.t_close - t) / 0.25)
        look = 0.0
        if open_k > 0:
            look = keyed([(self.t_open, 0.0), (self.t_open + 0.6, 0.0), (self.t_open + 0.9, 0.7), (self.t_open + 1.6, 0.7),
                          (self.t_open + 1.9, -0.75), (self.t_open + 2.6, -0.75), (self.t_open + 2.9, 0.0)], t)
        for ex in (-0.37, 0.37):
            cx, cy, er = ex, -0.2, 0.29
            pts = [Pp(cx + er * math.cos(k * math.pi / 16), cy + er * math.sin(k * math.pi / 16)) for k in range(32)]
            dr.polygon(pts, fill=S_EYE, outline=S_EDGE)
            dr.line(pts + [pts[0]], fill=S_EDGE, width=w)
            if open_k > 0.5:
                # les yeux ouverts : une pupille blanche qui regarde l'horloge, puis la fenêtre
                pu, pv = cx + look * 0.12, cy - 0.02
                pts2 = [Pp(pu + 0.1 * math.cos(k * math.pi / 8), pv + 0.1 * math.sin(k * math.pi / 8)) for k in range(16)]
                dr.polygon(pts2, fill=(238, 238, 238))
            else:
                dr.line([Pp(cx - er * 0.8, cy), Pp(cx + er * 0.8, cy)], fill=S_LID, width=w)
        # la bouche : plate ; s'ouvre quand il parle ; sourit à la fin
        smile = 1.0 if t >= self.t_close else 0.0
        mh = 0.15 + 0.22 * talk
        if smile > 0 and talk < 0.05:
            pts = [(-0.36 + 0.72 * k / 12, 0.36 + 0.10 * math.sin(math.pi * k / 12)) for k in range(13)]
            dr.line([Pp(u, v) for u, v in pts], fill=S_EDGE, width=int(w * 1.6), joint="curve")
        else:
            u0, u1, v0 = -0.40, 0.40, 0.40
            pts = []
            for k in range(13):
                a = math.pi / 2 + math.pi * k / 12
                pts.append((u0 + mh / 2 * math.cos(a) + mh / 2, v0 + mh / 2 * math.sin(a)))
            for k in range(13):
                a = -math.pi / 2 + math.pi * k / 12
                pts.append((u1 + mh / 2 * math.cos(a) - mh / 2, v0 + mh / 2 * math.sin(a)))
            q = [Pp(u, v) for u, v in pts]
            dr.polygon(q, fill=S_MOUTH)
            dr.line(q + [q[0]], fill=S_EDGE, width=w)

    def draw_blanket(self, dr, t, S):
        k = keyed(self.cover, t)
        x = self.snooze_x(t)
        sq = self.squash(t)
        y = YM + 16 - R * (1 - sq)
        level = lerp(YM - 26, y - R * (1 - sq) - 16, k)
        top = []
        x_left = lerp(400, 205, ease(k * 1.4))
        for i in range(61):
            xx = lerp(x_left, 920, i / 60)
            yy = YM - 26 + 6 * math.sin(xx / 60)
            if k > 0:
                dd = xx - x
                rr = (R + 16) * (1 + sq)
                if abs(dd) < rr:
                    hump = y - math.sqrt(rr * rr - dd * dd) * (1 - sq)
                    yy = min(yy, max(level, hump))
            top.append((xx * S, yy * S))
        poly = top + [(920 * S, (YM + 76) * S), (x_left * S, (YM + 76) * S)]
        dr.polygon(poly, fill=BLANKET)
        dr.line(top, fill=BLANKET_D, width=int(6 * S), joint="curve")


DEFAULTS = {
    "fps": 60,
    "min_duration_s": 8.0,
    "max_duration_s": 75.0,
    "end_hold_s": 0.0,
    "hook_text_s": 2.6,
    "end_s": 61.8,
    "t_return": 57.0,
    "t_final_clock": 60.6,
}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
