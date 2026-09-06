#!/bin/zsh
# usage: render.sh <name> <w> <h> [scale]
N=$1; W=$2; H=$3; S=${4:-2.5}
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=$S --window-size=$W,$H --virtual-time-budget=4000 --screenshot="$PWD/$N.png" "file://$PWD/$N.html" 2>/dev/null
python3 -c "from PIL import Image; im=Image.open('$N.png'); print('$N.png', im.size); im.resize((int(im.size[0]/$S*0.75), int(im.size[1]/$S*0.75)), Image.LANCZOS).save('_$N''_preview.png')"
