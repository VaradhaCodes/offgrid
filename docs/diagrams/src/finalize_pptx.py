"""Takes the user's finalised OFFGRID_technical_approach.pptx and applies the final pass:
bordered cards, dark arrows, aligned images, a BUILT WITH logo row, one training line.
Caption wording is theirs, unchanged - only the missing paragraph breaks are restored."""
import base64, io, os, re, shutil, zipfile
from PIL import Image

SRC  = os.environ.get("SRC", "docs/diagrams/OFFGRID_technical_approach.pptx")
OUT  = os.environ.get("OUT", "docs/diagrams/OFFGRID_technical_approach_final.pptx")
WORK = "/private/tmp/claude-501/-Users-lokkeshayyappan-HACKATHON/a87e2c47-0afe-4db5-88a2-6ce786ef3eca/scratchpad/fin2"
LOGOS_SRC = "/private/tmp/claude-501/-Users-lokkeshayyappan-HACKATHON/a87e2c47-0afe-4db5-88a2-6ce786ef3eca/scratchpad/logos/ppt/media"

E = lambda v: int(round(v * 9525))
INK="14181F"; MUTED="58626F"; FAINT="8A94A0"; RULE="D8DEE4"; ARROW="1F262E"

# ---- grid -------------------------------------------------------------------
CARD_X = [30, 338, 646, 954]; CARD_W = 286
CARD_Y, CARD_H = 138, 432                 # bordered box
TITLE_Y, TITLE_H = 150, 32
IMG_WH = 206; IMG_Y = 186
CAP_Y,  CAP_H = 400, 158
ARROW_Y, ARROW_W, ARROW_H = 322, 18, 16
BAND_Y = 584

# ---- captions: their words, their bold runs, with the line breaks restored ---
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
TITLES = ["Phone sensors", "1-D CNN", "Fusion filter", "Live map"]
IMG_RID = ["rId7", "rId5", "rId6", "rId4"]        # sensors, CNN, fusion, live map

TRAINING = ("Trained on 30 logged rides over two campus roads, with GNSS speed as the label, "
            "then tested on rides the model had never seen.")

CHIPS = [("Android","image15.png",26),("Kotlin","image11.png",18),("PyTorch","image2.png",21),
         ("LiteRT","image10.png",18),("MapLibre","image16.png",19),("OpenStreetMap","image17.png",21)]

def esc(t): return t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def tbox(i, name, x, y, w, h, lines, sz, col, lnspc=100, algn="l", spc=0):
    paras = ""
    for runs in lines:
        body = "".join(
            f'<a:r><a:rPr lang="en-US" sz="{sz}" b="{b}" dirty="0">'
            f'<a:solidFill><a:srgbClr val="{col}"/></a:solidFill>'
            f'{f"<a:latin typeface=\"Calibri\"/><a:cs typeface=\"Calibri\"/>"}'
            f'</a:rPr><a:t>{esc(t)}</a:t></a:r>' for t, b in runs)
        paras += (f'<a:p><a:pPr algn="{algn}"><a:lnSpc><a:spcPct val="{lnspc*1000}"/></a:lnSpc>'
                  f'<a:spcBef><a:spcPts val="{spc}"/></a:spcBef></a:pPr>{body}</a:p>')
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="{name}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{E(x)}" y="{E(y)}"/><a:ext cx="{E(w)}" cy="{E(h)}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
            f'<p:txBody><a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0"><a:noAutofit/></a:bodyPr>'
            f'<a:lstStyle/>{paras}</p:txBody></p:sp>')

def card(i, x, y, w, h):
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="Card {i}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{E(x)}" y="{E(y)}"/><a:ext cx="{E(w)}" cy="{E(h)}"/></a:xfrm>'
            f'<a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val 4800"/></a:avLst></a:prstGeom>'
            f'<a:noFill/><a:ln w="19050"><a:solidFill><a:srgbClr val="{RULE}"/></a:solidFill></a:ln></p:spPr>'
            f'<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang="en-US"/></a:p></p:txBody></p:sp>')

def arrow(i, x, y, w, h):
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="Flow arrow {i}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{E(x)}" y="{E(y)}"/><a:ext cx="{E(w)}" cy="{E(h)}"/></a:xfrm>'
            f'<a:prstGeom prst="rightArrow"><a:avLst><a:gd name="adj1" fmla="val 50000"/>'
            f'<a:gd name="adj2" fmla="val 50000"/></a:avLst></a:prstGeom>'
            f'<a:solidFill><a:srgbClr val="{ARROW}"/></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr>'
            f'<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang="en-US"/></a:p></p:txBody></p:sp>')

