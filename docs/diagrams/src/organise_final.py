"""Final tidy on the user's 'final architecture.pptx': align the four card images,
darken the caption text so it reads on a projector, add the training line.
Nothing else is touched - their logo, their logo strip, their wording."""
import os, re, shutil, zipfile

SRC  = os.environ.get("SRC", "final architecture.pptx")
OUT  = os.environ.get("OUT", "docs/diagrams/OFFGRID_technical_approach_slide.pptx")
WORK = "/private/tmp/claude-501/-Users-lokkeshayyappan-HACKATHON/a87e2c47-0afe-4db5-88a2-6ce786ef3eca/scratchpad/fa2"
E = lambda v: int(round(v * 9525))

COL = [40, 348, 656, 964]; CW = 274
IMG_WH, IMG_Y = 236, 188                  # a little smaller, so the captions clear the footer band
CAP_Y,  CAP_H = 432, 162
TEXT   = "22282F"                         # captions: dark, readable on a projector
NOTE   = "333B45"                         # the training line
ARROW  = "1F262E"

TRAINING = ("Trained on 30 logged rides over two campus roads, with GNSS speed as the label, "
            "then tested on rides the model had never seen.")

# their words, their bold runs - only the missing line breaks are restored
CAPTIONS = [
 [[("1 — RAW MOTION DATA", 1)],
  [("6 IMU signals, sampled at 100 Hz", 1)],
  [("3-axis accelerometer + 3-axis gyroscope.", 0)],
  [("A ", 0), ("2.56-second window = 256 readings", 1), (" of vehicle motion.", 0)]],
 [[("A small network ", 0), ("learned how vibration changes with speed", 1),
   (". It reads the speed from the motion and its own uncertainty. 57 k weights, 240 KB.", 0)]],
 [[("Speed, direction and the satellite never quite agree. The filter decides weight of each, "
    "10 times a second.", 0)]],
 [[("The position keeps updating even when GNSS is switched off", 1)],
  [("On the test road: ", 0), ("569 m dead-reckoned → only 17.3 m position error at the end.", 1)]],
]

def esc(t): return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def tbox(i, name, x, y, w, h, lines, sz, col, lnspc=104, spc=140):
    paras = ""
    for runs in lines:
        body = "".join(f'<a:r><a:rPr lang="en-US" sz="{sz}" b="{b}" dirty="0">'
                       f'<a:solidFill><a:srgbClr val="{col}"/></a:solidFill>'
                       f'<a:latin typeface="Calibri"/><a:cs typeface="Calibri"/></a:rPr>'
                       f'<a:t>{esc(t)}</a:t></a:r>' for t, b in runs)
        paras += (f'<a:p><a:pPr><a:lnSpc><a:spcPct val="{lnspc*1000}"/></a:lnSpc>'
                  f'<a:spcBef><a:spcPts val="{spc}"/></a:spcBef></a:pPr>{body}</a:p>')
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="{name}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{E(x)}" y="{E(y)}"/><a:ext cx="{E(w)}" cy="{E(h)}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
            f'<p:txBody><a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0"><a:noAutofit/></a:bodyPr>'
            f'<a:lstStyle/>{paras}</p:txBody></p:sp>')

shutil.rmtree(WORK, ignore_errors=True); os.makedirs(WORK)
with zipfile.ZipFile(SRC) as z: z.extractall(WORK)
sp = f"{WORK}/ppt/slides/slide1.xml"; s = open(sp).read()

# 1. the four card images onto the column grid, matched by relationship id
def place(xml, rid, x, y, w, h):
    m = re.search(rf'<p:pic>(?:(?!</p:pic>).)*r:embed="{rid}".*?</p:pic>', xml, re.S)
    if not m: print("  ! not found", rid); return xml
    blk = m.group(0)
    fixed = re.sub(r'<a:off [^/]*/><a:ext [^/]*/>',
                   f'<a:off x="{E(x)}" y="{E(y)}"/><a:ext cx="{E(w)}" cy="{E(h)}"/>', blk, count=1)
    return xml.replace(blk, fixed)

for n, rid in enumerate(["rId7", "rId5", "rId6", "rId4"]):
    s = place(s, rid, COL[n] + (CW - IMG_WH) / 2, IMG_Y, IMG_WH, IMG_WH)

# 2. darker arrows, nudged to the new image centre line
s = s.replace('<a:srgbClr val="C3CAD3"/>', f'<a:srgbClr val="{ARROW}"/>')
for n, ax in enumerate([318, 626, 934]):
    m = re.search(rf'<p:sp>(?:(?!</p:sp>).)*name="Flow arrow {50+n}".*?</p:sp>', s, re.S)
    if m:
        fixed = re.sub(r'<a:off [^/]*/><a:ext [^/]*/>',
                       f'<a:off x="{E(ax)}" y="{E(297)}"/><a:ext cx="{E(22)}" cy="{E(18)}"/>',
                       m.group(0), count=1)
        s = s.replace(m.group(0), fixed)
    else: print("  ! arrow", n, "not found")

# 3. captions: darker, moved up, line breaks restored
for n in range(4):
    blk = re.search(rf'<p:sp>(?:(?!</p:sp>).)*name="Card caption {n+1}".*?</p:sp>', s, re.S)
    s = s.replace(blk.group(0), tbox(200 + n, f"Card caption {n+1}",
                                     COL[n], CAP_Y, CW, CAP_H, CAPTIONS[n], 1400, TEXT))

# 4. the training line
s = s.replace("</p:spTree>", tbox(210, "Training note", 40, 604, 780, 56,
                                  [[(TRAINING, 0)]], 1400, NOTE, lnspc=108, spc=0) + "</p:spTree>")
open(sp, "w").write(s)

if os.path.exists(OUT): os.remove(OUT)
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(f"{WORK}/[Content_Types].xml", "[Content_Types].xml")
    for root, _, files in os.walk(WORK):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), WORK)
            if rel != "[Content_Types].xml": z.write(os.path.join(root, f), rel)
print("wrote", OUT, os.path.getsize(OUT) // 1024, "KB")
