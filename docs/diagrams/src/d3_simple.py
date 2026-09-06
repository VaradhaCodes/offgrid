"""D3 — The prototype in five plain steps (for the video and for anyone who is not an engineer). 1600 x 520, white."""
import json, math, os
from lib import *

W, H = 1600, 520
s = SVG(W, H)
REVEAL = "img/p_reveal.png" if os.path.exists("img/p_reveal.png") else "img/p_reveal_old.png"
d = json.load(open("imu_window.json"))
rows = [("acc", 0), ("acc", 1), ("acc", 2), ("gyr", 0), ("gyr", 1), ("gyr", 2)]

TY, TH = 40, 400
TX = [40, 350, 660, 970, 1280]
TW = 280
for i, x in enumerate(TX):
    s.rect(x, TY, TW, TH, fill="#fff", stroke=HAIR, sw=1.25, r=10)
for x in TX[:-1]:
    s.path(f"M{x + TW + 6},{TY + 150} L{x + TW + 26},{TY + 150}", sw=1.6)

def head(x, t1, t2=None):
    s.text(x + 18, TY + 34, t1, size=21, weight=700)
    if t2: s.text(x + 18, TY + 58, t2, size=21, weight=700)

def body(x, lines, y=TY + 300):
    s.lines(x + 18, y, lines, size=15, color=MUTED, lh=20)

# ---- 1. the phone feels the ride ----------------------------------------
x = TX[0]
head(x, "The phone feels", "the ride")
gx0, gy0, gw, gh = x + 18, TY + 80, TW - 36, 176
s.rect(gx0, gy0, gw, gh, fill=PANEL, stroke="none", r=6)
for i, (k, ch) in enumerate(rows):
    v = [r[ch] for r in d[k]][::4]
    lo, hi = min(v), max(v); rng = (hi - lo) or 1
    rowh = gh / 6
    pts = " ".join(f"{gx0 + 6 + (j / (len(v) - 1)) * (gw - 12):.1f},{gy0 + i * rowh + rowh - 4 - (val - lo) / rng * (rowh - 8):.1f}" for j, val in enumerate(v))
    s.add(f'<polyline points="{pts}" fill="none" stroke="{INK if k == "acc" else MUTED}" stroke-width="1" opacity="{0.9 if k == "acc" else 0.7}"/>')
s.text(gx0 + 6, gy0 + gh + 16, "acceleration ×3, rotation ×3 — 2.56 s of a real ride", size=11.5, weight=500, color=MUTED)
body(x, ["Accelerometer and gyroscope,",
         "419 readings a second, from a",
         "phone seated in a bottle cage.",
         "No wheel sensor, nothing wired."])

# ---- 2. a small network reads the speed ------------------------------------
x = TX[1]
head(x, "A small network", "reads the speed")
cx0, cy0 = x + 24, TY + 96
s.rect(cx0, cy0, 56, 86, fill=PANEL, stroke="none", r=4)
for i, (k, ch) in enumerate(rows):
    v = [r[ch] for r in d[k]][::8]
    lo, hi = min(v), max(v); rng = (hi - lo) or 1
    rh = 86 / 6
    pts = " ".join(f"{cx0 + 4 + (j / (len(v) - 1)) * 48:.1f},{cy0 + i * rh + rh - 2 - (val - lo) / rng * (rh - 4):.1f}" for j, val in enumerate(v))
    s.add(f'<polyline points="{pts}" fill="none" stroke="{INK if k == "acc" else MUTED}" stroke-width="0.8"/>')
s.text(cx0 + 28, cy0 + 104, "last 2.56 s", size=11.5, weight=500, color=MUTED, anchor="middle")
s.line(cx0 + 62, cy0 + 43, cx0 + 78, cy0 + 43, sw=1.4)
for i, h_ in enumerate([76, 60, 46, 34]):
    s.rect(cx0 + 84 + i * 19, cy0 + 43 - h_ / 2, 14, h_, fill=AMBER_FILL, stroke=AMBER_STROKE, sw=1.1, r=2)
s.text(cx0 + 120, cy0 + 104, "4 conv layers", size=11.5, weight=500, color=AMBER_TEXT, anchor="middle")
s.line(cx0 + 164, cy0 + 43, cx0 + 180, cy0 + 43, sw=1.4)
s.text(cx0 + 186, cy0 + 40, "13", size=26, weight=700)
s.text(cx0 + 186, cy0 + 58, "km/h ± σ", size=12, weight=500, color=MUTED)
body(x, ["Trained on 30 rides with GNSS",
         "speed as the teacher. 57 k",
         "parameters, 240 KB, 0.07 ms",
         "per estimate on the phone."])

