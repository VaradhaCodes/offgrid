import math
# Pure-python S2 cell id (quadratic projection), enough for level-4 tokens.
SWAP, INVERT = 1, 2
kIJtoPos = [[0,1,3,2],[0,3,1,2],[2,3,1,0],[2,1,3,0]]
kPosToOrientation = [SWAP, 0, 0, SWAP|INVERT]

def latlon_to_xyz(lat, lon):
    p, t = math.radians(lat), math.radians(lon)
    c = math.cos(p)
    return (c*math.cos(t), c*math.sin(t), math.sin(p))

def xyz_to_face_uv(x, y, z):
    a = (abs(x), abs(y), abs(z))
    face = a.index(max(a))
    if (x, y, z)[face] < 0: face += 3
    if   face == 0: u, v =  y/x,  z/x
    elif face == 1: u, v = -x/y,  z/y
    elif face == 2: u, v = -x/z, -y/z
    elif face == 3: u, v =  z/x,  y/x
    elif face == 4: u, v =  z/y, -x/y
    else:           u, v = -y/z, -x/z
    return face, u, v

def uv_to_st(u):  # quadratic
    return 0.5*math.sqrt(1+3*u) if u >= 0 else 1-0.5*math.sqrt(1-3*u)

def st_to_ij(s):
    return max(0, min((1 << 30) - 1, int(math.floor(s * (1 << 30)))))

def cellid(lat, lon, level=30):
    face, u, v = xyz_to_face_uv(*latlon_to_xyz(lat, lon))
    i, j = st_to_ij(uv_to_st(u)), st_to_ij(uv_to_st(v))
    orient = face & SWAP
    n = face
    for k in range(29, 29-level, -1):
        ib, jb = (i >> k) & 1, (j >> k) & 1
        pos = kIJtoPos[orient][2*ib + jb]
        n = (n << 2) | pos
        orient ^= kPosToOrientation[pos]
    n = (n << (2*(30-level) + 1)) | (1 << (2*(30-level)))
    return n

def token(cid):
    h = format(cid, '016x').rstrip('0')
    return h if h else 'X'

if __name__ == '__main__':
    pts = {'centre': (28.524416, 77.573818),
           'SW': (28.5133, 77.5639), 'NE': (28.5335, 77.5823),
           'NW': (28.5335, 77.5639), 'SE': (28.5133, 77.5823)}
    for name, (la, lo) in pts.items():
        for lv in (4, 6, 8):
            print(f'{name:7s} L{lv}: {token(cellid(la, lo, lv))}', end='   ')
        print()
    # sanity checks against published S2 examples
    print('sanity Sydney L30 (-33.8688,151.2093):', token(cellid(-33.8688, 151.2093, 30)))
    print('sanity 0,0 L1..3:', [token(cellid(0.0, 0.0, l)) for l in (1,2,3)])
