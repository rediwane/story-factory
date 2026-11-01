"""
Prototype « question » : combien de sauts faut-il à Bounce pour atteindre le Soleil si
chaque saut va deux fois plus haut que le précédent ? Le premier saut fait 2 m, le saut
n fait 2^n m.

Ce qui doit se lire sans effort :
- une échelle sur le bord gauche, de la Terre au bord de l'univers, le Soleil marqué en
  or, un point rose qui grimpe : on sait toujours où il en est et ce qui arrive ;
- la caméra recule pour garder le saut en cours dans l'image ; ce qui arrive descend du
  haut, grandit à côté de Bounce, puis rapetisse en dessous ;
- la Terre passe du sol à une courbe, à une boule, à un point ;
- la hauteur en gros chiffres en haut.

Les distances sont réelles (sources dans DEFAULTS["sources"]) ; le temps est compressé.

    python3 src/stories/doubling.py configs/<name>.json [--simulate]
"""
import math, sys, os, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim
from listkit import Chapter, FLOOR_Y, SCENE_TOP, GREEN, AMBER, glow, mix

R_BOUNCE = 68.0
SPAN = FLOOR_Y - SCENE_TOP - 140.0          # hauteur d'image pour le saut en cours
LY = 9.4607e15
R_EARTH = 6.371e6
BX = 330.0                                  # Bounce
OX = 730.0                                  # les jalons
GOLD = (255, 205, 90)
BG = (6, 6, 12)

# (altitude m, nom, distance affichée, dessin, rayon réel m, rayon d'affichage max px, saut, phrase)
# Le saut d'un jalon est le premier dont la hauteur 2^n m dépasse sa distance.
MARKS = [
    (330.0, "EIFFEL TOWER", "330 M", "tower", None, None, 9, "Nine. The Eiffel Tower."),
    (8849.0, "MOUNT EVEREST", "8,849 M", "everest", None, None, 14, "Fourteen. Higher than Everest."),
    (408e3, "SPACE STATION", "408 KM", "iss", 55.0, 150.0, 19, "Nineteen. Past the space station."),
    (384400e3, "THE MOON", "384,400 KM", "moon", 1.737e6, 170.0, 29, "Twenty nine. The Moon."),
    (149.6e9, "THE SUN", "149.6 MILLION KM", "sun", 6.96e8, 230.0, 38, None),
    (25.8e12, "VOYAGER 1", "25.8 BILLION KM", "voyager", 3.0, 120.0, None, None),
    (4.24 * LY, "NEAREST STAR", "4.24 LIGHT-YEARS", "star", 1.07e8, 110.0, 56, "Fifty six. The nearest star."),
    (1344 * LY, "ORION NEBULA", "1,344 LIGHT-YEARS", "nebula", None, 190.0, None, None),
    (26000 * LY, "CENTER OF OUR GALAXY", "26,000 LIGHT-YEARS", "milkyway", None, 240.0, 68, "Sixty eight. The middle of our galaxy."),
    (160000 * LY, "LARGE MAGELLANIC CLOUD", "160,000 LIGHT-YEARS", "cloud", None, 170.0, None, None),
    (2.5e6 * LY, "ANDROMEDA", "2.5 MILLION LIGHT-YEARS", "andromeda", None, 230.0, 75, "Seventy five. Another galaxy."),
    (46.5e9 * LY, "EDGE OF THE OBSERVABLE UNIVERSE", "46.5 BILLION LIGHT-YEARS", "edge", None, 0.0, 89, None),
]
SUN_LINES = ("Thirty eight bounces. That's it.", "Now, how many to leave the observable universe?")
EDGE_LINE = "Eighty nine. The edge of the observable universe."

# la durée vidéo des déplacements de chaque tranche de sauts ; à chaque jalon nommé, Bounce
# s'arrête en haut de son saut le temps que le narrateur le dise (le compteur ne ment jamais)
SEGMENTS = [(1, 9, 8.2), (10, 14, 3.0), (15, 19, 3.0), (20, 29, 4.4), (30, 38, 4.4),
            (39, 56, 5.0), (57, 68, 3.4), (69, 75, 2.4), (76, 89, 4.0)]
LAST = 89
LOG_TOP = 27.0                              # l'échelle : de 1 m à 10^27 m
AFTER = 0.6                                 # un saut après le bord de l'univers


