"""
Une histoire en chapitres : une suite de petites simulations jouées l'une après l'autre
dans la même vidéo, avec le narrateur par-dessus. C'est le format « liste » : un titre
qui dit tout, des situations courtes avec chacune sa chute, la dernière qui retourne
la série.

Chaque chapitre est une classe de simulation ordinaire (step, snapshot, draw, done,
payoff, outcome), plus :
- `title` : le titre affiché en haut pendant le chapitre ;
- `lines` : [(t_local, texte, clé)] les répliques du narrateur qu'il déclenche ;
- `replies` : [(clé, délai)] les moments où Bounce répond ;
- `mood` : "win" / "lose" / None, le visage de Bounce une fois le chapitre joué ;
- `hold_s` : combien de temps la dernière image du chapitre tient.

`StorySim` les enchaîne et se présente à `base.run` comme un seul thème.
"""
import math
import numpy as np
import base


class StorySim:
    """cfg["_chapters"] : liste de (classe, dict de réglages du chapitre)."""

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.W, self.H = cfg["width"], cfg["height"]
        self.scene_top = cfg.get("scene_top", 0.22)
        self.t = 0.0
        self.i = 0
        self.t0 = 0.0                       # début du chapitre courant
        self.sims = []
        for k, (cls, over) in enumerate(cfg["_chapters"]):
            c = dict(cfg); c.update(over)
            seed = int(cfg["seed"]) * 100 + k
            self.sims.append(cls(c, np.random.default_rng(seed)))
        self.lines, self.replies = [], []
        self.done = False
        self.payoff = False
        self.outcome = None
        self.end_t = None
        # l'horloge du narrateur : une phrase ne commence qu'après la précédente ; le
        # chapitre ne se ferme pas avant que ses phrases soient dites
        import audio_kit as ak
        hook = ak.hook_voice(cfg["hook_text"]) if (cfg["hook_voice"] and cfg["hook_text"]) else None
        self.narr_free = (0.15 + len(hook) / ak.SR + 0.3) if hook is not None else 0.3
        self._open(0)

    def narr_dur(self, text):
        import voice as nv
        x = nv.say(text, self.cfg["narrator_voice"], self.cfg["narrator_length"])
        return (len(x) / nv.SR) if x is not None else 0.8

    def _place(self, trig, text):
        start = max(trig, self.narr_free + self.cfg["narr_gap_s"])
        self.narr_free = start + self.narr_dur(text)
        return start

    def _open(self, i):
        self.i = i
        self.t0 = self.t
        s = self.sims[i]
        for (tl, text, key) in getattr(s, "lines", []):
            self._place(self.t0 + tl, text)
            self.lines.append((self.t0 + tl, text, f"{i}:{key}"))
        for (key, delay) in getattr(s, "replies", []):
            self.replies.append((f"{i}:{key}", delay))
        s._lines_seen = len(getattr(s, "lines", []))
        s._replies_seen = len(getattr(s, "replies", []))
        s._end_local = None

    def step(self, dt):
        self.t += dt
        s = self.sims[self.i]
        evs = []
        if not getattr(s, "_finished", False):
            evs = s.step(dt)
            # répliques ajoutées pendant le chapitre
            L = getattr(s, "lines", [])
            for (tl, text, key) in L[s._lines_seen:]:
                self._place(self.t0 + tl, text)
                self.lines.append((self.t0 + tl, text, f"{self.i}:{key}"))
            s._lines_seen = len(L)
            Rp = getattr(s, "replies", [])
            for (key, delay) in Rp[s._replies_seen:]:
                self.replies.append((f"{self.i}:{key}", delay))
            s._replies_seen = len(Rp)
            if s.payoff and s._end_local is None:
                s._end_local = self.t - self.t0
            tl = self.t - self.t0
            over = (s._end_local is not None and tl - s._end_local >= getattr(s, "hold_s", 1.4)) or tl >= s.cfg.get("chapter_max_s", 14.0)
            if over and self.t < self.narr_free + 0.25 and tl < s.cfg.get("chapter_max_s", 14.0) + 4.0:
                over = False          # le narrateur finit sa phrase avant la coupe
            if over:
                s._finished = True
                if self.i + 1 < len(self.sims):
                    self._open(self.i + 1)
                else:
                    self.payoff = True
                    self.outcome = getattr(s, "outcome", "END")
                    self.end_t = self.t
                    evs = list(evs) + [("payoff", self.outcome)]
                    self.done = True
        return evs

    def snapshot(self):
        s = self.sims[self.i]
        return {"t": self.t, "i": self.i, "tl": self.t - self.t0, "snap": s.snapshot(),
                "end_local": s._end_local}

    def counter(self, snap):
        s = self.sims[snap["i"]]
        return s.counter(snap["snap"]) if hasattr(s, "counter") else None

    def hero_mood(self):
        return getattr(self.sims[-1], "mood", None)

    def draw(self, dr, snap, t, S):
        s = self.sims[snap["i"]]
        if snap["end_local"] is not None and getattr(s, "mood", None):
            base.HERO["expr"] = s.mood
        s.draw(dr, snap["snap"], snap["tl"], S)
        stamp = getattr(s, "stamp", None)
        if snap["end_local"] is not None and stamp:
            text, col = stamp
            age = snap["tl"] - snap["end_local"]
            k = min(1.0, age / 0.25)
            size = int((150 - 40 * (1 - k)) * S)
            f = base.font(size)
            x, y = self.W * S / 2, self.H * S * 0.52
            dr.text((x, y), text, fill=col, anchor="mm", font=f, stroke_width=int(6 * S), stroke_fill=(10, 8, 12))


class Hopper:
    """Les sauts de Bounce sur place, communs aux chapitres : h croît ou décroît au
    hasard, chaque retombée appelle self.on_land(k) avec k = hauteur relative."""

    def hop_init(self, x, floor_y, start_h=170.0, gain=(0.88, 1.18), min_h=90.0, max_h=360.0, wobble=60.0, xmin=None, xmax=None, h_ref=200.0, start_air=True):
        self.bx, self.floor_y, self.h = x, floor_y, start_h
        self.gain, self.min_h, self.max_h, self.wobble, self.h_ref = gain, min_h, max_h, wobble, h_ref
        self.xmin = x - 200 if xmin is None else xmin
        self.xmax = x + 200 if xmax is None else xmax
        self.by = floor_y - self.R - (start_h if start_air else 0.0)
        self.vx = self.vy = 0.0
        self.on = "air" if start_air else "ground"
        self.hits = 0
        self.last_hit = -9.0
        self.hit_t = -9.0

    def hop_go(self):
        s = math.sqrt(2 * self.g * self.h)
        T = 2 * s / self.g
        tx = min(self.xmax, max(self.xmin, self.bx + self.rng.uniform(-1, 1) * self.wobble))
        self.vx = (tx - self.bx) / T
        self.vy = -s
        self.on = "air"

    def hop_step(self, dt, evs):
        if self.on == "ground":
            self.hop_go()
            return
        if self.on != "air":
            return
        self.vy += self.g * dt
        self.bx += self.vx * dt
        self.by += self.vy * dt
        ly = self.floor_y - self.R
        if self.vy > 0 and self.by >= ly:
            self.by = ly
            k = self.h / self.h_ref
            if self.t - self.last_hit >= 0.15:
                self.last_hit = self.t
                self.hits += 1
                evs.append(("hit", "floor"))
            self.hit_t = self.t
            self.on_land(k, evs)
            self.h = min(self.max_h, max(self.min_h, self.h * self.rng.uniform(*self.gain)))
            if self.on == "air":
                self.hop_go()
