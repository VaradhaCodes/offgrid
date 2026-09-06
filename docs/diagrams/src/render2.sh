#!/bin/zsh
# usage: render2.sh <name> [audit]
N=$1; Q=""; OUT="$PWD/$N.png"; [ "$2" = "audit" ] && Q="?audit" && OUT="$PWD/_${N}_audit.png"
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 --window-size=1920,800 --virtual-time-budget=4000 --screenshot="$OUT" "file://$PWD/$N.html$Q" 2>/dev/null
python3 -c "from PIL import Image; print('$OUT'.split('/')[-1], Image.open('$OUT').size)"
