"""
Prototype « question » : combien de sauts faut-il à Bounce pour atteindre le Soleil si
chaque saut va deux fois plus haut que le précédent ? Le premier saut fait 2 m, le saut
n fait 2^n m. La caméra recule pour garder le saut en cours dans l'image : tout ce qui a
été dépassé s'écrase vers le sol, ce qui arrive descend du haut de l'image.

Les distances sont réelles (sources dans DEFAULTS["sources"]) ; le temps est compressé.

    python3 src/stories/doubling.py configs/<name>.json [--simulate]
"""
import math, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim
from listkit import Chapter, FLOOR_Y, SCENE_TOP, GREEN, AMBER, glow, mix

R_BOUNCE = 68.0
SPAN = FLOOR_Y - SCENE_TOP - 150.0          # hauteur d'image pour le saut en cours
LY = 9.4607e15

# (hauteur en m, nom, dessin, saut où il est atteint, phrase du narrateur)
MARKS = [
    (8.0, "HOUSE", "house", None, None),
    (330.0, "EIFFEL TOWER", "tower", 9, "Nine. The Eiffel Tower."),
    (8849.0, "EVEREST", "mountain", 14, "Fourteen. Higher than Everest."),
    (408e3, "SPACE STATION", "iss", 19, "Nineteen. Past the space station."),
    (384400e3, "THE MOON", "moon", 29, "Twenty nine. The Moon."),
    (149.6e9, "THE SUN", "sun", 38, "Thirty eight bounces. The Sun."),
    (4.5e12, "NEPTUNE", "neptune", None, None),
    (4.24 * LY, "NEAREST STAR", "star", 56, "Fifty six. The nearest star."),
    (26000 * LY, "CENTER OF THE MILKY WAY", "galaxy_mw", 68, "Sixty eight. The middle of our galaxy."),
    (2.5e6 * LY, "ANDROMEDA", "galaxy", 75, "Seventy five. Another galaxy."),
    (46.5e9 * LY, "EDGE OF THE OBSERVABLE UNIVERSE", "edge", 89, None),
]

# la durée vidéo de chaque tranche de sauts : lent pour poser la règle, puis de plus en plus vite
SEGMENTS = [(1, 9, 10.3), (10, 14, 5.0), (15, 19, 4.5), (20, 29, 7.0), (30, 38, 6.0),
            (39, 56, 8.0), (57, 68, 5.0), (69, 75, 3.5), (76, 89, 7.0)]
LAST = 89


def schedule():
    """[(n, t_debut, duree)] pour chaque saut."""
    out, t = [], 0.0
    for (a, b, d) in SEGMENTS:
        k = b - a + 1
        for n in range(a, b + 1):
            out.append((n, t, d / k))
            t += d / k
    return out


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
        return f"{ly / 1e3:,.0f} THOUSAND LIGHT-YEARS"
    if ly < 1e9:
        return f"{ly / 1e6:,.1f} MILLION LIGHT-YEARS"
    return f"{ly / 1e9:,.1f} BILLION LIGHT-YEARS"