def fmt(h):
    if h < 1000:
        return f"{h:,.0f} M"
    km = h / 1000.0
    if h < 0.5 * LY:
        if km < 1e6:
            return f"{km:,.0f} KM"
        if km < 1e9:
            return f"{km / 1e6:,.1f} MILLION KM"
        return f"{km / 1e9:,.1f} BILLION KM"
    ly = h / LY
    if ly < 1e3:
        return f"{ly:,.1f} LIGHT-YEARS"
    if ly < 1e6:
        return f"{ly:,.0f} LIGHT-YEARS"
    if ly < 1e9:
        return f"{ly / 1e6:,.1f} MILLION LIGHT-YEARS"
    return f"{ly / 1e9:,.1f} BILLION LIGHT-YEARS"


class Doubling(Chapter):
    title = None
    stamp = None
    stamp_y = 0.30
    mood = "lose"
    hold_s = 4.6

    def setup(self):
        self.R = R_BOUNCE
        self.n = 1
        self.bx, self.by = BX, FLOOR_Y - self.R
        self.on = "air"
        self.hit_t = -9.0
        self.said = set()
        self.sun_t = None
        self.prev_by = self.by
        rr = random.Random(7)
        self.stars = [(rr.uniform(110, self.W - 10), rr.uniform(SCENE_TOP + 10, FLOOR_Y - 10), rr.uniform(0.3, 1.0), rr.choice((2, 2, 3, 4)))
                      for _ in range(90)]
        self.web = [(rr.uniform(120, self.W), rr.uniform(-160, 0), rr.uniform(0.3, 1.0)) for _ in range(160)]
        self.mw = [(rr.uniform(0, 2 * math.pi), rr.uniform(0.05, 1.0), rr.random()) for _ in range(260)]
        self.neb = [(rr.uniform(-1, 1), rr.uniform(-1, 1), rr.uniform(0.3, 0.8), rr.choice(((220, 90, 140), (120, 110, 230), (240, 150, 110)))) for _ in range(14)]
        self.sched = self.schedule()
        self.line("Each bounce goes twice as high as the last.", "title", 0.0)
        self.line("Take a guess.", "ask", 0.5)

    def say_s(self, text):
        import voice as nv
        x = nv.say(text, self.cfg["narrator_voice"], self.cfg["narrator_length"])
        return (len(x) / nv.SR) if x is not None else 1.5

    def schedule(self):
        """[(n, t_debut, duree_deplacement, pause_au_sommet)]. Dans la première tranche, un
        petit saut est court et un grand est long (poids 2^(n/4)) : l'ouverture part vite."""
        hover = {}
        gap = self.cfg["narr_gap_s"]
        for m in MARKS:
            at, say = m[6], m[7]
            if at is None:
                continue
            if m[3] == "sun":
                hover[at] = self.say_s(SUN_LINES[0]) + gap + self.say_s(SUN_LINES[1]) + 0.9
            elif m[3] == "edge":
                hover[at] = self.say_s(EDGE_LINE) + 0.5
            else:
                hover[at] = self.say_s(say) + 0.5
        out, t = [], 0.0
        for i, (a, b, d) in enumerate(SEGMENTS):
            ns = list(range(a, b + 1))
            w = [2 ** (n / 4.0) for n in ns] if i == 0 else [1.0] * len(ns)
            for n, wi in zip(ns, w):
                dd = d * wi / sum(w)
                hv = hover.get(n, 0.0)
                out.append((n, t, dd, hv))
                t += dd + hv
        return out

    # --- le temps
    def state_at(self, t):
        """(n, u, pause) : le saut, sa phase (0 au sol, 0,5 au sommet, 1 au sol), et si Bounce
        est en pause au sommet."""
        for (n, t0, d, hv) in self.sched:
            if t < t0 + d + hv:
                x = t - t0
                if x < d / 2:
                    return n, x / d, False
                if x < d / 2 + hv:
                    return n, 0.5, True
                return n, (x - hv) / d, False
        n, t0, d, hv = self.sched[-1]
        k = (t - t0 - d - hv) / AFTER
        return LAST + 1 + int(k), k - int(k), False

    def hover_el(self, t):
        """Depuis combien de temps Bounce est en pause au sommet (0 sinon)."""
        for (n, t0, d, hv) in self.sched:
            if t < t0 + d + hv:
                x = t - t0 - d / 2
                return x if 0 <= x < hv else 0.0
        return 0.0

    @staticmethod
    def height(n):
        return 2.0 ** min(n, LAST + 20)

    def view(self, n, u):
        lo = math.log2(max(4.0, self.height(n - 1) * 1.25))
        hi = math.log2(max(4.0, self.height(n) * 1.25))
        k = min(1.0, u / 0.5)
        k = k * k * (3 - 2 * k)
        return 2.0 ** (lo + (hi - lo) * k)

    def alt(self, n, u, hover=False):
        a = self.height(n) * 4 * u * (1 - u)
        if hover:
            a *= 1.0 - 0.05 * (1 - math.cos(self.t * 6.0))      # il flotte au sommet
        return a

    def step(self, dt):
        self.t += dt
        evs = []
        n, u, hv = self.state_at(self.t)
        if n != self.n:
            self.n = n
            self.hit_t = self.t
            evs.append(("hit", "floor"))
        if hv and n not in self.said:
            self.said.add(n)
            for m in MARKS:
                at, say = m[6], m[7]
                if at != n:
                    continue
                if m[3] == "sun":
                    self.sun_t = self.t
                    self.line(SUN_LINES[0], "m38", self.t)
                    self.line(SUN_LINES[1], "q2", self.t + 0.1)
                elif m[3] == "edge":
                    self.finish("EDGE")
                    self.line(EDGE_LINE, "end", self.t)
                    self.line("Still bouncing.", "still", self.t + 0.1)
                elif say:
                    self.line(say, f"m{at}", self.t)
        self.prev_by = self.by
        V = self.view(n, u) * (1.0 + 0.07 * self.hover_el(self.t))
        self.by = FLOOR_Y - self.R - self.alt(n, u, hv) / V * SPAN
        return evs

    def snapshot(self):
        n, u, hv = self.state_at(self.t)
        s = self.base_snap()
        s.update({"n": n, "u": u, "hover": hv, "V": self.view(n, u) * (1.0 + 0.07 * self.hover_el(self.t)), "a": self.alt(n, u, hv), "sun_t": self.sun_t,
                  "vy": (self.by - self.prev_by) * 30.0})
        return s

    def counter(self, s):
        return None

    def focus(self, s):
        return (300.0, 520.0, 900.0, 1000.0)

    # --- dessin
    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        V = s["V"]
        px = SPAN / V                                       # pixels par mètre
        space = max(0.0, min(1.0, (math.log10(V) - 4.3) / 1.6))
        sky = mix((22, 30, 58), BG, space)
        dr.rectangle([0, P(SCENE_TOP), P(W), P(FLOOR_Y)], fill=sky)
        span_y = FLOOR_Y - SCENE_TOP
        for i, (x, y, b, r) in enumerate(self.stars):
            if space > 0:
                tw = 0.65 + 0.35 * math.sin(t * 3.0 + i * 1.7)          # elles scintillent
                yy = SCENE_TOP + (y - SCENE_TOP + t * (30 + 25 * r)) % span_y   # et défilent : le voyage
                circle(dr, P(x), P(yy), P(r), mix(sky, (210, 214, 236), space * b * tw))
        self.earth(dr, P, px, space)
        for m in MARKS:
            self.mark(dr, P, m, px, V, t, s)
        self.ladder(dr, P, s)
        self.streaks(dr, P, s)
        sun_on = s["sun_t"] is not None and s["n"] == 38 and s["hover"]
        if sun_on:
            base.HERO["expr"] = "win"
        elif s["end"] is None:
            base.HERO["expr"] = "calm"
        self.bounce(dr, P, s)
        if sun_on:
            k = min(1.0, (t - s["sun_t"]) / 0.25)
            fb = base.font(int((230 - 70 * (1 - k)) * S))
            sy = FLOOR_Y - 149.6e9 * SPAN / s["V"]
            dr.text((P(OX), P(sy)), "38", fill=(255, 255, 255), anchor="mm", font=fb, stroke_width=int(10 * S), stroke_fill=(40, 20, 10))
        if s["end"] is not None:
            k = min(1.0, (t - s["end"]) / 0.25)
            fb = base.font(int((230 - 70 * (1 - k)) * S))
            fl = base.font(int(56 * S))
            dr.text((P(OX - 20), P(1010)), "89", fill=GOLD, anchor="mm", font=fb, stroke_width=int(10 * S), stroke_fill=(40, 20, 10))
            dr.text((P(OX - 20), P(1145)), "BOUNCES", fill=GOLD, anchor="mm", font=fl, stroke_width=int(6 * S), stroke_fill=(40, 20, 10))
        dr.rectangle([0, 0, P(W), P(SCENE_TOP) - 1], fill=tuple(self.cfg["bg_color"]))      # rien sur le bandeau du haut
        self.hud(dr, P, s, t, S)

    def hud(self, dr, P, s, t, S):
        if t < self.cfg["hook_text_s"] or s["end"] is not None:
            return
        n = s["n"]
        f1 = base.font(int(52 * S))
        size = 74
        f2 = base.font(int(size * S))
        while base.text_w(f2, fmt(self.height(n))) > self.W * S * 0.9 and size > 36:
            size -= 4
            f2 = base.font(int(size * S))
        dr.text((P(self.W / 2), P(255)), f"BOUNCE {n}", fill=(225, 225, 236), anchor="mm", font=f1)
        dr.text((P(self.W / 2), P(345)), fmt(self.height(n)), fill=GOLD, anchor="mm", font=f2)

    def ladder(self, dr, P, s):
        """L'échelle : de 1 m (en bas) à 10^27 m (en haut), en logarithme."""
        x, y0, y1 = 58.0, FLOOR_Y - 30, SCENE_TOP + 60
        Y = lambda h: y0 - max(0.0, min(1.0, math.log10(max(h, 1.0)) / LOG_TOP)) * (y0 - y1)
        dr.rectangle([P(x - 5), P(y1), P(x + 5), P(y0)], fill=(60, 60, 78))
        f = base.font(int(30 * P(1)))
        dr.text((P(x - 18), P(y0 + 32)), "EARTH", fill=(150, 180, 230), anchor="lm", font=f)
        dr.text((P(x - 18), P(y1 - 30)), "EDGE", fill=(240, 200, 110), anchor="lm", font=f)
        for (h, name, dist, kind, rr, rmax, at, say) in MARKS:
            if at is None:
                continue
            y = Y(h)
            sun = kind == "sun"
            done = s["n"] > at or (s["n"] == at and s["u"] >= 0.5)
            col = GOLD if sun else ((150, 220, 160) if done else (130, 130, 150))
            w = 22 if sun else 13
            dr.rectangle([P(x - w), P(y - 3), P(x + w), P(y + 3)], fill=col)
            if sun:
                dr.text((P(x + 28), P(y)), "SUN", fill=GOLD, anchor="lm", font=f)
        # le plus haut atteint, et où il est maintenant
        top = self.height(s["n"]) if s["u"] >= 0.5 else self.height(s["n"] - 1)
        dr.rectangle([P(x - 5), P(Y(top)), P(x + 5), P(y0)], fill=(230, 60, 170))
        circle(dr, P(x), P(Y(max(1.0, s["a"]))), P(17), (255, 70, 200))

    def streaks(self, dr, P, s):
        v = s["vy"]
        if abs(v) < 900:
            return
        L = min(260.0, abs(v) * 0.08)
        d = 1 if v < 0 else -1                                # traînée derrière lui
        for k, dx in enumerate((-40, 0, 40)):
            y0 = s["by"] + d * (self.R + 10 + 14 * (k % 2))
            y1 = min(FLOOR_Y - 6, y0 + d * L) if d > 0 else y0 + d * L
            if d > 0 and y0 >= FLOOR_Y - 20:
                continue                                      # jamais dans le sol
            dr.line([(P(BX + dx), P(y0)), (P(BX + dx), P(y1))], fill=(120, 90, 140), width=max(1, int(P(5))))

    def earth(self, dr, P, px, space):
        """Le sol, puis la courbure, puis la boule, puis le point : la Terre à l'échelle."""
        W, H = self.W, self.H
        r = R_EARTH * px
        if r > 30000:
            dr.rectangle([0, P(FLOOR_Y), P(W), P(H)], fill=(26, 46, 34))
            dr.rectangle([0, P(FLOOR_Y), P(W), P(FLOOR_Y + 8)], fill=(56, 92, 64))
            self.ground_life(dr, P, px)
            return
        cx, cy = BX, FLOOR_Y + r
        globe = r < 900
        if globe:
            glow(dr, P, cx, cy, r * 1.12 + 10, (90, 150, 255), BG, 0.35)
        else:
            circle(dr, P(cx), P(cy), P(r + 30), (40, 70, 130))
        circle(dr, P(cx), P(cy), P(r), (36, 76, 150))
        for (ax, ay, ar) in ((-0.38, -0.55, 0.20), (-0.25, -0.42, 0.16), (-0.42, -0.35, 0.12), (0.22, -0.72, 0.15), (0.32, -0.6, 0.12),
                             (0.45, -0.22, 0.17), (0.36, -0.05, 0.13), (-0.12, 0.12, 0.2), (-0.02, 0.3, 0.14)):
            if globe and r * ar > 1.5:
                circle(dr, P(cx + ax * r), P(cy + ay * r), P(r * ar), (52, 110, 70))
        if globe and r > 40:
            dr.ellipse([P(cx - r * 0.22), P(cy - r * 0.99), P(cx + r * 0.22), P(cy - r * 0.86)], fill=(225, 232, 240))     # la calotte
        if r > 22:
            f = base.font(int(30 * P(1)))
            if r < 700:
                dr.text((P(cx + r + 26), P(min(cy, FLOOR_Y + 120))), "EARTH", fill=(170, 200, 240), anchor="lm", font=f)

    def ground_life(self, dr, P, px):
        """Ce qu'il y a au sol, à l'échelle : une clôture, un arbre, une maison, une ville."""
        def shape(h, fn):
            hp = h * px
            if 8 < hp < SPAN * 1.15:
                fn(hp)
        def fence(hp):
            dr.rectangle([P(OX - 300), P(FLOOR_Y - hp * 0.75), P(OX + 300), P(FLOOR_Y - hp * 0.62)], fill=(110, 92, 70))
            step = max(18.0, hp * 0.6)
            x = OX - 300
            while x <= OX + 300:
                dr.rectangle([P(x), P(FLOOR_Y - hp), P(x + max(4, hp * 0.08)), P(FLOOR_Y)], fill=(126, 104, 78))
                x += step

        def house(hp):
            w = hp * 0.9
            x = OX + 40
            dr.rectangle([P(x - w / 2), P(FLOOR_Y - hp * 0.62), P(x + w / 2), P(FLOOR_Y)], fill=(74, 66, 90))
            dr.polygon([(P(x - w / 2 - hp * 0.06), P(FLOOR_Y - hp * 0.62)), (P(x + w / 2 + hp * 0.06), P(FLOOR_Y - hp * 0.62)), (P(x), P(FLOOR_Y - hp))], fill=(120, 72, 62))
            dr.rectangle([P(x - w * 0.3), P(FLOOR_Y - hp * 0.45), P(x - w * 0.1), P(FLOOR_Y - hp * 0.28)], fill=(240, 200, 110))
            dr.rectangle([P(x + w * 0.12), P(FLOOR_Y - hp * 0.3), P(x + w * 0.3), P(FLOOR_Y)], fill=(50, 40, 50))
        shape(6.0, house)

        def tree(hp):
            x = OX - 200
            dr.rectangle([P(x - hp * 0.04), P(FLOOR_Y - hp * 0.45), P(x + hp * 0.04), P(FLOOR_Y)], fill=(80, 60, 44))
            circle(dr, P(x), P(FLOOR_Y - hp * 0.68), P(hp * 0.3), (40, 90, 56))

        def city(hp):
            rr = random.Random(3)
            x = -100.0
            while x < self.W + 100:
                w = rr.uniform(0.05, 0.12) * hp
                h = rr.uniform(0.15, 0.55) * hp
                dr.rectangle([P(x), P(FLOOR_Y - h), P(x + w), P(FLOOR_Y)], fill=(34, 36, 56))
                for wy in range(3):
                    if h > 60:
                        dr.rectangle([P(x + w * 0.3), P(FLOOR_Y - h + 14 + wy * h / 4), P(x + w * 0.45), P(FLOOR_Y - h + 22 + wy * h / 4)], fill=(150, 130, 80))
                x += w + rr.uniform(0.0, 0.05) * hp
        shape(330.0, city)

    def mark(self, dr, P, m, px, V, t, s):
        h, name, dist, kind, rreal, rmax, at, say = m
        y = FLOOR_Y - h * px
        if y < SCENE_TOP - 400:
            return
        f1 = base.font(int(38 * P(1)))
        f2 = base.font(int(30 * P(1)))
        label = None
        if kind == "tower":
            hp = h * px
            if hp < 10 or hp > SPAN * 1.25:
                return
            self.tower(dr, P, OX, hp)
            label = FLOOR_Y - hp - 70 if hp > 150 else None
        elif kind == "everest":
            hp = h * px
            if hp < 10 or hp > SPAN * 1.25:
                return
            self.mountains(dr, P, hp, t)
            label = FLOOR_Y - hp - 70 if hp > 150 else None
        elif kind == "edge":
            if y > FLOOR_Y - 40:
                return
            for (x, dy, b) in self.web:
                circle(dr, P(x), P(y + dy), P(3), mix(BG, (240, 170, 80), b))
            for x in range(120, int(self.W), 36):
                dr.rectangle([P(x), P(y - 3), P(x + 20), P(y + 3)], fill=GOLD)
            label = y + 50 if s["end"] is None else None          # le 89 et la voix le disent
        else:
            frac = h / V                                    # où il est dans l'image (1 = en haut)
            if frac > 1.15 or frac < 0.012:
                return
            r = max((rreal or 0) * px, rmax * min(1.0, frac / 0.8) ** 0.75)
            a = min(1.0, (frac - 0.012) / 0.04)
            getattr(self, "d_" + kind)(dr, P, OX, y, r, a, t)
            sun_moment = kind == "sun" and s["sun_t"] is not None and 0 <= t - s["sun_t"] < 3.4
            if r > 36 and not sun_moment:
                label = y + r + 34
        if label is not None:
            rows = [""]
            for wd in name.split():
                if rows[-1] and len(rows[-1]) + 1 + len(wd) > 14:
                    rows.append(wd)
                else:
                    rows[-1] = (rows[-1] + " " + wd).strip()
            lx = OX - 40
            for k, row in enumerate(rows):
                dr.text((P(lx), P(label + k * 42)), row, fill=(235, 235, 245), anchor="mm", font=f1, stroke_width=int(P(3)), stroke_fill=BG)
            dr.text((P(lx), P(label + len(rows) * 42)), dist, fill=GOLD, anchor="mm", font=f2, stroke_width=int(P(3)), stroke_fill=BG)

    # --- les jalons
    def tower(self, dr, P, x, hp):
        col = (150, 118, 84)
        w = hp * 0.38
        for (a, b) in ((0.0, 0.18), (0.18, 0.42), (0.42, 0.92)):
            wa = w * (1 - a) ** 1.6 / 2
            wb = w * (1 - b) ** 1.6 / 2
            ya, yb = FLOOR_Y - a * hp, FLOOR_Y - b * hp
            dr.polygon([(P(x - wa), P(ya)), (P(x + wa), P(ya)), (P(x + wb), P(yb)), (P(x - wb), P(yb))], fill=col)
            dr.rectangle([P(x - wb - 4), P(yb - max(2, hp * 0.012)), P(x + wb + 4), P(yb)], fill=dim(col, 0.75))
        dr.rectangle([P(x - 2), P(FLOOR_Y - hp), P(x + 2), P(FLOOR_Y - hp * 0.92)], fill=col)
        arch = w * 0.28
        dr.ellipse([P(x - arch), P(FLOOR_Y - hp * 0.12), P(x + arch), P(FLOOR_Y + hp * 0.06)], fill=(26, 46, 34))

    def mountains(self, dr, P, hp, t=0.0):
        for (dx, sc, col) in ((-520, 0.62, (60, 66, 88)), (430, 0.7, (64, 70, 92)), (0, 1.0, (88, 94, 118))):
            hh = hp * sc
            w = hh * 1.6
            x = OX + dx * hp / 900
            dr.polygon([(P(x - w / 2), P(FLOOR_Y)), (P(x + w / 2), P(FLOOR_Y)), (P(x + w * 0.06), P(FLOOR_Y - hh)), (P(x - w * 0.04), P(FLOOR_Y - hh * 0.97))], fill=col)
            sn = 0.22
            dr.polygon([(P(x - w / 2 * sn), P(FLOOR_Y - hh * (1 - sn))), (P(x + w / 2 * sn), P(FLOOR_Y - hh * (1 - sn) + hh * 0.03)), (P(x + w * 0.06), P(FLOOR_Y - hh)), (P(x - w * 0.04), P(FLOOR_Y - hh * 0.97))], fill=(228, 230, 240))
        for k in range(4):
            cy = FLOOR_Y - hp * (0.35 + 0.1 * k)
            cx = (k * 337 + 120 + t * 70) % (self.W + 300) - 150      # les nuages passent
            dr.ellipse([P(cx - hp * 0.25), P(cy - hp * 0.03), P(cx + hp * 0.25), P(cy + hp * 0.03)], fill=(96, 102, 128))

    def d_plane(self, dr, P, x, y, r, a, t):
        c = lambda col: mix(BG, col, a)
        dr.line([(P(x - r * 4), P(y + 2)), (P(x - r), P(y))], fill=c((70, 74, 96)), width=max(1, int(P(6))))
        dr.polygon([(P(x - r), P(y - r * 0.1)), (P(x + r), P(y - r * 0.1)), (P(x + r * 1.15), P(y)), (P(x + r), P(y + r * 0.1)), (P(x - r), P(y + r * 0.1))], fill=c((215, 218, 228)))
        dr.polygon([(P(x - r * 0.1), P(y)), (P(x + r * 0.25), P(y)), (P(x - r * 0.25), P(y + r * 0.55))], fill=c((185, 188, 200)))
        dr.polygon([(P(x - r), P(y - r * 0.1)), (P(x - r * 0.75), P(y - r * 0.1)), (P(x - r * 0.95), P(y - r * 0.45))], fill=c((185, 188, 200)))

    def d_iss(self, dr, P, x, y, r, a, t):
        c = lambda col: mix(BG, col, a)
        dr.rectangle([P(x - r), P(y - r * 0.05), P(x + r), P(y + r * 0.05)], fill=c((190, 190, 200)))
        for dx in (-0.85, -0.55, 0.55, 0.85):
            dr.rectangle([P(x + dx * r - r * 0.12), P(y - r * 0.5), P(x + dx * r + r * 0.12), P(y + r * 0.5)], fill=c((60, 96, 180)))
        dr.rectangle([P(x - r * 0.2), P(y - r * 0.14), P(x + r * 0.2), P(y + r * 0.14)], fill=c((215, 215, 225)))

    def d_moon(self, dr, P, x, y, r, a, t):
        c = lambda col: mix(BG, col, a)
        glow(dr, P, x, y, r * 1.25, (200, 200, 215), BG, 0.18 * a, rings=3)
        circle(dr, P(x), P(y), P(r), c((210, 210, 216)))
        for (dx, dy, cr) in ((-0.35, -0.25, 0.22), (0.3, 0.2, 0.15), (0.1, -0.5, 0.1), (-0.2, 0.45, 0.12), (0.45, -0.25, 0.09)):
            circle(dr, P(x + dx * r), P(y + dy * r), P(r * cr), c((172, 172, 182)))

    def d_voyager(self, dr, P, x, y, r, a, t):
        c = lambda col: mix(BG, col, a)
        circle(dr, P(x), P(y - r * 0.1), P(r * 0.42), c((215, 215, 222)))
        dr.rectangle([P(x - r * 0.18), P(y - r * 0.05), P(x + r * 0.18), P(y + r * 0.25)], fill=c((180, 160, 110)))
        dr.line([(P(x), P(y + r * 0.1)), (P(x - r), P(y + r * 0.5))], fill=c((190, 190, 200)), width=max(1, int(P(5))))
        dr.line([(P(x), P(y + r * 0.1)), (P(x + r * 0.9), P(y - r * 0.6))], fill=c((190, 190, 200)), width=max(1, int(P(4))))

    def d_nebula(self, dr, P, x, y, r, a, t):
        for (dx, dy, k, col) in self.neb:
            glow(dr, P, x + dx * r * 0.6, y + dy * r * 0.45, r * k, col, BG, 0.22 * a, rings=3)
        circle(dr, P(x), P(y), P(max(2, r * 0.05)), mix(BG, (255, 255, 255), a))

    def d_cloud(self, dr, P, x, y, r, a, t):
        for k in range(5, 0, -1):
            dr.ellipse([P(x - r * k / 5), P(y - r * k / 9), P(x + r * k / 5 * 0.8), P(y + r * k / 7)], fill=mix(BG, (170, 180, 230), a * (0.15 + 0.1 * (5 - k))))

    def d_sun(self, dr, P, x, y, r, a, t):
        glow(dr, P, x, y, r * 1.9, (255, 170, 60), BG, 0.45 * a, rings=7)
        for k in range(12):
            ang = k * math.pi / 6 + t * 0.4
            dr.line([(P(x + math.cos(ang) * r * 1.05), P(y + math.sin(ang) * r * 1.05)), (P(x + math.cos(ang) * r * 1.45), P(y + math.sin(ang) * r * 1.45))], fill=mix(BG, (255, 190, 80), a * 0.7), width=max(1, int(P(r * 0.06))))
        circle(dr, P(x), P(y), P(r), mix(BG, (255, 200, 80), a))
        circle(dr, P(x - r * 0.15), P(y - r * 0.15), P(r * 0.7), mix(BG, (255, 225, 130), a))

    def d_venus(self, dr, P, x, y, r, a, t):
        glow(dr, P, x, y, r * 1.4, (240, 220, 160), BG, 0.25 * a, rings=4)
        circle(dr, P(x), P(y), P(r), mix(BG, (230, 205, 150), a))
        dr.ellipse([P(x - r * 0.8), P(y - r * 0.2), P(x + r * 0.8), P(y + r * 0.05)], fill=mix(BG, (210, 180, 125), a))

    def d_neptune(self, dr, P, x, y, r, a, t):
        circle(dr, P(x), P(y), P(r), mix(BG, (70, 110, 220), a))
        dr.ellipse([P(x - r * 0.9), P(y - r * 0.15), P(x + r * 0.9), P(y + r * 0.05)], fill=mix(BG, (110, 150, 240), a))

    def d_star(self, dr, P, x, y, r, a, t):
        glow(dr, P, x, y, r * 2.2, (255, 110, 80), BG, 0.45 * a, rings=6)
        dr.line([(P(x - r * 2.4), P(y)), (P(x + r * 2.4), P(y))], fill=mix(BG, (255, 160, 130), a * 0.6), width=max(1, int(P(4))))
        dr.line([(P(x), P(y - r * 2.4)), (P(x), P(y + r * 2.4))], fill=mix(BG, (255, 160, 130), a * 0.6), width=max(1, int(P(4))))
        circle(dr, P(x), P(y), P(r), mix(BG, (255, 140, 100), a))

    def d_milkyway(self, dr, P, x, y, r, a, t):
        for (th, rho, b) in self.mw:
            arm = int(b * 2)
            ang = th + rho * 4.2 + arm * math.pi
            px_, py_ = x + math.cos(ang) * rho * r, y + math.sin(ang) * rho * r * 0.45
            circle(dr, P(px_), P(py_), P(max(1.5, r * 0.018)), mix(BG, (200, 190, 240), a * (0.4 + 0.6 * (1 - rho))))
        glow(dr, P, x, y, r * 0.35, (255, 230, 180), BG, 0.6 * a, rings=5)

    def d_andromeda(self, dr, P, x, y, r, a, t):
        for k in range(6, 0, -1):
            dr.ellipse([P(x - r * k / 6), P(y - r * k / 6 * 0.32), P(x + r * k / 6), P(y + r * k / 6 * 0.32)], fill=mix(BG, (190, 180, 235), a * (0.18 + 0.12 * (6 - k))))
        glow(dr, P, x, y, r * 0.25, (255, 240, 200), BG, 0.7 * a, rings=4)


