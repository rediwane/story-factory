"""Sketch comique face camera : les 5 etapes du 'typing...'."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import math
from lib import *

def build():
    st = Story([
        ("You send the text. Perfect text. You reread it twelve times.", 0.3),
        ("Stage one: typing appears. Hope.", 0.4),
        ("Stage two: it disappears. Panic.", 0.4),
        ("Stage three: it's back. You stand up. You sit down.", 0.3),
        ("Stage four: gone again. For nine minutes.", 0.4),
        ("You write a second text. You delete it. You write haha. You delete it.", 0.3),
        ("Stage five: the reply arrives.", 0.6),
        ("K.", 1.0),
        ("Anyway. I'm fine.", 0.0),
    ], speed=1.1, end_hold=3.0)
    S, E, m = st.S, st.E, st.mouth
    st.hook, st.hook_until = "The 5 stages of 'typing...'", 2.4

    def phone_big(txt_sent, typing=False, reply="", draft="", draft_del=False):
        o = phone(540, 960, 2.4)
        o += rect(230, 320, 620, 1280, "#fff", 24)
        if txt_sent:
            w = min(520, textw(txt_sent, 36) + 60)
            o += rect(850 - w - 20, 420, w, 90, "#1c7ed6", 30) + f'<text x="{850 - w / 2 - 20}" y="478" text-anchor="middle" font-family="Inter" font-weight="900" font-size="36" fill="#fff">{esc(txt_sent)}</text>'
        if typing:
            o += rect(250, 560, 170, 90, "#e9ecef", 30) + "".join(circ(295 + k * 40, 605, 12, "#868e96", f'opacity="{0.4 + 0.6 * (0.5 + 0.5 * math.sin(typing * 8 - k)):.2f}"') for k in range(3))
        if reply:
            w = textw(reply, 110) + 80
            o += rect(250, 560, w, 170, "#e9ecef", 40) + f'<text x="{250 + w / 2}" y="680" text-anchor="middle" font-family="Inter" font-weight="900" font-size="110" fill="{K}">{esc(reply)}</text>'
        o += rect(250, 1470, 580, 100, "#f1f3f5", 40, f'stroke="#ced4da" stroke-width="4"')
        if draft: o += f'<text x="290" y="1535" font-family="Inter" font-weight="900" font-size="44" fill="{"#adb5bd" if draft_del else K}">{esc(draft)}</text>' + (ln("M280,1520 L560,1520", 8, "#e03131") if draft_del else "")
        return o
    def stage(n, tl, col="#ffd43b"):
        return bigtext(f"STAGE {n}", 540, 300, 120, col, eout(tl / 0.2), -4) if tl > 0 else ""
    def scene(bgt, bgb, body_fn):
        def f(tl, d, t):
            o = grad(bgt, bgb) + floor(1450)
            o += body_fn(tl, d, t)
            return o, cam(1.0 + 0.04 * tl, 540, 1000)
        return f
    def s_send(tl, d, t):
        o = char(t, 340, 1150, 1.6, "happy", "hold", "hold", mouth=m(t), cable=False, tilt=8)
        o += phone(400, 1300, 0.6, "") + moth_near(t, 520, 820, 1.8)
        o += g(rect(-260, -60, 520, 120, "#1c7ed6", 40) + f'<text x="0" y="16" text-anchor="middle" font-family="Inter" font-weight="900" font-size="40" fill="#fff">hey :) free tonight?</text>', 760, 760, back(clamp(tl / 0.3)))
        if tl > 1.6: o += bigtext("x12", 820, 1000, 110, "#fff", eout((tl - 1.6) / 0.2), 8)
        return o
    def s_hope(tl, d, t):
        o = phone_big("hey :) free tonight?", typing=t if tl > 0.3 else False)
        o += char(t, 540, 1700, 1.3, "idea", "up", "up", mouth=m(t), cable=False, rays=clamp((tl - 0.5) / 0.3), halo_boost=0.3) if tl > 0.3 else char(t, 540, 1700, 1.3, "talk", "hold", "hold", mouth=m(t), cable=False)
        o += moth_near(t, 740, 1450, 1.8) + stage(1, tl - 0.1)
        return o
    def s_panic(tl, d, t):
        o = phone_big("hey :) free tonight?", typing=False)
        o += char(t, 540, 1700, 1.3, "fear", "head", "head", mouth=m(t), cable=False, shiver=0.8, eyes="wide")
        o += moth(740 + 40 * math.sin(t * 20), 1420 + 30 * math.sin(t * 27), 0, 1.8, abs(math.sin(t * 50)))
        o += stage(2, tl - 0.1, "#ff6b6b")
        return o
    def s_updown(tl, d, t):
        o = phone_big("hey :) free tonight?", typing=t)
        up = (t * 3) % 1 < 0.5
        o += char(t, 540, 1700 if up else 1800, 1.3, "happy" if up else "talk", "up" if up else "hold", "up" if up else "hold", mouth=m(t), cable=False)
        o += moth_near(t, 740, 1450, 1.8) + stage(3, tl - 0.1)
        return o
    def s_nine(tl, d, t):
        o = phone_big("hey :) free tonight?", typing=False)
        o += char(t, 540, 1760, 1.3, "sad", "hang", "hang", mouth=m(t), cable=False, tilt=16, lit=0.5)
        o += moth(700, 1560, 0, 1.8, 0.2) + stage(4, tl - 0.1, "#9fc8ff")
        mins = min(9, int(tl * 9 / max(0.1, d - 0.5)))
        o += g(clock(0, 0, 9, mins * 6, 1.0) + f'<text x="0" y="170" text-anchor="middle" font-family="Inter" font-weight="900" font-size="54" fill="{K}">{mins} min</text>', 930, 1180, 0.8)
        return o
    def s_draft(tl, d, t):
        ph = tl / d
        if ph < 0.25: dr, dd = "so anyway I was thinking", False
        elif ph < 0.45: dr, dd = "so anyway I was thinking", True
        elif ph < 0.7: dr, dd = "haha", False
        else: dr, dd = "haha", True
        o = phone_big("hey :) free tonight?", typing=False, draft=dr, draft_del=dd)
        o += char(t, 540, 1760, 1.3, "angry" if dd else "talk", "hold", "hold", mouth=m(t), cable=False, tilt=4)
        o += moth_near(t, 740, 1480, 1.8)
        return o
    def s_reply(tl, d, t):
        o = phone_big("hey :) free tonight?", typing=False, reply="" if tl < 0.8 else "")
        o += char(t, 540, 1700, 1.3, "idea", "up", "up", mouth=m(t), cable=False, rays=1.0, halo_boost=0.3 * (1 if (t * 6) % 1 < .5 else 0))
        o += moth_near(t, 740, 1450, 1.8) + stage(5, tl - 0.1, "#b2f2bb")
        if tl > 0.6: o += g(ln("M-40,-80 L-40,-120 M40,-80 L40,-120 M0,-90 L0,-140", 10, K), 540, 540 - 40 * ((t * 8) % 1))
        return o
    def s_k(tl, d, t):
        o = phone_big("hey :) free tonight?", reply="k.")
        o += char(t, 540, 1760, 1.3, "off", "hang", "hang", mouth=0, cable=False, tilt=20, lit=0.2)
        o += moth(700, 1560, 0, 1.8, 0.2)
        if tl > 0.5: o += bigtext("k.", 540, 1150, 320, "#fff", eout((tl - 0.5) / 0.25), -6)
        return o
    def s_fine(tl, d, t):
        o = grad("#e03131", "#862e2e") + floor(1450)
        o += char(t, 540, 1150, 1.8, "angry" if tl < 0.9 else "happy", "chest", "chest", mouth=m(t), cable=False, tilt=0, shiver=0.5 if tl < 0.9 else 0, lit=0.9)
        o += moth(740 + 20 * math.sin(t * 2), 800 + 25 * math.sin(t * 2.7), 15, 2.2, abs(math.sin(t * 36)))
        if tl > 1.4: o += g(ln("M0,0 L30,-20 M0,0 L30,20", 6, K), 760, 980) + label("there, there.", 790, 900, 40)
        if tl > 0.9: o += bigtext("I'M FINE.", 540, 520, 160, "#fff", eout((tl - 0.9) / 0.2), -3)
        return o, cam(1.0 + 0.08 * ease(tl / 2), 540, 1000)

    shots = [
        (0, S[1] - 0.05, scene("#5bc0be", "#1c6e7d", s_send), "cut"),
        (S[1] - 0.05, S[2] - 0.05, lambda tl, d, t: (grad("#b2f2bb", "#69db7c") + s_hope(tl, d, t), cam(1.0 + 0.05 * tl, 540, 1000)), "whip"),
        (S[2] - 0.05, S[3] - 0.05, lambda tl, d, t: (grad("#ffa8a8", "#e03131") + s_panic(tl, d, t), cam(1.0 + 0.05 * tl, 540, 1000, sh=4)), "whip"),
        (S[3] - 0.05, S[4] - 0.05, lambda tl, d, t: (grad("#ffec99", "#fab005") + s_updown(tl, d, t), cam(1.0 + 0.05 * tl, 540, 1000)), "whip"),
        (S[4] - 0.05, S[5] - 0.05, lambda tl, d, t: (grad("#a5d8ff", "#4dabf7") + s_nine(tl, d, t), cam(1.0 + 0.05 * tl, 540, 1000)), "whip"),
        (S[5] - 0.05, S[6] - 0.05, lambda tl, d, t: (grad("#e5dbff", "#9775fa") + s_draft(tl, d, t), cam(1.0 + 0.05 * tl, 540, 1000)), "whip"),
        (S[6] - 0.05, S[7] - 0.05, lambda tl, d, t: (grad("#b2f2bb", "#40c057") + s_reply(tl, d, t), cam(1.0 + 0.05 * tl, 540, 1000)), "whip"),
        (S[7] - 0.05, S[8] - 0.05, lambda tl, d, t: (grad("#495057", "#212529") + s_k(tl, d, t), cam(1.0 + 0.12 * ease(tl / 1.5), 540, 1000)), "flash"),
        (S[8] - 0.05, st.TOTAL + 1, s_fine, "whip"),
    ]
    buzz_s = np.concatenate([s_buzz(0.12, 60), np.zeros(int(0.1 * SR))] * 2)
    sfx = [(S[0] + 0.1, s_pop(700, 1100, 0.1), 0.7), (S[0] + 1.6, s_pop(900, 1300, 0.08), 0.6), (S[1] + 0.4, s_ding(), 0.6), (S[2] + 0.3, s_thud(), 0.9), (S[2] + 0.3, s_zap(), 0.5),
           (S[3] + 0.3, s_pop(500, 800, 0.1), 0.6), (S[3] + 0.6, s_pop(800, 500, 0.1), 0.6), (S[3] + 0.9, s_pop(500, 800, 0.1), 0.6), (S[3] + 1.2, s_pop(800, 500, 0.1), 0.6),
           (S[4] + 0.3, s_ticktock(8, 0.28), 0.6), (S[5] + 0.0, s_ticktock(12, 0.09), 0.3), (S[5] + 1.0, s_pop(300, 200, 0.12), 0.7), (S[5] + 2.2, s_pop(300, 200, 0.12), 0.7),
           (S[6] + 0.6, buzz_s, 1.0), (S[6] + 0.6, s_sparkle(), 0.8), (S[7] + 0.5, s_thud(100, 30, 0.9), 1.3), (S[8] + 0.9, s_ding(), 0.5), (S[8] + 1.4, s_pop(600, 900, 0.1), 0.6)]
    return st, shots, sfx, "funk", None

if __name__ == "__main__": main(build)
