"""Planche de personnages 'faits main' : trait qui tremble, visage griffonne, grain papier."""
import sys, math, random, io
import cairosvg
import numpy as np
from PIL import Image, ImageFilter

INK = "#2b2a33"
rnd = random.Random(7)

def jit(pts, amp=3.0, seed=0):
    r = random.Random(seed)
    return [(x + r.uniform(-amp, amp), y + r.uniform(-amp, amp)) for x, y in pts]

def sketch_path(pts, w=7, col=INK, closed=True, passes=2, amp=3.0, seed=0, fill=None):
    """un trace a main levee : plusieurs passes legerement decalees."""
    o = ""
    if fill:
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in jit(pts, amp * 0.6, seed + 99)) + (" Z" if closed else "")
        o += f'<path d="{d}" fill="{fill}" stroke="none"/>'
    for p in range(passes):
        q = jit(pts, amp, seed + p)
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in q) + (" Z" if closed else "")
        o += f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{w * (0.8 + 0.4 * p / max(1, passes - 1)):.1f}" stroke-linecap="round" stroke-linejoin="round" opacity="{0.9 if p == 0 else 0.5}"/>'
    return o

def ellipse_pts(cx, cy, rx, ry, n=40, rot=0):
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        x, y = rx * math.cos(a), ry * math.sin(a)
        c, s = math.cos(rot), math.sin(rot)
        out.append((cx + x * c - y * s, cy + x * s + y * c))
    return out

def rect_pts(x, y, w, h, n=8):
    pts = []
    for (x0, y0), (x1, y1) in [((x, y), (x + w, y)), ((x + w, y), (x + w, y + h)), ((x + w, y + h), (x, y + h)), ((x, y + h), (x, y))]:
        for i in range(n): u = i / n; pts.append((x0 + (x1 - x0) * u, y0 + (y1 - y0) * u))
    return pts

def hatch(x, y, w, h, seed=0, n=14, col=INK, op=.25):
    r = random.Random(seed); o = ""
    for i in range(n):
        xx = x + w * i / n + r.uniform(-4, 4)
        o += f'<path d="M{xx:.0f},{y + r.uniform(0, 10):.0f} L{xx + w * 0.35:.0f},{y + h + r.uniform(-10, 0):.0f}" stroke="{col}" stroke-width="2.5" opacity="{op}"/>'
    return o

def face(cx, cy, s=1.0, mood="flat", seed=0):
    """visage griffonne : deux points inegaux, un trait de bouche, un sourcil."""
    r = random.Random(seed); o = ""
    ex = 28 * s; ey = r.uniform(-4, 4)
    o += f'<ellipse cx="{cx - ex:.0f}" cy="{cy + ey:.0f}" rx="{5 * s:.1f}" ry="{6 * s:.1f}" fill="{INK}"/>'
    o += f'<ellipse cx="{cx + ex + r.uniform(0, 6):.0f}" cy="{cy - ey:.0f}" rx="{4 * s:.1f}" ry="{7 * s:.1f}" fill="{INK}"/>'
    if mood == "surprised":
        o += sketch_path(ellipse_pts(cx - ex, cy + ey, 11 * s, 13 * s, 20), 3, INK, True, 2, 1.5, seed + 1)
        o += sketch_path(ellipse_pts(cx + ex, cy - ey, 11 * s, 13 * s, 20), 3, INK, True, 2, 1.5, seed + 2)
        o += sketch_path(ellipse_pts(cx + 4, cy + 44 * s, 10 * s, 14 * s, 20), 3.5, INK, True, 2, 1.5, seed + 3, fill="#3a3540")
        o += sketch_path([(cx - ex - 14, cy - 28 * s), (cx - ex + 14, cy - 34 * s)], 3.5, INK, False, 2, 1.5, seed + 4)
        o += sketch_path([(cx + ex - 14, cy - 36 * s), (cx + ex + 14, cy - 30 * s)], 3.5, INK, False, 2, 1.5, seed + 5)
    else:
        o += sketch_path([(cx - 16 * s, cy + 40 * s), (cx + 14 * s, cy + 42 * s)], 3.5, INK, False, 2, 1.5, seed + 3)
        o += sketch_path([(cx - ex - 14, cy - 22 * s), (cx - ex + 12, cy - 26 * s)], 3.5, INK, False, 2, 1.5, seed + 4)
    return o

