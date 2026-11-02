"""
Prototype « l'entretien » : Bounce passe un entretien d'embauche. Le recruteur (une
silhouette sans visage derrière son bureau, la voix du narrateur) lui pose des questions ;
Bounce ne sait répondre que « Bounce ». Une bulle traduit ce qu'il voulait dire. Et il
ne peut pas s'empêcher de rebondir sur sa chaise : à chaque réponse, un grand rebond, et
le bureau part un peu plus en morceaux. Les dégâts restent d'une question à l'autre.

    python3 src/stories/interview.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim
from listkit import Chapter, FLOOR_Y, SCENE_TOP, glow, mix, settle_body, separate, body_poly

R_BOUNCE = 68.0
G = 3000.0
SEAT_Y = 1250.0
DESK = (470.0, 910.0, 1180.0)          # x0, x1, dessus
CEIL = 474.0
BX = 290.0
WALL = (36, 38, 56)
CARPET = (52, 48, 60)
WOOD = (122, 86, 58)

# l'état du bureau, qui passe d'une question à la suivante (remis à zéro par Sim)
OFFICE = {}


def rr(dr, box, **kw):
    """Un rectangle qui accepte des coins dans le désordre (la caméra peut les retourner)."""
    x0, y0, x1, y1 = box
    dr.rectangle([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)], **kw)


def rect(w, h):
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


def fresh_office():
    """Les objets du bureau : (genre, x, y du centre, largeur, hauteur, palier)."""
    objs = []

    def add(kind, x, w, h, tier, col, y=None):
        objs.append({"id": len(objs), "kind": kind, "x": x, "y": (DESK[2] - h / 2) if y is None else y,
                     "a": 0.0, "vx": 0.0, "vy": 0.0, "w": 0.0, "wd": w, "ht": h, "tier": tier,
                     "col": col, "rest": True, "free": False, "ph": 0.0})
    add("lamp", 492.0, 30.0, 120.0, 7, (230, 190, 90))
    add("mug", 545.0, 44.0, 54.0, 1, (236, 236, 240))
    add("plate", 640.0, 120.0, 40.0, 2, (200, 170, 90))
    add("laptop", 790.0, 130.0, 104.0, 6, (150, 152, 166))
    add("stack", 885.0, 40.0, 46.0, 3, (238, 238, 230))
    return {"objs": objs, "papers": [], "chair": "ok", "tile": "ok", "desk": "ok", "spill": 0.0,
            "chair_parts": [], "desk_parts": [], "tile_obj": None, "crack": 0}


class Question(Chapter):
    """Une question : le recruteur demande, Bounce répond d'un grand rebond, la bulle
    traduit, le bureau encaisse."""
    hold_s = 0.6
    stamp = None
    level = 1
    q = ""
    tr = ""
    react = ""
    target = 3.0                       # moment visé de la réponse (s, dans la question)

    def setup(self):
        self.R = R_BOUNCE
        self.bx, self.by = BX, SEAT_Y - self.R
        self.vx = self.vy = 0.0
        self.on = "air"
        self.hits = 0
        self.last_hit = -9.0
        self.hit_t = -9.0
        self.hop0, self.hopT, self.hopV = 0.0, 0.62, 0.0
        self.big = False
        self.reply_local = None
        self.started = False
        self.impact_t = -9.0
        self.title = f"QUESTION {self.n} / {self.N}"
        self.line(self.q, "title", 0.0)
        self.rng2 = np.random.default_rng(100 + self.level)
        # un premier petit rebond déjà en cours
        self.hop0, self.hopT = -0.2, 0.6
        self.hopV = G * self.hopT / 2

    # ------------------------------------------------------------------ Bounce
    def floor_y(self):
        return (SEAT_Y if OFFICE["chair"] == "ok" else FLOOR_Y) - self.R

    def plan(self):
        """À chaque retombée : un petit rebond, ou le grand, calé pour retomber pile au
        moment de sa réponse."""
        t = self.t
        if self.reply_local is not None and not self.big and getattr(self, "answer_at", None) is None and t < self.reply_local:
            d = self.reply_local - t
            aim = 1.30 if self.level == 4 else 1.22          # « Higher. » : jusqu'au plafond
            if d <= 1.30:
                self.big = True
                return d
            rest = d - aim
            if rest <= 0.85:
                return max(0.17, rest)
            return max(0.45, min(float(self.rng2.uniform(0.62, 0.78)), rest - 0.5))
        if self.n == 1 and t < 3.0:
            return float(self.rng2.uniform(0.82, 0.92))           # l'ouverture : de grands rebonds
        return float(self.rng2.uniform(0.62, 0.78))

    def step(self, dt):
        self.t += dt
        evs = []
        if not self.started:
            self.started = True
            if not OFFICE:
                OFFICE.update(fresh_office())
        te = self.t - self.hop0
        if te >= self.hopT - 1e-9 or (self.reply_local is not None and self.big and self.t >= self.reply_local):
            # retombée
            self.by = self.floor_y()
            if self.t - self.last_hit >= 0.15:
                self.last_hit = self.t; self.hits += 1
                evs.append(("hit", "floor"))
            self.hit_t = self.t
            was_big = self.big or (self.reply_local is not None and self.end_t is None and self.t >= self.reply_local
                                   and getattr(self, "answer_at", None) is None)
            if was_big:
                self.big = False
                self.impact()
                self.answer_at = self.t + 0.3       # la bulle de traduction, juste après son « Bounce »
            T = self.plan()
            self.hop0, self.hopT = self.t, T
            self.hopV = G * T / 2
        else:
            self.by = self.floor_y() - (self.hopV * te - 0.5 * G * te * te)
            if self.level == 4 and self.by - self.R < CEIL + 70 and OFFICE["tile"] == "ok":
                self.drop_tile()
        if getattr(self, "answer_at", None) is not None and self.t >= self.answer_at and self.end_t is None:
            self.finish("ANSWER")
            self.on_answer()
        self.physics(dt)
        return evs

    # ------------------------------------------------------------------ le bureau
    def kick(self, o, power, side_bias=0.8):
        side = 1.0 if self.rng2.random() < side_bias else -1.0
        o["rest"] = False
        o["free"] = True
        o["vy"] = -power * float(self.rng2.uniform(0.8, 1.2))
        o["vx"] = side * float(self.rng2.uniform(90, 300)) * (0.6 + 0.12 * self.level)
        o["w"] = float(self.rng2.uniform(-8, 8))

    def impact(self):
        """Le grand rebond : tout ce qui est sur le bureau saute, de plus en plus fort."""
        self.impact_t = self.t
        L = self.level
        for o in OFFICE["objs"]:
            if o.get("gone"):
                continue
            if o["tier"] == L:
                self.kick(o, 700 + 70 * L, 1.0)
            elif o["tier"] < L and o["free"]:
                self.kick(o, 260 + 40 * L, 1.0 if o["x"] < 600 else (0.2 if o["x"] > 880 else 0.5))
        if L == 1:
            OFFICE["spill_on"] = True
        if L == 3:
            # la pile de feuilles explose
            st = [o for o in OFFICE["objs"] if o["kind"] == "stack"][0]
            st["gone"] = True
            for k in range(14):
                OFFICE["papers"].append({"id": 100 + k, "x": st["x"] + float(self.rng2.uniform(-20, 20)), "y": st["y"] - 10,
                                         "vx": float(self.rng2.uniform(-520, 260)), "vy": -float(self.rng2.uniform(600, 1000)),
                                         "a": float(self.rng2.uniform(-0.5, 0.5)), "ph": float(self.rng2.uniform(0, 6)), "rest": False})
        if L == 4 and OFFICE["tile"] == "ok":
            self.drop_tile()                     # « Higher. » : le choc décroche une dalle du plafond
        if L == 5:
            self.break_chair()
        if L == 7:
            OFFICE["crack"] = 1
        if L == 9:
            self.break_desk()
        for p in OFFICE["papers"]:
            if p["rest"] and L > 3:
                p["rest"] = False
                p["vy"] = -float(self.rng2.uniform(250, 500)); p["vx"] = float(self.rng2.uniform(-200, 200))

    def drop_tile(self):
        OFFICE["tile"] = "falling"
        OFFICE["objs"].append({"id": 50, "kind": "tile", "x": 470.0, "y": CEIL + 14, "a": 0.0, "vx": 60.0, "vy": 80.0,
                               "w": 1.5, "wd": 110.0, "ht": 16.0, "tier": 4, "col": (190, 190, 200), "rest": False,
                               "free": True, "ph": 0.0})

    def break_chair(self):
        OFFICE["chair"] = "broken"
        parts = [("seatL", BX - 50, SEAT_Y + 10, 96.0, 18.0, -520.0), ("seatR", BX + 50, SEAT_Y + 10, 96.0, 18.0, 520.0),
                 ("back", BX - 85, 1150.0, 18.0, 200.0, -260.0)]
        for k, (nm, x, y, w, h, vx) in enumerate(parts):
            OFFICE["objs"].append({"id": 60 + k, "kind": "wood", "x": x, "y": y, "a": 0.0, "vx": vx,
                                   "vy": -float(self.rng2.uniform(350, 650)), "w": float(self.rng2.uniform(-7, 7)),
                                   "wd": w, "ht": h, "tier": 5, "col": WOOD, "rest": False, "free": True, "ph": 0.0})

    def break_desk(self):
        OFFICE["desk"] = "broken"
        x0, x1, top = DESK
        mid = (x0 + x1) / 2
        for k, cx in enumerate(((x0 + mid) / 2, (mid + x1) / 2)):
            OFFICE["objs"].append({"id": 70 + k, "kind": "deskhalf", "x": cx, "y": (top + FLOOR_Y) / 2 - 2, "a": 0.0,
                                   "vx": (-1 if k == 0 else 1) * 90.0, "vy": -260.0, "w": (-1 if k == 0 else 1) * 2.6,
                                   "wd": (x1 - x0) / 2 - 8, "ht": FLOOR_Y - top - 4, "tier": 9, "col": WOOD, "rest": False,
                                   "free": True, "ph": 0.0})
        for o in OFFICE["objs"]:
            if o["kind"] not in ("deskhalf",) and not o.get("gone") and o["rest"]:
                o["rest"] = False; o["free"] = True

    @staticmethod
    def aabb(o):
        pts = body_poly(o, rect(o["wd"], o["ht"]))
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def ground(self, o):
        """Le sol d'un objet : le bureau, la moquette, ou le dessus d'un objet déjà posé
        juste en dessous (ils s'empilent au lieu de se traverser)."""
        x0, x1, top = DESK
        g = top if (OFFICE["desk"] == "ok" and x0 <= o["x"] <= x1 and o["y"] < top) else FLOOR_Y
        ax0, ay0, ax1, ay1 = self.aabb(o)
        for r in OFFICE["objs"]:
            if r is o or not r["rest"] or r.get("gone") or r["kind"] in ("tile",):
                continue
            bx0, by0, bx1, by1 = self.aabb(r)
            tol = 6.0 + max(0.0, o["vy"]) / 60.0 + 2.0             # il arrive par-dessus (au plus un pas de chute)
            if bx0 < ax1 - 4 and ax0 + 4 < bx1 and ay1 <= by0 + tol and by0 < g:
                g = by0
        return g

    def physics(self, dt):
        objs = [o for o in OFFICE["objs"] if not o.get("gone")]
        for o in objs:
            if o["rest"]:
                continue
            o["vy"] += G * 0.85 * dt
            o["x"] += o["vx"] * dt
            o["y"] += o["vy"] * dt
            o["a"] += o["w"] * dt
            xmin = 40.0 if o["kind"] == "wood" else 405.0 + 0.5 * max(o["wd"], o["ht"])   # le coin de Bounce reste libre
            if o["x"] < xmin:
                o["x"] = xmin; o["vx"] = abs(o["vx"]) * 0.5
            if o["x"] > 1040:
                o["x"] = 1040; o["vx"] = -abs(o["vx"]) * 0.5
            if o["y"] < CEIL + 30 and o["vy"] < 0:
                o["vy"] = -o["vy"] * 0.4
            corners = rect(o["wd"], o["ht"])
            if settle_body(o, self.ground(o), math.pi / 2, dt, corners):
                pass
        sep = [o for o in objs if o["kind"] not in ("tile",) and o["free"]]
        fixed = [o for o in objs if o["kind"] not in ("tile",) and not o["free"]]    # pas encore lancés : des obstacles
        for _ in range(2):
            flags = [o["rest"] for o in sep]
            for o in sep:
                o["rest"] = False
            separate(sep + fixed, lambda o: rect(o["wd"], o["ht"]), iters=3, max_step=3.0)
            for o, f in zip(sep, flags):
                o["rest"] = f
            # rien ne s'enfonce : chaque objet reste posé sur son sol (bureau ou moquette),
            # et reste dans la pièce
            for o in objs:
                hw = 0.5 * max(o["wd"], o["ht"])
                xmin = 40.0 if o["kind"] == "wood" else 405.0 + hw
                o["x"] = min(1040.0 - hw, max(xmin, o["x"]))
                ca, sa = math.cos(o["a"]), math.sin(o["a"])
                low = max(dx * sa + dy * ca for dx, dy in rect(o["wd"], o["ht"]))
                g = self.ground(o)
                if o["y"] + low > g + 0.5:
                    o["y"] = g - low
                elif o["rest"] and o["y"] + low < g - 2:
                    o["rest"] = False
        # la tasse renversée : le café s'étale
        if OFFICE.get("spill_on"):
            OFFICE["spill"] = min(1.0, OFFICE["spill"] + dt * 0.8)
        # les feuilles : elles planent en se balançant
        for p in OFFICE["papers"]:
            if p["rest"]:
                continue
            p["age"] = p.get("age", 0.0) + dt
            p["vy"] = min(p["vy"] + G * 0.5 * dt, 230.0)
            p["vx"] += math.sin(p["age"] * 5 + p["ph"]) * 420 * dt - p["vx"] * 0.8 * dt
            p["x"] += p["vx"] * dt; p["y"] += p["vy"] * dt
            p["a"] = 0.5 * math.sin(p["age"] * 5 + p["ph"]) * min(1.0, p["age"] * 3)
            p["x"] = min(1030.0, max(50.0, p["x"]))
            gy = FLOOR_Y
            if OFFICE["desk"] == "ok" and DESK[0] <= p["x"] <= DESK[1] and p["y"] < DESK[2] - 2 and p["vy"] > 0:
                gy = DESK[2]
            if p["vy"] > 0 and p["y"] >= gy - 3 and (gy == FLOOR_Y or p["y"] < gy + 6):
                p["y"] = gy - 3; p["rest"] = True

    # ------------------------------------------------------------------ récit
    def on_answer(self):
        self.mood = None
        if self.react:
            self.line(self.react, "react", self.t + 1.3)

    def snapshot(self):
        s = self.base_snap()
        s["objs"] = [dict(o) for o in OFFICE.get("objs", []) if not o.get("gone")]
        s["papers"] = [dict(p) for p in OFFICE.get("papers", [])]
        for k in ("chair", "tile", "desk", "spill", "crack"):
            s[k] = OFFICE.get(k)
        s["impact"] = self.impact_t
        s["ans"] = self.end_t
        return s

    # ------------------------------------------------------------------ contrat du contrôle
    def cam(self, s):
        dur, z0 = (2.2, 1.75) if self.n == 1 else (1.4, 0.95)
        k = min(1.0, s["t"] / dur)
        Z = z0 + (1.0 - z0) * (k * k * (3 - 2 * k))
        dy = 0.0
        age = s["t"] - s["impact"]
        if 0 <= age < 0.5:
            dy = 9.0 * math.exp(-age * 7) * math.sin(age * 60)
        return Z, dy

    def xf(self, s):
        Z, dy = self.cam(s)
        cx, cy = 540.0, 1100.0
        if self.n == 1:
            # l'ouverture : gros plan sur Bounce qui rebondit, puis on découvre l'entretien
            k = min(1.0, s["t"] / 2.2)
            k = k * k * (3 - 2 * k)
            cx, cy = 330.0 + 210.0 * k, 1120.0 - 20.0 * k
        X = lambda x: (x - cx) * Z + 540
        Y = lambda y: (y - cy) * Z + 1100 + dy
        return X, Y, Z

    def hero(self, s):
        X, Y, Z = self.xf(s)
        return (X(s["bx"]), Y(s["by"]), self.R * Z)

    def solids(self, s):
        X, Y, Z = self.xf(s)
        out = []
        if s["desk"] == "ok":
            out.append(("rect", X(DESK[0]), Y(DESK[2]), X(DESK[1]), Y(FLOOR_Y)))
        if s["chair"] == "ok":
            out.append(("rect", X(196), Y(1040), X(214), Y(SEAT_Y)))
            out.append(("rect", X(196), Y(SEAT_Y), X(384), Y(SEAT_Y + 20)))
        for o in s["objs"]:
            if o["kind"] in ("wood",):
                continue
            out.append(("poly", [(X(x), Y(y)) for (x, y) in body_poly(o, rect(o["wd"], o["ht"]))]))
        return out

    def focus(self, s):
        X, Y, Z = self.xf(s)
        return (X(70), Y(560), X(660), Y(SEAT_Y + 20))

    def bodies(self, s):
        X, Y, Z = self.xf(s)
        out = []
        for o in s["objs"]:
            if o["free"]:
                poly = [(X(x), Y(y)) for (x, y) in body_poly(o, rect(o["wd"] - 8, o["ht"] - 8))]
                out.append((o["id"], X(o["x"]), Y(o["y"]), o["a"], poly if o["kind"] not in ("tile", "wood", "deskhalf") else None))
        for p in s["papers"]:
            out.append((p["id"], X(p["x"]), Y(p["y"]), p["a"]))
        return out

    # ------------------------------------------------------------------ dessin
    def draw(self, dr, s, t, S):
        X0, Y0, Z = self.xf(s)
        X = lambda x: X0(x) * S
        Y = lambda y: Y0(y) * S
        Q = lambda v: v * Z * S
        P = lambda v: v * S
        W, H = self.W, self.H
        rr(dr, [0, P(SCENE_TOP), P(W), P(H)], fill=WALL)
        # le plafond et ses dalles
        rr(dr, [0, P(SCENE_TOP), P(W), Y(CEIL)], fill=(70, 72, 88))
        for x in range(0, 1100, 120):
            dr.line([(X(x), Y(SCENE_TOP - 60)), (X(x), Y(CEIL))], fill=(54, 56, 70), width=max(1, int(Q(3))))
        if s["tile"] == "ok":
            pass
        else:
            rr(dr, [X(385), Y(SCENE_TOP - 60), X(495), Y(CEIL)], fill=(14, 14, 20))
        # la fenêtre : la ville la nuit
        rr(dr, [X(70), Y(560), X(380), Y(930)], fill=(16, 22, 44))
        for k, (bx_, bw, bh) in enumerate(((80, 60, 220), (150, 50, 300), (205, 70, 180), (280, 90, 260))):
            rr(dr, [X(bx_), Y(930 - bh), X(bx_ + bw), Y(930)], fill=(26, 30, 52))
            for r in range(3):
                for c in range(2):
                    if (k + r + c) % 2 == 0:
                        rr(dr, [X(bx_ + 10 + c * 22), Y(930 - bh + 20 + r * 40), X(bx_ + 22 + c * 22), Y(930 - bh + 34 + r * 40)], fill=(150, 130, 70))
        rr(dr, [X(222), Y(560), X(228), Y(930)], fill=(60, 60, 80))
        rr(dr, [X(70), Y(740), X(380), Y(746)], fill=(60, 60, 80))
        rr(dr, [X(64), Y(554), X(386), Y(562)], fill=(80, 80, 98))
        if s["crack"]:
            pts = [(300, 600), (270, 660), (300, 700), (250, 780), (285, 840)]
            dr.line([(X(x), Y(y)) for (x, y) in pts], fill=(200, 210, 230), width=max(1, int(Q(3))))
            dr.line([(X(270), Y(660)), (X(210), Y(690))], fill=(200, 210, 230), width=max(1, int(Q(3))))
        # l'horloge, qui tourne
        cx, cy = 560.0, 640.0
        circle(dr, X(cx), Y(cy), Q(46), (220, 220, 228))
        circle(dr, X(cx), Y(cy), Q(40), (240, 240, 244))
        a = (t * 6.0) % (2 * math.pi)
        dr.line([(X(cx), Y(cy)), (X(cx + 34 * math.sin(a)), Y(cy - 34 * math.cos(a)))], fill=(200, 40, 40), width=max(1, int(Q(3))))
        dr.line([(X(cx), Y(cy)), (X(cx + 22 * math.sin(1.1)), Y(cy - 22 * math.cos(1.1)))], fill=(30, 30, 40), width=max(1, int(Q(5))))
        # « employé du mois », sans visage
        rr(dr, [X(780), Y(560), X(900), Y(700)], fill=(150, 120, 60))
        rr(dr, [X(790), Y(570), X(890), Y(690)], fill=(60, 64, 84))
        circle(dr, X(840), Y(615), Q(20), (90, 94, 116))
        rr(dr, [X(815), Y(640), X(865), Y(690)], fill=(90, 94, 116))
        # le sol
        rr(dr, [0, Y(FLOOR_Y), P(W), P(H)], fill=CARPET)
        rr(dr, [0, Y(FLOOR_Y), P(W), Y(FLOOR_Y + 6)], fill=dim(CARPET, 1.3))
        # le recruteur : une silhouette, derrière le bureau
        talk = 0.0
        if t < 2.6:
            talk = 3.0 * math.sin(t * 22)
        rc = (74, 78, 100)
        rr(dr, [X(700), Y(930), X(820), Y(FLOOR_Y)], fill=(46, 50, 70))                     # la veste
        dr.polygon([(X(740), Y(930)), (X(780), Y(930)), (X(760), Y(990))], fill=(232, 232, 236))   # la chemise
        dr.polygon([(X(754), Y(940)), (X(766), Y(940)), (X(770), Y(1010)), (X(760), Y(1024)), (X(750), Y(1010))], fill=(190, 40, 50))
        rr(dr, [X(690), Y(950), X(712), Y(1150)], fill=(46, 50, 70))                       # les bras
        rr(dr, [X(808), Y(950), X(830), Y(1150)], fill=(46, 50, 70))
        rr(dr, [X(640), Y(1080), X(700), Y(1160)], fill=(150, 120, 80))                     # le porte-documents
        rr(dr, [X(648), Y(1090), X(692), Y(1150)], fill=(236, 236, 230))
        circle(dr, X(760), Y(880 + talk), Q(44), rc)
        rr(dr, [X(830), Y(1000), X(846), Y(FLOOR_Y)], fill=(50, 50, 64))           # le dossier du fauteuil
        # le bureau
        if s["desk"] == "ok":
            x0, x1, top = DESK
            rr(dr, [X(x0 + 16), Y(top + 24), X(x1 - 16), Y(FLOOR_Y)], fill=dim(WOOD, 0.7))
            rr(dr, [X(x0), Y(top), X(x1), Y(top + 26)], fill=WOOD)
            rr(dr, [X(x0), Y(top), X(x1), Y(top + 5)], fill=mix(WOOD, (255, 230, 190), 0.3))
            if s["spill"] > 0:
                w = 90 * s["spill"]
                dr.ellipse([X(560 - w * 0.3), Y(top - 6), X(560 + w), Y(top + 4)], fill=(96, 60, 36))
        # la chaise
        if s["chair"] == "ok":
            rr(dr, [X(196), Y(1040), X(214), Y(SEAT_Y)], fill=WOOD)
            rr(dr, [X(196), Y(SEAT_Y), X(384), Y(SEAT_Y + 20)], fill=WOOD)
            for lx in (206, 370):
                rr(dr, [X(lx - 6), Y(SEAT_Y + 20), X(lx + 6), Y(FLOOR_Y)], fill=dim(WOOD, 0.7))
        else:
            for lx, ang in ((206, -0.5), (370, 0.6)):
                dr.line([(X(lx), Y(FLOOR_Y)), (X(lx + 120 * math.sin(ang)), Y(FLOOR_Y - 14))], fill=dim(WOOD, 0.7), width=max(1, int(Q(12))))
        # les objets
        for o in s["objs"]:
            self.obj(dr, X, Y, Q, o)
        for p in s["papers"]:
            pts = body_poly({"x": p["x"], "y": p["y"], "a": p["a"]}, rect(56, 6))
            dr.polygon([(X(x), Y(y)) for (x, y) in pts], fill=(238, 238, 230))
        base.ball(dr, X(s["bx"]), Y(s["by"]), Q(self.R))
        self.bubble(dr, X, Y, Q, P, s, t)
        rr(dr, [0, 0, P(W), P(SCENE_TOP) - 1], fill=tuple(self.cfg["bg_color"]))

    def obj(self, dr, X, Y, Q, o):
        poly = [(X(x), Y(y)) for (x, y) in body_poly(o, rect(o["wd"], o["ht"]))]
        k = o["kind"]
        if k == "mug":
            dr.polygon(poly, fill=o["col"])
            ca, sa = math.cos(o["a"]), math.sin(o["a"])
            hx, hy = o["x"] + 28 * ca, o["y"] + 28 * sa
            circle(dr, X(hx), Y(hy), Q(12), o["col"])
            circle(dr, X(hx), Y(hy), Q(6), WALL)
            return
        if k == "plate":
            dr.polygon(poly, fill=o["col"])
            if abs(o["a"]) < 0.4:
                f = base.font(Q(26))
                dr.text((X(o["x"]), Y(o["y"])), "HR", fill=(40, 30, 10), anchor="mm", font=f)
            return
        if k == "laptop":
            # un portable ouvert : le socle en bas, l'écran (vu de dos) au-dessus
            base_ = body_poly(o, [(-65, 34), (65, 34), (65, 52), (-65, 52)])
            scr = body_poly(o, [(-58, -52), (58, -52), (58, 34), (-58, 34)])
            dr.polygon([(X(x), Y(y)) for (x, y) in scr], fill=(120, 122, 136))
            dr.polygon([(X(x), Y(y)) for (x, y) in base_], fill=o["col"])
            c = body_poly(o, [(0, -10)])[0]
            circle(dr, X(c[0]), Y(c[1]), Q(9), (170, 172, 186))
            return
        if k == "lamp":
            dr.polygon(poly, fill=(80, 80, 90))
            ca, sa = math.cos(o["a"]), math.sin(o["a"])
            hx, hy = o["x"] + 60 * sa, o["y"] - 60 * ca
            circle(dr, X(hx), Y(hy), Q(28), o["col"])
            return
        if k == "deskhalf":
            # une moitié de bureau : le plateau en haut, le panneau en dessous
            dr.polygon(poly, fill=dim(WOOD, 0.7))
            slab = body_poly(o, [(-o["wd"] / 2, -o["ht"] / 2), (o["wd"] / 2, -o["ht"] / 2), (o["wd"] / 2, -o["ht"] / 2 + 26), (-o["wd"] / 2, -o["ht"] / 2 + 26)])
            dr.polygon([(X(x), Y(y)) for (x, y) in slab], fill=WOOD)
            return
        dr.polygon(poly, fill=o["col"])

    def bubble(self, dr, X, Y, Q, P, s, t):
        """La traduction : une bulle au-dessus de Bounce, dès qu'il a répondu."""
        if s["ans"] is None:
            return
        age = s["t"] - s["ans"]
        k = min(1.0, age / 0.15)
        x0, y0, x1, y1 = 80.0, 590.0, 660.0, 800.0
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        sc = 0.6 + 0.4 * k
        bx0, bx1 = cx - (cx - x0) * sc, cx + (x1 - cx) * sc
        by0, by1 = cy - (cy - y0) * sc, cy + (y1 - cy) * sc
        dr.rounded_rectangle([P(bx0), P(by0), P(bx1), P(by1)], radius=int(P(26)), fill=(250, 250, 252), outline=(20, 20, 26), width=int(P(5)))
        tx, ty = X(s["bx"]), Y(s["by"]) - Q(self.R) - P(10)
        dr.polygon([(P(250), P(by1 - 3)), (P(330), P(by1 - 3)), (tx, max(ty, P(by1 + 30)))], fill=(250, 250, 252))
        if k < 1.0:
            return
        f1 = base.font(P(28))
        dr.text((P(x0 + 28), P(y0 + 34)), "TRANSLATION:", fill=(120, 120, 140), anchor="lm", font=f1)
        words = self.tr.split()
        rows, cur = [], ""
        size = 58
        f2 = base.font(P(size))
        for w in words:
            cand = (cur + " " + w).strip()
            if base.text_w(f2, cand) <= P(x1 - x0 - 60) or not cur:
                cur = cand
            else:
                rows.append(cur); cur = w
        rows.append(cur)
        for i, row in enumerate(rows):
            yy = y0 + 112 + (i - (len(rows) - 1) / 2) * 64 + (8 if len(rows) == 1 else 22)
            dr.text((P(cx), P(yy)), row, fill=(20, 20, 26), anchor="mm", font=f2)


# ---------------------------------------------------------------- les questions
QUESTIONS = [
    ("What's your name?", "BOUNCE.", "Great start.", 4.6),
    ("Why do you want to work here?", "Your floor looked bouncy.", "It's carpet.", 3.1),
    ("What's your biggest weakness?", "I can't sit still.", "I noticed.", 4.7),
    ("Where do you see yourself in five years?", "Higher.", "Noted.", 3.4),
    ("How do you handle pressure?", "Like this.", "That was a chair.", 5.2),
    ("What's a challenge you've overcome?", "Gravity.", "Clearly not.", 3.2),
    ("Are you a team player?", "I am the team.", "Okay.", 4.8),
    ("What are your salary expectations?", "A trampoline.", "We can do that.", 3.5),
    ("Can you start Monday?", "I already started.", "You're hired.", 5.0),
]


def make(n, q, tr, react, target):
    class Q_(Question):
        pass
    Q_.n, Q_.N, Q_.level = n, len(QUESTIONS), n
    Q_.q, Q_.tr, Q_.react, Q_.target = q, tr, react, target
    Q_.__name__ = f"Q{n}"
    if n == len(QUESTIONS):
        Q_.mood = "win"
        Q_.hold_s = 1.0
    return Q_


CHAPTERS = [(make(i + 1, *qq), {}) for i, qq in enumerate(QUESTIONS)]

DEFAULTS = {
    "ball_r": R_BOUNCE, "gravity": G,
    "chapter_max_s": 12.0,
    "counter_font_size": 72, "counter_y": 0.19, "hook_text_s": 2.4,
    "sub_y": 0.80, "watermark_y": 0.93, "end_hold_s": 1.4, "narr_tail_s": 0.3, "narr_gap_s": 0.3,
}


class Sim(StorySim):
    def __init__(self, cfg, rng):
        OFFICE.clear()
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)

    def _open(self, i):
        s = self.sims[i]
        # la réponse de Bounce : calée sur le moment visé, au moins 1,2 s après la question
        start = max(self.t, self.narr_free + self.cfg["narr_gap_s"])
        q_end = start + self.narr_dur(s.q)
        delay = max(1.65, s.target - (q_end - self.t))      # de quoi placer un « Bounce » avant sa réponse
        s.replies = [("title", delay)]
        super()._open(i)
        # (+1 image : le contrôle date les événements au début du pas)
        s.reply_local = (self._line_end.get(f"{i}:title", q_end) + delay) - self.t0 + 1.0 / self.cfg["fps"]


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
