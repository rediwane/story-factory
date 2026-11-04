"""
Prototype « passer devant Snooze » : Bounce doit traverser la chambre où Snooze dort, jusqu'à
la porte. Chaque rebond sur quelque chose de dur fait « Bounce », de plus en plus fort ; il
fait tomber l'horloge sur la tête de Snooze, renverse la lampe, lui rebondit sur la tête :
Snooze dort comme une pierre. Devant la porte, Bounce atterrit sur le tapis, qui est mou :
plus un bruit. C'est le silence qui réveille Snooze. Dès que Bounce redit son nom, Snooze se
rendort ; dès qu'il se tait, Snooze se réveille. Il ne partira jamais.

Snooze ne dit que « Snooze » (banque de voix hors dépôt, cfg["snooze_bank"]), sans sous-titre.
Bounce ne s'arrête jamais ; sur le tapis et le matelas (mous), ses rebonds ne font pas de bruit.

    python3 src/stories/sneak.py configs/<name>.json [--simulate]
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




# ------------------------------------------------------------------ la chambre
SX = 400.0                       # Snooze sur son oreiller
FY = FLOOR - RB                  # Bounce posé au sol
HEAD_Y = SY - R - RB             # Bounce posé sur la tête de Snooze
CLOCK_C, CLOCK_R = (330.0, 760.0), 70.0
STAND = (790.0, 1250.0, 880.0)   # la table de nuit : x0, dessus, x1
LAMP_X = 835.0
DOOR = (930.0, 1040.0, 1072.0)   # x0, haut, x1
RUG = (870.0, 1075.0)
RUG_Y = FY + 10                  # le tapis est mou : Bounce s'y enfonce un peu, sans bruit
T_CLOCK, T_LAMP = 8.10, 32.10


def draw_snooze_at(dr, x, y, r, S, open_k=0.0, look=0.0, talk=0.0, smile=False, sq=0.0):
    sx, sy = 1 + sq, 1 - sq
    dr.ellipse([(x - 1.6 * r * sx) * S, (y - 1.6 * r * sy) * S, (x + 1.6 * r * sx) * S, (y + 1.6 * r * sy) * S], fill=S_HALO)
    dr.ellipse([(x - r * sx) * S, (y - r * sy) * S, (x + r * sx) * S, (y + r * sy) * S], fill=S_DISC)

    def P(u, v):
        return ((x + u * r * sx) * S, (y + v * r * sy) * S)
    w = max(2, int(0.05 * r * S))
    for ex in (-0.37, 0.37):
        cx, cy, er = ex, -0.2, 0.29
        pts = [P(cx + er * math.cos(k * math.pi / 16), cy + er * math.sin(k * math.pi / 16)) for k in range(32)]
        dr.polygon(pts, fill=S_EYE)
        dr.line(pts + [pts[0]], fill=S_EDGE, width=w)
        if open_k > 0.5:
            pu, pv = cx + look * 0.12, cy
            dr.polygon([P(pu + 0.13 * math.cos(k * math.pi / 8), pv + 0.13 * math.sin(k * math.pi / 8)) for k in range(16)], fill=(242, 242, 242))
            dr.polygon([P(pu + 0.05 * math.cos(k * math.pi / 8), pv + 0.05 * math.sin(k * math.pi / 8)) for k in range(16)], fill=S_LID)
        else:
            dr.line([P(cx - er * 0.8, cy), P(cx + er * 0.8, cy)], fill=S_LID, width=w)
    mh = 0.15 + 0.22 * talk
    if smile and talk < 0.05:
        pts = [(-0.36 + 0.72 * k / 12, 0.36 + 0.10 * math.sin(math.pi * k / 12)) for k in range(13)]
        dr.line([P(u, v) for u, v in pts], fill=S_EDGE, width=int(w * 1.6), joint="curve")
    else:
        pts = []
        for k in range(13):
            a = math.pi / 2 + math.pi * k / 12
            pts.append((-0.40 + mh / 2 * math.cos(a) + mh / 2, 0.40 + mh / 2 * math.sin(a)))
        for k in range(13):
            a = -math.pi / 2 + math.pi * k / 12
            pts.append((0.40 + mh / 2 * math.cos(a) - mh / 2, 0.40 + mh / 2 * math.sin(a)))
        q = [P(u, v) for u, v in pts]
        dr.polygon(q, fill=S_MOUTH)
        dr.line(q + [q[0]], fill=S_EDGE, width=w)


def arc(t, t0, x0, y0, t1, x1, y1, cap=CEIL + RB):
    d = max(1e-6, t1 - t0)
    s = (t - t0) / d
    h = min(0.5 * G * (d / 2) ** 2, 700.0)
    top = max(min(y0, y1) - h, cap)
    a0, a1 = max(0.0, y0 - top), max(0.0, y1 - top)
    sm = math.sqrt(a0) / (math.sqrt(a0) + math.sqrt(a1) + 1e-9)
    if s <= sm:
        u = s / sm if sm > 0 else 1
        y = top + a0 * (1 - u) ** 2
    else:
        u = (s - sm) / (1 - sm) if sm < 1 else 1
        y = top + a1 * u ** 2
    return lerp(x0, x1, s), y


class Sim:
    scene_top = 0.24

    def __init__(self, cfg, rng):
        self.cfg = cfg
        load_bank(cfg)
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        C = []                       # (t, x, y, dur) ; dur : True si la surface est dure (il dit son nom)

        def c(t, x, y, hard=True):
            C.append((t, x, y, hard))
        # le début : de tout petits rebonds, vers la droite
        for i, x in enumerate((110, 140, 170, 195, 215, 205)):
            c(0.6 + 1.0 * i, x, FY)
        c(6.95, 255, 980 - RB)                                      # la tête de lit
        c(T_CLOCK, CLOCK_C[0], CLOCK_C[1] - CLOCK_R - RB)          # sur l'horloge, qui tombe
        c(9.15, SX, HEAD_Y); c(10.2, SX, HEAD_Y); c(11.25, SX, HEAD_Y)
        c(12.35, 610, YM - RB + 8, hard=False)                     # le matelas : mou
        xs = [640, 560, 700, 620, 720, 540, 690, 600, 710, 560, 680, 620, 700, 580, 660, 600, 700, 640]
        t = 13.4
        for i, x in enumerate(xs):
            c(t, x, FY)
            t += 0.80 if i % 4 != 3 else 1.15
        c(30.95, 812, STAND[1] - RB)                               # la table de nuit
        c(T_LAMP, LAMP_X, 1090 - RB)                               # l'abat-jour : la lampe tombe
        for x in (700, 650, 760, 700, 790, 730, 820):
            t = C[-1][0] + 1.08
            c(t, x, FY)
        # le tapis : mou, plus un bruit
        t = C[-1][0] + 1.15
        self.t_rug = t
        for x in (960, 985, 965, 980, 962, 984):
            c(t, x, RUG_Y, hard=False); t += 0.78
        self.t_wake = self.t_rug + 1.25
        self.t_off = t + 0.3                                        # il redescend du tapis
        c(self.t_off, 830, FY)
        self.awake = [(self.t_wake, self.t_off + 0.18)]
        t = self.t_off + 1.05
        c(t, 800, FY)
        # rug / sol / rug / sol, de plus en plus vite
        for dt in (1.0, 0.85, 0.75, 0.65):
            t_r = t + dt
            c(t_r, 965, RUG_Y, hard=False)
            t_f = t_r + dt
            c(t_f, 830, FY)
            self.awake.append((t_r + 0.35, t_f + 0.12))
            t = t_f
        # il abandonne : il rebondit sur place, pour que Snooze dorme
        for x in (790, 760, 790, 760, 790, 770, 790):
            t += 1.0
            c(t, x, FY)
        self.C = sorted(C)
        self.end_s = min(66.0, max(61.6, self.C[-1][0] + 0.6))
        self.hits = [(e[0], "hard") for e in self.C if e[3]]
        self.hi = 0
        self.head_hits = [e[0] for e in self.C if abs(e[1] - SX) < 1 and e[3]]
        self.clock_hit = T_CLOCK + 0.75                            # l'horloge lui tombe sur la tête
        self.head_hits.append(self.clock_hit)
        tw = self.t_wake
        L = [(5.55, "marmonne1"), (self.clock_hit + 0.2, "marmonne2"), (23.6, "marmonne1"),
             (tw + 0.9, "agace1"), (self.end_s - 3.4, "content")]
        self.lines = [(t, "Snooze " + k, f"s{i}") for i, (t, k) in enumerate(L)]
        self.payoff_at = tw + 2.3

    # ---- Bounce
    def bounce_at(self, t):
        C = self.C
        if t <= C[0][0]:
            return arc(t, -0.5, 40.0, 900.0, C[0][0], C[0][1], C[0][2])
        for a, b in zip(C, C[1:]):
            if a[0] <= t <= b[0]:
                return arc(t, a[0], a[1], a[2], b[0], b[1], b[2])
        t0, x0, y0, _ = C[-1]
        s = t - t0
        return x0, y0 - 1100 * s + 0.5 * G * s * s if s < 0.84 else y0

    def step(self, dt):
        evs = []
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= self.t:
            evs.append(("hit", self.hits[self.hi][1]))
            self.hi += 1
        if not self.payoff and self.t >= self.payoff_at:
            self.payoff = True
            evs.append(("payoff", "coince"))
        if self.t >= self.end_s:
            self.done = True
        return evs

    def hero_mood(self):
        return "lose"

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    def is_awake(self, t):
        for a, b in self.awake:
            if a <= t <= b:
                return True
        return False

    def talking(self, t):
        for n in self.narr:
            if n["start"] <= t <= n["end"]:
                e = ENV.get(n["text"])
                if e is None:
                    return 0.0
                i = int((t - n["start"]) * 60)
                return float(e[min(i, len(e) - 1)])
        return 0.0

    # ---- dessin
    def draw(self, dr, snap, t, S):
        def rect(x0, y0, x1, y1, col):
            dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)
        P = lambda x, y: (x * S, y * S)
        wall, sky = (20, 20, 32), (12, 14, 34)
        rect(0, CEIL, W, FLOOR, wall)
        rect(0, CEIL - 8, W, CEIL, dim(wall, 0.6))
        rect(0, FLOOR, W, H, FLOOR_COL)
        # la fenêtre de nuit
        rect(30, 540, 210, 870, (52, 46, 46)); rect(42, 552, 198, 858, sky)
        rect(114, 552, 126, 858, (52, 46, 46)); rect(42, 699, 198, 711, (52, 46, 46))
        dr.ellipse([140 * S, 580 * S, 186 * S, 626 * S], fill=(232, 232, 210))
        dr.ellipse([152 * S, 574 * S, 196 * S, 618 * S], fill=sky)
        for (sx_, sy_) in [(70, 600), (95, 650), (160, 670), (70, 780), (150, 820), (180, 760)]:
            dr.ellipse([(sx_ - 3) * S, (sy_ - 3) * S, (sx_ + 3) * S, (sy_ + 3) * S], fill=(200, 200, 220))
        # la porte et le tapis
        x0, y0, x1 = DOOR
        rect(x0 - 10, y0 - 10, x1 + 8, FLOOR, (60, 46, 40))
        rect(x0, y0, x1, FLOOR, (110, 80, 60))
        dr.ellipse([(x0 + 18) * S, 1270 * S, (x0 + 40) * S, 1292 * S], fill=(210, 190, 120))
        dr.ellipse([RUG[0] * S, (FLOOR - 12) * S, RUG[1] * S, (FLOOR + 14) * S], fill=(150, 60, 70))
        dr.ellipse([(RUG[0] + 20) * S, (FLOOR - 6) * S, (RUG[1] - 20) * S, (FLOOR + 8) * S], fill=(176, 84, 92))
        # l'horloge murale, puis sa chute
        if t < T_CLOCK + 0.15:
            cx, cy = CLOCK_C
            ang = 0.0
        else:
            k = t - (T_CLOCK + 0.15)
            if k < 0.6:
                s = k / 0.6
                cx, cy = lerp(CLOCK_C[0], SX, s), lerp(CLOCK_C[1], SY - R - CLOCK_R + 10, s * s)
            elif k < 1.4:
                s = (k - 0.6) / 0.8
                cx = lerp(SX, 560, s)
                cy = lerp(SY - R - CLOCK_R + 10, FLOOR - CLOCK_R, s) - 260 * math.sin(math.pi * s)
            else:
                cx, cy = 560, FLOOR - CLOCK_R
            ang = min(k, 1.4) * 5.0
        dr.ellipse([(cx - CLOCK_R) * S, (cy - CLOCK_R) * S, (cx + CLOCK_R) * S, (cy + CLOCK_R) * S], fill=(230, 226, 214), outline=(70, 60, 64), width=int(7 * S))
        for a, ln in ((ang - 1.2, 0.5), (ang + 0.6, 0.75)):
            dr.line([P(cx, cy), P(cx + ln * CLOCK_R * math.sin(a), cy - ln * CLOCK_R * math.cos(a))], fill=(40, 36, 40), width=int(6 * S))
        # le lit
        rect(230, 980, 282, FLOOR, BED)
        dr.ellipse([225 * S, 960 * S, 287 * S, 1004 * S], fill=BED)
        rect(230, YM + 70, 780, YM + 120, BED)
        rect(250, YM + 120, 278, FLOOR, BED); rect(745, YM + 120, 772, FLOOR, BED)
        rect(282, YM, 780, YM + 72, MATT)
        dr.rounded_rectangle([292 * S, (YM - 52) * S, 510 * S, (YM + 6) * S], radius=26 * S, fill=PILLOW)
        # Snooze
        awake = self.is_awake(t)
        first = self.awake[0]
        sit = 0.0
        if first[0] <= t <= first[1]:
            sit = min(1.0, (t - first[0]) / 0.3, (first[1] - t) / 0.2)
        sq = 0.0
        for th in self.head_hits:
            d = t - th
            if 0 <= d < 0.5:
                sq = max(sq, 0.13 * math.exp(-d * 8) * math.cos(d * 24))
        bx, by = self.bounce_at(t)
        look = max(-1.0, min(1.0, (bx - SX) / 300.0))
        draw_snooze_at(dr, SX, YM + 16 - R * (1 - sq) - 45 * sit, R, S, open_k=1.0 if awake else 0.0, look=look,
                       talk=self.talking(t), smile=(not awake) and (t > 9.2), sq=sq)
        if not awake:
            for i in range(3):
                ph = (t * 0.6 + i / 3) % 1.0
                zx, zy = SX + 90 + 70 * ph, SY - R - 30 - 160 * ph
                col = mix(wall, (170, 170, 200), min(1.0, ph * 3, (1 - ph) * 3))
                dr.text((zx * S, zy * S), "z" if i % 2 else "Z", fill=col, anchor="mm", font=font(int((34 + 30 * ph) * S)))
        # la couverture
        top = [(lerp(470, 780, i / 30) * S, (YM - 24 + 5 * math.sin(lerp(470, 780, i / 30) / 50)) * S) for i in range(31)]
        dr.polygon(top + [(780 * S, (YM + 76) * S), (470 * S, (YM + 76) * S)], fill=BLANKET)
        # la table de nuit et la lampe
        sx0, stop, sx1 = STAND
        rect(sx0, stop, sx1, FLOOR, (70, 52, 46))
        k = max(0.0, min(1.0, (t - T_LAMP - 0.1) / 0.55))
        a = -math.pi / 2 * (k ** 2)              # elle bascule vers la gauche
        if k >= 1.0:
            a = -math.pi / 2
        px, py = sx0 + 10 if k > 0 else LAMP_X, stop
        if k > 0:
            # le pied tourne autour du coin de la table, puis la lampe tombe au sol
            px, py = lerp(LAMP_X, sx0 - 40, k), lerp(stop, FLOOR - 16, k ** 2)
        ca, sa = math.cos(a), math.sin(a)

        def RP(u, v):
            return ((px + u * ca - v * sa) * S, (py + u * sa + v * ca) * S)
        dr.polygon([RP(-8, 0), RP(8, 0), RP(8, -80), RP(-8, -80)], fill=(150, 140, 120))
        dr.polygon([RP(-45, -80), RP(45, -80), RP(28, -160), RP(-28, -160)], fill=(220, 200, 150))
        # Bounce
        base.ball(dr, bx * S, by * S, RB * S)


DEFAULTS = {
    "fps": 60,
    "min_duration_s": 8.0,
    "max_duration_s": 75.0,
    "end_hold_s": 0.0,
    "hook_text_s": 2.6,
}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
