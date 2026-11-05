"""
Prototype « le premier jour » : la suite de « Will Bounce get hired? ». Le même recruteur
(voix du narrateur, sous-titrée), la même bulle qui traduit les « Bounce ». Un open space
« QUIET ZONE » : chaque « Bounce » fait jaillir les têtes des trois collègues. En réunion,
quand le chef demande un volontaire, les collègues plongent derrière leurs cloisons et la
balle, qui ne s'arrête jamais de rebondir, est la seule qui dépasse : chaque rebond vaut une
main levée. Les tâches s'empilent, de plus en plus vite. Un carton de déménagement attend
sur la desserte du chef. À la fin, c'est lui qui part s'asseoir sur la petite chaise, le
carton dans les bras ; la balle prend son fauteuil.

Tout est calculé d'avance sur une seule horloge : les contacts de la balle (durs : bureau,
téléphone, desserte ; mous : coussin, siège de cuir), les arcs qui les relient sous une
gravité unique, les répliques placées comme base.build_narration les placera (mêmes durées,
mêmes écarts), et les poses des personnages.

Une voix en plus du narrateur : la cliente au téléphone (Kokoro af_sarah, générée au rendu).

    python3 src/stories/firstday.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
import audio_kit as ak
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import voice as narr_voice

SR = ak.SR

# ------------------------------------------------------------------ voix
CLIENT_VOICE = "af_sarah"
CLIENT = {"This is a disaster! I'm canceling everything!", "Oh. Okay. Sorry."}
_orig_say = narr_voice.say


def story_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    if text in CLIENT:
        return _orig_say(text, CLIENT_VOICE, length_scale, sr)
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = story_say

_orig_build = base.build_narration


def build_narration_keep(sim, cfg):
    narr, replies = _orig_build(sim, cfg)
    sim.narr = narr
    return narr, replies


base.build_narration = build_narration_keep

_orig_hero_word = base.hero_word
_hero_memo = {}


def steady_hero_word(text, cfg):
    """Le même « Bounce » pour toute la vidéo : la prise la plus courte (≤ 0,78 s)."""
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

_orig_hook = base.hook_audio
_hook_memo = {}


def steady_hook(cfg):
    """La même prise d'accroche pour le plan et pour le rendu (piper varie d'une prise à l'autre)."""
    key = (cfg.get("hook_text"), cfg.get("hook_narrator"))
    if key not in _hook_memo:
        _hook_memo[key] = _orig_hook(cfg)
    v = _hook_memo[key]
    return None if v is None else v.copy()


base.hook_audio = steady_hook

# ------------------------------------------------------------------ le décor
W, H = 1080, 1920
G = 2600.0
R = 90.0
FLOOR = 1400.0
SCENE_TOP = 422.0
WALL = (36, 38, 56)
CARPET = (52, 48, 60)
WOOD = (122, 86, 58)
PINK = (255, 60, 200)
SUIT = (46, 50, 70)
HEAD = (74, 78, 100)
CARD = (176, 132, 82)

CUSH = (60.0, 245.0, 1190.0)          # coussin bleu : x0, x1, dessus
DESK = (255.0, 600.0, 1130.0)
PHONE = (526.0, 598.0, 1074.0)          # dessus du combiné
PART = (320.0, 732.0, 1000.0)           # cloisons : x0, x1, dessus
TABLE = (680.0, 780.0, 1235.0)          # la desserte du chef
SEAT = (772.0, 900.0, 1180.0)           # siège de cuir
BOARD = (500.0, 446.0, 930.0, 760.0)
SIGN = (215.0, 726.0, 495.0, 800.0)
COLS = [(395.0, (70, 150, 150)), (525.0, (200, 170, 70)), (655.0, (140, 120, 190))]
FOLD_COL = [(230, 190, 60), (80, 140, 220), (210, 60, 60), (90, 190, 110)]
STACK_X = 470.0
FOLD_W, FOLD_H = 80.0, 24.0

SPOTS = {   # où la balle touche : (x, y du centre, dur ?)
    "cushion": (152.0, CUSH[2] - R, False),
    "desk": (345.0, DESK[2] - R, True),
    "phone": (562.0, PHONE[2] - R, True),
    "table": (725.0, TABLE[2] - R, True),
    "seat": (836.0, SEAT[2] - R, False),
}

# poses des collègues (y du centre de la tête)
PEEK, ATTN, POP, DUCK, STAND = 990.0, 955.0, 872.0, 1078.0, 800.0


def clamp01(u):
    return max(0.0, min(1.0, u))


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def lerp(a, b, u):
    return a + (b - a) * u


class Track:
    """Une valeur qui change par segments (début, durée, cible), sans chevauchement."""

    def __init__(self, v):
        self.v0 = v
        self.segs = []

    def to(self, t0, dur, v, ease=smooth):
        self.segs.append((t0, max(1e-3, dur), v, ease))
        self.segs.sort(key=lambda s: s[0])
        return self

    def __call__(self, t):
        v = self.v0
        for (t0, d, tgt, e) in self.segs:
            if t < t0:
                break
            if t >= t0 + d:
                v = tgt
            else:
                v = lerp(v, tgt, e((t - t0) / d))
                break
        return v


def rr(dr, b, **kw):
    dr.rectangle([min(b[0], b[2]), min(b[1], b[3]), max(b[0], b[2]), max(b[1], b[3])], **kw)


def rot(pts, cx, cy, a):
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for (x, y) in pts]