# ---- 3. the gyroscope keeps the heading -----------------------------------
x = TX[2]
head(x, "The gyroscope", "keeps the heading")
ccx, ccy, cr = x + TW / 2, TY + 150, 58
s.circle(ccx, ccy, cr, fill="none", stroke=HAIR, sw=1.5)
for a in range(0, 360, 30):
    r1, r2 = (cr - 8, cr) if a % 90 else (cr - 14, cr)
    ax, ay = math.radians(a), None
    s.line(ccx + r1 * math.cos(ax), ccy + r1 * math.sin(ax), ccx + r2 * math.cos(ax), ccy + r2 * math.sin(ax), stroke=MUTED, sw=1.2, marker=False)
ang = math.radians(-55)
s.path(f"M{ccx - 10 * math.cos(ang + math.pi / 2):.1f},{ccy - 10 * math.sin(ang + math.pi / 2):.1f} L{ccx + (cr - 12) * math.cos(ang):.1f},{ccy + (cr - 12) * math.sin(ang):.1f} L{ccx + 10 * math.cos(ang + math.pi / 2):.1f},{ccy + 10 * math.sin(ang + math.pi / 2):.1f} Z", fill=INK, stroke="none", marker=False)
s.circle(ccx, ccy, 4, fill="#fff", stroke=INK, sw=2)
# arc showing the turn
s.path(f"M{ccx + (cr + 12) * math.cos(math.radians(-140)):.1f},{ccy + (cr + 12) * math.sin(math.radians(-140)):.1f} A{cr + 12},{cr + 12} 0 0 1 {ccx + (cr + 12) * math.cos(math.radians(-55)):.1f},{ccy + (cr + 12) * math.sin(math.radians(-55)):.1f}", stroke=AMBER_STROKE, sw=2)
s.text(ccx, ccy + cr + 34, "ψ from integrated turn rate", size=11.5, weight=500, color=MUTED, anchor="middle")
body(x, ["Turn rate is integrated into a",
         "heading. Its small bias is",
         "measured in the 15 s still stand,",
         "and trimmed while GNSS is good."])

# ---- 4. a filter follows the road -------------------------------------------
x = TX[3]
head(x, "A filter fuses both", "and follows the road")
r2 = json.load(open("corridor_route2.json"))
xs = [p[0] for p in r2]; ys = [p[1] for p in r2]
mw, mh = TW - 60, 140
mx0, my0 = x + 30, TY + 86
sc = min(mw / (max(xs) - min(xs)), mh / (max(ys) - min(ys)))
def M(p): return (mx0 + (p[0] - min(xs)) * sc, my0 + (max(ys) - p[1]) * sc + 10)
def seg(pts, col, sw, dash=None):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    pp = " ".join(f"{a:.1f},{b:.1f}" for a, b in map(M, pts))
    s.add(f'<polyline points="{pp}" fill="none" stroke="{col}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"{da}/>')
seg(r2, HAIR, 7)                      # the road
seg(r2[:7], GREEN_STROKE, 3)          # locked part
seg(r2[6:30], AMBER_STROKE, 3, "6 5") # dead reckoning through the turn
seg(r2[29:], GREEN_STROKE, 3)         # locked again
p_ = M(r2[20]); s.circle(*p_, 5, fill="#fff", stroke=INK, sw=2)
s.text(M(r2[2])[0], M(r2[2])[1] - 12, "GNSS good", size=11, weight=600, color=GREEN_TEXT)
s.text(M(r2[14])[0] + 12, M(r2[14])[1] + 4, "no GNSS", size=11, weight=600, color=AMBER_TEXT)
s.text(M(r2[34])[0] - 10, M(r2[34])[1] - 6, "GNSS back", size=11, weight=600, color=GREEN_TEXT, anchor="end")
body(x, ["Speed and heading are fused",
         "10 times a second; the known",
         "road geometry constrains where",
         "the estimate can be."])

# ---- 5. the marker never freezes --------------------------------------------
x = TX[4]
head(x, "The marker never", "freezes")
PW, PH = 108, 198
s.image("img/p_dr.png", x + 22, TY + 78, PW, PH, r=9, clip_id="d3a")
s.rect(x + 22, TY + 78, PW, PH, fill="none", stroke="#8A939E", sw=1.2, r=9)
s.image(REVEAL, x + 150, TY + 78, PW, PH, r=9, clip_id="d3b")
s.rect(x + 150, TY + 78, PW, PH, fill="none", stroke="#8A939E", sw=1.2, r=9)
s.text(x + 22, TY + 292, "dead reckoning", size=11, weight=600, color=AMBER_TEXT)
s.text(x + 150, TY + 292, "off by 17.3 m after 569 m", size=11, weight=600, color=GREEN_TEXT)
body(x, ["Through a 120° turn with GNSS",
         "withheld, then the withheld",
         "track is revealed and the miss",
         "is printed. Same code live."], y=TY + 320)

s.text(40, 484, "Bicycle prototype, Shiv Nadar University campus · offline test on 10 held-out rides of road 2 with GNSS withheld for 600–850 m: drift 1.52 % of distance (median), 5.73 % worst, all under the 10 % target.", size=13, weight=400, color=MUTED)

open("d3_simple.html", "w").write(page(s.render(), W, H, "Prototype in five steps"))
print("ok")
