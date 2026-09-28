"""Per-cut OSM road graphs from a local Geofabrik extract (replaces the Overpass fetch, which was rate-limited).

Usage: .venv/Scripts/python engine/iovopt/osm_extract.py
Reads D:/offgrid_iov/osm/england-latest.osm.pbf, keeps drivable ways in the bbox of all cut points (+0.1 deg), then writes one
Overpass-style JSON per cut (ways with any node within R of the last healthy fix: only the cut position is used, never the route).
"""
import sys, os, json, pickle, math
from pathlib import Path; HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import numpy as np
import osmium

OSM = Path(r'D:\offgrid_iov\osm'); R = 2500.0
HW = set('motorway trunk primary secondary tertiary unclassified residential motorway_link trunk_link primary_link secondary_link tertiary_link living_street service road'.split())
KEEP = ('highway', 'oneway', 'junction', 'service', 'access', 'maxspeed', 'name', 'ref', 'lanes')

class H(osmium.SimpleHandler):
    def __init__(self, bb):
        super().__init__(); self.bb = bb; self.ways = []
    def way(self, w):
        hw = w.tags.get('highway')
        if hw not in HW: return
        try: pts = [(n.ref, n.location.lat, n.location.lon) for n in w.nodes]
        except osmium.InvalidLocationError: return
        la = [p[1] for p in pts]; lo = [p[2] for p in pts]; b = self.bb
        if max(la) < b[0] or min(la) > b[1] or max(lo) < b[2] or min(lo) > b[3]: return
        self.ways.append(dict(id=w.id, tags={k: w.tags.get(k) for k in KEEP if w.tags.get(k) is not None}, nodes=[p[0] for p in pts], geometry=[dict(lat=p[1], lon=p[2]) for p in pts]))

def main():
    cuts = json.load(open(OSM / 'cuts.json')); la = np.array([c[2] for c in cuts]); lo = np.array([c[3] for c in cuts])
    bb = (la.min() - 0.1, la.max() + 0.1, lo.min() - 0.15, lo.max() + 0.15); cache = OSM / 'ways_bbox.pkl'
    if cache.exists(): ways = pickle.load(open(cache, 'rb'))
    else:
        ways = {}
        for f in sorted((OSM / 'gf').glob('*.osm.pbf')):
            h = H(bb); h.apply_file(str(f), locations=True, idx='flex_mem'); print(f.name, len(h.ways), flush=True)
            for w in h.ways: ways[w['id']] = w
        ways = list(ways.values()); pickle.dump(ways, open(cache, 'wb'))
    print(len(ways), 'ways in bbox', bb, flush=True)
    wl = [np.array([[g['lat'], g['lon']] for g in w['geometry']]) for w in ways]
    cen = np.array([x.mean(0) for x in wl]); rad = np.array([np.max(np.hypot((x[:, 0] - c[0]) * 111320, (x[:, 1] - c[1]) * 111320 * math.cos(math.radians(c[0])))) for x, c in zip(wl, cen)])
    for s, m0, lat, lon, lat0, lon0 in cuts:
        mlon = 111320 * math.cos(math.radians(lat)); dc = np.hypot((cen[:, 0] - lat) * 111320, (cen[:, 1] - lon) * mlon); cand = np.where(dc < R + rad)[0]; sel = []
        for i in cand:
            x = wl[i]
            if np.min(np.hypot((x[:, 0] - lat) * 111320, (x[:, 1] - lon) * mlon)) < R: sel.append(i)
        j = dict(elements=[dict(type='way', **ways[i]) for i in sel], cut=dict(lat=lat, lon=lon, lat0=lat0, lon0=lon0))
        json.dump(j, open(OSM / f'{s}_{m0}.json', 'w'))
    print('wrote', len(cuts), 'cut graphs')

if __name__ == '__main__':
    main()