DEFAULTS = {
    "ball_r": R_BOUNCE, "gravity": 3000.0,
    "chapter_max_s": 75.0,
    "hook_text_s": 2.6,
    "hook_narrator": True,
    "sub_y": 0.84, "watermark_y": 0.93, "end_hold_s": 2.2, "narr_tail_s": 0.3, "narr_gap_s": 0.25,
    "sources": {
        "Eiffel Tower 330 m": "https://www.toureiffel.paris/en/the-monument/key-figures",
        "Everest 8,849 m": "https://www.nationalgeographic.com/science/article/mount-everest-is-taller-than-we-thought",
        "ISS ~408 km": "https://www.nasa.gov/international-space-station/space-station-facts-and-figures/",
        "Moon 384,400 km": "https://science.nasa.gov/moon/facts/",
        "Sun 149.6 million km (1 AU)": "https://www.iau.org/static/resolutions/IAU2012_English.pdf",
        "Neptune ~4.5 billion km": "https://science.nasa.gov/neptune/facts/",
        "Proxima Centauri 4.24 ly": "https://science.nasa.gov/exoplanet-catalog/proxima-centauri-b/",
        "Galactic center ~26,000 ly": "https://www.eso.org/public/news/eso1904/",
        "Andromeda ~2.5 million ly": "https://science.nasa.gov/messier-objects/m31/",
        "Observable universe radius ~46.5 billion ly": "https://en.wikipedia.org/wiki/Observable_universe",
    },
}

CHAPTERS = [(Doubling, {})]


class Sim(StorySim):
    def __init__(self, cfg, rng):
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
