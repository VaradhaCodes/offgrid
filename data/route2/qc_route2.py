import json, os, csv, math, sys, re
BASE="data/route2/sessions"
dirs=sorted([d for d in os.listdir(BASE) if os.path.isdir(os.path.join(BASE,d))],
            key=lambda s:int(re.search(r'run(\d+)$',s).group(1)))

def ev(p):
    out={}
    with open(p) as f:
        for r in csv.DictReader(f): out[r['type']]=int(r['t_ns'])
    return out

def grav_mean(p, t0, t1):
    sx=sy=sz=0.0; n=0
    with open(p) as f:
        rd=csv.reader(f); next(rd)
        for row in rd:
            t=int(row[0])
            if t<t0: continue
            if t>t1: break
            sx+=float(row[1]); sy+=float(row[2]); sz+=float(row[3]); n+=1
    if not n: return None
    x,y,z=sx/n,sy/n,sz/n
    m=math.hypot(math.hypot(x,y),z)
    return (x/m,y/m,z/m,m,n)

rows=[]
for d in dirs:
    p=os.path.join(BASE,d)
    j=json.load(open(os.path.join(p,'session.json')))
    e=ev(os.path.join(p,'events.csv'))
    st=j['streams']
    ride=None
    if 'RIDE_START' in e and 'STOP_CALIB_START' in e:
        ride=(e['STOP_CALIB_START']-e['RIDE_START'])/1e9
    # gravity orientation over start calib window
    g=None
    if 'CALIB_START' in e and 'CALIB_END' in e:
        g=grav_mean(os.path.join(p,'grav.csv'), e['CALIB_START'], e['CALIB_END'])
    # gnss
    lat=[];lon=[];acc=[]
    with open(os.path.join(p,'gnss_fix.csv')) as f:
        for r in csv.DictReader(f):
            lat.append(float(r['lat'])); lon.append(float(r['lon'])); acc.append(float(r['acc_h']))
    rows.append(dict(
        name=d, run=int(re.search(r'run(\d+)$',d).group(1)), dirn=j['direction'],
        status=j['status'], dur=j['duration_s'], ride=ride,
        acc_rows=st['acc']['rows'], acc_hz=st['acc']['median_hz'], acc_drop=st['acc']['dropped'],
        acc_gaps=st['acc']['gaps_over_50ms'], acc_maxdt=st['acc']['max_dt_ms'],
        gyr_hz=st['gyr']['median_hz'], gyr_drop=st['gyr']['dropped'], gyr_gaps=st['gyr']['gaps_over_50ms'],
        nfix=len(lat), meanacc=sum(acc)/len(acc) if acc else None,
        lat0=lat[0] if lat else None, lon0=lon[0] if lon else None,
        lat1=lat[-1] if lat else None, lon1=lon[-1] if lon else None,
        g=g, missing=','.join(j.get('missing_streams',[])),
    ))
json.dump(rows, open('qc_route2.json','w'), indent=1)

print(f"{'run':>3} {'dir':>3} {'status':>9} {'dur_s':>7} {'ride_s':>7} {'accHz':>6} {'gyrHz':>6} {'drop':>5} {'gaps':>5} {'maxdt':>6} {'fix':>4} {'m_acc':>6}")
for r in rows:
    print(f"{r['run']:>3} {r['dirn']:>3} {r['status']:>9} {r['dur']:>7.1f} {(r['ride'] or 0):>7.1f} "
          f"{(r['acc_hz'] or 0):>6.1f} {(r['gyr_hz'] or 0):>6.1f} {r['acc_drop']+r['gyr_drop']:>5} "
          f"{r['acc_gaps']+r['gyr_gaps']:>5} {r['acc_maxdt']:>6.0f} {r['nfix']:>4} {(r['meanacc'] or 0):>6.2f}")