# ------------------------------------------------------------------ le plan
class Plan:
    def __init__(self, cfg):
        self.cfg = cfg
        hook = base.hook_audio(cfg)
        self.hook_end = 0.15 + len(hook) / SR if hook is not None else 0.0
        self.narr_free = (self.hook_end + 0.3) if hook is not None else 0.3
        self.C = []            # contacts (t, spot)
        self.lines = []        # (start, text, key, end, who)
        self.bubbles = []      # (t, text)
        self.last_hard = -9.0
        self.last_line_end = self.hook_end
        self.bubble_free = 0.0
        self.home = "cushion"
        self.t = 0.0
        self.cols = [Track(PEEK) for _ in COLS]
        self.lean = [Track(0.0) for _ in COLS]
        self.phones = [False] * 3        # casque, sac...
        self.marks = {}

    # --- voix
    def dur(self, text):
        x = narr_voice.say(text, self.cfg["narrator_voice"], self.cfg["narrator_length"])
        return len(x) / SR if x is not None else 0.8

    def line(self, text, earliest=None, who="boss"):
        st = max(earliest if earliest is not None else self.t, self.last_hard + 0.92,
                 self.last_line_end + self.cfg["narr_gap_s"] + 0.02, self.bubble_free)
        d = self.dur(text)
        self.lines.append((st, text, f"l{len(self.lines)}", st + d, who))
        self.last_line_end = st + d
        self.t = st + d
        return st, st + d

    # --- la balle
    def contact(self, t, spot):
        self.C.append((t, spot))

    def fill_home(self, t0, t1, period=0.5):
        """Petits sauts sur le coussin (ou le siège) entre t0 et t1 (t0, t1 : contacts)."""
        gap = t1 - t0
        n = max(1, int(round(gap / period)))
        for k in range(1, n):
            self.contact(t0 + gap * k / n, self.home)

    def hard(self, spot="desk", earliest=None, tin=0.85, chain=False):
        """Un contact dur ; la balle vient de son coussin (arc d'approche `tin`), ou
        directement du contact précédent si `chain`."""
        t = max(earliest if earliest is not None else self.t, self.last_hard + 0.92,
                self.last_line_end + 0.15)
        prev_t, prev_spot = self.C[-1]
        if chain:
            pass
        else:
            if SPOTS[prev_spot][2]:              # on était sur du dur : retour au coussin
                back = prev_t + 0.55
                self.contact(back, self.home)
                prev_t = back
            t = max(t, prev_t + tin + 0.2)
            self.fill_home(prev_t, t - tin)
            self.contact(t - tin, self.home)
        self.contact(t, spot)
        self.last_hard = t
        self.t = t
        return t

    def bubble(self, text, t_hit):
        self.bubbles.append((t_hit + 0.3, text))
        self.bubble_free = t_hit + 0.3 + 1.8
        self.t = t_hit

    def hold(self, t1, period=0.5):
        """La balle saute sur son coussin jusqu'à t1 (au moins)."""
        prev_t, prev_spot = self.C[-1]
        if SPOTS[prev_spot][2]:
            back = prev_t + 0.55
            self.contact(back, self.home)
            prev_t = back
        if t1 > prev_t + 0.2:
            self.fill_home(prev_t, t1, period)
            self.contact(t1, self.home)
        self.t = max(self.t, t1)

    # --- les collègues
    def heads(self, t, pose, dur=0.12, who=(0, 1, 2), lean=None, stagger=0.0, settle=True):
        for k, i in enumerate(who):
            tt = t + k * stagger
            if pose == POP and settle:
                self.cols[i].to(tt, dur, POP - 14).to(tt + dur, 0.3, POP)
            else:
                self.cols[i].to(tt, dur, pose)
            if lean is not None:
                self.lean[i].to(tt, max(dur, 0.2), lean)

    def jolt(self, t, amount=40.0):
        """Les têtes déjà levées sursautent."""
        for i in range(3):
            v = self.cols[i](t)
            self.cols[i].to(t, 0.08, v - amount).to(t + 0.08, 0.3, v)


