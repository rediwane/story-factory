"""
Prototype « la machine de Bounce » : Bounce veut éteindre la lumière. L'interrupteur est
par terre, à un mètre de lui. Il rebondit sur une bascule et déclenche une machine
d'une minute qui traverse toute la pièce pour revenir appuyer sur cet interrupteur.

Toute la machine est calculée d'avance, pièce par pièce, avec une vraie physique simple
(projectiles, roulement sur rail, dominos qui basculent sur leur arête, levier, poulie à
contrepoids, pendule de Newton, catapulte) ; chaque pièce est placée là où la précédente
envoie sa bille, si bien que tout s'enchaîne sans tricher.

    python3 src/stories/machine.py configs/<name>.json [--simulate]
"""
import math, sys, os, bisect
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim
from listkit import Chapter, SCENE_TOP, GREEN, AMBER, glow, mix

G = 2200.0
FLOOR = 1500.0
CEIL = -760.0
RB = 26.0                      # rayon des billes
R_BOUNCE = 58.0
DT = 1.0 / 240.0
SCREEN_CY = 1060.0             # où se place le point suivi par la caméra, à l'écran
WOOD = (120, 84, 56)
RAIL = (150, 150, 165)
BALL_COLS = {"A": (80, 170, 255), "B": (255, 170, 60), "C": (120, 220, 140), "D": (240, 240, 250)}
DOM_COLS = [(230, 80, 90), (240, 150, 70), (240, 210, 80), (110, 200, 120), (80, 170, 230), (150, 120, 230)]


class Track:
    """La trajectoire échantillonnée d'un corps : [(t, x, y, a)]."""

    def __init__(self, x, y, a=0.0):
        self.t, self.x, self.y, self.a = [], [], [], []
        self.x0, self.y0, self.a0 = x, y, a

    def add(self, t, x, y, a=0.0):
        self.t.append(t); self.x.append(x); self.y.append(y); self.a.append(a)

    def at(self, t):
        if not self.t or t <= self.t[0]:
            return (self.x[0], self.y[0], self.a[0]) if self.t else (self.x0, self.y0, self.a0)
        if t >= self.t[-1]:
            return self.x[-1], self.y[-1], self.a[-1]
        i = bisect.bisect_right(self.t, t)
        t0, t1 = self.t[i - 1], self.t[i]
        k = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
        return (self.x[i - 1] + (self.x[i] - self.x[i - 1]) * k, self.y[i - 1] + (self.y[i] - self.y[i - 1]) * k,
                self.a[i - 1] + (self.a[i] - self.a[i - 1]) * k)

    def last(self):
        return self.t[-1], self.x[-1], self.y[-1]


def path(x, y, ang, pieces, step=6.0):
    """Une ligne (le chemin du centre de la bille) : départ (x, y), direction ang (radians,
    0 = vers la droite, positif = vers le bas), puis des morceaux ("s", longueur) droits ou
    ("a", angle, rayon) en arc."""
    pts = [(x, y)]
    for pc in pieces:
        if pc[0] == "s":
            n = max(1, int(pc[1] / step))
            for _ in range(n):
                x += math.cos(ang) * pc[1] / n; y += math.sin(ang) * pc[1] / n
                pts.append((x, y))
        else:
            turn, rad = pc[1], pc[2]
            n = max(2, int(abs(turn) * rad / step))
            for _ in range(n):
                ang += turn / n
                x += math.cos(ang) * abs(turn) * rad / n; y += math.sin(ang) * abs(turn) * rad / n
                pts.append((x, y))
    return pts, ang


def roll(track, pts, t, v, mu=0.12, c=40.0, roll_a=0.0, stop_at_end=False):
    """La bille roule le long de pts (centre) à partir de la vitesse v. Renvoie (t, v, ang)
    à la fin. a = g·pente − frottements."""
    seg = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        if L > 1e-6:
            seg.append((x0, y0, (x1 - x0) / L, (y1 - y0) / L, L))
    s, i, ra = 0.0, 0, roll_a
    while i < len(seg):
        x0, y0, ux, uy, L = seg[i]
        acc = G * uy - mu * v - c
        v = max(25.0, v + acc * DT)
        s += v * DT
        ra += v * DT / RB
        while i < len(seg) and s > seg[i][4]:
            s -= seg[i][4]; i += 1
        if i >= len(seg):
            break
        x0, y0, ux, uy, L = seg[i]
        t += DT
        track.add(t, x0 + ux * s, y0 + uy * s, ra)
    ux, uy = seg[-1][2], seg[-1][3]
    return t, v, math.atan2(uy, ux), ra


def fly(track, t, x, y, vx, vy, stop, ra=0.0, spin=0.0, max_t=6.0):
    """Projectile jusqu'à ce que stop(x, y, vx, vy) soit vrai. Renvoie (t, x, y, vx, vy, ra)."""
    t_end = t + max_t
    while t < t_end:
        vy += G * DT
        x += vx * DT; y += vy * DT
        ra += spin * DT
        t += DT
        track.add(t, x, y, ra)
        if stop(x, y, vx, vy):
            break
    return t, x, y, vx, vy, ra


def hit_time(y0, vy, y_target, descending=True):
    """Le temps où un projectile (y0, vy) passe à la hauteur y_target."""
    a, b, c = 0.5 * G, vy, y0 - y_target
    d = b * b - 4 * a * c
    if d < 0:
        return None
    r = [(-b - math.sqrt(d)) / (2 * a), (-b + math.sqrt(d)) / (2 * a)]
    r = [x for x in r if x > 0]
    return max(r) if descending else min(r)