def limbs(cx, y0, seed=0, pose="flat"):
    """bras et jambes en fil de fer, un peu tordus."""
    r = random.Random(seed); o = ""
    la = [(cx - 40, y0), (cx - 70 + r.uniform(-8, 8), y0 + 70), (cx - 60, y0 + 130)]
    ra = [(cx + 40, y0), (cx + 70, y0 + 70), (cx + 60 + r.uniform(-8, 8), y0 + 130)]
    if pose == "surprised":
        la = [(cx - 40, y0), (cx - 90, y0 + 20), (cx - 110, y0 - 50)]; ra = [(cx + 40, y0), (cx + 95, y0 + 15), (cx + 118, y0 - 45)]
    for p in (la, ra): o += sketch_path(p, 6, INK, False, 2, 2.5, seed)
    for dx in (-22, 22): o += sketch_path([(cx + dx, y0 + 150), (cx + dx + r.uniform(-10, 10), y0 + 250)], 7, INK, False, 2, 2.5, seed + dx)
    for dx in (-22, 22): o += sketch_path([(cx + dx - 14, y0 + 252), (cx + dx + 22, y0 + 250)], 6, INK, False, 1, 1.5, seed + dx + 5)
    return o

# -------- personnages (chaque fonction : (fond, svg) pour une pose)
def gobelet(pose, seed=1):
    o = ""
    body = [(150, 120), (250, 120), (236, 400), (164, 400)]
    o += sketch_path(body, 7, INK, True, 2, 3, seed, fill="#f3ede2")
    o += hatch(165, 140, 70, 250, seed, 10)
    o += sketch_path(rect_pts(138, 96, 124, 30), 6, INK, True, 2, 2.5, seed + 1, fill="#d8d2c6")
    o += sketch_path(ellipse_pts(200, 94, 62, 14), 5, INK, True, 2, 2, seed + 2, fill="#e9e4da")
    o += sketch_path([(206, 60), (216, 92)], 5, INK, False, 2, 2, seed + 3)  # paille / trou
    o += sketch_path(rect_pts(150, 230, 100, 60), 4, INK, True, 2, 2, seed + 4, fill="#c9b79a")  # manchon
    o += face(200, 180, 1.0, pose, seed)
    o += limbs(200, 300, seed, pose)
    return "#cfe3d6", o
def cone(pose, seed=2):
    o = ""
    o += sketch_path([(120, 420), (280, 420), (236, 100), (164, 100)], 7, INK, True, 2, 3, seed, fill="#f08c3a")
    o += sketch_path(rect_pts(142, 210, 116, 50), 4, INK, True, 2, 2, seed + 1, fill="#f5f0e8")
    o += sketch_path(rect_pts(130, 320, 140, 50), 4, INK, True, 2, 2, seed + 2, fill="#f5f0e8")
    o += sketch_path(rect_pts(90, 420, 220, 26), 6, INK, True, 2, 2.5, seed + 3, fill="#e8762a")
    o += face(200, 150, 0.8, pose, seed)
    o += limbs(200, 290, seed, pose).replace("y0 + 250", "y0 + 250")
    return "#dfe6ee", o
def patate(pose, seed=3):
    pts = [(200 + 110 * math.cos(a) * (1 + 0.12 * math.sin(3 * a + 1)), 240 + 150 * math.sin(a) * (1 + 0.1 * math.cos(2 * a))) for a in [2 * math.pi * i / 36 for i in range(36)]]
    o = sketch_path(pts, 7, INK, True, 2, 4, seed, fill="#c9a06b")
    r = random.Random(seed)
    for i in range(9): o += f'<ellipse cx="{r.uniform(120, 280):.0f}" cy="{r.uniform(130, 360):.0f}" rx="5" ry="3" fill="{INK}" opacity=".5"/>'
    o += sketch_path(rect_pts(160, 60, 80, 40), 5, INK, True, 2, 2.5, seed + 1, fill="#3a3540") + sketch_path([(140, 102), (262, 100)], 6, INK, False, 2, 2, seed + 2)
    o += face(200, 220, 0.9, pose, seed)
    o += limbs(200, 330, seed, pose)
    return "#f2e6cf", o