class Sim:
    scene_top = SCENE_TOP / H

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        self.build()

    # ================================================================ le scénario
    def build(self):
        p = Plan(self.cfg)
        self.p = p
        board = []            # (t, durée d'écriture, tâche)
        folders = []          # (t lancer, index)
        boss = {k: Track(v) for k, v in dict(x=836.0, hip=SEAT[2], larm=12.0, llen=150.0, rarm=12.0,
                                              rlen=150.0, nod=0.0, walk=0.0).items()}
        self.boss = boss
        clock = Track(9.0)
        self.clock = clock
        counter = [(0.0, "DAY 1 · 9:00 AM")]
        sign_tilt = Track(0.0)
        sign_fall = [None]
        phone_ring = []       # (t0, t1)
        self.box_mode = []    # (t, mode) : table / carried / lap

        def arm(t, side, ang, ln=150.0, dur=0.25):
            boss["larm" if side == "l" else "rarm"].to(t, dur, ang)
            boss["llen" if side == "l" else "rlen"].to(t, dur, ln)

        def write(t, task, dur=0.6, standing=False):
            arm(t - 0.25, "r", 165.0 if not standing else 150.0, 240.0 if not standing else 190.0, 0.25)
            board.append((t, dur, task))
            arm(t + dur + 0.05, "r", 12.0, 150.0, 0.3)

        def toss(t, k):
            arm(t - 0.3, "l", 40.0, 160.0, 0.2)
            arm(t - 0.1, "l", 115.0, 190.0, 0.12)
            folders.append((t, k))
            arm(t + 0.25, "l", 12.0, 150.0, 0.35)

        # ---- 9:00 : l'open space silencieux
        p.contact(-0.38, "cushion")
        p.contact(0.30, "desk")                         # muet, sous l'accroche
        p.last_hard = 0.30
        p.heads(0.30, POP, 0.12, lean=-22.0)
        sign_tilt.to(0.30, 0.06, 0.03).to(0.36, 0.3, 0.0)
        h = p.hard("desk", earliest=p.hook_end + 0.15)
        p.jolt(h, 45.0)
        sign_tilt.to(h, 0.06, 0.03).to(h + 0.06, 0.3, 0.0)
        s, e = p.line("Welcome to the quiet floor.", h + 0.9)
        arm(s, "l", 60.0, 170.0, 0.4); arm(s, "r", 60.0, 170.0, 0.4)
        arm(e, "l", 12.0, 150.0, 0.4); arm(e, "r", 12.0, 150.0, 0.4)
        h = p.hard("desk", e + 0.15)
        p.jolt(h, 35.0)
        h = p.hard("desk", h + 1.08, chain=True)
        p.jolt(h, 50.0)
        sign_tilt.to(h, 0.25, 0.30)                     # il pend de travers
        p.bubble("Hi, I'm new.", h)
        s, e = p.line("Shh. We whisper here.")
        arm(s, "l", 165.0, 105.0, 0.25)                 # le doigt devant la tête
        arm(s + 0.75, "l", 8.5, 303.0, 0.35)            # puis la main posée sur le carton
        self.box_pats = [(s + 1.1, 0.35)]
        p.heads(s + 0.3, PEEK, 0.5, lean=0.0)
        h = p.hard("desk", e + 0.15)
        arm(h - 0.2, "l", 12.0, 150.0, 0.3)
        p.heads(h, POP, 0.12, lean=-22.0)
        h = p.hard("desk", chain=True)
        p.jolt(h, 40.0)
        self.headphones_t = h + 0.15
        h = p.hard("desk", h + 1.1, chain=True)
        p.jolt(h, 40.0)
        sign_fall[0] = h
        p.cols[0].to(h + 0.05, 0.1, DUCK).to(h + 0.6, 0.3, POP)
        p.bubble("That was my whisper.", h)
        s, e = p.line("Noted.")
        boss["nod"].to(s, 0.25, 1.0).to(s + 0.25, 0.25, 0.0)
        arm(s, "l", 8.5, 303.0, 0.3)
        self.box_pats.append((s + 0.35, 0.3))
        arm(e + 0.1, "l", 12.0, 150.0, 0.3)
        # ---- 11:00 : la réunion
        tc = e + 0.25
        clock.to(tc, 0.6, 11.0)
        counter.append((tc + 0.3, "DAY 1 · 11:00 AM"))
        p.heads(tc, ATTN, 0.4, lean=14.0)
        s, e = p.line("Who wants to plan the office party?", tc + 0.7)
        arm(s, "l", 12.0, 150.0, 0.3); arm(s, "r", 150.0, 170.0, 0.3)
        p.heads(s + 0.72 * (e - s), DUCK, 0.18, stagger=0.05)
        p.hold(e + 0.1, 0.42)                          # tout le monde a plongé ; elle seule bouge
        h = p.hard("desk", e + 0.15 + 1.25, tin=1.2)
        arm(h - 0.75, "l", 100.0, 210.0, 0.2); arm(h - 0.75, "r", 12.0, 150.0, 0.3)
        p.bubble("I'm just sitting here.", h)
        s, e = p.line("Bounce! Great.")
        write(e + 0.05, "PARTY")
        toss(e + 0.9, 0)
        p.heads(e + 1.4, PEEK, 0.7, lean=0.0)
        # samedi : il coupe sa question
        s, e = p.line("Who can work Saturday—", e + 1.55)
        p.heads(s, DUCK, 0.12)
        h = p.hard("desk", e + 0.15, tin=0.8)
        write(h + 0.05, "SATURDAY", 0.5)
        toss(h + 0.7, 1)
        h = p.hard("desk", h + 1.85, tin=1.0)
        p.bubble("I don't even have hands.", h)
        # le client : la ligne est au tableau avant la fin de sa question
        s, e = p.line("Who wants—")
        write(s - 0.1, "CLIENT", 0.5)
        h = p.hard("desk", e + 0.15, tin=0.8)
        toss(h + 0.35, 2)
        # le PDG : il écrit d'abord, puis il demande
        write(h + 0.75, "CEO", 0.45)
        boss["nod"].to(h + 1.35, 0.3, -1.0)
        s, e = p.line("Who will pitch to the CEO?", h + 1.55)
        h = p.hard("desk", e + 0.15, tin=1.15)
        boss["nod"].to(h - 0.5, 0.3, 0.0)
        p.bubble("I'll stop moving now.", h)
        # la tentative d'arrêt : des sauts de plus en plus petits, dès la bulle
        back = h + 0.55
        p.contact(back, "cushion")
        tt = back
        for per in (0.46, 0.4, 0.34, 0.29, 0.25, 0.22, 0.2, 0.2):
            tt += per
            p.contact(tt, "cushion")
        self.tiny = (back, tt)
        s, e = p.line("Bold.")
        toss(e + 0.2, 3)
        p.heads(back + 0.9, PEEK + 20, 0.7, who=(0,), lean=-10.0)
        p.heads(back + 1.5, PEEK, 0.7, who=(1,), lean=-10.0)
        p.heads(back + 2.1, PEEK - 15, 0.7, who=(2,), lean=-14.0)
        ring0 = tt - 0.6
        p.t = tt
        h = p.hard("phone", tt + 0.7, tin=0.7)
        phone_ring.append((ring0, h))
        p.heads(h, DUCK, 0.12)
        s, e = p.line("This is a disaster! I'm canceling everything!", h + 0.9, who="client")
        h = p.hard("desk", e + 0.15, tin=0.8)
        h = p.hard("desk", chain=True)
        p.bubble("No.", h)
        s2, e2 = p.line("Oh. Okay. Sorry.", who="client")
        self.phone_off = e2
        p.heads(e2 + 0.15, PEEK - 30, 0.9, lean=-24.0, stagger=0.2)
        # ---- 4:59 : tout le monde s'en va, le chef prend le carton
        tc = e2 + 0.6
        clock.to(tc, 0.6, 16.0 + 59.0 / 60.0)
        counter.append((tc + 0.3, "DAY 1 · 4:59 PM"))
        p.heads(tc + 0.3, STAND, 0.5, lean=-10.0, stagger=0.1)
        self.bags_t = tc + 0.3
        tu = tc + 0.4
        hb = p.hard("desk", e2 + 0.95, tin=0.8)
        boss["hip"].to(tu, 0.35, 1090.0)                # il se lève
        self.box_mode.append((tu + 0.3, "carried"))
        arm(tu + 0.1, "l", 25.0, 130.0, 0.3); arm(tu + 0.1, "r", 25.0, 130.0, 0.3)
        boss["x"].to(tu + 0.45, 1.3, 545.0, ease=lambda u: u)
        boss["walk"].to(tu + 0.45, 1.3, 1.0, ease=lambda u: u)
        s, e = p.line("Any questions?", tu + 0.9)
        p.heads(s + 0.3, STAND - 6, 0.1)                # ils se figent
        h = p.hard("desk", e + 0.75, tin=1.0)
        self.collapse_t = h
        s, e = p.line("Anyone want my job too?", h + 1.25)
        boss["nod"].to(s, 0.4, 1.0)
        p.heads(s + 0.25, DUCK, 0.14, stagger=0.06)
        h = p.hard("desk", e + 0.15)
        h = p.hard("desk", h + 1.1, chain=True)
        p.bubble("Finally, one I want.", h)
        s, e = p.line("...Fine.")
        boss["nod"].to(s, 0.4, 0.0)
        # il écrit la dernière ligne, puis va s'asseoir sur la petite chaise
        self.box_mode.append((e + 0.2, "hip"))
        write(e + 0.45, "MY JOB", 0.55, standing=True)
        tw = e + 1.25
        arm(tw, "l", 25.0, 130.0, 0.25); arm(tw, "r", 25.0, 130.0, 0.25)
        self.box_mode.append((tw, "carried"))
        # la balle part vers le fauteuil de cuir
        h = p.hard("desk", e + 0.15, tin=0.8)
        h = p.hard("table", h + 1.3, chain=True)
        p.contact(h + 0.55, "seat")
        p.home = "seat"
        boss["x"].to(tw + 0.1, 1.25, SPOTS["cushion"][0], ease=lambda u: u)
        boss["walk"].to(tw + 0.1, 1.25, 2.0, ease=lambda u: u)
        sit = tw + 1.4
        boss["hip"].to(sit, 0.3, CUSH[2] + 4)
        self.box_mode.append((sit + 0.15, "lap"))
        self.boss_sit = sit
        p.heads(h + 0.6, PEEK, 0.6, lean=0.0)
        p.t = sit + 0.3
        h = p.hard("table", sit + 0.5, tin=0.7)
        p.bubble("What's your name?", h)
        s, e = p.line("Um... Bounce?", h + 0.3 + 1.8 + 0.1)
        self.boss_hops = [s + 0.35]
        p.heads(s + 0.35, POP, 0.12, lean=-26.0)
        h = p.hard("table", e + 0.15, tin=0.75)
        self.smile_t = h
        p.bubble("You're hired.", h)
        p.heads(h + 0.35, PEEK, 0.45, lean=0.0)          # elles redescendent...
        h2 = p.hard("table", h + 1.3, tin=0.6)
        self.boss_hops.append(h2)
        p.heads(h2, POP, 0.12, lean=-26.0)               # ...et rejaillissent, comme à 0,3 s
        self.end_t = h2 + 1.1
        p.hold(self.end_t + 0.6)

        # ---- mise en forme
        self.C = sorted(p.C)
        self.hard_t = [t for (t, s) in self.C if SPOTS[s][2] and t >= 0]
        self.lines = [(st, text, key) for (st, text, key, en, who) in p.lines]
        self.line_who = {text: who for (st, text, key, en, who) in p.lines}
        self.plan_lines = p.lines
        self.bubbles = p.bubbles
        self.board = board
        self.folders = folders
        self.counter_ev = counter
        self.sign_tilt, self.sign_fall = sign_tilt, sign_fall[0]
        self.phone_ring = phone_ring
        self.cols_y, self.cols_lean = p.cols, p.lean
        self.hi = 0
        self.check_arcs()

    def check_arcs(self):
        """Aucun arc plus haut que 700 px, aucun sommet dans la bande du haut."""
        self.worst = 0.0
        for (a, b) in zip(self.C, self.C[1:]):
            T = b[0] - a[0]
            (x0, y0, _), (x1, y1, _) = SPOTS[a[1]], SPOTS[b[1]]
            vy = (y1 - y0 - 0.5 * G * T * T) / T
            top = y0 - vy * vy / (2 * G) if vy < 0 else y0
            hgt = max(y0, y1) - top
            self.worst = max(self.worst, hgt)
            if hgt > 700 or top < 470:
                print(f"[firstday] arc trop haut à {a[0]:.2f} : {hgt:.0f} px, sommet {top:.0f}", file=sys.stderr)

    # ================================================================ la balle
    def ball_at(self, t):
        C = self.C
        if t <= C[0][0]:
            return SPOTS[C[0][1]][0], SPOTS[C[0][1]][1], None
        for a, b in zip(C, C[1:]):
            if a[0] <= t <= b[0]:
                T = b[0] - a[0]
                (x0, y0, _), (x1, y1, _) = SPOTS[a[1]], SPOTS[b[1]]
                s = t - a[0]
                vy = (y1 - y0 - 0.5 * G * T * T) / T
                x = x0 + (x1 - x0) * s / T
                y = y0 + vy * s + 0.5 * G * s * s
                # le coussin se creuse au contact mou
                dent = 0.0
                for (tc, sp, hop) in ((a[0], a[1], T), (b[0], b[1], T)):
                    if not SPOTS[sp][2]:
                        k = 1 - abs(t - tc) / 0.09
                        if k > 0:
                            dent = max(dent, k * min(26.0, 6.0 + 30.0 * hop))
                return x, y + dent, (dent, a[1] if t - a[0] < b[0] - t else b[1])
        return SPOTS[C[-1][1]][0], SPOTS[C[-1][1]][1], None

    # ================================================================ moteur
    def step(self, dt):
        self.t += dt
        evs = []
        while self.hi < len(self.hard_t) and self.hard_t[self.hi] <= self.t:
            evs.append(("hit", "dur"))
            self.hi += 1
        if not self.payoff and self.t >= self.end_t - 0.3:
            self.payoff = True
            evs.append(("payoff", "hired"))
        if self.t >= self.end_t - 0.3:
            self.done = True
        return evs

    def hero_mood(self):
        return None

    def snapshot(self):
        return self.t

    def counter(self, snap):
        txt = None
        for (t0, s) in self.counter_ev:
            if snap >= t0:
                txt = s
        return txt

    # ================================================================ dessin
    def talking(self, t, who="boss"):
        for n in self.narr:
            if n["start"] <= t <= n["end"] and self.line_who.get(n["text"], "boss") == who:
                return True
        return False

    def draw(self, dr, snap, t, S):
        P = lambda v: v * S
        rr(dr, [0, P(SCENE_TOP), P(W), P(H)], fill=WALL)
        self.draw_wall(dr, t, S)
        self.draw_sign(dr, t, S)
        self.draw_colleagues(dr, t, S)
        # cloisons
        x0, x1, top = PART
        rr(dr, [P(x0), P(top), P(x1), P(FLOOR)], fill=(78, 84, 104))
        rr(dr, [P(x0), P(top), P(x1), P(top + 12)], fill=(112, 118, 142))
        for xx in (460.0, 590.0):
            rr(dr, [P(xx - 3), P(top), P(xx + 3), P(FLOOR)], fill=(60, 64, 84))
        # sol
        rr(dr, [0, P(FLOOR), P(W), P(H)], fill=CARPET)
        rr(dr, [0, P(FLOOR), P(W), P(FLOOR + 6)], fill=dim(CARPET, 1.3))
        self.draw_exec(dr, t, S)
        self.draw_table(dr, t, S)
        self.draw_small_chair(dr, t, S)
        bx = self.boss["x"](t)
        seated_exec = self.boss["hip"](t) > 1150 and bx > 700
        if not seated_exec:
            self.draw_boss(dr, t, S)
        self.draw_folders(dr, t, S, back=True)
        self.draw_desk(dr, t, S)
        self.draw_folders(dr, t, S)
        if t >= self.smile_t:
            base.HERO["expr"] = "win"
        x, y, _ = self.ball_at(t)
        base.ball(dr, P(x), P(y), P(R))
        self.draw_bubble(dr, t, S, x, y)
        rr(dr, [0, 0, P(W), P(SCENE_TOP) - 1], fill=tuple(self.cfg["bg_color"]))

    def draw_wall(self, dr, t, S):
        P = lambda v: v * S
        # l'horloge
        cx, cy = 95.0, 520.0
        circle(dr, P(cx), P(cy), P(46), (220, 220, 228))
        circle(dr, P(cx), P(cy), P(39), (240, 240, 244))
        hrs = self.clock(t)
        am = (hrs % 1.0) * 2 * math.pi
        ah = (hrs % 12.0) / 12.0 * 2 * math.pi
        dr.line([(P(cx), P(cy)), (P(cx + 32 * math.sin(am)), P(cy - 32 * math.cos(am)))], fill=(30, 30, 40), width=max(1, int(P(5))))
        dr.line([(P(cx), P(cy)), (P(cx + 21 * math.sin(ah)), P(cy - 21 * math.cos(ah)))], fill=(30, 30, 40), width=max(1, int(P(7))))
        circle(dr, P(cx), P(cy), P(5), (30, 30, 40))
        # le tableau blanc
        x0, y0, x1, y1 = BOARD
        rr(dr, [P(x0), P(y0), P(x1), P(y1)], fill=(150, 152, 162))
        rr(dr, [P(x0 + 10), P(y0 + 10), P(x1 - 10), P(y1 - 10)], fill=(236, 238, 242))
        dr.text((P((x0 + x1) / 2), P(y0 + 36)), "TODAY", fill=(110, 110, 130), anchor="mm", font=base.font(P(30)))
        f = base.font(P(32))
        for i, (tw, d, task) in enumerate(self.board):
            if t < tw:
                continue
            u = clamp01((t - tw) / d)
            y = y0 + 76 + i * 40
            dr.text((P(x0 + 24), P(y)), task, fill=(30, 40, 90), anchor="lm", font=f)
            dr.text((P(x1 - 26), P(y)), "BOUNCE", fill=(220, 30, 160), anchor="rm", font=f)
            if u < 1:
                cx0 = x0 + 24 + u * (x1 - x0 - 50)
                rr(dr, [P(cx0), P(y - 19), P(x1 - 10), P(y + 19)], fill=(236, 238, 242))

    def sign_pose(self, t):
        x0, y0, x1, y1 = SIGN
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        a = self.sign_tilt(t)
        pts = rot(pts, x1 - 20, y0 + 6, -a)
        dy = 0.0
        if self.sign_fall is not None and t >= self.sign_fall:
            s = t - self.sign_fall
            dy = 0.5 * G * 0.8 * s * s
            pts = rot(pts, x1 - 20, y0 + 6, -0.25 * min(1.0, s * 3))
        return [(x, y + dy) for (x, y) in pts], dy

    def draw_sign(self, dr, t, S):
        P = lambda v: v * S
        pts, dy = self.sign_pose(t)
        if dy > 700:
            return
        dr.polygon([(P(x), P(y)) for (x, y) in pts], fill=(200, 50, 60))
        cx = sum(p[0] for p in pts) / 4
        cy = sum(p[1] for p in pts) / 4
        inner = [(cx + (x - cx) * 0.95, cy + (y - cy) * 0.82) for (x, y) in pts]
        dr.polygon([(P(x), P(y)) for (x, y) in inner], fill=(240, 236, 230))
        a = math.atan2(pts[1][1] - pts[0][1], pts[1][0] - pts[0][0])
        if abs(a) < 0.05:
            dr.text((P(cx), P(cy)), "QUIET ZONE", fill=(200, 50, 60), anchor="mm", font=base.font(P(37)))
        else:
            from PIL import Image, ImageDraw
            fnt = base.font(P(37))
            w, h = int(P(280)), int(P(66))
            im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((w / 2, h / 2), "QUIET ZONE", fill=(200, 50, 60, 255), anchor="mm", font=fnt)
            im = im.rotate(-math.degrees(a), resample=Image.BICUBIC, expand=True)
            self._paste = getattr(self, "_paste", [])
            dr._image.paste(im, (int(P(cx) - im.width / 2), int(P(cy) - im.height / 2)), im)
        for (nx, ny) in ((SIGN[0] + 20, SIGN[1] + 6), (SIGN[2] - 20, SIGN[1] + 6)):
            circle(dr, P(nx), P(ny), P(5), (160, 160, 170))

    def draw_colleagues(self, dr, t, S):
        P = lambda v: v * S
        for i, (cx, col) in enumerate(COLS):
            hy = self.cols_y[i](t)
            ln = self.cols_lean[i](t)
            hx = cx + ln
            body = [(cx - 52, FLOOR), (cx + 52, FLOOR), (hx + 50, hy + 60), (hx - 50, hy + 60)]
            dr.polygon([(P(x), P(y)) for (x, y) in body], fill=col)
            dr.rounded_rectangle([P(hx - 50), P(hy + 40), P(hx + 50), P(hy + 90)], radius=int(P(20)), fill=col)
            circle(dr, P(hx), P(hy), P(44), dim(col, 1.15))
            if i == 1 and t >= self.headphones_t:
                k = clamp01((t - self.headphones_t) / 0.25)
                yy = hy - 30 * (1 - k)
                dr.arc([P(hx - 52), P(yy - 56), P(hx + 52), P(yy + 40)], 180, 360, fill=(30, 30, 36), width=int(P(9)))
                for sx in (-1, 1):
                    dr.rounded_rectangle([P(hx + sx * 50 - 12), P(yy - 12), P(hx + sx * 50 + 12), P(yy + 26)], radius=int(P(8)), fill=(30, 30, 36))
            if t >= getattr(self, "bags_t", 1e9) and hy < 900:
                bxx = hx - 62
                dr.line([(P(bxx), P(hy + 120)), (P(bxx + 6), P(hy + 150))], fill=(30, 30, 36), width=int(P(5)))
                rr(dr, [P(bxx - 20), P(hy + 150), P(bxx + 26), P(hy + 190)], fill=dim(col, 0.55))

    def draw_exec(self, dr, t, S):
        """Le fauteuil de direction, et le chef quand il y est assis."""
        P = lambda v: v * S
        x0, x1, top = SEAT
        dr.rounded_rectangle([P(x0 - 6), P(714), P(x1 + 30), P(top)], radius=int(P(40)), fill=(28, 28, 34))       # dossier
        dr.rounded_rectangle([P(x0 + 10), P(732), P(x1 + 14), P(top - 10)], radius=int(P(32)), fill=(36, 36, 44))
        bx = self.boss["x"](t)
        seated_exec = self.boss["hip"](t) > 1150 and bx > 700
        if seated_exec:
            self.draw_boss(dr, t, S)
        dent = 0.0
        x, y, info = self.ball_at(t)
        if info and info[1] == "seat":
            dent = info[0]
        pts = [(x0, top + 2)]
        for k in range(13):
            xx = x0 + (x1 - x0) * k / 12
            d = dent * max(0.0, 1 - abs(xx - x) / 110)
            pts.append((xx, top + d))
        pts += [(x1, top + 30), (x0, top + 30)]
        dr.polygon([(P(a), P(b)) for (a, b) in pts], fill=(44, 44, 52))
        rr(dr, [P(830), P(top + 30), P(844), P(1355)], fill=(70, 70, 80))
        rr(dr, [P(776), P(1355), P(898), P(1366)], fill=(70, 70, 80))
        for wx in (786, 888):
            circle(dr, P(wx), P(1382), P(14), (30, 30, 36))

    def draw_table(self, dr, t, S):
        P = lambda v: v * S
        x0, x1, top = TABLE
        rr(dr, [P(x0), P(top), P(x1), P(top + 14)], fill=(150, 150, 160))
        for lx in (x0 + 8, x1 - 14):
            rr(dr, [P(lx), P(top + 14), P(lx + 6), P(FLOOR)], fill=(110, 110, 120))
        mode = "table"
        for (tm, m) in self.box_mode:
            if t >= tm:
                mode = m
        if mode == "table":
            pat = 0.0
            for (tp, d) in self.box_pats:
                if tp <= t < tp + d:
                    pat = 5 * abs(math.sin((t - tp) / d * 2 * math.pi))
            self.box(dr, S, 730.0, top - 44 + pat * 0.3)

    def box(self, dr, S, cx, cy):
        """Un carton de déménagement vide, rabats ouverts."""
        P = lambda v: v * S
        rr(dr, [P(cx - 50), P(cy - 40), P(cx + 50), P(cy + 44)], fill=CARD)
        rr(dr, [P(cx - 50), P(cy - 40), P(cx + 50), P(cy - 30)], fill=dim(CARD, 0.75))
        dr.polygon([(P(cx - 50), P(cy - 40)), (P(cx - 76), P(cy - 68)), (P(cx - 40), P(cy - 68)), (P(cx - 18), P(cy - 40))], fill=dim(CARD, 1.12))
        dr.polygon([(P(cx + 50), P(cy - 40)), (P(cx + 76), P(cy - 68)), (P(cx + 40), P(cy - 68)), (P(cx + 18), P(cy - 40))], fill=dim(CARD, 1.12))
        rr(dr, [P(cx - 16), P(cy - 8), P(cx + 16), P(cy + 2)], fill=dim(CARD, 0.6))

    def draw_small_chair(self, dr, t, S):
        P = lambda v: v * S
        x0, x1, top = CUSH
        rr(dr, [P(x0 + 4), P(960), P(x0 + 22), P(top)], fill=(70, 70, 84))          # dossier
        rr(dr, [P(x0 + 4), P(940), P(x0 + 40), P(1020)], fill=(70, 70, 84))
        rr(dr, [P(x0 + 30), P(top + 26), P(x1 - 4), P(top + 40)], fill=(70, 70, 84))
        rr(dr, [P(146), P(top + 40), P(158), P(1352)], fill=(90, 90, 100))
        rr(dr, [P(86), P(1352), P(218), P(1362)], fill=(90, 90, 100))
        for wx in (94, 210):
            circle(dr, P(wx), P(1380), P(14), (40, 40, 48))
        dent = 0.0
        x, y, info = self.ball_at(t)
        bxo = SPOTS["cushion"][0]
        if info and info[1] == "cushion":
            dent = info[0]
        if self.boss_sit is not None and t >= self.boss_sit:
            bxo = self.boss["x"](t)
            dent = 18.0 + self.boss_bob(t) * 0.8
            if t < self.boss_sit + 0.3:
                dent *= (t - self.boss_sit) / 0.3
        pts = [(x0, top + 30)]
        for k in range(13):
            xx = x0 + (x1 - x0) * k / 12
            d = dent * max(0.0, 1 - abs(xx - bxo) / 120)
            pts.append((xx, top + d))
        pts.append((x1, top + 30))
        dr.polygon([(P(a), P(b)) for (a, b) in pts], fill=(96, 104, 150))

    def boss_bob(self, t):
        """Ses petits sauts sur le coussin, à la fin (0 au repos, >0 en l'air)."""
        v = 0.0
        for th in getattr(self, "boss_hops", []):
            s = t - th
            if 0 <= s < 0.34:
                v = max(v, 34.0 * math.sin(math.pi * s / 0.34))
        return v

    def draw_boss(self, dr, t, S):
        """Le recruteur : tête ronde grise sans visage, costume, col blanc, cravate rouge."""
        P = lambda v: v * S
        b = self.boss
        x, hip = b["x"](t), b["hip"](t)
        walking = 0.0 < b["walk"](t) < 2.0 and abs(b["walk"](t) - round(b["walk"](t))) > 1e-3
        ph = t * 9.0
        bob = 6.0 * abs(math.sin(ph)) if walking else 0.0
        hop = self.boss_bob(t) if self.boss_sit is not None and t >= self.boss_sit else 0.0
        hip = hip - bob - hop
        top = hip - 330.0
        talk = self.talking(t, "boss")
        nod = b["nod"](t)
        # jambes
        for sx in (-1, 1):
            off = (10.0 * math.sin(ph + (0 if sx < 0 else math.pi))) if walking else 0.0
            rr(dr, [P(x + sx * 28 - 17 + off), P(hip - 4), P(x + sx * 28 + 17 + off), P(FLOOR - (0 if hop == 0 else 0))], fill=dim(SUIT, 0.85))
        # buste
        rr(dr, [P(x - 58), P(top), P(x + 58), P(hip)], fill=SUIT)
        dr.polygon([(P(x - 20), P(top)), (P(x + 20), P(top)), (P(x), P(top + 58))], fill=(232, 232, 236))
        dr.polygon([(P(x - 6), P(top + 10)), (P(x + 6), P(top + 10)), (P(x + 10), P(top + 80)), (P(x), P(top + 94)), (P(x - 10), P(top + 80))], fill=(190, 40, 50))
        # bras
        mode = "table"
        for (tm, m) in self.box_mode:
            if t >= tm:
                mode = m
        for side in ("l", "r"):
            sx = -1 if side == "l" else 1
            ang = math.radians(b["larm" if side == "l" else "rarm"](t))
            ln = b["llen" if side == "l" else "rlen"](t)
            sh = (x + sx * 50, top + 22)
            hand = (sh[0] + sx * math.sin(ang) * ln, sh[1] + math.cos(ang) * ln)
            if mode in ("carried", "lap"):
                hand = (x + sx * 30, hip - 120 if mode == "carried" else hip - 60)
            dr.line([(P(sh[0]), P(sh[1])), (P(hand[0]), P(hand[1]))], fill=SUIT, width=int(P(24)))
            circle(dr, P(hand[0]), P(hand[1]), P(12), SUIT)
        if mode == "carried":
            self.box(dr, S, x, hip - 140)
        elif mode == "hip":
            self.box(dr, S, x - 80, hip - 40)
        elif mode == "lap":
            self.box(dr, S, x, hip - 70)
        # tête
        hy = top - 52 + (3.0 * math.sin(t * 22) if talk else 0.0) + 8.0 * nod
        circle(dr, P(x + (-6.0 * nod if nod < 0 else 0)), P(hy), P(52), HEAD)

    def draw_desk(self, dr, t, S):
        P = lambda v: v * S
        x0, x1, top = DESK
        rr(dr, [P(x0 + 16), P(top + 24), P(x1 - 16), P(FLOOR)], fill=dim(WOOD, 0.7))
        rr(dr, [P(x0), P(top), P(x1), P(top + 26)], fill=WOOD)
        rr(dr, [P(x0), P(top), P(x1), P(top + 5)], fill=base.dim(WOOD, 1.25))
        # le téléphone
        px0, px1, ptop = PHONE
        jx = 0.0
        ringing = any(a <= t < b for (a, b) in self.phone_ring)
        if ringing:
            jx = 3.0 * math.sin(t * 70)
        x, y, info = self.ball_at(t)
        squash = 0.0
        if abs(x - SPOTS["phone"][0]) < 10 and y > SPOTS["phone"][1] - 4:
            squash = 4.0
        rr(dr, [P(px0 + jx), P(ptop + 14 + squash), P(px1 + jx), P(top)], fill=(60, 62, 72))
        rr(dr, [P(px0 - 4 + jx), P(ptop + squash), P(px1 + 4 + jx), P(ptop + 14 + squash)], fill=(40, 42, 50))
        on = ringing and (t * 6) % 1 < 0.5
        speaking = self.talking(t, "client")
        circle(dr, P(px1 - 10 + jx), P(top - 14), P(6), (240, 60, 60) if on else (90, 40, 40))
        if ringing:
            for sx in (-1, 1):
                for k in range(2):
                    xx = (px0 if sx < 0 else px1) + sx * (12 + 10 * k)
                    dr.line([(P(xx), P(ptop + 2)), (P(xx), P(top - 6))], fill=(220, 220, 230), width=int(P(4)))
        if speaking:
            cx, cy = px1 + 10, ptop - 10
            for k in range(3):
                r = 26 + 26 * k + 10 * ((t * 3) % 1)
                dr.arc([P(cx - r), P(cy - r), P(cx + r), P(cy + r)], 300, 360, fill=(230, 230, 240), width=int(P(5)))

    def folder_pose(self, t, k):
        """(x, y, angle) d'un dossier, ou None s'il n'est pas encore lancé."""
        ft = [f for f in self.folders if f[1] == k]
        if not ft or t < ft[0][0]:
            return None
        t0 = ft[0][0]
        sx, sy = self.boss_hand(t0)
        ex, ey = STACK_X, DESK[2] - FOLD_H * (k + 0.5)
        T = 0.7
        if t < t0 + T:
            s = t - t0
            vy = (ey - sy - 0.5 * G * T * T) / T
            return sx + (ex - sx) * s / T, sy + vy * s + 0.5 * G * s * s, 2.0 * (1 - s / T)
        c = self.collapse_t
        if t < c:
            # la pile tremble à chaque coup sur le bureau
            w = 0.0
            for h in self.hard_t:
                if 0 <= t - h < 0.35 and h > t0 + T:
                    w = 0.04 * (k + 1) * math.sin((t - h) * 40) * (1 - (t - h) / 0.35)
            lean = 0.012 * k * k
            return ex + 6.0 * k * k / 3, ey, lean + w
        # l'effondrement : les dossiers sautent et retombent derrière le bureau
        s = t - c - 0.04 * k
        x0_ = ex + 6.0 * k * k / 3
        if s < 0:
            return x0_, ey, 0.012 * k * k
        vx = (-150.0, 70.0, -60.0, 140.0)[k]
        vy = -(420.0 + 90.0 * k)
        y = ey + vy * s + 0.5 * G * s * s
        if y > FLOOR + 40:
            return None
        return x0_ + vx * s, y, (-1) ** k * (2.5 + k) * s

    def boss_hand(self, t):
        b = self.boss
        x, hip = b["x"](t), b["hip"](t)
        top = hip - 330.0
        ang = math.radians(b["larm"](t))
        ln = b["llen"](t)
        return x - 50 - math.sin(ang) * ln, top + 22 + math.cos(ang) * ln

    def draw_folders(self, dr, t, S, back=False):
        P = lambda v: v * S
        if back != (t >= self.collapse_t):
            return
        for k in range(4):
            fp = self.folder_pose(t, k)
            if fp is None:
                continue
            x, y, a = fp
            pts = [(x - FOLD_W / 2, y - FOLD_H / 2), (x + FOLD_W / 2, y - FOLD_H / 2), (x + FOLD_W / 2, y + FOLD_H / 2), (x - FOLD_W / 2, y + FOLD_H / 2)]
            pts = rot(pts, x, y, a)
            dr.polygon([(P(a_), P(b_)) for (a_, b_) in pts], fill=FOLD_COL[k])
            tab = rot([(x - 30, y - FOLD_H / 2 - 6), (x - 8, y - FOLD_H / 2 - 6), (x - 8, y - FOLD_H / 2), (x - 30, y - FOLD_H / 2)], x, y, a)
            dr.polygon([(P(a_), P(b_)) for (a_, b_) in tab], fill=dim(FOLD_COL[k], 0.8))

    def draw_bubble(self, dr, t, S, bx, by):
        """La bulle de l'entretien : « “BOUNCE.” », « means: », la traduction."""
        P = lambda v: v * S
        cur = None
        for i, (tb, text) in enumerate(self.bubbles):
            if t < tb:
                break
            # elle reste jusqu'à la réplique suivante (ou la bulle suivante)
            nxt = sorted((st, en) for (st, tx, k, en, w) in self.plan_lines if st > tb)
            end = nxt[0][1] + 0.2 if nxt else 1e9
            if i + 1 < len(self.bubbles):
                end = min(end, self.bubbles[i + 1][0])
            if text in ("You're hired.",):
                end = 1e9
            if t < end:
                cur = (tb, text)
        if cur is None:
            return
        tb, text = cur
        age = t - tb
        k = min(1.0, age / 0.15)
        x0, x1, y0 = 30.0, 486.0, 448.0
        f2 = base.font(P(56))
        rows, c = [], ""
        for w in text.split():
            cand = (c + " " + w).strip()
            if base.text_w(f2, cand) <= P(x1 - x0 - 60) or not c:
                c = cand
            else:
                rows.append(c); c = w
        rows.append(c)
        row0 = y0 + 222
        y1 = row0 + (len(rows) - 1) * 66 + 50
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        sc = 0.6 + 0.4 * k
        qx0, qx1 = cx - (cx - x0) * sc, cx + (x1 - cx) * sc
        qy0, qy1 = cy - (cy - y0) * sc, cy + (y1 - cy) * sc
        tx, ty = bx, by - R - 8
        ax = min(max(bx, 150.0), 380.0)
        dr.polygon([(P(ax - 50), P(qy1 - 4)), (P(ax + 50), P(qy1 - 4)), (P(tx), P(max(ty, qy1 + 30)))], fill=(250, 250, 252))
        dr.rounded_rectangle([P(qx0), P(qy0), P(qx1), P(qy1)], radius=int(P(30)), fill=(250, 250, 252), outline=(20, 20, 26), width=max(1, int(P(5))))
        if k < 1.0:
            return
        f1 = base.font(P(76))
        dr.text((P(cx), P(y0 + 70)), "“BOUNCE.”", fill=PINK, anchor="mm", font=f1, stroke_width=max(1, int(P(3))), stroke_fill=(120, 0, 80))
        if age < 0.4:
            return
        dr.text((P(cx), P(y0 + 150)), "means:", fill=(110, 110, 130), anchor="mm", font=base.font(P(38)))
        for i, row in enumerate(rows):
            dr.text((P(cx), P(row0 + i * 66)), row, fill=(20, 20, 26), anchor="mm", font=f2)

    boss_sit = None


DEFAULTS = {
    "ball_r": R, "gravity": G,
    "counter_font_size": 72, "counter_y": 0.19, "hook_text_s": 2.4,
    "sub_y": 0.80, "watermark_y": 0.93, "end_hold_s": 0.3, "narr_tail_s": 0.3, "narr_gap_s": 0.3,
}


def report(sim):
    p = sim.p
    print("contacts durs :", [round(t, 2) for t in sim.hard_t])
    for (st, text, key, en, who) in p.lines:
        print(f"  {st:6.2f}-{en:6.2f} {who}: {text}")
    for (tb, text) in p.bubbles:
        print(f"  bulle {tb:6.2f} {text}")
    print("fin", round(sim.end_t, 2), "arc le plus haut", round(sim.worst))


if __name__ == "__main__":
    if "--plan" in sys.argv:
        cfg = base.load_config(sys.argv[1], DEFAULTS)
        report(Sim(cfg, None))
        sys.exit(0)
    sys.exit(base.run(sys.modules[__name__]))