class Machine(Chapter):
    title = None
    stamp = None
    mood = "win"
    hold_s = 0.5

    # ------------------------------------------------------------------ construction
    def setup(self):
        self.R = R_BOUNCE
        self.on = "air"
        self.hit_t = -9.0
        self.bx, self.by = 280.0, 1200.0
        self.evs = []                 # (t, kind, data) préparés
        self.marks = []               # (t, numéro d'étape)
        self.focus_segs = []          # (t_debut, nom du corps suivi)
        self.ceil_t0 = None
        self.build()
        self.slow = self.slow_windows()
        self.make_camera()
        self.ev_i = 0
        self.lines_plan()

    def step_mark(self, t, n):
        self.marks.append((t, n))

    def build(self):
        T = 0.0
        self.tracks = {}
        tr = self.tracks
        # --- 1. la bascule : la bille A attend sur le bout droit, posé au sol
        self.ss_piv = (640.0, FLOOR - 34.0)
        self.ss_L = 175.0
        ss = tr["seesaw"] = Track(0, 0, 0.17)
        sx, sy = self.ss_piv
        right = lambda a: (sx + self.ss_L * math.cos(a), sy + self.ss_L * math.sin(a))
        left = lambda a: (sx - self.ss_L * math.cos(a), sy - self.ss_L * math.sin(a))
        rx, ry = right(0.17)
        A = tr["A"] = Track(rx - RB * math.sin(0.17), ry - RB * math.cos(0.17) - 8)
        # Bounce : deux rebonds sur le lit, puis un saut sur le bout gauche de la bascule
        bounce = tr["bounce"] = Track(280, 1330 - R_BOUNCE)
        self.bounce_hits = []
        bed_top = 1330.0
        tb = 0.0
        bxp = 280.0
        hops = []
        byp = bed_top - R_BOUNCE
        for (x_to, h, _) in hops:
            vy = -math.sqrt(2 * G * h); dur = 2 * -vy / G
            n = int(dur / DT)
            for k in range(1, n + 1):
                tt = k * DT
                bounce.add(tb + tt, bxp + (x_to - bxp) * tt / dur, byp + vy * tt + 0.5 * G * tt * tt)
            tb += dur
            self.bounce_hits.append(tb)
            bxp = x_to
        # le saut vers la bascule : du lit (y 1330) au bout gauche relevé
        lx, ly = left(0.17)
        land_y = ly - 10 - R_BOUNCE
        vy = -950.0
        dur = hit_time(byp, vy, land_y)
        n = int(dur / DT)
        for k in range(1, n + 1):
            tt = k * DT
            bounce.add(tb + tt, bxp + (lx - bxp) * tt / dur, byp + vy * tt + 0.5 * G * tt * tt)
        tb += dur
        self.bounce_hits.append(tb)
        T_launch = tb
        # la bascule bascule en 0,12 s ; la bille A part
        ss.add(T_launch, 0, 0, 0.17)
        for k in range(1, 30):
            tt = k * DT
            a = 0.17 - 0.34 * min(1.0, tt / 0.12)
            ss.add(T_launch + tt, 0, 0, a)
        # Bounce rebondit ensuite sur le bout gauche (au sol) tant que la machine tourne
        self.bounce_base = (lx, left(-0.17)[1] - 10 - R_BOUNCE)
        self.bounce_t0 = tb
        # bille A : envol
        ax, ay, _ = A.at(0)
        rx2, ry2 = right(-0.17)
        ax0, ay0 = rx2 - RB * math.sin(-0.17), ry2 - RB * math.cos(-0.17) - 8
        A.add(T_launch, ax, ay)
        A.add(T_launch + 0.1, ax0, ay0)
        vx, vy = 470.0, -2180.0
        t = T_launch + 0.1
        y_land = 470.0
        t, x, y, vx, vy, ra = fly(A, t, ax0, ay0, vx, vy, lambda x, y, vx, vy: vy > 0 and y >= y_land, spin=6.0)
        self.focus_segs.append((5.2, "A"))                  # la chambre d'abord : le gag, puis la machine
        # --- 2. les rampes en zigzag
        self.step_mark(t, 1)
        self.rails = []               # lignes de centre de bille, pour le dessin
        self.bumpers = []
        ang0 = math.atan2(vy, vx)
        v = math.hypot(vx, vy) * 0.55
        pts, ang = path(x, y, ang0, [("a", math.radians(7) - ang0, 160), ("s", 460)])
        self.rails.append(pts)
        t, v, ang, ra = roll(A, pts, t, v, roll_a=ra)
        n_levels = 3
        x_end, y_end = pts[-1]
        direction = 1
        xl, xr = pts[0][0] + 40, x_end
        for lev in range(1, n_levels):
            # la butée : la bille s'arrête net et tombe sur le niveau d'en dessous
            self.bumpers.append((x_end + direction * (RB + 6), y_end))
            A.add(t + 0.04, x_end + direction * 3, y_end)
            t += 0.04
            t, x, y, vx2, vy2, ra = fly(A, t, x_end + direction * 3, y_end, -direction * 40.0, 0.0,
                                        lambda x, y, vx, vy: y >= y_end + 48, ra=ra, spin=-direction * 2)
            direction = -direction
            length = (xr - xl) - 10
            pts, ang = path(x, y, math.pi + math.radians(-7) if direction < 0 else math.radians(7),
                            [("s", length)])
            if direction < 0:
                pts = [(px, py) for (px, py) in pts]
            self.rails.append(pts)
            t, v, ang, ra = roll(A, pts, t, 60.0, roll_a=ra)
            x_end, y_end = pts[-1]
        # la sortie du dernier niveau : un escalier, que la bille descend en rebondissant
        vx = math.cos(ang) * v * 0.55; vy = math.sin(ang) * v * 0.55
        n_st = 6
        st_h = (FLOOR - (y_end + RB + 40)) / n_st
        st_w = 120.0
        sx0 = x_end + 40
        self.stairs = (sx0, y_end + RB + 40, st_w, st_h, n_st)
        x, y = x_end, y_end
        vx = max(vx, 320.0)
        self.stairs_t = t
        for k in range(n_st + 1):
            top = FLOOR if k == n_st else self.stairs[1] + st_h * k
            # chute jusqu'à la marche k
            t, x, y, vx, vy, ra = fly(A, t, x, y, vx, vy, lambda xx, yy, a, b: b > 0 and yy >= top - RB, ra=ra, spin=vx / RB)
            y = top - RB
            # un petit rebond
            vy = -abs(vy) * 0.33
            if abs(vy) > 60:
                t, x, y, vx, vy, ra = fly(A, t, x, y, vx, vy, lambda xx, yy, a, b: b > 0 and yy >= top - RB, ra=ra, spin=vx / RB)
                y = top - RB
            if k == n_st:
                break
            # elle roule jusqu'au bord de la marche, puis tombe
            edge = sx0 + (k + 1) * st_w
            vx = max(vx * 0.97, 320.0)
            while x < edge:
                x += vx * DT; t += DT; ra += vx * DT / RB
                A.add(t, x, y, ra)
            vy = 0.0
        vx = max(vx, 420.0)
        # roulement au sol
        v = abs(vx)
        x_dom0 = x + 160.0
        pts = [(x, FLOOR - RB), (x_dom0 - 14 - RB, FLOOR - RB)]
        t, v, ang, ra = roll(A, path(x, FLOOR - RB, 0.0, [("s", x_dom0 - 14 - RB - x)])[0], t, v, mu=0.05, c=10.0, roll_a=ra)
        # --- 3. les dominos, de plus en plus grands, dont un qui hésite
        self.step_mark(t, 2)
        self.focus_segs.append((t - 0.2, "dom"))
        N = 28
        self.doms = []
        xd = x_dom0
        for i in range(N):
            h = 56.0 * 1.095 ** i
            w = 0.2 * h
            self.doms.append({"x": xd, "h": h, "w": w, "track": Track(xd, FLOOR, 0.0)})
            xd += w + 0.5 * h
        self.suspense = 18
        omega = 9.0
        t_hit = t
        A.add(t + 0.15, A.x[-1] - 6, A.y[-1], A.a[-1])                 # la bille rebondit un peu
        for i, d in enumerate(self.doms):
            h, w = d["h"], d["w"]
            diag = math.hypot(h, w)
            Acoef = 1.5 * G / diag
            th_tip = math.atan(w / h)
            if i > 0:
                prev = self.doms[i - 1]
                omega = max(math.sqrt(2 * Acoef * (1 - math.cos(th_tip))) * 1.35, prev["w_hit"] * 0.82 * math.sqrt(prev["h"] / h))
                if i == self.suspense:
                    omega = math.sqrt(2 * Acoef * (1 - math.cos(th_tip))) * 1.03
            th, om = 0.0, omega
            tt = t_hit
            nxt = self.doms[i + 1] if i + 1 < N else None
            contact = None
            while tt < t_hit + 12.0:
                om += Acoef * math.sin(th - th_tip) * DT
                th += om * DT
                tt += DT
                d["track"].add(tt, d["x"], FLOOR, th)
                top_x = d["x"] + w / 2 + h * math.sin(th) - w * (1 - math.cos(th))
                if nxt is not None and top_x >= nxt["x"] - nxt["w"] / 2:
                    contact = tt
                    break
                if nxt is None and th >= math.radians(62):
                    contact = tt
                    break
            d["w_hit"] = om
            d["th_c"] = th
            d["t_c"] = contact
            t_hit = contact
        t = t_hit
        # chaque domino reste appuyé contre le dos du suivant pendant que celui-ci tombe
        for i in range(N - 2, -1, -1):
            d, n_ = self.doms[i], self.doms[i + 1]
            px_i = d["x"] + d["w"] / 2
            px1 = n_["x"] + n_["w"] / 2
            tr1 = n_["track"]
            lo_a = d["th_c"]
            for k in range(len(tr1.t)):
                tt = tr1.t[k]
                if tt <= d["t_c"]:
                    continue
                th1 = tr1.a[k]
                bxp, byp = px1 - n_["w"] * math.cos(th1), FLOOR - n_["w"] * math.sin(th1)
                nx, ny = math.cos(th1), math.sin(th1)
                f = lambda a: (px_i + d["h"] * math.sin(a) - bxp) * nx + (FLOOR - d["h"] * math.cos(a) - byp) * ny
                a0, a1 = lo_a, math.radians(88)
                if f(a1) < 0:
                    a_s = a1
                else:
                    for _ in range(30):
                        am = 0.5 * (a0 + a1)
                        if f(am) < 0:
                            a0 = am
                        else:
                            a1 = am
                    a_s = a1
                lo_a = max(lo_a, a_s)
                if k % 4 == 0:
                    d["track"].add(tt, d["x"], FLOOR, lo_a)
        last = self.doms[-1]
        # --- 4. le levier : le grand domino tombe sur son bout gauche
        self.step_mark(t, 3)
        self.marks_d = {3: t}
        th = last["th_c"]
        tipx = last["x"] + last["w"] / 2 + last["h"] * math.sin(th) - last["w"] * (1 - math.cos(th))
        tipy = FLOOR - last["h"] * math.cos(th)
        self.lev_L = 150.0
        self.lev_piv = (tipx + self.lev_L * math.cos(0.32) + 4, tipy + 6 + self.lev_L * math.sin(0.32))
        lev = tr["lever"] = Track(0, 0, 0.32)
        lev.add(t, 0, 0, 0.32)
        for k in range(1, 30):
            lev.add(t + k * DT, 0, 0, 0.32 - 0.64 * min(1.0, k * DT / 0.1))
        last["track"].add(t + 0.1, last["x"], FLOOR, th + 0.05)
        px, py = self.lev_piv
        bx0 = px + self.lev_L * math.cos(0.32)
        by0 = py + self.lev_L * math.sin(0.32) - RB - 9
        B = tr["B"] = Track(bx0, by0)
        B.add(t, bx0, by0)
        bx1 = px + self.lev_L * math.cos(0.32)
        by1 = py - self.lev_L * math.sin(0.32) - RB - 9
        t += 0.1
        B.add(t, bx1, by1)
        self.focus_segs.append((t - 0.4, "B"))
        # --- 5. la poulie : la bille B tombe dans le seau, le seau descend, la plateforme monte
        vx, vy = 430.0, -2620.0
        self.pul_y = -380.0
        self.bucket_top0 = self.pul_y + 120
        t_up = hit_time(by1, vy, self.bucket_top0 - 30)
        x_land = bx1 + vx * t_up
        self.pul_x = x_land + 70
        t, x, y, vx, vy, ra = fly(B, t, bx1, by1, vx, vy, lambda x, y, vx, vy: vy > 0 and y >= self.bucket_top0 + 20, spin=5)
        self.step_mark(t, 4)
        self.elev_t0 = t
        self.focus_segs.append((t, "plat"))
        bucket = tr["bucket"] = Track(0, self.bucket_top0, 0)
        plat = tr["plat"] = Track(0, FLOOR - 20, 0)
        acc, vv, dist = 0.0, 0.0, 0.0
        rise = (FLOOR - 20) - (self.pul_y + 170)
        tt = t
        bucket.add(tt, 0, self.bucket_top0); plat.add(tt, 0, FLOOR - 20)
        C = tr["C"] = Track(self.pul_x + 70, FLOOR - 20 - RB)
        while dist < rise:
            vv += 205.0 * DT
            dist += vv * DT
            tt += DT
            bucket.add(tt, 0, self.bucket_top0 + min(dist, rise)); plat.add(tt, 0, FLOOR - 20 - min(dist, rise))
            B.add(tt, self.pul_x - 70, self.bucket_top0 + min(dist, rise) + 40)
            C.add(tt, self.pul_x + 70, FLOOR - 20 - min(dist, rise) - RB)
        t = tt
        # --- 6. le grand huit : la plateforme bute en haut, la bille C part sur la piste avec un looping
        self.step_mark(t, 5)
        self.focus_segs.append((t, "C"))
        cx0, cy0 = self.pul_x + 70, FLOOR - 20 - rise - RB
        pts, ang = path(cx0, cy0, 0.0, [("s", 60), ("a", math.radians(40), 120), ("s", 700), ("a", math.radians(-40), 260),
                                        ("s", 120), ("a", -2 * math.pi, 150), ("s", 160), ("a", math.radians(-24), 220), ("s", 40)])
        self.coaster = pts
        t0c = t
        t, v, ang, ra = roll(C, pts, t, 120.0, mu=0.05, c=10.0)
        # le début du looping : le moment où la bille passe le point le plus bas avant de monter
        lowest = max(range(len(C.t)), key=lambda k: C.y[k] if C.t[k] >= t0c else -1e9)
        self.loop_t0 = C.t[lowest] - 0.25
        # le saut par-dessus le vide, et la réception sur la suite de la piste
        vx, vy = math.cos(ang) * v, math.sin(ang) * v
        x, y = pts[-1]
        y_rx = y + 140
        t, x, y, vx, vy, ra = fly(C, t, x, y, vx, vy, lambda xx, yy, a, b: b > 0 and yy >= y_rx, ra=ra, spin=vx / RB)
        self.gap = (pts[-1][0], x)
        self.jump_t1 = t
        ang2 = math.atan2(vy, vx)
        pts2, ang = path(x, y, ang2, [("a", math.radians(4) - ang2, 260), ("s", 380), ("a", math.radians(-4), 300), ("s", 200)])
        self.coaster2 = pts2
        t, v, ang, ra = roll(C, pts2, t, math.hypot(vx, vy) * 0.8, mu=0.12, c=30.0, roll_a=ra)
        v = min(v, 520.0)
        pts = pts2
        # --- 7. le pendule de Newton
        self.step_mark(t, 6)
        self.focus_segs.append((t, "cradle"))
        ex, ey = pts[-1]
        self.table_y = ey + RB
        self.cr_L = 230.0
        self.cr_x0 = ex + 2 * RB
        self.cr_bar = ey - self.cr_L
        cr = tr["cradle5"] = Track(0, 0, 0.0)
        cr1 = tr["cradle1"] = Track(0, 0, 0.0)
        # la bille C cogne la première, la cinquième part
        v5 = v * 0.92
        phi, om = 0.0, v5 / self.cr_L
        tt = t
        self.cat_hit = None
        self.cat_x = self.cr_x0 + 4 * 2 * RB + self.cr_L * math.sin(math.radians(30)) + RB + 6
        swings = 0
        while tt < t + 9.0:
            om += -(G / self.cr_L) * math.sin(phi) * DT
            om *= (1 - 0.15 * DT)
            phi += om * DT
            tt += DT
            if self.cat_hit is not None:
                # elle a frappé le cran : elle retombe et s'immobilise contre les autres
                phi = max(0.0, phi)
                om = -abs(om) * 0.35 if phi > 0.02 else 0.0
            cr.add(tt, 0, 0, max(0.0, phi))
            cr1.add(tt, 0, 0, 0.0)
            if self.cat_hit is None and phi >= math.radians(30):
                self.cat_hit = tt
                om = -abs(om) * 0.2
            if self.cat_hit is not None and tt > self.cat_hit + 1.5:
                break
        t = self.cat_hit
        # --- 8. la catapulte : la cinquième bille fait sauter le cran, le bras lance la bille D
        self.cat_piv = (self.cat_x + 40, self.table_y - 30)
        self.cat_len = 190.0
        cat = tr["cat"] = Track(0, 0, 0.0)
        cpx, cpy = self.cat_piv
        cup = lambda a: (cpx + math.cos(a) * self.cat_len - math.sin(a) * (RB + 10), cpy - math.sin(a) * self.cat_len - math.cos(a) * (RB + 10))
        dx0, dy0 = cup(0.0)
        D = tr["D"] = Track(dx0, dy0)
        cat.add(t, 0, 0, 0.0)
        D.add(t, dx0, dy0)
        a, om, tt = 0.0, 0.0, t
        released = None
        while a < math.radians(100):
            om += 260.0 * DT                     # le ressort
            a += om * DT
            tt += DT
            cat.add(tt, 0, 0, min(a, math.radians(100)))
            if released is None:
                D.add(tt, *cup(a))
                if a >= math.radians(30):
                    released = (tt, cup(a))
        tr_, (dx1, dy1) = released
        vx, vy = -1150.0, -1950.0
        self.ceil_y0 = CEIL + 140
        self.d_launch = tr_
        self.focus_segs.append((tr_ + 0.05, "D"))
        D.t = [x for x in D.t if x <= tr_]; D.x = D.x[:len(D.t)]; D.y = D.y[:len(D.t)]; D.a = D.a[:len(D.t)]
        t, x, y, vx, vy, ra = fly(D, tr_, dx1, dy1, vx, vy, lambda x, y, vx, vy: vy > 0 and y >= self.ceil_y0, spin=-8)
        # --- 9. le rail du plafond : tout le chemin du retour
        self.step_mark(t, 7)
        self.ceil_t0 = t + 0.4
        ang0 = math.atan2(vy, vx)
        self.switch_x = 790.0
        length = x - (self.switch_x + 2) - 200
        pts, ang = path(x, y, ang0, [("a", (math.pi - math.radians(5.0)) - ang0, 150), ("s", length)])
        self.ceiling = pts
        t, v, ang, ra = roll(D, pts, t, math.hypot(vx, vy) * 0.5, mu=0.03, c=6.0)
        # la butée au-dessus de l'interrupteur, puis la chute
        xe, ye = pts[-1]
        self.bumpers.append((xe - RB - 6, ye))
        t += 0.04
        D.add(t, xe, ye)
        self.step_mark(t, 8)
        self.drop_t0 = t
        self.focus_segs.append((t, "Ddrop"))
        btn_top = FLOOR - 22
        t, x, y, vx, vy, ra = fly(D, t, xe, ye, 0.0, 0.0, lambda x, y, vx, vy: y >= btn_top - RB, ra=ra)
        self.switch_x = x
        self.t_off = t
        D.add(t + 0.25, x + 30, FLOOR - RB)
        D.add(t + 0.9, x + 120, FLOOR - RB)
        # --- la fin : dans le noir, Bounce saute sur l'interrupteur et rallume
        self.focus_segs.append((t + 0.2, "bounce"))
        self.t_bounce_on = t + 2.8
        self.t_on = None
        self.T_total = self.t_bounce_on + 7.4

    def slow_windows(self):
        """Les ralentis : le grand domino qui frappe le levier, le looping et le saut, la
        chute sur l'interrupteur. (début, fin, facteur) en temps de simulation."""
        W = []
        last2 = self.doms[-2]["t_c"]
        W.append((last2 - 0.15, self.marks_d[3] + 0.35, 0.4))
        W.append((self.loop_t0, self.jump_t1 + 0.15, 0.4))
        W.append((self.t_off - 0.55, self.t_off + 0.25, 0.35))
        return W

    def tau_of(self, t):
        """Temps de vidéo d'un instant de simulation."""
        tau = t
        for (a, b, f) in self.slow:
            if t > a:
                tau += (min(t, b) - a) * (1.0 / f - 1.0)
        return tau

    def sim_of(self, tau):
        """Instant de simulation d'un temps de vidéo (inverse de tau_of)."""
        lo, hi = 0.0, tau
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if self.tau_of(mid) < tau:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    def slowmo(self, t):
        return any(a <= t <= b for (a, b, f) in self.slow)

    def zoom_at(self, t):
        """1 en temps normal ; pendant le retour par le plafond, la caméra recule jusqu'à
        montrer toute la pièce (le rail en haut, la machine déjà jouée en bas)."""
        if t < 2.2:
            k = min(1.0, t / 2.2)
            k = k * k * (3 - 2 * k)
            return 1.55 - 0.70 * k                         # l'ouverture : de Bounce en gros plan à toute la chambre
        if t < 5.4:
            k = (t - 2.2) / 3.2
            return 0.85 + 0.17 * k                         # puis un lent travelling avant
        if t < 6.0:
            return 1.02 - 0.02 * (t - 5.4) / 0.6
        if self.ceil_t0 is None:
            return 1.0
        t0, t1 = self.ceil_t0, self.drop_t0 - 0.6
        if t < t0 or t > t1 + 0.8:
            return 1.0
        k = min(1.0, (t - t0) / 0.9, (t1 + 0.8 - t) / 0.8)
        k = k * k * (3 - 2 * k)
        return 1.0 - 0.42 * k

    def make_camera(self):
        """La caméra suit le corps actif, lissée (amortissement critique)."""
        self.cam = Track(0, 0)
        cx, cy = 560.0, 1080.0
        vx = vy = 0.0
        t = 0.0
        w = 6.0
        while t < self.T_total + 1:
            Z = self.zoom_at(t)
            fx, fy = self.focus_at(t)
            if Z < 0.999 and self.ceil_t0 is not None and t >= self.ceil_t0:
                fy = (CEIL + FLOOR) / 2 + 40
            ax = w * w * (fx - cx) - 2 * w * vx
            ay = w * w * (fy - cy) - 2 * w * vy
            vx += ax * DT * 2; vy += ay * DT * 2
            cx += vx * DT * 2; cy += vy * DT * 2
            lo = CEIL + (SCREEN_CY - SCENE_TOP - 60) / Z
            hi = FLOOR - (self.H - SCREEN_CY - 430) / Z
            cy = max(lo, min(hi, cy)) if lo <= hi else (lo + hi) / 2
            self.cam.add(t, cx, cy, Z)
            t += DT * 2

    def focus_at(self, t):
        name = "bounce"
        for (t0, nm) in self.focus_segs:
            if t >= t0:
                name = nm
        tr = self.tracks
        if name in ("A", "B", "C", "D", "Ddrop"):
            x, y, _ = tr["D" if name == "Ddrop" else name].at(t)
            if name == "Ddrop":
                return x - 120, min(y, FLOOR - 430)
            if name == "D" and self.ceil_t0 is not None and t >= self.ceil_t0:
                return x - 260, y                  # le retour : la caméra recule, la machine défile dessous
            return x + 120, y
        if name == "dom":
            # le domino qui tombe en ce moment
            for d in self.doms:
                if d["t_c"] is not None and t < d["t_c"]:
                    return d["x"] + 200, FLOOR - max(260.0, d["h"] * 0.8)
            return self.doms[-1]["x"] + 300, FLOOR - 400
        if name == "plat":
            _, y, _ = tr["plat"].at(t)
            _, yb, _ = tr["bucket"].at(t)
            w = min(1.0, max(0.0, (t - self.elev_t0) / 2.2))
            w = w * w * (3 - 2 * w)
            return self.pul_x, (yb + 40) * (1 - w) + (0.55 * (y - 80) + 0.45 * 500.0) * w
        if name == "cradle":
            return self.cr_x0 + 330, self.table_y - 200
        if name == "bounce":
            cxr, cyr = 0.5 * (60.0 + self.switch_x) + 60, FLOOR - 430
            if t < 2.2:
                bx, by = self.bounce_pos(t)
                w = (t / 2.2) ** 2
                return bx * (1 - w) + cxr * w, (by - 60) * (1 - w) + cyr * w
            return cxr, cyr
        return 560.0, 1080.0

    def bounce_pos(self, t):
        """Bounce : la trajectoire préparée, puis des rebonds sur la bascule, puis le saut
        final vers l'interrupteur."""
        tr = self.tracks["bounce"]
        if t <= tr.t[-1]:
            x, y, _ = tr.at(t)
            return x, y
        x0, y0 = self.bounce_base
        if t < self.t_bounce_on - 0.9:
            period = 0.62 if t < 5.6 else 0.86
            t0b = self.bounce_t0 if t < 5.6 else 5.6
            u = ((t - t0b) % period) / period
            h = 340.0 if t < 5.6 else 230.0
            return x0, y0 - h * 4 * u * (1 - u)
        # le grand saut vers l'interrupteur
        t0 = self.t_bounce_on - 0.9
        if t < self.t_bounce_on:
            u = (t - t0) / 0.9
            x1, y1 = self.switch_x, FLOOR - 22 - R_BOUNCE
            return x0 + (x1 - x0) * u, y0 + (y1 - y0) * u - 420 * 4 * u * (1 - u)
        u = ((t - self.t_bounce_on) % 0.8) / 0.8
        return self.switch_x, FLOOR - 22 - R_BOUNCE - 160 * 4 * u * (1 - u)

    def bounce_landings(self):
        out = list(self.bounce_hits)
        t = self.bounce_t0
        while t + 0.62 < 5.6:
            t += 0.62
            out.append(t)
        t = 5.6
        while t < self.t_bounce_on - 0.9:
            t += 0.86
            if t < self.t_bounce_on - 0.9:
                out.append(t)
        t = self.t_bounce_on
        while t < self.T_total + 2:
            out.append(t)
            t += 0.8
        return out

    def lines_plan(self):
        m = dict((n, t) for (t, n) in self.marks)
        self.plan = [
            (0.0, "Bounce wants to turn off the light.", "title"),
            (0.1, "The switch was right there.", "there"),
            (0.2, "He built this instead.", "built"),
            (self.stairs_t + 0.1, "Stairs. Obviously.", "stairs"),
            (m[2] + 0.3, "Twenty eight dominoes.", "dom"),
            (self.doms[self.suspense]["track"].t[0] + 0.9, "Come on.", "come"),
            (m[4] + 0.6, "This part took him a week.", "week"),
            (m[5] + 0.4, "He never tested the loop.", "loop"),
            (self.jump_t1 + 0.05, "It works.", "works"),
            (m[7] + 0.6, "All the way back.", "back"),
            (self.drop_t0 - 2.4, "Almost there.", "almost"),
            (self.t_off - 0.5, "Here it comes.", "comes"),
            (self.t_off + 0.8, "Goodnight, Bounce.", "night"),
            (self.t_bounce_on + 1.0, "Tomorrow, a bigger machine.", "tomorrow"),
        ]
        # tout ce qui est préparé en temps de simulation passe en temps de vidéo (ralentis)
        self.plan = [(self.tau_of(tt), text, key) for (tt, text, key) in self.plan]
        self.plan_i = 0
        self.land = [self.tau_of(x) for x in self.bounce_landings()]
        self.land_i = 0

    # ------------------------------------------------------------------ déroulé
    def step(self, dt):
        self.t += dt
        evs = []
        while self.plan_i < len(self.plan) and self.plan[self.plan_i][0] <= self.t:
            tt, text, key = self.plan[self.plan_i]
            self.line(text, key, tt)
            self.plan_i += 1
        while self.land_i < len(self.land) and self.land[self.land_i] <= self.t:
            tl = self.sim_of(self.land[self.land_i])
            self.land_i += 1
            bx, by = self.bounce_pos(tl)
            cx, cy, _ = self.cam.at(tl)
            dist = math.hypot(bx - cx, by - cy)
            if dist < 650:
                evs.append(("hit", "floor"))
            else:
                evs.append(("hit", "far:%.2f" % max(0.3, min(0.85, 1.0 - dist / 5000.0))))
            self.hit_t = tl
            if self.t_on is None and abs(tl - self.t_bounce_on) < 0.03:
                self.t_on = tl
        ts = self.sim_of(self.t)
        if not self.payoff and ts >= self.T_total - 1.0:
            self.finish("ON")
        self.bx, self.by = self.bounce_pos(ts)
        return evs

    def snapshot(self):
        s = self.base_snap()
        ts = self.sim_of(self.t)
        s["ts"] = ts
        s["cam"] = self.cam.at(ts)
        return s

    def counter(self, s):
        return None

    def focus(self, s):
        return (300.0, 600.0, 900.0, 1300.0)

    # ------------------------------------------------------------------ dessin
    def lit(self, t):
        """1 : lampe allumée ; 0 : éteinte. Après le saut sur l'interrupteur, chacun de ses
        rebonds appuie dessus : allumé, éteint, allumé..."""
        if t < self.t_off:
            return 1.0
        if t < self.t_bounce_on:
            return 0.0
        k = int((t - self.t_bounce_on) / 0.8 + 1e-6)
        return 1.0 if k % 2 == 0 else 0.0

    def draw(self, dr, s, t_video, S):
        W, H = self.W, self.H
        t = s.get("ts", t_video)
        cx, cy, Z = s["cam"]
        P = lambda v: v * S
        Q = lambda v: v * S * Z
        X = lambda x: ((x - cx) * Z + W / 2) * S
        Y = lambda y: ((y - cy) * Z + SCREEN_CY) * S
        vis = lambda x0, x1: (x1 - cx) * Z + W / 2 > -100 and (x0 - cx) * Z + W / 2 < W + 100
        self.Zc = Z
        wall = (30, 30, 46)
        dr.rectangle([0, P(SCENE_TOP), P(W), P(H)], fill=wall)
        # plafond, sol, plinthe, et des repères au mur pour sentir le déplacement
        dr.rectangle([0, Y(CEIL - 400), P(W), Y(CEIL)], fill=(20, 20, 30))
        dr.rectangle([0, Y(FLOOR), P(W), Y(FLOOR + 600)], fill=(56, 40, 34))
        dr.rectangle([0, Y(FLOOR - 24), P(W), Y(FLOOR)], fill=(40, 38, 56))
        self.decor(dr, X, Y, Q, t, vis)
        x = math.floor((cx - W / Z) / 320) * 320
        while x < cx + W / Z:
            if x > 1150:
                dr.rectangle([X(x), Y(CEIL), X(x + 6), Y(FLOOR - 24)], fill=(34, 34, 52))
            dr.rectangle([X(x), Y(FLOOR), X(x + 160), Y(FLOOR + 12)], fill=(62, 46, 38))
            x += 320
        self.machine(dr, X, Y, Q, t, vis, S * Z)
        bx, by = self.bounce_pos(t)
        if self.lit(t) < 0.5:
            base.HERO["expr"] = "calm"
        base.ball(dr, X(bx), Y(by), Q(self.R))
        # la nuit : tout s'assombrit sauf la lune et Bounce
        if self.lit(t) < 0.5:
            from PIL import Image
            box = (0, int(P(SCENE_TOP)), int(P(W)), int(P(H)))
            reg = dr._image.crop(box)
            dark = Image.blend(reg, Image.new("RGB", reg.size, (2, 2, 6)), 0.78)
            dr._image.paste(dark, box[:2])
            base.ball(dr, X(bx), Y(by), Q(self.R))
        dr.rectangle([0, 0, P(W), P(SCENE_TOP) - 1], fill=tuple(self.cfg["bg_color"]))
        self.inset(dr, P, t, S)
        if self.slowmo(t):
            f = base.font(int(40 * S))
            dr.text((P(W - 60), P(SCENE_TOP + 46)), "SLOW MOTION", fill=(255, 205, 90), anchor="rm", font=f, stroke_width=int(4 * S), stroke_fill=(10, 10, 14))
        self.hud(dr, P, t_video, S)

    def inset(self, dr, P, t, S):
        """Pendant que la machine tourne, un coin de l'image montre Bounce dans sa chambre,
        qui rebondit à côté de l'interrupteur."""
        if t < 5.7 or t > self.drop_t0 - 0.2:
            return
        if self.d_launch - 0.4 <= t <= self.ceil_t0 + 0.6:
            return                                  # la bille D vole par là : on ne la cache pas
        k = min(1.0, (t - 5.7) / 0.3, (self.drop_t0 - 0.2 - t) / 0.3)
        if k <= 0:
            return
        x0, y0, w, h = 36.0, SCENE_TOP + 30, 300.0, 300.0
        dr.rounded_rectangle([P(x0 - 6), P(y0 - 6), P(x0 + w + 6), P(y0 + h + 6)], radius=int(P(22)), fill=(235, 235, 245))
        dr.rounded_rectangle([P(x0), P(y0), P(x0 + w), P(y0 + h)], radius=int(P(18)), fill=(30, 30, 46))
        fl = y0 + h - 46
        dr.rectangle([P(x0), P(fl), P(x0 + w), P(y0 + h - 8)], fill=(56, 40, 34))
        # l'interrupteur, juste là
        sx = x0 + 215
        dr.rectangle([P(sx - 36), P(fl - 12), P(sx + 36), P(fl)], fill=(60, 60, 70))
        dr.rectangle([P(sx - 22), P(fl - 22), P(sx + 22), P(fl - 12)], fill=(90, 220, 120))
        f = base.font(int(22 * S))
        dr.text((P(sx), P(fl - 44)), "SWITCH", fill=(235, 235, 245), anchor="mm", font=f)
        # Bounce, qui rebondit à côté
        bx, by = self.bounce_pos(t)
        base_y = self.bounce_base[1]
        hgt = max(0.0, base_y - by)
        r = 34.0
        cy = fl - r - hgt * 0.42
        expr = base.HERO["expr"]
        sus = self.doms[self.suspense]
        if sus["track"].t and sus["track"].t[0] <= t <= sus["t_c"]:
            base.HERO["expr"] = "shock"
        elif self.loop_t0 <= t <= self.jump_t1:
            base.HERO["expr"] = "shock"
        else:
            base.HERO["expr"] = "calm"
        base.ball(dr, P(x0 + 90), P(cy), P(r))
        base.HERO["expr"] = expr
        f2 = base.font(int(24 * S))
        dr.text((P(x0 + 16), P(y0 + 22)), "BOUNCE CAM", fill=(240, 80, 80), anchor="lm", font=f2)
        circle(dr, P(x0 + w - 24), P(y0 + 22), P(7), (240, 60, 60))

    def hud(self, dr, P, t, S):
        if t < self.cfg["hook_text_s"]:
            return
        n = 0
        for (tm, k) in self.marks:
            if t >= tm:
                n = k
        if n == 0 or t > self.t_off + 0.6:
            return
        f = base.font(int(60 * S))
        txt = f"STEP {n} / 8"
        dr.text((P(self.W / 2), P(300)), txt, fill=(230, 230, 240), anchor="mm", font=f)
        bw = 520
        x0 = self.W / 2 - bw / 2
        dr.rectangle([P(x0), P(360), P(x0 + bw), P(374)], fill=(60, 60, 78))
        dr.rectangle([P(x0), P(360), P(x0 + bw * n / 8), P(374)], fill=(255, 205, 90))

    def decor(self, dr, X, Y, P, t, vis):
        lit = self.lit(t)
        # la chambre : fenêtre, lune, lit, table de nuit, lampe
        if vis(0, 1200):
            dr.rectangle([X(560), Y(700), X(900), Y(1060)], fill=(16, 22, 44))
            circle(dr, X(800), Y(800), P(40), (226, 228, 236))
            dr.rectangle([X(726), Y(700), X(734), Y(1060)], fill=(46, 46, 66)); dr.rectangle([X(560), Y(876), X(900), Y(884)], fill=(46, 46, 66))
            dr.rectangle([X(120), Y(1330), X(440), Y(FLOOR)], fill=(70, 56, 80))
            dr.rectangle([X(110), Y(1300), X(450), Y(1345)], fill=(200, 200, 215))
            dr.rectangle([X(110), Y(1180), X(140), Y(FLOOR)], fill=(90, 66, 50))
            dr.rectangle([X(20), Y(1380), X(100), Y(FLOOR)], fill=(90, 66, 50))
            if lit > 0.5:
                glow(dr, P, X(60) / P(1), Y(1240) / P(1), 260, (255, 205, 140), (30, 30, 46), 0.42, rings=10)
            dr.polygon([(X(30), Y(1250)), (X(90), Y(1250)), (X(76), Y(1205)), (X(44), Y(1205))], fill=(240, 210, 140) if lit > 0.5 else (90, 80, 70))
            dr.rectangle([X(57), Y(1250), X(63), Y(1380)], fill=(80, 70, 60))
        # des étagères, des cadres, des cartons le long du chemin : on sent la distance
        x = 1300.0
        k = 0
        while x < 9000:
            if vis(x - 200, x + 400):
                if k % 3 == 0:
                    dr.rectangle([X(x), Y(900), X(x + 260), Y(912)], fill=(70, 56, 46))
                    for j in range(5):
                        dr.rectangle([X(x + 20 + j * 46), Y(900 - 60 - (j % 2) * 18), X(x + 52 + j * 46), Y(900)], fill=[(110, 60, 70), (60, 90, 120), (120, 110, 60)][j % 3])
                elif k % 3 == 1:
                    dr.rectangle([X(x), Y(300), X(x + 200), Y(450)], fill=(46, 46, 66))
                    dr.rectangle([X(x + 14), Y(314), X(x + 186), Y(436)], fill=(36, 56, 70))
            x += 900
            k += 1

    def machine(self, dr, X, Y, P, t, vis, S):
        tr = self.tracks
        # l'interrupteur au sol, à un mètre de Bounce
        swx = self.switch_x
        on = self.lit(t) > 0.5
        dr.rectangle([X(swx - 70), Y(FLOOR - 20), X(swx + 70), Y(FLOOR)], fill=(60, 60, 70))
        dr.rectangle([X(swx - 44), Y(FLOOR - 36), X(swx + 44), Y(FLOOR - 20)], fill=(90, 220, 120) if on else (200, 60, 60))
        if t < 6.0 or t > self.t_off - 0.6:
            f = base.font(int(34 * S))
            dr.text((X(swx + 90), Y(FLOOR - 70)), "LIGHT SWITCH", fill=(235, 235, 245), anchor="lm", font=f, stroke_width=int(P(3)), stroke_fill=(10, 10, 14))
        # la bascule
        a = tr["seesaw"].at(t)[2]
        sx, sy = self.ss_piv
        dr.polygon([(X(sx - 30), Y(FLOOR)), (X(sx + 30), Y(FLOOR)), (X(sx), Y(sy))], fill=(90, 70, 60))
        self.plank(dr, X, Y, P, sx, sy, a, self.ss_L, 14, WOOD)
        # supports : poteaux du zigzag et de la piste, tiges du rail du plafond (derrière les rails)
        for pts in self.rails:
            x0p, y0p = pts[len(pts) // 2]
            if vis(x0p - 10, x0p + 10):
                dr.rectangle([X(x0p - 4), Y(y0p + RB + 6), X(x0p + 4), Y(FLOOR)], fill=(52, 52, 68))
        for k in range(0, len(self.coaster2), 40):
            x0p, y0p = self.coaster2[k]
            if vis(x0p - 10, x0p + 10):
                dr.rectangle([X(x0p - 4), Y(y0p + RB + 6), X(x0p + 4), Y(FLOOR)], fill=(52, 52, 68))
        for k in range(0, len(self.ceiling), 90):
            x0p, y0p = self.ceiling[k]
            if vis(x0p - 10, x0p + 10):
                dr.rectangle([X(x0p - 3), Y(CEIL), X(x0p + 3), Y(y0p + RB)], fill=(52, 52, 68))
        # les rails et les butées
        for pts in self.rails + [self.coaster, self.coaster2, self.ceiling]:
            xs = [p[0] for p in pts]
            if vis(min(xs), max(xs)):
                self.rail(dr, X, Y, P, pts)
        for (bxp, byp) in self.bumpers:
            if vis(bxp - 20, bxp + 20):
                dr.rectangle([X(bxp - 6), Y(byp - 60), X(bxp + 6), Y(byp + RB + 10)], fill=(170, 120, 70))
        # l'escalier
        sx0, sy0, sw, sh, ns = self.stairs
        if vis(sx0 - 20, sx0 + ns * sw + 20):
            for k in range(ns):
                dr.rectangle([X(sx0 + k * sw), Y(sy0 + k * sh), X(sx0 + (k + 1) * sw), Y(FLOOR)], fill=dim(WOOD, 0.9 - 0.04 * k))
                dr.rectangle([X(sx0 + k * sw), Y(sy0 + k * sh), X(sx0 + (k + 1) * sw), Y(sy0 + k * sh + 8)], fill=mix(WOOD, (255, 230, 190), 0.25))
        # les dominos
        for i, d in enumerate(self.doms):
            if not vis(d["x"] - 20, d["x"] + d["h"] + 40):
                continue
            th = d["track"].at(t)[2]
            col = DOM_COLS[i % len(DOM_COLS)]
            self.domino(dr, X, Y, d["x"], d["h"], d["w"], th, col)
        # le levier
        lx, ly = self.lev_piv
        if vis(lx - 200, lx + 200):
            dr.rectangle([X(lx - 14), Y(ly), X(lx + 14), Y(FLOOR)], fill=(80, 70, 70))
            self.plank(dr, X, Y, P, lx, ly, tr["lever"].at(t)[2], self.lev_L, 14, WOOD)
        # la poulie, le seau, la plateforme
        px = self.pul_x
        if vis(px - 200, px + 200):
            by = tr["bucket"].at(t)[1]
            py = tr["plat"].at(t)[1]
            dr.rectangle([X(px - 6), Y(CEIL), X(px + 6), Y(self.pul_y)], fill=(80, 80, 96))
            circle(dr, X(px), Y(self.pul_y), P(70), (110, 110, 130))
            circle(dr, X(px), Y(self.pul_y), P(18), (60, 60, 70))
            dr.line([(X(px - 70), Y(self.pul_y)), (X(px - 70), Y(by))], fill=(200, 200, 210), width=max(1, int(P(3))))
            dr.line([(X(px + 70), Y(self.pul_y)), (X(px + 70), Y(py - 90))], fill=(200, 200, 210), width=max(1, int(P(3))))
            dr.line([(X(px + 70), Y(py - 90)), (X(px + 22), Y(py))], fill=(200, 200, 210), width=max(1, int(P(3))))
            dr.line([(X(px + 70), Y(py - 90)), (X(px + 138), Y(py))], fill=(200, 200, 210), width=max(1, int(P(3))))
            dr.polygon([(X(px - 115), Y(by)), (X(px - 25), Y(by)), (X(px - 35), Y(by + 80)), (X(px - 105), Y(by + 80))], fill=(150, 100, 70))
            dr.rectangle([X(px + 20), Y(py), X(px + 140), Y(py + 14)], fill=(150, 150, 160))
        # le pendule de Newton
        if vis(self.cr_x0 - 100, self.cr_x0 + 600):
            ty = self.table_y
            dr.rectangle([X(self.cr_x0 - 120), Y(ty), X(self.cat_x + 300), Y(ty + 22)], fill=WOOD)
            for xx in (self.cr_x0 - 100, self.cat_x + 270):
                dr.rectangle([X(xx), Y(ty + 22), X(xx + 18), Y(FLOOR)], fill=dim(WOOD, 0.8))
            bar_y = self.cr_bar
            dr.rectangle([X(self.cr_x0 - 40), Y(bar_y - 8), X(self.cr_x0 + 8 * RB + 40), Y(bar_y)], fill=(170, 170, 185))
            for xx in (self.cr_x0 - 40, self.cr_x0 + 8 * RB + 34):
                dr.rectangle([X(xx), Y(bar_y), X(xx + 6), Y(ty)], fill=(170, 170, 185))
            p1 = tr["cradle1"].at(t)[2]
            p5 = tr["cradle5"].at(t)[2]
            for k in range(5):
                ax = self.cr_x0 + k * 2 * RB
                phi = p1 if k == 0 else (p5 if k == 4 else 0.0)
                bxp = ax + self.cr_L * math.sin(phi)
                byp = bar_y + self.cr_L * math.cos(phi)
                dr.line([(X(ax), Y(bar_y)), (X(bxp), Y(byp))], fill=(200, 200, 210), width=max(1, int(P(2))))
                circle(dr, X(bxp), Y(byp), P(RB), (200, 205, 215))
            # la catapulte
            ca = tr["cat"].at(t)[2]
            cpx, cpy = self.cat_piv
            dr.polygon([(X(cpx - 30), Y(ty)), (X(cpx + 30), Y(ty)), (X(cpx), Y(cpy))], fill=(90, 70, 60))
            ex, ey = cpx + math.cos(ca) * self.cat_len, cpy - math.sin(ca) * self.cat_len
            dr.line([(X(cpx), Y(cpy)), (X(ex), Y(ey))], fill=WOOD, width=max(1, int(P(14))))
            dr.ellipse([X(ex - 30), Y(ey - 18), X(ex + 30), Y(ey + 6)], fill=dim(WOOD, 0.8))
            if ca < 0.05:
                dr.rectangle([X(self.cat_x - 4), Y(ty - 70), X(self.cat_x + 4), Y(ty)], fill=(220, 80, 80))
        # les billes
        Z = getattr(self, "Zc", 1.0)
        for name in ("A", "B", "C", "D"):
            x, y, ra = tr[name].at(t)
            if vis(x - 40, x + 40):
                self.marble(dr, X, Y, P, x, y, ra, BALL_COLS[name], grow=1.0 / Z if name == "D" else 1.0)

    def plank(self, dr, X, Y, P, cx, cy, a, L, th, col):
        ca, sa = math.cos(a), math.sin(a)
        pts = []
        for (dx, dy) in ((-L, -th / 2), (L, -th / 2), (L, th / 2), (-L, th / 2)):
            pts.append((X(cx + dx * ca - dy * sa), Y(cy + dx * sa + dy * ca)))
        dr.polygon(pts, fill=col)

    def rail(self, dr, X, Y, P, pts):
        # la surface est sous le centre de la bille, décalée d'un rayon selon la normale
        # la surface est du côté droit du sens de marche (sous la bille, à l'extérieur d'un looping) ;
        # pour un rail parcouru vers la gauche, on retourne la normale
        sign = 1.0 if pts[-1][0] >= pts[0][0] else -1.0
        surf = []
        for i in range(0, len(pts) - 1, 2):
            (x0, y0), (x1, y1) = pts[i], pts[min(i + 1, len(pts) - 1)]
            L = math.hypot(x1 - x0, y1 - y0) or 1.0
            nx, ny = -(y1 - y0) / L * sign, (x1 - x0) / L * sign
            surf.append((X(x0 + nx * (RB + 4)), Y(y0 + ny * (RB + 4))))
        if len(surf) > 1:
            dr.line(surf, fill=(70, 52, 38), width=max(1, int(P(16))), joint="curve")
            dr.line(surf, fill=(196, 150, 100), width=max(1, int(P(9))), joint="curve")

    def domino(self, dr, X, Y, x, h, w, th, col):
        px, py = x + w / 2, FLOOR
        ca, sa = math.cos(th), math.sin(th)
        corners = [(-w, 0), (0, 0), (0, -h), (-w, -h)]
        pts = [(X(px + dx * ca - dy * sa), Y(py + dx * sa + dy * ca)) for (dx, dy) in corners]
        dr.polygon(pts, fill=col)

    def marble(self, dr, X, Y, P, x, y, ra, col, grow=1.0):
        P0 = P
        P = lambda v: P0(v * grow)
        circle(dr, X(x), Y(y), P(RB), col)
        circle(dr, X(x + math.cos(ra) * RB * 0.55), Y(y + math.sin(ra) * RB * 0.55), P(RB * 0.28), dim(col, 0.6))
        circle(dr, X(x - RB * 0.35), Y(y - RB * 0.35), P(RB * 0.22), mix(col, (255, 255, 255), 0.6))


DEFAULTS = {
    "ball_r": R_BOUNCE, "gravity": G,
    "chapter_max_s": 90.0,
    "hook_text_s": 2.6,
    "hook_narrator": True,
    "sub_y": 0.85, "watermark_y": 0.94, "end_hold_s": 2.0, "narr_tail_s": 0.3, "narr_gap_s": 0.25,
}


class MachineChapter(Machine):
    pass


CHAPTERS = [(MachineChapter, {})]


class Sim(StorySim):
    def __init__(self, cfg, rng):
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
