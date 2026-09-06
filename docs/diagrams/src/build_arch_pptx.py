"""Rewrites the user's architecture.pptx into a finished TECHNICAL APPROACH slide:
four columns (image + title + a plain-English caption), the two missing visuals filled in,
and the two supplied photos re-placed on the same grid."""
import os, re, shutil, zipfile

SRC = os.environ.get("SRC", "architecture.pptx")
OUT = os.environ.get("OUT", "docs/diagrams/OFFGRID_technical_approach.pptx")
WORK = "/private/tmp/claude-501/-Users-lokkeshayyappan-HACKATHON/a87e2c47-0afe-4db5-88a2-6ce786ef3eca/scratchpad/build"
IMG = os.path.dirname(os.path.abspath(__file__)) + "/img"

EMU = 9525
def E(v): return int(round(v * EMU))

# ---- the grid, in slide pixels (the deck is exactly 1280 x 720) -------------
COLS = [40, 348, 656, 964]; CW = 274
IMG_XY, IMG_WH = 194, 274
TITLE_Y, TITLE_H = 150, 34
CAP_Y,  CAP_H    = 482, 132
ARROW_Y, ARROW_W, ARROW_H = 322, 26, 18

INK, MUTED, ARROW_C = "14181F", "58626F", "C3CAD3"

CARDS = [
    ("Phone sensors", "The phone&#8217;s own sensors feel every bump and turn, 419 times a "
                      "second. Nothing is attached to the bicycle."),
    ("1-D CNN",       "A small neural network turns 2.56 s of vibration into a speed &#8212; and its "
                      "own uncertainty. 57 k weights, 240 KB."),
    ("Fusion filter", "Speed, direction and the satellite never quite agree. The filter decides "
                      "how much to trust each, 10 times a second."),
    ("Live map",      "The satellite signal was switched off for 569 m. The marker never stopped, "
                      "and ended up 17.3 m off."),
]

def textbox(i, name, x, y, w, h, text, sz, bold, col, lnspc=100):
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="{name}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{E(x)}" y="{E(y)}"/><a:ext cx="{E(w)}" cy="{E(h)}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
            f'<p:txBody><a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0"><a:noAutofit/></a:bodyPr>'
            f'<a:lstStyle/><a:p><a:pPr algn="l"><a:lnSpc><a:spcPct val="{lnspc*1000}"/></a:lnSpc></a:pPr>'
            f'<a:r><a:rPr lang="en-US" sz="{sz}" b="{1 if bold else 0}" dirty="0">'
            f'<a:solidFill><a:srgbClr val="{col}"/></a:solidFill>'
            f'<a:latin typeface="Calibri" panose="020F0502020204030204" pitchFamily="34" charset="0"/>'
            f'<a:cs typeface="Calibri" panose="020F0502020204030204" pitchFamily="34" charset="0"/>'
            f'</a:rPr><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp>')

def picture(i, name, rid, x, y, w, h):
    return (f'<p:pic><p:nvPicPr><p:cNvPr id="{i}" name="{name}"/>'
            f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
            f'<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
            f'<p:spPr><a:xfrm><a:off x="{E(x)}" y="{E(y)}"/><a:ext cx="{E(w)}" cy="{E(h)}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')

def arrow(i, x, y, w, h):
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="Flow arrow {i}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{E(x)}" y="{E(y)}"/><a:ext cx="{E(w)}" cy="{E(h)}"/></a:xfrm>'
            f'<a:prstGeom prst="rightArrow"><a:avLst>'
            f'<a:gd name="adj1" fmla="val 52000"/><a:gd name="adj2" fmla="val 48000"/></a:avLst></a:prstGeom>'
            f'<a:solidFill><a:srgbClr val="{ARROW_C}"/></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr>'
            f'<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang="en-US"/></a:p></p:txBody></p:sp>')

# ---------------------------------------------------------------- unpack
shutil.rmtree(WORK, ignore_errors=True); os.makedirs(WORK)
with zipfile.ZipFile(SRC) as z: names = z.namelist(); z.extractall(WORK)

shutil.copy(f"{IMG}/sq_sensors.png", f"{WORK}/ppt/media/image3.png")  # de-labelled, palette-unified
shutil.copy(f"{IMG}/sq_cnn_labelled.png", f"{WORK}/ppt/media/image4.png")  # generated art + Motion/Pattern/Speed
shutil.copy(f"{IMG}/sq_fusion_gen.png",   f"{WORK}/ppt/media/image5.png")

rp = f"{WORK}/ppt/slides/_rels/slide1.xml.rels"; rels = open(rp).read()
rels = rels.replace("</Relationships>",
  '<Relationship Id="rId6" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image4.png"/>'
  '<Relationship Id="rId7" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image5.png"/>'
  "</Relationships>")
open(rp, "w").write(rels)

# ---------------------------------------------------------------- the slide
sp = f"{WORK}/ppt/slides/slide1.xml"; s = open(sp).read()
s = s.replace("<a:t>Your Team Name</a:t>", "<a:t>OFFGRID</a:t>")
# re-place the two supplied images onto the grid
s = s.replace('<a:off x="185531" y="1395246"/><a:ext cx="2898458" cy="2898458"/>',      # IMU  -> col 1
              f'<a:off x="{E(COLS[0])}" y="{E(IMG_XY)}"/><a:ext cx="{E(IMG_WH)}" cy="{E(IMG_WH)}"/>')
s = s.replace('<a:off x="9780086" y="1747372"/><a:ext cx="2194206" cy="2194206"/>',     # map  -> col 4
              f'<a:off x="{E(COLS[3])}" y="{E(IMG_XY)}"/><a:ext cx="{E(IMG_WH)}" cy="{E(IMG_WH)}"/>')

add = [picture(40, "CNN diagram",    "rId6", COLS[1], IMG_XY, IMG_WH, IMG_WH),
       picture(41, "Fusion diagram", "rId7", COLS[2], IMG_XY, IMG_WH, IMG_WH)]
for n, x in enumerate(COLS[:-1]):
    add.append(arrow(50+n, x+CW+4, ARROW_Y, ARROW_W, ARROW_H))
for n, (title, cap) in enumerate(CARDS):
    add.append(textbox(60+n, f"Card title {n+1}", COLS[n], TITLE_Y, CW, TITLE_H, title, 1800, True,  INK))
    add.append(textbox(70+n, f"Card caption {n+1}", COLS[n], CAP_Y,  CW, CAP_H,  cap,  1400, False, MUTED, 108))

s = s.replace("</p:spTree>", "".join(add) + "</p:spTree>")
open(sp, "w").write(s)

# ---------------------------------------------------------------- repack
if os.path.exists(OUT): os.remove(OUT)
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(f"{WORK}/[Content_Types].xml", "[Content_Types].xml")
    for root, _, files in os.walk(WORK):
        for f in files:
            full = os.path.join(root, f); rel = os.path.relpath(full, WORK)
            if rel == "[Content_Types].xml": continue
            z.write(full, rel)
print("wrote", OUT, os.path.getsize(OUT)//1024, "KB")
