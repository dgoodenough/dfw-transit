"""Fit a buildable railway alignment to a line's corridor: straight tangents,
clothoid (spiral) transitions and circular arcs, with a straight section through
every platform and a minimum radius per mode. Numpy only.

Formulation: the alignment is a polygon of intersection points (PIs). Each
station sits on a straight edge B_k -> S_k -> A_k along the corridor's local
direction (total-least-squares fit), so platforms are tangent track. Between
stations the free PIs are Douglas-Peucker vertices of the corridor. Every PI
gets a spiral-arc-spiral fillet; its radius is the largest that keeps the curve
within the corridor tolerance, subject to the tangent length available on both
adjacent edges (shared max-min fairly). A greedy repair loop deletes PIs, slides
platform tangents or rotates a platform heading (up to 15 degrees) to remove
violations. Whatever can't be fixed is reported, never silently kept:
RADIUS_BELOW_MIN (no curve of the minimum radius fits) or OUTSIDE_CORRIDOR (the
curve leaves the corridor tolerance). The geometry is built by integrating the
piecewise-linear curvature profile (closure error under a few cm).

Design parameters live in config.json "geometry". Adapted from the alignment
prototype in the v2 geometry review.
"""
import math

import numpy as np

LAT0, LON0 = 32.8, -97.0
R_KM = 6371.0088
KX = math.radians(1) * R_KM * 1000 * math.cos(math.radians(LAT0))
KY = math.radians(1) * R_KM * 1000
DS = 5.0
HARD = 2.0   # deviation beyond HARD*tol counts as badly as a radius violation


def params(cfg, mode):
    m = dict(cfg["geometry"][mode])
    m["vmax"] = m["vmax_kmh"] / 3.6
    return m


def to_xy(lon, lat):
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


def to_ll(x, y):
    return (x / KX + LON0, y / KY + LAT0)


