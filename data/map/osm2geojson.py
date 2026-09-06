"""Convert an Overpass `out body geom` JSON dump to a MapLibre-friendly GeoJSON
FeatureCollection.  No external deps beyond the stdlib."""
import json, sys, collections

SRC, DST = sys.argv[1], sys.argv[2]

# Tags that imply a closed way is an area rather than a line.
AREA_KEYS = {
    'building', 'building:part', 'landuse', 'leisure', 'amenity', 'natural',
    'shop', 'tourism', 'historic', 'place', 'water', 'waterway_area',
    'man_made', 'office', 'craft', 'public_transport', 'military', 'boundary',
    'aeroway', 'golf', 'playground', 'healthcare', 'club', 'emergency',
}
AREA_VALUES = {          # key -> values that are areas even though the key is normally linear
    'man_made': {'water_tower', 'reservoir_covered', 'storage_tank', 'wastewater_plant',
                 'water_works', 'bridge', 'pier', 'courtyard'},
    'highway':  {'pedestrian', 'services', 'rest_area', 'platform'},
    'power':    {'generator', 'plant', 'substation'},
}
# Keys that are normally linear.  A closed way carrying one of these is a line
# UNLESS it also carries a STRONG_AREA key (the campus fence, way/369248213, is
# tagged barrier=fence + amenity=university and *is* the campus polygon).
LINEAR_KEYS = ('highway', 'barrier', 'waterway', 'power', 'railway')
STRONG_AREA = {'building', 'landuse', 'leisure', 'natural', 'amenity', 'water',
               'place', 'tourism', 'historic', 'shop', 'office', 'military',
               'aeroway', 'healthcare', 'boundary'}

def is_area(tags, geom):
    if len(geom) < 4:
        return False
    if geom[0] != geom[-1]:
        return False
    if tags.get('area') == 'yes':
        return True
    if tags.get('area') == 'no':
        return False
    if 'highway' in tags:                       # roads/paths are never areas here
        return tags['highway'] in AREA_VALUES['highway']
    for k in LINEAR_KEYS:
        if k in tags:
            if k in AREA_VALUES and tags[k] in AREA_VALUES[k]:
                return True
            if any(sk in tags for sk in STRONG_AREA):
                return True
            return False
    return any(k in tags for k in AREA_KEYS)

def classify(tags):
    """One coarse class per feature so the style can filter cheaply."""
    if tags.get('amenity') == 'university' or tags.get('boundary') == 'campus':
        return 'campus'
    if 'building' in tags:                      return 'building'
    h = tags.get('highway')
    if h:
        if h in ('footway', 'path', 'steps', 'cycleway', 'pedestrian', 'track', 'corridor'):
            return 'path'
        if h == 'crossing':                     return 'crossing_node'
        return 'road'
    if tags.get('natural') in ('water',) or tags.get('waterway') or 'water' in tags:
        return 'water'
    if tags.get('leisure') in ('pitch', 'track', 'sports_centre', 'stadium', 'golf_course', 'playground'):
        return 'sport'
    if tags.get('leisure') in ('park', 'garden', 'nature_reserve', 'common'):
        return 'green'
    if tags.get('natural') in ('wood', 'scrub', 'grassland', 'tree_row'):
        return 'green'
    if tags.get('natural') == 'tree':           return 'tree'
    if tags.get('landuse'):                     return 'landuse'
    if tags.get('amenity') == 'parking':        return 'parking'
    if 'amenity' in tags or 'shop' in tags or 'office' in tags or 'tourism' in tags:
        return 'poi'
    if 'barrier' in tags:                       return 'barrier'
    if 'man_made' in tags or 'power' in tags:   return 'manmade'
    return 'other'

# ---------------------------------------------------------------- height rule
DEFAULT_H = {                      # metres, when neither height nor levels is tagged
    'dormitory': 19.2, 'residential': 9.6, 'apartments': 16.0, 'university': 12.8,
    'school': 9.6, 'college': 12.8, 'commercial': 9.6, 'retail': 6.4,
    'industrial': 8.0, 'warehouse': 8.0, 'greenhouse': 4.0, 'roof': 4.0,
    'shed': 3.2, 'garage': 3.2, 'garages': 3.2, 'hut': 3.2, 'service': 3.2,
    'construction': 9.6, 'yes': 6.4,
}
LEVEL_M = 3.2