def postit(pose, seed=4):
    o = sketch_path(rect_pts(110, 90, 180, 180), 6, INK, True, 2, 3, seed, fill="#ffe66d")
    o += f'<path d="M290,270 L250,270 L290,230 Z" fill="#e6c94d" stroke="{INK}" stroke-width="4"/>'
    o += sketch_path(rect_pts(170, 60, 60, 30), 3, INK, True, 1, 1.5, seed + 1, fill="#cfd8dc")  # ruban
    o += face(200, 165, 1.1, pose, seed)
    o += limbs(200, 270, seed, pose)
    return "#dbe4f0", o
def oeuf(pose, seed=5):
    pts = [(200 + 120 * math.cos(a), 250 + (170 if math.sin(a) > 0 else 150) * math.sin(a)) for a in [2 * math.pi * i / 40 for i in range(40)]]
    o = sketch_path(pts, 7, INK, True, 2, 3, seed, fill="#f7f1e3")
    crack = [(130, 150), (160, 175), (175, 150), (205, 185), (225, 155), (255, 175), (272, 150)]
    o += sketch_path(crack, 5, INK, False, 2, 2, seed + 1)
    o += sketch_path([(150, 160), (176, 136), (200, 165), (226, 140), (250, 160)], 4, INK, False, 1, 1.5, seed + 2)
    o += hatch(140, 110, 120, 50, seed, 8)
    o += face(200, 260, 1.0, pose, seed)
    o += limbs(200, 400, seed, pose)
    return "#e9dcd0", o
def chaussette(pose, seed=6):
    pts = [(150, 80), (250, 80), (250, 280), (300, 330), (290, 400), (150, 400), (150, 280)]
    o = sketch_path(pts, 7, INK, True, 2, 3, seed, fill="#8fb3c9")
    for y in (120, 160, 200): o += sketch_path([(152, y), (248, y + 3)], 5, "#4f6f87", False, 1, 2, seed + y)
    o += sketch_path([(150, 282), (250, 282)], 5, INK, False, 1, 2, seed + 7)
    o += face(200, 230, 0.9, pose, seed)
    o += limbs(200, 330, seed, pose)
    return "#f0e4e4", o

chars = [("gobelet", gobelet), ("cône", cone), ("patate", patate), ("post-it", postit), ("œuf", oeuf), ("chaussette", chaussette)]
cw, ch = 400, 620; W, H = cw * len(chars), ch * 2 + 60
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"><rect width="{W}" height="{H}" fill="#d8d8d8"/>']
for i, (name, fn) in enumerate(chars):
    for j, pose in enumerate(("flat", "surprised")):
        bg, body = fn(pose)
        svg.append(f'<g transform="translate({i * cw},{60 + j * ch})"><rect x="4" y="4" width="{cw - 8}" height="{ch - 8}" rx="14" fill="{bg}"/><g transform="translate(0,30)">{body}</g></g>')
    svg.append(f'<text x="{i * cw + cw / 2}" y="42" text-anchor="middle" font-family="DejaVu Sans" font-weight="bold" font-size="30" fill="{INK}">{name}</text>')
svg.append("</svg>")
png = cairosvg.svg2png(bytestring="".join(svg).encode())
im = Image.open(io.BytesIO(png)).convert("RGB")
# grain papier
noise = np.random.default_rng(1).normal(0, 1, (H, W)).astype(np.float32)
noise = np.asarray(Image.fromarray(((noise - noise.min()) / (noise.max() - noise.min()) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))).astype(np.float32) / 255
arr = np.asarray(im).astype(np.float32)
arr = arr * (0.9 + 0.2 * noise[..., None])
Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(sys.argv[1]); print("ok")
