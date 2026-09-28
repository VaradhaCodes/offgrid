"""Download OSM drivable ways around every protocol cut point (the last healthy fix, radius R): causal, the route after the cut is never used.
Output D:/offgrid_iov/osm/<seq>_<m0>.json (Overpass 'out geom')."""
import sys, os, json, time, urllib.request, urllib.parse
from pathlib import Path; HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from core import load, all_seqs, masks_of
OUT = Path(r'D:\offgrid_iov\osm'); R = 2500
HW = 'motorway|trunk|primary|secondary|tertiary|unclassified|residential|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link|living_street|service|road'
EPS = ['https://maps.mail.ru/osm/tools/overpass/api/interpreter']

def cut_points():
    os.chdir(HERE.parent.parent); from iovnbd import load as vload; pts = []
    for s in all_seqs():
        d = load(s); v = vload(s); lat0, lon0 = v['lat0'], v['lon0']; mlon = 111320.0 * np.cos(np.radians(lat0))
        from session import M_PER_DEG_LAT
        for m in masks_of(d):
            i = m['i_cut']; pts.append((s, int(m['m0']), float(lat0 + d['fy'][i] / M_PER_DEG_LAT), float(lon0 + d['fx'][i] / (M_PER_DEG_LAT * np.cos(np.radians(lat0)))), lat0, lon0))
    return pts

def fetch(p, k=[0]):
    s, m0, lat, lon, lat0, lon0 = p; fn = OUT / f'{s}_{m0}.json'
    if fn.exists() and fn.stat().st_size > 100: return s, m0, 'skip'
    q = f'[out:json][timeout:90];way["highway"~"^({HW})$"](around:{R},{lat:.6f},{lon:.6f});out geom;'
    for attempt in range(6):
        ep = EPS[(attempt + hash(s) + m0) % len(EPS)]
        try:
            req = urllib.request.Request(ep, data=urllib.parse.urlencode({'data': q}).encode(), headers={'User-Agent': 'offgrid-research/1.0'})
            r = urllib.request.urlopen(req, timeout=120).read(); j = json.loads(r); j['cut'] = dict(lat=lat, lon=lon, lat0=lat0, lon0=lon0)
            json.dump(j, open(fn, 'w')); return s, m0, len(j['elements'])
        except Exception as e: err = str(e)[:80]; time.sleep(5 + 5 * attempt)
    return s, m0, 'ERR ' + err

if __name__ == '__main__':
    pts = cut_points(); json.dump(pts, open(OUT / 'cuts.json', 'w'))
    lats = np.array([p[2] for p in pts]); lons = np.array([p[3] for p in pts]); print(len(pts), 'cuts; lat', lats.min().round(3), lats.max().round(3), 'lon', lons.min().round(3), lons.max().round(3), flush=True)
    with ThreadPoolExecutor(4) as ex:
        for r in ex.map(fetch, pts): print(r, flush=True)