class Doubling(Chapter):
    title = None
    stamp = ("89 BOUNCES", AMBER)
    stamp_y = 0.30
    mood = "lose"
    hold_s = 5.5
    exit_ok = False
    BX = 250.0

    def setup(self):
        self.sched = schedule()
        self.R = R_BOUNCE
        self.n = 1
        self.bx, self.by = self.BX, FLOOR_Y - self.R
        self.on = "air"
        self.hit_t = -9.0
        self.marks_said = set()
        self.sun_t = None
        import random
        rr = random.Random(7)
        self.stars = [(rr.uniform(10, self.W - 10), rr.uniform(SCENE_TOP + 10, FLOOR_Y - 10), rr.uniform(0.3, 1.0), rr.choice((2, 2, 3, 4))) for _ in range(70)]
        self.line("First bounce: two meters. Every bounce after that goes twice as high.", "title", 0.0)
        self.line("How many bounces to reach the Sun? Take a guess.", "ask", 4.0)

    # --- la position dans le saut
    def state_at(self, t):
        for (n, t0, d) in self.sched:
            if t < t0 + d:
                return n, (t - t0) / d
        n, t0, d = self.sched[-1]
        return n + 1 + int((t - t0 - d) / 0.45), ((t - t0 - d) % 0.45) / 0.45

    def height(self, n):
        return 2.0 ** n

    def view(self, n, u):
        """La hauteur montrée par l'image (m) : elle suit le saut en cours, en montant."""
        if n > LAST:
            return self.height(LAST) * 1.25
        lo = math.log2(self.height(n - 1) * 1.25) if n > 1 else math.log2(2.5)
        hi = math.log2(self.height(n) * 1.25)
        k = min(1.0, u / 0.5)
        k = k * k * (3 - 2 * k)
        return 2.0 ** (lo + (hi - lo) * k)

    def step(self, dt):
        self.t += dt
        evs = []
        n, u = self.state_at(self.t)
        if n != self.n:
            self.n = n
            self.hit_t = self.t
            evs.append(("hit", "floor"))
        if u >= 0.5:                        # au sommet du saut n : ce qu'il vient d'atteindre
            for (h, name, kind, at, say) in MARKS:
                if at is not None and n == at and at not in self.marks_said:
                    self.marks_said.add(at)
                    if say:
                        self.line(say, f"m{at}", self.t)
                    if at == 38:
                        self.sun_t = self.t
                        self.line("And he did not stop.", "go", self.t + 2.0)
                    if at == LAST and not self.payoff:
                        self.finish("EDGE")
                        self.line("Eighty nine bounces. The edge of the observable universe.", "end", self.t + 0.2)
                        self.line("Still bouncing.", "still", self.t + 3.0)
        nn = min(n, LAST + 1)
        h = self.height(min(n, LAST)) * 4 * u * (1 - u)
        V = self.view(n, u)
        self.by = FLOOR_Y - self.R - h / V * SPAN
        return evs

    def snapshot(self):
        n, u = self.state_at(self.t)
        s = self.base_snap()
        s.update({"n": n, "u": u, "V": self.view(n, u), "sun_t": self.sun_t})
        return s

    def counter(self, s):
        n = min(s["n"], LAST)
        return f"BOUNCE {n}  ·  {fmt(self.height(n))}"

    def solids(self, s):
        return []

    def focus(self, s):
        return (100.0, 520.0, 900.0, 1000.0)

    def bodies(self, s):
        return []

    # --- dessin
    def Y(self, h, V):
        return FLOOR_Y - h / V * SPAN

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        V = s["V"]
        space = max(0.0, min(1.0, (math.log10(V) - 3.5) / 2.0))     # du ciel de nuit à l'espace
        sky = mix((20, 26, 48), (6, 6, 12), space)
        dr.rectangle([0, P(SCENE_TOP), P(W), P(FLOOR_Y)], fill=sky)
        if space > 0:
            for (x, y, b, r) in self.stars:
                circle(dr, P(x), P(y), P(r), mix(sky, (200, 205, 230), space * b))
        # la Terre
        dr.rectangle([0, P(FLOOR_Y), P(W), P(H)], fill=(26, 44, 34))
        dr.rectangle([0, P(FLOOR_Y), P(W), P(FLOOR_Y + 8)], fill=(50, 80, 60))
        f = base.font(int(38 * S))
        for (h, name, kind, at, say) in MARKS:
            y = self.Y(h, V)
            if y < SCENE_TOP - 300:
                continue
            self.mark(dr, P, kind, h, V, y, name, f, S)
        # le Soleil : la réponse
        if s["sun_t"] is not None and 0 <= t - s["sun_t"] < 3.2:
            k = min(1.0, (t - s["sun_t"]) / 0.25)
            fb = base.font(int((170 - 50 * (1 - k)) * S))
            dr.text((P(W / 2), P(H * 0.30)), "38", fill=GREEN, anchor="mm", font=fb, stroke_width=int(6 * S), stroke_fill=(10, 8, 12))
        self.bounce(dr, P, s)

    def mark(self, dr, P, kind, h, V, y, name, f, S):
        X = 720.0
        px_m = SPAN / V
        label_y = None
        if kind in ("house", "tower", "mountain"):
            hp = h * px_m                                   # à l'échelle réelle
            if hp < 6 or hp > SPAN * (0.9 if kind == "house" else 1.3):
                return
            if kind == "house":
                w = 7 * px_m
                dr.rectangle([P(X - w / 2), P(FLOOR_Y - hp * 0.6), P(X + w / 2), P(FLOOR_Y)], fill=(70, 62, 80))
                dr.polygon([(P(X - w / 2 - 6), P(FLOOR_Y - hp * 0.6)), (P(X + w / 2 + 6), P(FLOOR_Y - hp * 0.6)), (P(X), P(FLOOR_Y - hp))], fill=(110, 70, 60))
            elif kind == "tower":
                w = 125 * px_m
                dr.polygon([(P(X - w / 2), P(FLOOR_Y)), (P(X + w / 2), P(FLOOR_Y)), (P(X + 4), P(FLOOR_Y - hp)), (P(X - 4), P(FLOOR_Y - hp))], fill=(120, 96, 70))
            else:
                w = 18000 * px_m
                dr.polygon([(P(X - w / 2), P(FLOOR_Y)), (P(X + w / 2), P(FLOOR_Y)), (P(X), P(FLOOR_Y - hp))], fill=(84, 90, 110))
                snow = 0.18
                dr.polygon([(P(X - w / 2 * snow), P(FLOOR_Y - hp * (1 - snow))), (P(X + w / 2 * snow), P(FLOOR_Y - hp * (1 - snow))), (P(X), P(FLOOR_Y - hp))], fill=(225, 228, 236))
            if hp > 60:
                label_y = FLOOR_Y - hp - 34
        else:
            hgt = FLOOR_Y - y
            if hgt < 40:
                return                                      # dépassé : il s'écrase dans le sol
            a = min(1.0, (hgt - 40) / 60)
            col = lambda c: mix((6, 6, 12), c, a)
            if kind == "plane":
                dr.polygon([(P(X - 60), P(y)), (P(X + 60), P(y - 6)), (P(X + 60), P(y + 6))], fill=col((200, 200, 210)))
                dr.polygon([(P(X - 5), P(y)), (P(X + 25), P(y - 40)), (P(X + 35), P(y))], fill=col((170, 170, 185)))
                r = 30
            elif kind == "iss":
                dr.rectangle([P(X - 70), P(y - 4), P(X + 70), P(y + 4)], fill=col((180, 180, 190)))
                for dx in (-60, -40, 40, 60):
                    dr.rectangle([P(X + dx - 8), P(y - 30), P(X + dx + 8), P(y + 30)], fill=col((70, 100, 170)))
                dr.rectangle([P(X - 14), P(y - 12), P(X + 14), P(y + 12)], fill=col((200, 200, 210)))
                r = 34
            elif kind == "moon":
                r = 46
                circle(dr, P(X), P(y), P(r), col((200, 200, 205)))
                circle(dr, P(X - 14), P(y - 10), P(9), col((165, 165, 172)))
                circle(dr, P(X + 16), P(y + 14), P(6), col((165, 165, 172)))
            elif kind == "sun":
                r = 70
                glow(dr, P, X, y, 170, (255, 200, 90), (6, 6, 12), 0.35 * a)
                circle(dr, P(X), P(y), P(r), col((255, 210, 90)))
            elif kind == "neptune":
                r = 30
                circle(dr, P(X), P(y), P(r), col((80, 120, 220)))
            elif kind == "star":
                r = 22
                glow(dr, P, X, y, 80, (255, 120, 90), (6, 6, 12), 0.35 * a)
                circle(dr, P(X), P(y), P(r), col((255, 150, 110)))
            elif kind in ("galaxy", "galaxy_mw"):
                r = 80
                for k in range(5, 0, -1):
                    dr.ellipse([P(X - r * k / 5), P(y - r * k / 12), P(X + r * k / 5), P(y + r * k / 12)], fill=col(mix((6, 6, 12), (200, 190, 230), 0.25 + 0.15 * (5 - k))))
                circle(dr, P(X), P(y), P(10), col((255, 245, 220)))
            elif kind == "edge":
                for x in range(0, int(self.W), 40):
                    dr.rectangle([P(x), P(y - 2), P(x + 22), P(y + 2)], fill=col((240, 190, 70)))
                r = 10
            label_y = y + r + 30
        if label_y is not None:
            rows = [""]
            for wd in name.split():                     # lignes courtes : rien sous les boutons TikTok
                if rows[-1] and len(rows[-1]) + 1 + len(wd) > 12:
                    rows.append(wd)
                else:
                    rows[-1] = (rows[-1] + " " + wd).strip()
            for k, row in enumerate(rows):
                dr.text((P(X), P(label_y + k * 44)), row, fill=(220, 220, 232), anchor="mm", font=f)


DEFAULTS = {
    "ball_r": R_BOUNCE, "gravity": 3000.0,
    "chapter_max_s": 75.0,
    "counter_font_size": 50, "counter_y": 0.19, "hook_text_s": 2.6,
    "hook_narrator": True,
    "sub_y": 0.80, "watermark_y": 0.93, "end_hold_s": 1.3, "narr_tail_s": 0.3, "narr_gap_s": 0.25,
    "sources": {
        "Eiffel Tower 330 m": "https://www.toureiffel.paris/en/the-monument/key-figures",
        "Everest 8,849 m": "https://www.nationalgeographic.com/science/article/mount-everest-is-taller-than-we-thought",
        "ISS ~408 km": "https://www.nasa.gov/international-space-station/space-station-facts-and-figures/",
        "Moon 384,400 km": "https://science.nasa.gov/moon/facts/",
        "Sun 149.6 million km (1 AU)": "https://www.iau.org/static/resolutions/IAU2012_English.pdf",
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