# ---------------------------------------------------------------- geometry helpers
def cumlen(xy):
    return np.concatenate([[0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])


def resample(xy, ds):
    s = cumlen(xy)
    keep = np.concatenate([[True], np.diff(s) > 1e-9])
    xy, s = xy[keep], s[keep]
    n = max(2, int(math.ceil(s[-1] / ds)) + 1)
    t = np.linspace(0, s[-1], n)
    return np.c_[np.interp(t, s, xy[:, 0]), np.interp(t, s, xy[:, 1])], t, s


def circumradius(xy):
    """3-point circumradius at interior vertices (inf for collinear)."""
    a = xy[:-2]; b = xy[1:-1]; c = xy[2:]
    ab = np.hypot(*(b - a).T); bc = np.hypot(*(c - b).T); ca = np.hypot(*(a - c).T)
    cr = np.abs((b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0])
    with np.errstate(divide="ignore", invalid="ignore"):
        R = ab * bc * ca / (2 * cr)
    R[~np.isfinite(R)] = np.inf
    return R


def pt_to_poly(P, Q, chunk=400):
    """distance from each point of P to polyline Q."""
    A, B = Q[:-1], Q[1:]
    AB = B - A
    L2 = np.maximum((AB ** 2).sum(1), 1e-12)
    out = np.empty(len(P))
    for i in range(0, len(P), chunk):
        p = P[i:i + chunk, None, :]
        t = np.clip(((p - A) * AB).sum(2) / L2, 0, 1)
        d = np.hypot(*(A + t[..., None] * AB - p).transpose(2, 0, 1))
        out[i:i + chunk] = d.min(1)
    return out


def dp(xy, tol, i0, i1, keep):
    stack = [(i0, i1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        d = xy[b] - xy[a]
        L = math.hypot(*d) or 1e-9
        rel = xy[a + 1:b] - xy[a]
        dist = np.abs(rel[:, 0] * d[1] - rel[:, 1] * d[0]) / L
        k = int(np.argmax(dist))
        if dist[k] > tol:
            m = a + 1 + k
            keep.add(m)
            stack += [(a, m), (m, b)]


def tls(P, through=None):
    """total-least-squares line; optionally constrained through a point."""
    c = P.mean(0) if through is None else np.asarray(through, float)
    M = (P - c).T @ (P - c)
    w, v = np.linalg.eigh(M)
    d = v[:, -1]
    if np.dot(P[-1] - P[0], d) < 0:
        d = -d
    return c, d


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


# ---------------------------------------------------------------- spiral-arc-spiral fillet
def fillet(R, Ls, D):
    """Symmetric clothoid-arc-clothoid for deflection D (rad, >0). Returns T, Ls_used, Lc, external offset."""
    if Ls / R > D:              # spirals alone exceed the deflection: shorten (spiral-spiral)
        Ls = R * D
    th = Ls / (2 * R)
    Xs = Ls * (1 - th ** 2 / 10 + th ** 4 / 216)
    Ys = Ls * (th / 3 - th ** 3 / 42 + th ** 5 / 1320)
    p = Ys - R * (1 - math.cos(th))
    k = Xs - R * math.sin(th)
    T = (R + p) * math.tan(D / 2) + k
    Lc = R * (D - 2 * th)
    E = (R + p) / math.cos(D / 2) - R
    return T, Ls, Lc, E


def spiral_len(R, m):
    v = min(m["vmax"], math.sqrt(m["alat"] * R))
    return max(m["min_spiral_m"], v ** 3 / (m["jerk"] * R))


def curve_pts(TS, d_in, sgn, R, Ls, Lc, step=1.0):
    """integrate curvature profile 0->1/R (Ls) , 1/R (Lc), 1/R->0 (Ls). returns pts, kappa."""
    L = 2 * Ls + Lc
    n = max(3, int(math.ceil(L / step)) + 1)
    s = np.linspace(0, L, n)
    if Ls > 0:
        k = np.where(s < Ls, s / (R * Ls), np.where(s < Ls + Lc, 1 / R, (L - s) / (R * Ls)))
    else:
        k = np.full_like(s, 1 / R)
    k = np.clip(k, 0, 1 / R)
    th = np.concatenate([[0], np.cumsum((k[1:] + k[:-1]) / 2 * np.diff(s))])
    th0 = math.atan2(d_in[1], d_in[0])
    h = th0 + sgn * th
    c, sn = np.cos(h), np.sin(h)
    x = np.concatenate([[0], np.cumsum((c[1:] + c[:-1]) / 2 * np.diff(s))])
    y = np.concatenate([[0], np.cumsum((sn[1:] + sn[:-1]) / 2 * np.diff(s))])
    return np.c_[TS[0] + x, TS[1] + y], k


# ---------------------------------------------------------------- the fitter
class Fit:
    """Vertex (PI) polygon formulation.

    Polygon = S_0, A_0, V.., B_1, S_1, A_1, V.., B_2, S_2, ...  where A_k = S_k + a_k d_k and
    B_k = S_k - b_k d_k lie on the station tangent (d_k), so every station sits on a straight
    edge B_k->S_k->A_k; V are Douglas-Peucker vertices of the corridor between stations.
    Every non-station vertex is a PI that receives a spiral-arc-spiral fillet."""

    RGRID = np.geomspace(5, 6000, 70)

    def __init__(self, L, dp_frac=0.5):
        self.L = L
        self.m = m = L["params"]
        self.C, self.s, _ = resample(L["xy"], DS)
        so = cumlen(L["xy"])
        self.s_st = np.array([so[i] for i in L["seg_end"]])
        self.i_st = np.clip(np.searchsorted(self.s, self.s_st), 0, len(self.s) - 1)
        seg_idx = np.clip(np.searchsorted(self.s_st, self.s, side="right") - 1, 0, len(L["grades"]) - 1)
        self.grade = np.array(L["grades"])[seg_idx]
        self.tol = np.array([m["tol"][g] for g in self.grade], float)
        self.dp_frac = dp_frac
        self.flags = []
        self.cache = {}
        self.rot = {}
        self.Tmin = fillet(m["Rmin"], spiral_len(m["Rmin"], m), math.radians(20))[0]

    # ---- polygon ----
    def station_dirs(self):
        half = self.m["Lp"] / 2
        win = max(half, 100.0)
        D = []
        for k, sk in enumerate(self.s_st):
            lo, hi = np.searchsorted(self.s, [sk - win, sk + win])
            idx = np.arange(lo, min(hi, len(self.s) - 1) + 1)
            p, d = tls(self.C[idx], through=self.L["S"][k])
            th = math.radians(self.rot.get(k, 0.0))
            d = np.array([d[0] * math.cos(th) - d[1] * math.sin(th), d[0] * math.sin(th) + d[1] * math.cos(th)])
            D.append(d)
        return D

    def idx_at(self, sval):
        return int(np.clip(np.searchsorted(self.s, sval), 0, len(self.s) - 1))

    def polygon(self, a_scale=None):
        m, C, S = self.m, self.C, self.L["S"]
        half = m["Lp"] / 2
        self.D = D = self.station_dirs()
        n = len(S)
        a_scale = a_scale or {}
        V = []
        for k in range(n):
            V.append(dict(P=S[k], idx=int(self.i_st[k]), kind="S", k=k))
            if k == n - 1:
                break
            ia, ib = int(self.i_st[k]), int(self.i_st[k + 1])
            gap = self.s_st[k + 1] - self.s_st[k]
            tol = self.dp_frac * float(self.tol[ia:ib + 1].min())
            keep = {ia, ib}
            dp(C, tol, ia, ib, keep)
            ks = sorted(keep)[1:-1]
            a = b = half + self.Tmin
            if ks:   # stretch the station tangent while the corridor stays on it
                i = ks[0]; r = C[i] - S[k]
                if abs(cross(r, D[k])) <= tol and np.dot(r, D[k]) > a:
                    a = float(np.dot(r, D[k]))
                i = ks[-1]; r = C[i] - S[k + 1]
                if abs(cross(r, D[k + 1])) <= tol and -np.dot(r, D[k + 1]) > b:
                    b = float(-np.dot(r, D[k + 1]))
            a *= a_scale.get(("A", k), 1.0)
            b *= a_scale.get(("B", k + 1), 1.0)
            lim = 0.47 * gap
            if gap < m["Lp"] + 10:
                self.flags.append(("STATION_GAP_SHORTER_THAN_PLATFORMS", k))
            a, b = min(a, max(lim, half + 2)), min(b, max(lim, half + 2))
            A = S[k] + a * D[k]; B = S[k + 1] - b * D[k + 1]
            V.append(dict(P=A, idx=self.idx_at(self.s_st[k] + a), kind="A", k=k, dist=a))
            for i in ks:
                if self.s[i] > self.s_st[k] + a + 5 and self.s[i] < self.s_st[k + 1] - b - 5:
                    V.append(dict(P=C[i].copy(), idx=i, kind="V", k=k))
            V.append(dict(P=B, idx=self.idx_at(self.s_st[k + 1] - b), kind="B", k=k + 1, dist=b))
        # drop zero-length edges
        out = [V[0]]
        for v in V[1:]:
            if np.linalg.norm(v["P"] - out[-1]["P"]) > 0.5 or v["kind"] == "S":
                out.append(v)
        return out

    # ---- radii ----
    def geom(self, V, j):
        u = V[j]["P"] - V[j - 1]["P"]; w = V[j + 1]["P"] - V[j]["P"]
        lu, lw = np.linalg.norm(u), np.linalg.norm(w)
        u, w = u / lu, w / lw
        cr = cross(u, w)
        Dl = math.atan2(abs(cr), float(np.dot(u, w)))
        return u, w, Dl, (1 if cr > 0 else -1), lu, lw

    def dev_for(self, V, j, R):
        """max distance of the attributable corridor samples from the fillet (cached)."""
        u, w, Dl, sgn, lu, lw = self.geom(V, j)
        i_lo = (V[j - 1]["idx"] + V[j]["idx"]) // 2
        i_hi = (V[j]["idx"] + V[j + 1]["idx"]) // 2
        if i_hi < i_lo:
            i_lo, i_hi = i_hi, i_lo
        key = (tuple(np.round(V[j - 1]["P"], 2)), tuple(np.round(V[j]["P"], 2)), tuple(np.round(V[j + 1]["P"], 2)), i_lo, i_hi, round(R, 3))
        if key in self.cache:
            return self.cache[key]
        Ls = spiral_len(R, self.m)
        T, Ls2, Lc, E = fillet(R, Ls, Dl)
        TS = V[j]["P"] - T * u
        pts, _ = curve_pts(TS, u, sgn, R, Ls2, Lc, step=max(1.0, min(5.0, (2 * Ls2 + Lc) / 40)))
        poly = np.vstack([V[j - 1]["P"], TS, pts, V[j]["P"] + T * w, V[j + 1]["P"]])
        idx = np.arange(i_lo, i_hi + 1, 2)
        dv = float(pt_to_poly(self.C[idx], poly).max()) if len(idx) else 0.0
        tol = float(self.tol[i_lo:i_hi + 1].min()) if i_hi >= i_lo else 40.0
        self.cache[key] = (dv, tol)
        return dv, tol

    def choose(self, V, j, cap):
        m = self.m
        u, w, Dl, sgn, lu, lw = self.geom(V, j)
        if Dl < math.radians(0.05):
            return dict(R=np.inf, Ls=0, dev=0.0, tol=99, Rmax_geo=np.inf, D=Dl, straight=True)
        cand = []
        for R in self.RGRID:
            T = fillet(R, spiral_len(R, m), Dl)[0]
            if T > cap or R > m["Rmax"]:
                break
            cand.append(R)
        if not cand:
            R = 5.0
            dv, tol = self.dev_for(V, j, R)
            return dict(R=R, Ls=spiral_len(R, m), dev=dv, tol=tol, Rmax_geo=0.0, D=Dl, straight=False)
        dt = [self.dev_for(V, j, R) for R in cand]
        ok = [R for R, (dv, tol) in zip(cand, dt) if R >= m["Rmin"] and dv <= tol]
        if ok:
            R = max(ok)                                   # largest radius inside the corridor
        else:
            ge = [(R, dv) for R, (dv, tol) in zip(cand, dt) if R >= m["Rmin"]]
            R = min(ge, key=lambda t: t[1])[0] if ge else cand[-1]   # honour Rmin (flag dev) else flag R
        dv, tol = dt[cand.index(R)]
        return dict(R=R, Ls=spiral_len(R, m), dev=dv, tol=tol, Rmax_geo=cand[-1], D=Dl, straight=False)

    def solve_radii(self, V):
        """Tangent-length budget per edge, shared max-min fairly: first every PI gets the
        tangent it needs for Rmin (if the edge allows), the surplus is split in proportion
        to what each PI would like (its best-fit radius)."""
        m = self.m
        half = m["Lp"] / 2
        PI = [j for j in range(1, len(V) - 1) if V[j]["kind"] != "S"]
        Tmin, Tdes = {}, {}
        for j in PI:
            u, w, Dl, *_ = self.geom(V, j)
            Tmin[j] = fillet(m["Rmin"], spiral_len(m["Rmin"], m), Dl)[0] if Dl > 1e-4 else 0.0
            Tdes[j] = None
        sol = {}
        for it in range(3):
            new = {}
            for j in PI:
                caps = []
                for nb in (j - 1, j + 1):
                    Lg = float(np.linalg.norm(V[j]["P"] - V[nb]["P"]))
                    if V[nb]["kind"] == "S":
                        caps.append(Lg - half); continue
                    avail = Lg - m["Ltmin"]
                    if it == 0:
                        caps.append(avail); continue
                    a_min, b_min = Tmin[j], Tmin[nb]
                    a_des, b_des = max(Tdes[j], a_min), max(Tdes[nb], b_min)
                    if a_des + b_des <= avail:
                        caps.append(avail - b_des if a_des > 0 else avail)  # both fit
                    elif a_min + b_min <= avail:
                        sur = avail - a_min - b_min
                        wa, wb = a_des - a_min, b_des - b_min
                        caps.append(a_min + (sur * wa / (wa + wb) if wa + wb > 0 else sur / 2))
                    else:
                        caps.append(avail * a_min / (a_min + b_min) if a_min + b_min > 0 else avail / 2)
                new[j] = self.choose(V, j, max(min(caps), 0.0))
            sol = new
            for j, r in sol.items():
                Tdes[j] = 0.0 if r["straight"] else fillet(r["R"], r["Ls"], r["D"])[0]
        # enforce: shared edges never overlap (shrink the later PI if needed)
        for j in PI:
            nb = j + 1
            if nb in sol and not sol[j]["straight"] and not sol[nb]["straight"]:
                Lg = float(np.linalg.norm(V[nb]["P"] - V[j]["P"])) - m["Ltmin"]
                if Tdes[j] + Tdes[nb] > Lg + 0.5:
                    sol[nb] = self.choose(V, nb, max(0.0, Lg - Tdes[j]))
                    Tdes[nb] = 0.0 if sol[nb]["straight"] else fillet(sol[nb]["R"], sol[nb]["Ls"], sol[nb]["D"])[0]
        return sol

    def score(self, sol):
        m = self.m
        hard = sum(1 for r in sol.values() if r["dev"] > HARD * r["tol"])
        rv = sum(1 for r in sol.values() if r["R"] < m["Rmin"] - 1e-6)
        dv = sum(1 for r in sol.values() if r["dev"] > r["tol"])
        ex = sum(max(0, r["dev"] - r["tol"]) for r in sol.values())
        return (hard, rv, dv, ex)

    def run(self, max_iter=150):
        m = self.m
        a_scale = {}
        V = self.polygon(a_scale)
        sol = self.solve_radii(V)
        for _ in range(max_iter):
            base = self.score(sol)
            bad = [j for j, r in sol.items() if r["R"] < m["Rmin"] - 1e-6 or r["dev"] > r["tol"]]
            if not bad:
                break
            best = None
            for j in bad:
                trials = []
                for q in (j - 1, j, j + 1):
                    if 0 < q < len(V) - 1 and V[q]["kind"] == "V":
                        trials.append(("del", q))
                    if 0 < q < len(V) - 1 and V[q]["kind"] in "AB":
                        trials.append(("slide", (V[q]["kind"], V[q]["k"])))
                for q in (j - 1, j + 1):
                    if 0 <= q < len(V) and V[q]["kind"] == "S":
                        for dth in (-6, -3, 3, 6):
                            trials.append(("rot", (V[q]["k"], dth)))
                for t in trials:
                    rot0 = self.rot
                    if t[0] == "del":
                        V2 = V[:t[1]] + V[t[1] + 1:]
                        a2 = a_scale
                    else:
                        a2 = dict(a_scale)
                        if t[0] == "slide":
                            a2[t[1]] = a2.get(t[1], 1.0) * 1.3
                        else:
                            k, dth = t[1]
                            if abs(self.rot.get(k, 0.0) + dth) > 15:
                                continue
                            self.rot = dict(rot0); self.rot[k] = rot0.get(k, 0.0) + dth
                        V2 = self.polygon(a2)
                        keepidx = {v["idx"] for v in V if v["kind"] == "V"}
                        V2 = [v for v in V2 if v["kind"] != "V" or v["idx"] in keepidx]
                    s2 = self.solve_radii(V2)
                    sc = self.score(s2)
                    if sc < base and (best is None or sc < best[0]):
                        best = (sc, V2, s2, a2, self.rot)
                    self.rot = rot0
                if best is not None and best[0][:3] < base[:3]:
                    break
            if best is None:
                break
            _, V, sol, a_scale, self.rot = best
        self.V, self.sol = V, sol
        for j, r in sol.items():
            if r["R"] < m["Rmin"] - 1e-6:
                self.flags.append(("RADIUS_BELOW_MIN", j, round(r["R"]), round(r["Rmax_geo"])))
            elif r["dev"] > r["tol"]:
                self.flags.append(("OUTSIDE_CORRIDOR", j, round(r["dev"]), r["tol"]))
        return self.build()

    # ---- geometry ----
    def build(self):
        V, sol = self.V, self.sol
        pts = [V[0]["P"][None, :]]
        kap = [np.zeros(1)]
        self.curves = []
        for j in range(1, len(V)):
            if j == len(V) - 1 or j not in sol or sol[j]["straight"]:
                target = V[j]["P"]; c = None
            else:
                r = sol[j]
                u, w, Dl, sgn, lu, lw = self.geom(V, j)
                T, Ls, Lc, E = fillet(r["R"], r["Ls"], Dl)
                target = V[j]["P"] - T * u
                c, k = curve_pts(target, u, sgn, r["R"], Ls, Lc, step=1.0)
                ST = V[j]["P"] + T * w
                r.update(T=T, Ls_used=Ls, Lc=Lc, D_deg=math.degrees(Dl), closure_m=float(np.linalg.norm(c[-1] - ST)))
                c[-1] = ST
                self.curves.append(r)
            prev = pts[-1][-1]
            Lt = float(np.linalg.norm(target - prev))
            if Lt > 2e5:
                raise ValueError("degenerate fillet")
            if Lt > 1e-6:
                nn = max(2, int(Lt / DS) + 1)
                seg = prev + np.linspace(0, 1, nn)[1:, None] * (target - prev)
                pts.append(seg); kap.append(np.zeros(len(seg)))
            if c is not None:
                pts.append(c[1:]); kap.append(k[1:])
        self.out = np.vstack(pts)
        self.kappa = np.concatenate(kap)
        return self.out


# ---------------------------------------------------------------- run-time with curve speed limits
def runtime(curv_R_at_s, s_grid, stop_s, m, vcap=None):
    """kinematic min-time: v <= vmax, v <= sqrt(alat R), stop at each station, accel/decel limits."""
    vmax = m["vmax"] if vcap is None else vcap
    vlim = np.minimum(vmax, np.sqrt(m["alat"] * curv_R_at_s))
    stop_idx = np.searchsorted(s_grid, stop_s).clip(0, len(s_grid) - 1)
    vlim[stop_idx] = 0
    ds = np.diff(s_grid)
    v = vlim.copy()
    for i in range(1, len(v)):
        v[i] = min(v[i], math.sqrt(v[i - 1] ** 2 + 2 * m["acc"] * ds[i - 1]))
    for i in range(len(v) - 2, -1, -1):
        v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + 2 * m["dec"] * ds[i]))
    vm = np.maximum((v[1:] + v[:-1]) / 2, 0.3)
    t = float((ds / vm).sum()) + m["dwell"] * (len(stop_s) - 2)
    return t / 60




def fit_line(pts_lonlat, seg_end, grades, stations_lonlat, m):
    """Fit one line. pts_lonlat: the joined corridor polyline; seg_end: vertex index of
    each station along it; stations_lonlat: station coordinates in order.
    Returns (segments, report): one lon/lat polyline per consecutive stop pair, each
    starting and ending exactly at its stations, and a dict of metrics and flags."""
    xy = np.array([to_xy(*p) for p in pts_lonlat])
    S = np.array([to_xy(*p) for p in stations_lonlat])
    F = Fit(dict(xy=xy, seg_end=seg_end, grades=grades, S=S, params=m))
    try:
        new = F.run()
        ok = np.isfinite(new).all() and float(pt_to_poly(new[::5], F.C).max()) < 1000
    except (ValueError, MemoryError, FloatingPointError, IndexError):
        ok = False
    if not ok:  # degenerate corridor (e.g. a near U-turn): keep the drawn line, flag it
        segs = [list(pts_lonlat[seg_end[k]:seg_end[k + 1] + 1]) for k in range(len(seg_end) - 1)]
        for k, sg in enumerate(segs):
            sg[0], sg[-1] = stations_lonlat[k], stations_lonlat[k + 1]
        return segs, dict(min_radius_m=float("nan"), curves_below_min=-1, max_deviation_m=0.0, mean_deviation_m=0.0,
                          length_change_pct=0.0, flags=[("FIT_FAILED", 0)], flag_where=[], failed=True)
    idx = [int(np.argmin(np.hypot(*(new - s).T))) for s in S]
    segs = []
    for k in range(len(idx) - 1):
        seg = new[idx[k]: idx[k + 1] + 1]
        seg = np.vstack([S[k], seg[1:-1], S[k + 1]])
        seg = seg[np.r_[True, np.hypot(*np.diff(seg, axis=0).T) > 0.5]]
        segs.append([to_ll(*p) for p in _thin(seg)])
    dev = pt_to_poly(F.C, new)
    R = np.array([r["R"] for r in F.curves]) if F.curves else np.array([np.inf])
    report = dict(
        min_radius_m=float(R.min()),
        curves_below_min=int((R < m["Rmin"] - 1e-6).sum()),
        max_deviation_m=float(dev.max()), mean_deviation_m=float(dev.mean()),
        length_change_pct=100 * (cumlen(new)[-1] / cumlen(xy)[-1] - 1),
        flags=[f for f in F.flags if f[0] in ("RADIUS_BELOW_MIN", "OUTSIDE_CORRIDOR", "STATION_GAP_SHORTER_THAN_PLATFORMS")],
        flag_where=[_flag_where(F, f) for f in F.flags if f[0] in ("RADIUS_BELOW_MIN", "OUTSIDE_CORRIDOR")],
    )
    return segs, report


def _flag_where(F, f):
    """Index of the station nearest a flagged PI."""
    j = f[1]
    P = F.V[j]["P"] if j < len(F.V) else F.V[-1]["P"]
    return int(np.argmin(np.hypot(*(F.L["S"] - P).T)))


def _thin(seg, tol=0.05):
    """Drop interior points of straight runs (keeps curves dense, tangents as endpoints)."""
    if len(seg) < 3:
        return seg
    keep = [0]
    for i in range(1, len(seg) - 1):
        a, b, c = seg[keep[-1]], seg[i], seg[i + 1]
        u, w = b - a, c - b
        nu, nw = np.hypot(*u), np.hypot(*w)
        if nu < 1e-9 or nw < 1e-9:
            continue
        if abs(u[0] * w[1] - u[1] * w[0]) / (nu * nw) > 1e-4 or nu > 500:
            keep.append(i)
    keep.append(len(seg) - 1)
    return seg[keep]


def chord_radii(pts_lonlat, step=20.0, half=60.0):
    """Radius (m) along a polyline measured on a step-m resampling with chords +-half m
    (resolution-independent: vertex noise doesn't create fake tight radii)."""
    xy = np.array([to_xy(*p) for p in pts_lonlat])
    if len(xy) < 2 or cumlen(xy)[-1] < 2 * half:
        return np.array([np.inf])
    Q = resample(xy, step)[0]
    k = max(1, int(half // step))
    a, b, c = Q[:-2 * k], Q[k:-k], Q[2 * k:]
    ab, bc, ca = np.hypot(*(b - a).T), np.hypot(*(c - b).T), np.hypot(*(a - c).T)
    cr = np.abs((b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0])
    with np.errstate(divide="ignore", invalid="ignore"):
        R = ab * bc * ca / (2 * cr)
    R[~np.isfinite(R)] = np.inf
    return R


def station_slides(pts_lonlat, seg_end, m, max_move, movable):
    """Suggest moving stations along the corridor (at most max_move m) to the
    straightest spot within reach, so the platform can sit on tangent track.
    movable[k] False keeps station k where it is. Returns {k: (lon, lat, moved_m)}."""
    xy = np.array([to_xy(*p) for p in pts_lonlat])
    C, s, _ = resample(xy, DS)
    so = cumlen(xy)
    s_st = np.array([so[i] for i in seg_end])
    h = np.unwrap(np.arctan2(*np.diff(C, axis=0).T[::-1]))
    half = m["Lp"] / 2
    out = {}
    for k, sk in enumerate(s_st):
        if not movable[k] or k in (0, len(s_st) - 1):
            continue
        lo = max(sk - max_move, (s_st[k - 1] + sk) / 2 + half)
        hi = min(sk + max_move, (sk + s_st[k + 1]) / 2 - half)

        def bend(sv):
            a, b = np.searchsorted(s, [sv - half, sv + half])
            a, b = max(a, 0), min(b, len(h) - 1)
            return float(np.ptp(h[a:b + 1])) if b > a else 0.0
        here = bend(sk)
        if here < math.radians(8) or hi <= lo:
            continue
        cands = np.arange(lo, hi + 1e-6, DS)
        scores = np.array([bend(c) for c in cands])
        best = float(scores.min())
        if best > here - math.radians(5):
            continue
        sv = float(cands[np.flatnonzero(scores <= best + 1e-9)][np.argmin(np.abs(cands[scores <= best + 1e-9] - sk))])
        p = C[int(np.clip(np.searchsorted(s, sv), 0, len(C) - 1))]
        out[k] = (*to_ll(*p), abs(sv - sk))
    return out


def denoise(pts_lonlat, tol=8.0):
    """Remove out-and-back spikes (heading reversal > 150 deg) and vertex jitter
    (Douglas-Peucker at tol m) from a road- or track-following polyline."""
    xy = np.array([to_xy(*p) for p in pts_lonlat])
    if len(xy) < 3:
        return pts_lonlat
    changed = True
    while changed and len(xy) > 2:
        changed = False
        for i in range(1, len(xy) - 1):
            u, w = xy[i] - xy[i - 1], xy[i + 1] - xy[i]
            nu, nw = np.hypot(*u), np.hypot(*w)
            if nu < 1e-6 or nw < 1e-6 or np.dot(u, w) / (nu * nw) < -0.866:
                xy = np.delete(xy, i, axis=0)
                changed = True
                break
    keep = {0, len(xy) - 1}
    dp(xy, tol, 0, len(xy) - 1, keep)
    return [to_ll(*xy[i]) for i in sorted(keep)]