def pic(i, name, rid, x, y, w, h):
    return (f'<p:pic><p:nvPicPr><p:cNvPr id="{i}" name="{name}"/>'
            f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
            f'<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
            f'<p:spPr><a:xfrm><a:off x="{E(x)}" y="{E(y)}"/><a:ext cx="{E(w)}" cy="{E(h)}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')

# ---- unpack -----------------------------------------------------------------
shutil.rmtree(WORK, ignore_errors=True); os.makedirs(WORK)
with zipfile.ZipFile(SRC) as z: z.extractall(WORK)

# add the six brand logos as new media + relationships
rels_path = f"{WORK}/ppt/slides/_rels/slide1.xml.rels"; rels = open(rels_path).read()
new_rels = ""; chip_meta = []
for n, (label, fn, h) in enumerate(CHIPS):
    idx = 20 + n; rid = f"rId{idx}"
    im = Image.open(f"{LOGOS_SRC}/{fn}").convert("RGBA")
    im = im.resize((round(im.width * h * 3 / im.height), h * 3), Image.LANCZOS)
    im.save(f"{WORK}/ppt/media/logo{n}.png", optimize=True)
    new_rels += (f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/'
                 f'2006/relationships/image" Target="../media/logo{n}.png"/>')
    chip_meta.append((rid, round(im.width / 3), h, label))
open(rels_path, "w").write(rels.replace("</Relationships>", new_rels + "</Relationships>"))

# ---- rebuild the slide body -------------------------------------------------
sp = f"{WORK}/ppt/slides/slide1.xml"; s = open(sp).read()
KEEP = ("Rectangle 9", "Title 1", "Slide Number Placeholder 5", "Footer Placeholder 6", "Picture 11")
kept = []
for m in re.finditer(r'<p:(sp|pic)>.*?</p:\1>', s, re.S):
    blk = m.group(0); nm = re.search(r'name="([^"]*)"', blk).group(1)
    if nm in KEEP: kept.append(blk)

add = [card(100 + n, CARD_X[n], CARD_Y, CARD_W, CARD_H) for n in range(4)]
for n in range(4):
    add.append(pic(110 + n, f"Art {n+1}", IMG_RID[n],
                   CARD_X[n] + (CARD_W - IMG_WH) / 2, IMG_Y, IMG_WH, IMG_WH))
    add.append(tbox(120 + n, f"Card title {n+1}", CARD_X[n] + 16, TITLE_Y, CARD_W - 32, TITLE_H,
                    [[(TITLES[n], 1)]], 1800, INK))
    add.append(tbox(130 + n, f"Card caption {n+1}", CARD_X[n] + 16, CAP_Y, CARD_W - 32, CAP_H,
                    CAPTIONS[n], 1400, MUTED, lnspc=104, spc=160))
for n in range(3):
    add.append(arrow(140 + n, CARD_X[n] + CARD_W + 2, ARROW_Y, ARROW_W, ARROW_H))

# bottom band: how it was trained (left) + BUILT WITH logos (right)
add.append(tbox(150, "Training note", 30, BAND_Y + 2, 480, 60, [[(TRAINING, 0)]], 1200, FAINT, lnspc=110))
add.append(tbox(151, "Built with", 560, BAND_Y, 680, 20, [[("BUILT WITH", 1)]], 1000, FAINT, algn="r"))
gap = 26; total = sum(w for _, w, _, _ in chip_meta) + gap * (len(chip_meta) - 1)
x = 1240 - total
for n, (rid, w, h, label) in enumerate(chip_meta):
    add.append(pic(160 + n, f"Logo {label}", rid, x, BAND_Y + 24 + (26 - h) / 2, w, h)); x += w + gap

# the team wordmark, in place of the template's "Your Team Name" oval
add.append(tbox(170, "Team wordmark", 34, 46, 260, 46, [[("offgrid", 1)]], 2800, INK))

body = "".join(kept) + "".join(add)
s = re.sub(r'(<p:spTree>.*?</p:nvGrpSpPr>).*?(</p:spTree>)', lambda m: m.group(1) + body + m.group(2), s, flags=re.S)
open(sp, "w").write(s)

# ---- repack -----------------------------------------------------------------
if os.path.exists(OUT): os.remove(OUT)
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(f"{WORK}/[Content_Types].xml", "[Content_Types].xml")
    for root, _, files in os.walk(WORK):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), WORK)
            if rel != "[Content_Types].xml": z.write(os.path.join(root, f), rel)
print("wrote", OUT, os.path.getsize(OUT) // 1024, "KB")
