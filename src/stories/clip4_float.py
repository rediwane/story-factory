EXPR = {
    "serene": {"eyes": ("closed", "closed"), "brow": None, "mouth": "smile"},
    "calm": {"eyes": ("closed", "closed"), "brow": None, "mouth": "flat"},
    "slit": {"eyes": ("slit", "closed"), "brow": "V", "mouth": "flat"},
    "squint": {"eyes": ("squint", "squint"), "brow": "tilt", "mouth": "frown"},
    "squint_flat": {"eyes": ("squint", "squint"), "brow": "tilt", "mouth": "flat"},
    "wide": {"eyes": ("wide", "wide"), "brow": "up", "mouth": "csmile"},
    "wide_o": {"eyes": ("wide", "wide"), "brow": "up", "mouth": "o"},
    "wide_flat": {"eyes": ("wide", "wide"), "brow": "up", "mouth": "flat"},
    "glacial": {"eyes": ("lid", "lid"), "brow": "flat", "mouth": "flat"},
    "slit_door": {"eyes": ("slit", "closed"), "brow": "V", "mouth": "flat"},
}


def draw_float(dr, V, x, y, a, expr, look=(0.0, 0.0), mouth=0.0, nod=0.0, foam=0.0):
    """Float, d'après la référence du fan : disque #00CB80, anneau épais #007949 (un quart
    du rayon), deux yeux en « Y » en miroir (un trait vertical, un cil en diagonale vers
    l'extérieur et le haut), un petit sourire en U. Toutes les expressions gardent ce trait
    noir épais et arrondi."""
    r = RF
    dr.ellipse(V.box(x - r, y - r, x + r, y + r), fill=F_RING)
    ri = r * 0.735
    dr.ellipse(V.box(x - ri, y - ri, x + ri, y + ri), fill=F_IN)
    ca, sa = math.cos(a), math.sin(a)
    dy0 = nod

    def P(u, v):
        v = v + dy0
        return V.X(x + (u * ca - v * sa) * r), V.Y(y + (u * sa + v * ca) * r)

    wst = 0.072

    def stroke(pts, w=wst, col=INK):
        q = [P(u, v) for u, v in pts]
        lw = max(1, int(V.L(w * r)))
        dr.line(q, fill=col, width=lw, joint="curve")
        rr = V.L(w * r) / 2
        for (qx, qy) in (q[0], q[-1]):
            dr.ellipse([qx - rr, qy - rr, qx + rr, qy + rr], fill=col)

    def blob(u, v, ru, rv, col, n=20):
        dr.polygon([P(u + ru * math.cos(k * 2 * math.pi / n), v + rv * math.sin(k * 2 * math.pi / n)) for k in range(n)], fill=col)

    def arc_pts(u, v, ru, rv, a0, a1, n=10):
        return [(u + ru * math.cos(a0 + (a1 - a0) * k / n), v + rv * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]

    lx, ly = look
    for side, state in zip((-1, 1), expr["eyes"]):
        ex = 0.197 * side
        if state == "closed":
            stroke([(ex, -0.325), (ex, 0.02)])
            stroke([(0.19 * side, -0.20), (0.40 * side, -0.315)])
            continue
        cy = -0.15
        if state == "wide":
            ru, rv, top, bot = 0.13, 0.18, -1.0, 1.0
        elif state == "squint":
            ru, rv, top, bot = 0.135, 0.16, -0.4, 0.55
        elif state == "slit":
            ru, rv, top, bot = 0.135, 0.16, 0.0, 1.0
        else:  # "lid" : paupière lourde, regard glacial
            ru, rv, top, bot = 0.135, 0.16, -0.2, 1.0
        # le blanc visible entre les paupières
        pts = []
        for k in range(25):
            th = math.pi * k / 24
            u = ex + ru * math.cos(th + math.pi)
            vv = rv * math.sin(th + math.pi)
            pts.append((u, cy + max(vv, top * rv)))
        for k in range(25):
            th = math.pi * k / 24
            u = ex + ru * math.cos(th)
            vv = rv * math.sin(th)
            pts.append((u, cy + min(vv, bot * rv)))
        dr.polygon([P(u, v) for u, v in pts], fill=EYE_W)
        # la pupille, qui regarde
        pr = 0.062 if state != "wide" else 0.07
        pu = ex + lx * (ru - pr) * 0.85
        pv = cy + ly * (rv - pr) * 0.6
        lo, hi = cy + top * rv + pr * 0.4, cy + bot * rv - pr * 0.4
        if lo < hi:
            pv = max(lo, min(hi, pv))
        blob(pu, pv, pr, pr, INK)
        # ce qui dépasse des paupières est recouvert de peau
        if top > -1.0:
            blob(ex, cy + top * rv - 0.12, ru + 0.03, 0.12, F_IN)
        if bot < 1.0:
            blob(ex, cy + bot * rv + 0.12, ru + 0.03, 0.12, F_IN)
        # les traits : paupières et contour, dans le trait de la référence
        if top > -1.0:
            stroke([(ex - ru, cy + top * rv), (ex + ru, cy + top * rv)])
        else:
            stroke(arc_pts(ex, cy, ru, rv, math.pi, 2 * math.pi), w=0.055)
        if bot < 1.0:
            # la paupière du bas, une courbe fine qui remonte le blanc
            stroke(arc_pts(ex, cy + bot * rv - 0.03, ru * 0.85, 0.05, 0.15 * math.pi, 0.85 * math.pi, 8), w=0.045)
        else:
            stroke(arc_pts(ex, cy, ru, rv, 0, math.pi), w=0.055)
        # le cil de la référence, du coin extérieur vers le haut
        yt = cy + (top * rv if top > -1.0 else -rv * 0.6)
        stroke([(ex + side * ru * 0.9, yt), (ex + side * (ru + 0.12), yt - 0.08)])
    # les sourcils
    b = expr["brow"]
    if b == "V":
        for side in (-1, 1):
            stroke([(0.07 * side, -0.37), (0.30 * side, -0.48)])
    elif b == "tilt":
        for side in (-1, 1):
            stroke([(0.06 * side, -0.35), (0.31 * side, -0.52)])
    elif b == "up":
        for side in (-1, 1):
            stroke(arc_pts(0.2 * side, -0.38, 0.12, 0.06, math.pi * 1.1, math.pi * 1.9, 8))
    elif b == "flat":
        for side in (-1, 1):
            stroke([(0.09 * side, -0.33), (0.31 * side, -0.33)])
    # la bouche
    mo = expr["mouth"]
    m = max(0.0, min(1.0, mouth))
    if mo in ("smile", "csmile"):
        rx = 0.165 if mo == "smile" else 0.19
        ry = 0.145 if mo == "smile" else 0.12
        if m > 0.05:
            pts = arc_pts(0.0, 0.18, rx, ry + 0.05 * m, 0.0, math.pi, 12)
            dr.polygon([P(u, v) for u, v in pts], fill=(30, 40, 34))
        stroke(arc_pts(0.0, 0.18, rx, ry + 0.05 * m, 0.0, math.pi, 12))
    elif mo == "flat":
        if m > 0.05:
            blob(0.0, 0.25, 0.12, 0.05 * m + 0.01, (30, 40, 34))
        stroke([(-0.13, 0.25 - 0.02 * m), (0.13, 0.25 - 0.02 * m)])
    elif mo == "frown":
        if m > 0.05:
            blob(0.0, 0.27, 0.11, 0.05 * m + 0.01, (30, 40, 34))
        stroke(arc_pts(0.0, 0.33, 0.15, 0.09, math.pi * 1.0, math.pi * 2.0, 10))
    elif mo == "o":
        blob(0.0, 0.27, 0.07, 0.09 + 0.03 * m, INK)
    if foam > 0:
        k = foam
        for (u, v, rr) in ((-0.35, -0.85, 0.28), (0.0, -0.98, 0.34), (0.35, -0.86, 0.27), (-0.15, -1.15, 0.2),
                           (0.2, -1.12, 0.22)):
            blob(u, v + (1 - k) * 0.3, rr * k, rr * k * 0.85, FOAMC)