def parse_len(v):
    if v is None: return None
    v = str(v).strip().lower().replace('m', '').strip()
    try:    return float(v)
    except ValueError: return None

def height_for(tags):
    h = parse_len(tags.get('height'))
    if h and h > 0: return round(h, 2), 'height'
    h = parse_len(tags.get('building:height'))
    if h and h > 0: return round(h, 2), 'building:height'
    lv = parse_len(tags.get('building:levels'))
    if lv and lv > 0: return round(lv * LEVEL_M, 2), 'levels'
    return DEFAULT_H.get(tags.get('building', 'yes'), 6.4), 'default'

def min_height_for(tags):
    mh = parse_len(tags.get('min_height'))
    if mh: return round(mh, 2)
    ml = parse_len(tags.get('building:min_level'))
    if ml: return round(ml * LEVEL_M, 2)
    return 0.0

# ---------------------------------------------------------------------- main
raw = json.load(open(SRC))
els = raw['elements']
by_id = {(e['type'], e['id']): e for e in els}
feats, stats = [], collections.Counter()
geom_stats = collections.Counter()

def add(fid, tags, geometry, extra=None):
    props = dict(tags)
    props['@id'] = fid
    props['@class'] = classify(tags)
    if extra: props.update(extra)
    if 'building' in tags:
        h, src = height_for(tags)
        props['render_height'] = h
        props['render_min_height'] = min_height_for(tags)
        props['height_source'] = src
    feats.append({'type': 'Feature', 'id': fid, 'properties': props, 'geometry': geometry})
    stats[props['@class']] += 1
    geom_stats[geometry['type']] += 1

for e in els:
    tags = e.get('tags')
    if not tags:
        continue
    t = e['type']
    if t == 'node':
        add(f'node/{e["id"]}', tags, {'type': 'Point', 'coordinates': [e['lon'], e['lat']]})
    elif t == 'way':
        g = e.get('geometry')
        if not g: continue
        coords = [[p['lon'], p['lat']] for p in g if p]
        if len(coords) < 2: continue
        if is_area(tags, coords):
            if coords[0] != coords[-1]: coords.append(coords[0])
            add(f'way/{e["id"]}', tags, {'type': 'Polygon', 'coordinates': [coords]})
        else:
            add(f'way/{e["id"]}', tags, {'type': 'LineString', 'coordinates': coords})
    elif t == 'relation':
        rt = tags.get('type')
        members = e.get('members', [])
        if rt in ('multipolygon', 'boundary'):
            outers, inners = [], []
            for m in members:
                mg = m.get('geometry')
                if not mg: continue
                ring = [[p['lon'], p['lat']] for p in mg if p]
                if len(ring) < 4: continue
                if ring[0] != ring[-1]: ring.append(ring[0])
                (inners if m.get('role') == 'inner' else outers).append(ring)
            if not outers: continue
            polys = [[o] + inners for o in outers] if len(outers) > 1 else [[outers[0]] + inners]
            geom = ({'type': 'Polygon', 'coordinates': polys[0]} if len(polys) == 1
                    else {'type': 'MultiPolygon', 'coordinates': polys})
            add(f'relation/{e["id"]}', tags, geom)
        else:
            lines = []
            for m in members:
                mg = m.get('geometry')
                if not mg: continue
                ln = [[p['lon'], p['lat']] for p in mg if p]
                if len(ln) >= 2: lines.append(ln)
            if not lines: continue
            add(f'relation/{e["id"]}', tags,
                {'type': 'MultiLineString', 'coordinates': lines})

fc = {'type': 'FeatureCollection',
      'name': 'snu_osm_full',
      'crs': {'type': 'name', 'properties': {'name': 'urn:ogc:def:crs:OGC:1.3:CRS84'}},
      'metadata': {
          'source': 'OpenStreetMap via Overpass API',
          'licence': 'ODbL 1.0 - (c) OpenStreetMap contributors',
          'overpass_generator': raw.get('generator'),
          'osm_base_timestamp': raw.get('osm3s', {}).get('timestamp_osm_base'),
          'bbox': [77.5639, 28.5133, 77.5823, 28.5335],
          'height_rule': 'height -> building:height -> building:levels x 3.2 m -> default by building type',
      },
      'features': feats}
json.dump(fc, open(DST, 'w'))
print('features:', len(feats))
print('by class:', dict(stats.most_common()))
print('by geometry:', dict(geom_stats))
