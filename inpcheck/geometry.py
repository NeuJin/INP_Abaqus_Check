# -*- coding: utf-8 -*-
"""Bang mat element Abaqus + tien ich hinh hoc (stdlib only).

Bang mat dung CORNER NODE (node dinh). Voi element bac 2 (C3D10M, C3D20...)
node giua canh khong tham gia dinh danh mat — du de match/so hinh hoc.
Thu tu mat = S1..S6 theo quy uoc chinh thuc cua Abaqus.
"""
import math

# 0-based index vao tuple connectivity
_FACES_TET = ((0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0))                     # C3D4/C3D10(M): S1..S4
_FACES_HEX = ((0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
              (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0))                       # C3D8(I/R)/C3D20: S1..S6
_FACES_WEDGE = ((0, 1, 2), (3, 5, 4), (0, 3, 4, 1),
                (1, 4, 5, 2), (2, 5, 3, 0))                                   # C3D6/C3D15: S1..S5


def solid_face_table(etype):
    t = etype.upper()
    if t.startswith("C3D4") or t.startswith("C3D10"):
        return _FACES_TET
    if t.startswith("C3D8") or t.startswith("C3D20"):
        return _FACES_HEX
    if t.startswith("C3D6") or t.startswith("C3D15"):
        return _FACES_WEDGE
    return None


def is_solid(etype):
    return etype.upper().startswith("C3D")


def is_skin(etype):
    """Membrane/shell dung lam lop da surface."""
    t = etype.upper()
    return t.startswith("M3D") or t.startswith("S3") or t.startswith("S4") or t.startswith("STRI")


def skin_corner_count(etype):
    t = etype.upper()
    if "3D3" in t or t.startswith("S3") or t.startswith("STRI"):
        return 3
    return 4


def centroid(pts):
    n = len(pts)
    return (sum(p[0] for p in pts) / n,
            sum(p[1] for p in pts) / n,
            sum(p[2] for p in pts) / n)


def dist(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def unit(v):
    l = math.sqrt(dot(v, v))
    if l <= 0.0:
        return (0.0, 0.0, 0.0)
    return (v[0] / l, v[1] / l, v[2] / l)


class Grid(object):
    """Spatial hash don gian: chia khong gian thanh o vuong canh `cell`."""

    def __init__(self, cell):
        self.cell = cell if cell > 0 else 1.0
        self.d = {}

    def _key(self, p):
        c = self.cell
        return (int(math.floor(p[0] / c)),
                int(math.floor(p[1] / c)),
                int(math.floor(p[2] / c)))

    def add(self, p, payload):
        self.d.setdefault(self._key(p), []).append((p, payload))

    def near(self, p):
        """Duyet moi item trong o chua p + 26 o ke."""
        kx, ky, kz = self._key(p)
        get = self.d.get
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    bucket = get((kx + dx, ky + dy, kz + dz))
                    if bucket:
                        for item in bucket:
                            yield item


def cluster_points(pts, radius):
    """Gom cac diem thanh cum (union-find, lien ket khi cach nhau <= radius).
    Tra ve list cum, moi cum la list index vao pts, sap theo size giam dan."""
    n = len(pts)
    if n == 0:
        return []
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    g = Grid(radius if radius > 0 else 1.0)
    for i, p in enumerate(pts):
        g.add(p, i)
    for i, p in enumerate(pts):
        for q, j in g.near(p):
            if j > i and dist(p, q) <= radius:
                union(i, j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return sorted(groups.values(), key=len, reverse=True)
