# -*- coding: utf-8 -*-
"""Cac phep kiem tra. Moi check tra ve list Finding(sev, check, file, line, msg).

sev: "ERROR" (gan nhu chac chan la loi) | "WARN" (nghi van, can xac nhan)
     | "INFO" (thong tin de soat)
"""
from collections import namedtuple, Counter

from .geometry import (solid_face_table, is_solid, is_skin, skin_corner_count,
                       centroid, dist, sub, cross, dot, unit, tri_area,
                       Grid, cluster_points)

Finding = namedtuple("Finding", "sev check file line msg")

CK_STRUCT = "1. CAU TRUC / INCLUDE"
CK_SYMBOL = "2. THAM CHIEU (symbol table)"
CK_PARAM = "3. PARAMETER"
CK_SECTION = "4. SECTION / MATERIAL"
CK_LOAD = "5. TAI / BC <-> MESH"
CK_SHARE = "6. SHARE NODE"
CK_GEOM = "7. HINH HOC CONTACT/SURFACE"
CK_OFF = "8. SETUP DANG TAT (comment)"
CK_STEP = "9. TONG QUAN STEP"
CK_GROUP = "10. GROUP CONTACT/TIE (so khop 2 phia)"

CHECK_ORDER = [CK_STRUCT, CK_SYMBOL, CK_PARAM, CK_SECTION, CK_LOAD,
               CK_SHARE, CK_GEOM, CK_GROUP, CK_OFF, CK_STEP]


def _fmt_pt(p):
    return "(%.4f, %.4f, %.4f)" % p


# ==================================================================== #
# 1. CAU TRUC / INCLUDE
# ==================================================================== #
def check_structure(reader):
    F = []
    for f, l, target in reader.missing_includes:
        F.append(Finding("ERROR", CK_STRUCT, f, l,
                         "*INCLUDE tro toi file KHONG ton tai: %s" % target))
    resolved = Counter(r for (_f, _l, _t, r) in reader.includes if r)
    for path, n in resolved.items():
        if n > 1:
            F.append(Finding("WARN", CK_STRUCT, path, 0,
                             "file duoc include %d lan (dinh nghia se bi nhan doi?)" % n))
    for f, l, target, exists in reader.commented_includes:
        if exists:
            F.append(Finding("INFO", CK_STRUCT, f, l,
                             "include dang TAT (file dich ton tai): %s" % target))
        else:
            F.append(Finding("WARN", CK_STRUCT, f, l,
                             "include dang TAT va file dich KHONG ton tai: %s "
                             "(bo comment se crash)" % target))
    for path, msg in reader.read_errors:
        F.append(Finding("ERROR", CK_STRUCT, path, 0, msg))
    if reader.orphan_data:
        f, l, txt = reader.orphan_data[0]
        F.append(Finding("WARN", CK_STRUCT, f, l,
                         "%d dong data khong thuoc keyword nao (vd: %s)"
                         % (len(reader.orphan_data), txt[:50])))
    return F


# ==================================================================== #
# 2. THAM CHIEU
# ==================================================================== #
def _missing_refs(F, refs, defined, kind, extra=frozenset()):
    seen = {}
    for name, ctx, f, l in refs:
        if name in defined or name in extra:
            continue
        if name in seen:
            seen[name][0] += 1
        else:
            seen[name] = [1, ctx, f, l]
    for name in sorted(seen):
        n, ctx, f, l = seen[name]
        F.append(Finding("ERROR", CK_SYMBOL, f, l,
                         "%s '%s' duoc tham chieu (%s%s) nhung KHONG dinh nghia"
                         % (kind, name, ctx, ", +%d cho khac" % (n - 1) if n > 1 else "")))


def _unused(F, defined_names, refs, kind, skip=frozenset(), sev="INFO"):
    used = set(name for name, _c, _f, _l in refs)
    unused = sorted(n for n in defined_names if n not in used and n not in skip)
    if unused:
        shown = ", ".join(unused[:15]) + (" ..." if len(unused) > 15 else "")
        F.append(Finding(sev, CK_SYMBOL, "", 0,
                         "%d %s dinh nghia nhung khong ai tham chieu: %s"
                         % (len(unused), kind, shown)))


def check_symbols(model):
    m = model
    F = []
    # ---- tham chieu thieu ----
    _missing_refs(F, m.surface_refs, set(m.surfaces), "SURFACE")
    _missing_refs(F, m.nset_refs, set(m.nsets), "NSET")
    _missing_refs(F, m.elset_refs, set(m.elsets), "ELSET")
    _missing_refs(F, m.interaction_refs, set(m.interactions), "SURFACE INTERACTION")
    _missing_refs(F, m.material_refs, set(m.materials), "MATERIAL")
    _missing_refs(F, m.amplitude_refs, set(m.amplitudes), "AMPLITUDE")
    # ---- surface element-based tro element khong ton tai (stale sau remesh) ----
    for name, surf in sorted(m.surfaces.items()):
        if surf.kind != "ELEMENT":
            continue
        missing = [(ref, f, l) for (ref, face, f, l) in surf.items
                   if isinstance(ref, int) and ref not in m.elements]
        if missing:
            ref, f, l = missing[0]
            F.append(Finding("ERROR", CK_SYMBOL, f, l,
                             "SURFACE '%s' tro toi %d element KHONG ton tai "
                             "(vd elem %d) - surface bi stale sau remesh?"
                             % (name, len(missing), ref)))
        if not surf.items:
            f, l = surf.defs[0]
            F.append(Finding("WARN", CK_SYMBOL, f, l,
                             "SURFACE '%s' (TYPE=ELEMENT) khong co dong data nao" % name))
    # ---- dinh nghia trung ----
    for name, surf in sorted(m.surfaces.items()):
        if len(surf.defs) > 1:
            f, l = surf.defs[1]
            F.append(Finding("WARN", CK_SYMBOL, f, l,
                             "SURFACE '%s' dinh nghia %d lan (lan dau: %s:%d)"
                             % (name, len(surf.defs), surf.defs[0][0], surf.defs[0][1])))
    # ---- dinh nghia khong dung (surface = group -> WARN theo yeu cau) ----
    _unused(F, m.surfaces, m.surface_refs, "SURFACE (group assign ma khong dung)",
            sev="WARN")
    _unused(F, m.interactions, m.interaction_refs, "SURFACE INTERACTION")
    _unused(F, m.materials, m.material_refs, "MATERIAL")
    _unused(F, m.nsets, m.nset_refs, "NSET")
    if m.unknown_keywords:
        items = ", ".join("%s(%d)" % (k, v) for k, v in m.unknown_keywords.most_common(10))
        F.append(Finding("INFO", CK_SYMBOL, "", 0,
                         "keyword chua duoc parser xu ly (chi ghi nhan): %s" % items))
    for f, l, msg in model.malformed[:20]:
        F.append(Finding("WARN", CK_SYMBOL, f, l, msg))
    return F


# ==================================================================== #
# 3. PARAMETER
# ==================================================================== #
def check_parameters(model, reader):
    m = model
    F = []
    for name in sorted(m.param_refs):
        ctx, f, l = m.param_refs[name]
        if name not in m.parameters:
            F.append(Finding("ERROR", CK_PARAM, f, l,
                             "tham chieu <%s> (trong *%s) nhung *PARAMETER khong dinh nghia"
                             % (name, ctx)))
    seen_c = set()
    for name, f, l in reader.comment_param_refs:
        if name not in m.parameters and name not in seen_c:
            seen_c.add(name)
            F.append(Finding("WARN", CK_PARAM, f, l,
                             "<%s> nam trong dong dang COMMENT va chua duoc dinh nghia "
                             "- bo comment se fail" % name))
    used = set(m.param_refs) | set(n for n, _f, _l in reader.comment_param_refs)
    unused = sorted(p for p in m.parameters if p not in used)
    if unused:
        F.append(Finding("INFO", CK_PARAM, "", 0,
                         "parameter dinh nghia nhung khong dung: %s" % ", ".join(unused)))
    return F


# ==================================================================== #
# 4. SECTION / MATERIAL
# ==================================================================== #
def check_sections(model):
    m = model
    F = []
    sectioned = {}
    for kind, elset, mat, f, l in m.sections:
        if not elset:
            F.append(Finding("WARN", CK_SECTION, f, l, "*%s thieu ELSET=" % kind))
            continue
        if elset in sectioned:
            F.append(Finding("WARN", CK_SECTION, f, l,
                             "ELSET '%s' co 2 section (lan dau: %s:%d)"
                             % (elset, sectioned[elset][1], sectioned[elset][2])))
        sectioned[elset] = (kind, f, l)
        if elset in m.elsets and not m.elset_ids(elset):
            F.append(Finding("WARN", CK_SECTION, f, l,
                             "*%s gan vao ELSET '%s' RONG (0 element)" % (kind, elset)))
    covered = set()
    for es in sectioned:
        covered.update(m.elset_ids(es))
    uncovered = Counter()
    for eid in m.elements:
        if eid not in covered:
            uncovered[m.elem_elset.get(eid, "") or "(khong elset)"] += 1
    for elset, n in sorted(uncovered.items(), key=lambda kv: -kv[1]):
        F.append(Finding("ERROR", CK_SECTION, "", 0,
                         "%d element cua '%s' KHONG thuoc section nao "
                         "(thieu *SOLID/MEMBRANE SECTION?)" % (n, elset)))
    return F


# ==================================================================== #
# 5. TAI / BC <-> MESH
# ==================================================================== #
def check_loads(model):
    m = model
    F = []
    # BC tro node id khong ton tai
    miss_bc = sorted(nid for nid in m.boundary_nodes if nid not in m.nodes)
    for nid in miss_bc[:10]:
        f, l = m.boundary_nodes[nid]
        F.append(Finding("ERROR", CK_LOAD, f, l,
                         "*BOUNDARY tro node %d KHONG ton tai" % nid))
    if len(miss_bc) > 10:
        F.append(Finding("ERROR", CK_LOAD, "", 0,
                         "... tong %d node BOUNDARY khong ton tai" % len(miss_bc)))
    # CLOAD tro node khong ton tai (diem ghep voi tool map luc ngoai)
    miss = sorted(nid for nid in m.cload_nodes if nid not in m.nodes)
    for nid in miss[:10]:
        f, l = m.cload_nodes[nid]
        F.append(Finding("ERROR", CK_LOAD, f, l,
                         "*CLOAD tro node %d KHONG ton tai "
                         "(mesh doi ma file luc chua sinh lai?)" % nid))
    if len(miss) > 10:
        F.append(Finding("ERROR", CK_LOAD, "", 0,
                         "... tong %d node CLOAD khong ton tai" % len(miss)))
    # CLOAD vao node "long" (khong thuoc element, khong phai ref node hop le)
    allowed = set()
    for node, _surf, _f, _l in m.pretensions:
        if node is None:
            continue
        try:
            allowed.add(int(node))
        except (TypeError, ValueError):
            allowed.update(m.nset_ids(str(node)))
    for _c, ref, _s, _f, _l in m.couplings:
        if ref is None:
            continue
        try:
            allowed.add(int(ref))
        except (TypeError, ValueError):
            allowed.update(m.nset_ids(str(ref)))
    for ref, _a, _f, _l in m.rigidbodies:
        if ref is None:
            continue
        try:
            allowed.add(int(ref))
        except (TypeError, ValueError):
            allowed.update(m.nset_ids(str(ref)))
    loose = sorted(nid for nid in m.cload_nodes
                   if nid in m.nodes and nid not in m.node_used and nid not in allowed)
    if loose:
        f, l = m.cload_nodes[loose[0]]
        F.append(Finding("WARN", CK_LOAD, f, l,
                         "%d node nhan CLOAD nhung khong thuoc element nao va khong phai "
                         "ref node cua coupling/pretension/rigid body (vd node %d) "
                         "- luc se khong truyen di dau" % (len(loose), loose[0])))
    if m.cload_nodes:
        F.append(Finding("INFO", CK_LOAD, "", 0,
                         "CLOAD: %d dong, %d node rieng biet nhan luc truc tiep"
                         % (m.cload_total_lines, len(m.cload_nodes))))
    # phu thuoc odb (INITIAL CONDITIONS, FILE=...)
    for ctype, fpar, spar, f, l in m.initialconds:
        if fpar:
            F.append(Finding("INFO", CK_LOAD, f, l,
                             "*INITIAL CONDITIONS TYPE=%s doc tu FILE=%s (STEP=%s) "
                             "- mesh doi thi PHAI chay lai bai do truoc" % (ctype, fpar, spar)))
    return F


# ==================================================================== #
# 6. SHARE NODE
# ==================================================================== #
def check_shared_nodes(model, tol):
    m = model
    F = []
    if not m.nodes:
        return [Finding("ERROR", CK_SHARE, "", 0, "khong doc duoc node nao tu deck")]
    grid = Grid(tol)
    items = list(m.nodes.items())
    for nid, p in items:
        grid.add(p, nid)
    pairs = []
    for nid, p in items:
        for q, other in grid.near(p):
            if other > nid and dist(p, q) <= tol:
                pairs.append((nid, other))
    if not pairs:
        F.append(Finding("INFO", CK_SHARE, "", 0,
                         "khong co cap node trung toa do (tol=%g)" % tol))
        return F
    # node -> cac elset su dung no
    node_elsets = {}
    for eid, (etype, nds) in m.elements.items():
        es = m.elem_elset.get(eid, "") or "?"
        for nid in nds:
            s = node_elsets.get(nid)
            if s is None:
                node_elsets[nid] = {es}
            else:
                s.add(es)
    critical = [(a, b) for a, b in pairs
                if a in m.node_used and b in m.node_used]
    n_ignored = len(pairs) - len(critical)
    F.append(Finding("INFO", CK_SHARE, "", 0,
                     "%d cap node trung toa do; %d cap ca 2 node deu duoc element dung "
                     "(loai %d cap co node tu do/ref node)"
                     % (len(pairs), len(critical), n_ignored)))
    if not critical:
        return F

    # ---- phan loai theo contact/tie: 2 lop node CO CHU DICH hay LOI? ----
    # node thuoc surface nao (chi surface element-based)
    node_surfs = {}
    for sname, surf in m.surfaces.items():
        if surf.kind != "ELEMENT":
            continue
        for _key, ordered, _eid in _resolve_surface_faces(m, surf):
            for nid in ordered:
                s = node_surfs.get(nid)
                if s is None:
                    node_surfs[nid] = {sname}
                else:
                    s.add(sname)
    # cap surface nao co contact/tie
    cp_label = {}
    for sl, ms, _inter, _step, _f, _l in m.contact_pairs:
        cp_label.setdefault(frozenset((sl, ms)), "CONTACT %s<->%s" % (sl, ms))
    for _name, sl, ms, _pt, _step, _f, _l in m.ties:
        cp_label.setdefault(frozenset((sl, ms)), "TIE %s<->%s" % (sl, ms))

    def pair_contact(a, b):
        sa = node_surfs.get(a)
        sb = node_surfs.get(b)
        if not sa or not sb:
            return None
        for x in sa:
            for y in sb:
                lb = cp_label.get(frozenset((x, y)))
                if lb:
                    return lb
        return None

    # gom nhom theo CAP ELSET truoc (Upper<->Lower khac Bush<->Bore),
    # roi cluster khong gian trong tung nhom (ban kinh = 3 lan canh element)
    groups = {}
    for i, (a, b) in enumerate(critical):
        ea = ",".join(sorted(node_elsets.get(a, ["?"])))
        eb = ",".join(sorted(node_elsets.get(b, ["?"])))
        groups.setdefault(tuple(sorted((ea, eb))), []).append(i)
    radius = 3.0 * m.median_edge
    vung = 0
    results = []
    for key in sorted(groups):
        gidx = groups[key]
        pts = [m.nodes[critical[i][0]] for i in gidx]
        for cl in cluster_points(pts, radius):
            sel = [gidx[j] for j in cl]
            c = centroid([m.nodes[critical[i][0]] for i in sel])
            labels = Counter()
            uncov = 0
            for i in sel:
                lb = pair_contact(*critical[i])
                if lb:
                    labels[lb] += 1
                else:
                    uncov += 1
            results.append((key, sel, c, labels, uncov))
    # ERROR truoc, WARN giua, INFO cuoi de dot vao mat loi that
    def rank(r):
        _k, sel, _c, labels, uncov = r
        if uncov == 0 and labels:
            return 2
        if labels:
            return 1
        return 0
    results.sort(key=lambda r: (rank(r), -len(r[1])))
    for key, sel, c, labels, uncov in results:
        vung += 1
        n = len(sel)
        a0, b0 = critical[sel[0]]
        es_a = ",".join(sorted(node_elsets.get(a0, ["?"])))
        es_b = ",".join(sorted(node_elsets.get(b0, ["?"])))
        base = ("VUNG %d: %d cap node trung toa do quanh %s | vd node %d/%d | %s <-> %s"
                % (vung, n, _fmt_pt(c), a0, b0, es_a, es_b))
        if uncov == 0 and labels:
            lb = labels.most_common(1)[0][0]
            F.append(Finding("INFO", CK_SHARE, "", 0,
                             base + " = vung %s (2 lop node CO CHU DICH)" % lb))
        elif labels:
            lb = labels.most_common(1)[0][0]
            F.append(Finding("WARN", CK_SHARE, "", 0,
                             base + " | %d/%d cap thuoc %s nhung %d cap NGOAI surface "
                             "contact - mep contact chon thieu element hoac mat share "
                             "node sat vung contact" % (n - uncov, n, lb, uncov)))
        else:
            F.append(Finding("ERROR", CK_SHARE, "", 0,
                             base + " | KHONG thuoc contact/tie nao -> nghi MAT SHARE NODE"))
    return F


# ==================================================================== #
# 7. HINH HOC CONTACT / SURFACE
# ==================================================================== #
def _face_key(ids):
    return tuple(sorted(ids))


def _face_edges(ordered):
    n = len(ordered)
    out = []
    for i in range(n):
        a, b = ordered[i], ordered[(i + 1) % n]
        out.append((a, b) if a < b else (b, a))
    return out


def _resolve_surface_faces(m, surf):
    """Tra ve list (key, ordered_ids, eid). Bo qua item khong resolve duoc."""
    out = []
    for ref, face, f, l in surf.items:
        eids = [ref] if isinstance(ref, int) else m.elset_ids(ref)
        for eid in eids:
            el = m.elements.get(eid)
            if el is None:
                continue
            etype, nds = el
            if is_skin(etype):
                n = min(skin_corner_count(etype), len(nds))
                ordered = tuple(nds[:n])
                out.append((_face_key(ordered), ordered, eid))
            elif is_solid(etype):
                ft = solid_face_table(etype)
                if ft is None or not face or not face.startswith("S"):
                    continue
                try:
                    fi = int(face[1:]) - 1
                except ValueError:
                    continue
                if fi < 0 or fi >= len(ft):
                    continue
                try:
                    ordered = tuple(nds[i] for i in ft[fi])
                except IndexError:
                    continue
                out.append((_face_key(ordered), ordered, eid))
    return out


def _face_geo(m, ordered):
    pts = [m.nodes[n] for n in ordered if n in m.nodes]
    if len(pts) < 3:
        return None
    c = centroid(pts)
    r = max(dist(c, p) for p in pts)
    nrm = unit(cross(sub(pts[1], pts[0]), sub(pts[2], pts[0])))
    return c, r, nrm


def check_geometry(model, gap_tol=None, coin_tol=None, pen_tol=None):
    m = model
    F = []
    if not m.elements:
        return F
    if gap_tol is None:
        gap_tol = 0.2 * m.median_edge
    if coin_tol is None:
        coin_tol = max(1e-3, 0.01 * m.median_edge)
    if pen_tol is None:
        pen_tol = 0.1 * m.median_edge

    # ---- ban do mat: key -> [count, eid, face_idx] ----
    face_map = {}
    for eid, (etype, nds) in m.elements.items():
        if not is_solid(etype):
            continue
        ft = solid_face_table(etype)
        if ft is None:
            continue
        for fi, fidx in enumerate(ft):
            try:
                ids = tuple(nds[i] for i in fidx)
            except IndexError:
                continue
            key = _face_key(ids)
            ent = face_map.get(key)
            if ent is None:
                face_map[key] = [1, eid, fi]
            else:
                ent[0] += 1

    # ---- resolve moi surface element-based ----
    surf_faces = {}
    all_surf_keys = set()
    for name, surf in m.surfaces.items():
        if surf.kind != "ELEMENT":
            continue
        faces = _resolve_surface_faces(m, surf)
        surf_faces[name] = faces
        for key, _o, _e in faces:
            all_surf_keys.add(key)

    # ---- 7a. LO THUNG trong surface (chon thieu element) ----
    for name in sorted(surf_faces):
        faces = surf_faces[name]
        if not faces:
            continue
        # chi ap dung cho surface tren solid (mat S#)
        solid_faces = [(k, o, e) for k, o, e in faces
                       if is_solid(m.elements[e][0])]
        if not solid_faces:
            continue
        skeys = set(k for k, _o, _e in solid_faces)
        edge_set = set()
        for _k, ordered, _e in solid_faces:
            edge_set.update(_face_edges(ordered))
        parts = set(m.elem_elset.get(e, "") for _k, _o, e in solid_faces)
        holes = []
        for key, (cnt, eid, fi) in face_map.items():
            if cnt != 1 or key in skeys:
                continue
            if m.elem_elset.get(eid, "") not in parts:
                continue
            etype, nds = m.elements[eid]
            ft = solid_face_table(etype)
            ordered = tuple(nds[i] for i in ft[fi])
            shared = sum(1 for e in _face_edges(ordered) if e in edge_set)
            if shared >= 2:
                geo = _face_geo(m, ordered)
                holes.append((shared, eid, fi + 1, geo[0] if geo else (0, 0, 0)))
        holes.sort(reverse=True)
        for shared, eid, sno, c in holes[:20]:
            F.append(Finding("WARN", CK_GEOM, "", 0,
                             "SURFACE '%s': nghi thieu element %d (mat S%d, %d canh giap "
                             "surface) tai %s" % (name, eid, sno, shared, _fmt_pt(c))))
        if len(holes) > 20:
            F.append(Finding("WARN", CK_GEOM, "", 0,
                             "SURFACE '%s': ... tong %d mat nghi thieu" % (name, len(holes))))

    # ---- 7b. DO PHU contact/tie: moi mat slave phai duoc master phu ----
    pairs = []
    for slave, master, inter, step, f, l in m.contact_pairs:
        pairs.append((slave, master, "CONTACT PAIR", None, f, l))
    for name, slave, master, postol, step, f, l in m.ties:
        pairs.append((slave, master, "TIE %s" % (name or ""), postol, f, l))
    for slave, master, label, postol, f, l in pairs:
        sf = surf_faces.get(slave)
        mf = surf_faces.get(master)
        if not sf or not mf:
            continue  # analytical / node-based / undefined -> bo qua
        gap = postol if postol is not None else gap_tol
        mgeo = []
        rmax = 0.0
        master_skin = False
        for key, ordered, eid in mf:
            g = _face_geo(m, ordered)
            if not g:
                continue
            c, r, nrm = g
            el = m.elements.get(eid)
            if el is not None and is_skin(el[0]):
                master_skin = True  # membrane: khong biet huong ngoai -> bo phan dau
            elif el is not None:
                pts_e = [m.nodes[n] for n in el[1] if n in m.nodes]
                if pts_e:
                    ec = centroid(pts_e)
                    if dot(nrm, sub(c, ec)) < 0.0:
                        nrm = (-nrm[0], -nrm[1], -nrm[2])  # phap tuyen huong RA ngoai
            mgeo.append((c, r, nrm))
            if r > rmax:
                rmax = r
        if not mgeo:
            continue
        grid = Grid(rmax + gap + pen_tol)
        for c, r, nrm in mgeo:
            grid.add(c, (r, nrm, c))
        uncovered = []
        samples = []   # (diem tren slave, khoang cach co dau toi master)
        for key, ordered, eid in sf:
            g = _face_geo(m, ordered)
            if not g:
                continue
            cs, rs, ns = g
            ok = False
            for cm, (r_m, n_m, c_m) in grid.near(cs):
                v = sub(cs, c_m)
                d_n = abs(dot(v, n_m))
                if d_n > gap:
                    continue
                inplane2 = dot(v, v) - d_n * d_n
                if inplane2 <= (r_m * 1.1) ** 2:
                    ok = True
                    break
            if not ok:
                uncovered.append((cs, eid))
            # 7e. do khoang cach CO DAU tai dinh + tam mat slave (lech bien dang)
            if not master_skin:
                for p in [m.nodes[n] for n in ordered if n in m.nodes] + [cs]:
                    best = None
                    for cm, (r_m, n_m, c_m) in grid.near(p):
                        v = sub(p, c_m)
                        d_n = dot(v, n_m)
                        inplane2 = dot(v, v) - d_n * d_n
                        if inplane2 <= (r_m * 1.05) ** 2:
                            if best is None or abs(d_n) < abs(best):
                                best = d_n
                    if best is not None:
                        samples.append((p, best))
        if uncovered:
            frac = 100.0 * len(uncovered) / max(1, len(sf))
            if frac > 60.0:
                F.append(Finding("WARN", CK_GEOM, f, l,
                                 "%s %s<->%s: %d/%d mat slave (%.0f%%) khong doi dien master "
                                 "- 2 surface co that su ap nhau khong? (gap=%.3g)"
                                 % (label, slave, master, len(uncovered), len(sf), frac, gap)))
            else:
                pts = [c for c, _e in uncovered]
                clusters = cluster_points(pts, 3.0 * m.median_edge)
                for ci, idxs in enumerate(clusters[:10], 1):
                    c = centroid([pts[i] for i in idxs])
                    eid0 = uncovered[idxs[0]][1]
                    F.append(Finding("WARN", CK_GEOM, f, l,
                                     "%s %s<->%s: VUNG %d co %d mat slave KHONG duoc master phu "
                                     "quanh %s (vd elem %d) - master thung/hut?"
                                     % (label, slave, master, ci, len(idxs), _fmt_pt(c), eid0)))
        # ---- 7e. LECH BIEN DANG: thong ke khoang cach co dau + vung xuyen thau ----
        if samples:
            dvals = [d for _p, d in samples]
            dmin = min(dvals)
            dmax = max(dvals)
            davg = sum(dvals) / len(dvals)
            F.append(Finding("INFO", CK_GEOM, f, l,
                             "%s %s<->%s: lech bien dang mat-doi-mat: xuyen sau nhat %+.4g / "
                             "trung binh %+.4g / ho lon nhat %+.4g (%d diem do; am=xuyen thau, "
                             "duong=ho khe - so voi clearance/interference thiet ke)"
                             % (label, slave, master, dmin, davg, dmax, len(samples))))
            pen = [(p, d) for p, d in samples if d < -pen_tol]
            if pen:
                ppts = [p for p, _d in pen]
                for ci, idxs in enumerate(cluster_points(ppts, 3.0 * m.median_edge)[:8], 1):
                    c = centroid([ppts[i] for i in idxs])
                    depth = min(pen[i][1] for i in idxs)
                    F.append(Finding("WARN", CK_GEOM, f, l,
                                     "%s %s<->%s: VUNG XUYEN THAU %d: 2 mat cat nhau sau toi da "
                                     "%.4g quanh %s (%d diem) - 2 part chia luoi lech bien dang?"
                                     % (label, slave, master, ci, -depth, _fmt_pt(c), len(idxs))))

    # ---- 7c. Mat tu do ap sat nhau NGOAI moi surface (mat share/quen contact) ----
    free = []
    for key, (cnt, eid, fi) in face_map.items():
        if cnt != 1 or key in all_surf_keys:
            continue
        etype, nds = m.elements[eid]
        ft = solid_face_table(etype)
        ordered = tuple(nds[i] for i in ft[fi])
        g = _face_geo(m, ordered)
        if g:
            free.append((g[0], g[2], eid))
    grid = Grid(max(coin_tol * 2.0, 1e-6))
    for c, nrm, eid in free:
        grid.add(c, (nrm, eid))
    coin = []
    seen = set()
    for c, nrm, eid in free:
        for cq, (nq, eq) in grid.near(c):
            if eq <= eid:
                continue
            if dist(c, cq) <= coin_tol and dot(nrm, nq) < 0.0:
                ea = m.elem_elset.get(eid, "")
                eb = m.elem_elset.get(eq, "")
                pk = (eid, eq)
                if pk not in seen:
                    seen.add(pk)
                    coin.append((c, eid, eq, ea, eb))
    if coin:
        pts = [c for c, _a, _b, _ea, _eb in coin]
        clusters = cluster_points(pts, 3.0 * m.median_edge)
        for ci, idxs in enumerate(clusters[:15], 1):
            c = centroid([pts[i] for i in idxs])
            _c0, ea_id, eb_id, ea, eb = coin[idxs[0]]
            F.append(Finding("WARN", CK_GEOM, "", 0,
                             "MAT AP NHAU ngoai moi surface: VUNG %d co %d cap mat quanh %s "
                             "(%s <-> %s, vd elem %d/%d) - mat share node hoac quen khai contact?"
                             % (ci, len(idxs), _fmt_pt(c), ea or "?", eb or "?", ea_id, eb_id)))

    # ---- 7d. PATTERN MISMATCH tai mat tiep giap share-node ----
    # 2 khoi share node nhung chia tam giac theo duong cheo khac nhau:
    # mat khop pattern -> count==2 (mat trong); mat lech pattern -> mat TU DO
    # o CA 2 phia ma toan bo node cua mat deu la node dung chung 2 component.
    node_elsets = {}
    for eid, (etype, nds) in m.elements.items():
        es = m.elem_elset.get(eid, "") or "?"
        for nid in nds:
            s = node_elsets.get(nid)
            if s is None:
                node_elsets[nid] = {es}
            else:
                s.add(es)
    mis = {}  # frozenset((A,B)) -> list (centroid, owner_elset, eid, S#)
    for key, (cnt, eid, fi) in face_map.items():
        if cnt != 1 or key in all_surf_keys:
            continue
        E = m.elem_elset.get(eid, "") or "?"
        sets = [node_elsets.get(nid) for nid in key]
        if any(s is None for s in sets):
            continue
        common = set(sets[0])
        for s in sets[1:]:
            common &= s
            if len(common) <= 1:
                break
        others = common - {E}
        if not others:
            continue
        etype, nds = m.elements[eid]
        ft = solid_face_table(etype)
        ordered = tuple(nds[i] for i in ft[fi])
        g = _face_geo(m, ordered)
        if not g:
            continue
        for B in others:
            mis.setdefault(frozenset((E, B)), []).append((g[0], E, eid, fi + 1))
    vung_mm = 0
    for pk in sorted(mis, key=lambda k: tuple(sorted(k))):
        items = mis[pk]
        if len(set(o for _c, o, _e, _s in items)) < 2:
            continue  # can bang chung tu CA 2 phia moi ket luan
        pts = [c for c, _o, _e, _s in items]
        for cl in cluster_points(pts, 3.0 * m.median_edge):
            owners = {}
            for i in cl:
                owners.setdefault(items[i][1], items[i])
            if len(owners) < 2:
                continue
            vung_mm += 1
            c = centroid([pts[i] for i in cl])
            (na, nb) = sorted(owners)
            ea = owners[na]
            eb = owners[nb]
            F.append(Finding("ERROR", CK_GEOM, "", 0,
                             "PATTERN MISMATCH %s <-> %s: VUNG %d co %d mat tu do tai vung "
                             "share-node quanh %s (vd elem %d S%d / elem %d S%d) - 2 ben chia "
                             "tam giac theo duong cheo KHAC NHAU, mat tiep giap khong lien tuc"
                             % (na, nb, vung_mm, len(cl), _fmt_pt(c),
                                ea[2], ea[3], eb[2], eb[3])))

    # ---- 7f. GHEP SHARE-NODE KHONG KHOP (khong can contact pair) ----
    # 2 khoi CUNG solid ghep bang share node -> da co node chung o cho ghep OK.
    # Cho nao giua DUNG CAP KHOI DO van con mat tu do 2 phia doi dien nhau
    # trong cu ly < ~1 canh element (ma khong thuoc surface contact nao)
    # => bien dang 2 ben khong khop, share node bi xot.
    join_share = {}
    for nid, es in node_elsets.items():
        if len(es) > 1:
            lst = sorted(es)
            for i in range(len(lst)):
                for j in range(i + 1, len(lst)):
                    k = (lst[i], lst[j])
                    join_share[k] = join_share.get(k, 0) + 1
    join_pairs = set(k for k, n in join_share.items() if n >= 3)
    if join_pairs and free:
        prox = 0.75 * m.median_edge
        grid_j = Grid(prox)
        for idx, (c, nrm, eid) in enumerate(free):
            grid_j.add(c, idx)
        cand = []
        for i, (c, nrm, eid) in enumerate(free):
            E = m.elem_elset.get(eid, "") or "?"
            hit = None
            for cq, j in grid_j.near(c):
                if j == i:
                    continue
                c2, n2, e2 = free[j]
                E2 = m.elem_elset.get(e2, "") or "?"
                if E2 == E:
                    continue
                key2 = (E, E2) if E < E2 else (E2, E)
                if key2 not in join_pairs:
                    continue
                if dist(c, c2) > prox or dot(nrm, n2) > -0.2:
                    continue
                d = abs(dot(sub(c2, c), nrm))
                if hit is None or d > hit[1]:
                    hit = (key2, d)
            if hit is not None:
                cand.append((c, E, eid, hit[0], hit[1]))
        by_pair = {}
        for c, E, eid, key2, d in cand:
            by_pair.setdefault(key2, []).append((c, E, eid, d))
        vung_j = 0
        for key2 in sorted(by_pair):
            items = by_pair[key2]
            pts = [c for c, _E, _e, _d in items]
            for cl in cluster_points(pts, 3.0 * m.median_edge):
                owners = set(items[i][1] for i in cl)
                if len(owners) < 2:
                    continue  # phai co mat tu do o CA 2 phia
                vung_j += 1
                cc = centroid([pts[i] for i in cl])
                dmaxj = max(items[i][3] for i in cl)
                e0 = items[cl[0]][2]
                F.append(Finding("ERROR", CK_GEOM, "", 0,
                                 "GHEP SHARE-NODE KHONG KHOP %s <-> %s: VUNG %d co %d mat tu do "
                                 "doi nhau (lech toi da ~%.4g) quanh %s (vd elem %d) - 2 khoi da "
                                 "share node noi khac nhung cho nay bien dang KHONG KHOP, ghep bi xot?"
                                 % (key2[0], key2[1], vung_j, len(cl), dmaxj, _fmt_pt(cc), e0)))
    return F


# ==================================================================== #
# 10. GROUP CONTACT/TIE - so khop 2 phia
# ==================================================================== #
def _surface_area_stats(m, faces):
    """(n_tri, n_quad, tong dien tich) cua list face (key, ordered, eid)."""
    n_tri = n_quad = 0
    area = 0.0
    for _key, ordered, _eid in faces:
        pts = [m.nodes[n] for n in ordered if n in m.nodes]
        if len(pts) < 3:
            continue
        if len(pts) == 3:
            n_tri += 1
            area += tri_area(pts[0], pts[1], pts[2])
        else:
            n_quad += 1
            area += tri_area(pts[0], pts[1], pts[2]) + tri_area(pts[0], pts[2], pts[3])
    return n_tri, n_quad, area


def _breakdown(n_tri, n_quad):
    parts = []
    if n_tri:
        parts.append("%d tri" % n_tri)
    if n_quad:
        parts.append("%d quad" % n_quad)
    return " + ".join(parts) or "0 mat"


def _opposite_gaps(m, src_faces, dst_faces):
    """Khoang cach tu tam moi mat src toi tam mat dst GAN NHAT.

    Y tuong: pattern tile/xen ke cho khoang cach NEN deu nhau; thieu 1 element
    thi cac mat quanh do co khoang cach vot len >> nen. Tra ve:
        (baseline, threshold, [(diem, d hoac None)], tong so mat src)
    d = None nghia la khong tim thay gi trong pham vi quet (rat xa).
    """
    dst_pts = []
    for _key, ordered, _eid in dst_faces:
        g = _face_geo(m, ordered)
        if g:
            dst_pts.append(g[0])
    src_pts = []
    for _key, ordered, _eid in src_faces:
        g = _face_geo(m, ordered)
        if g:
            src_pts.append(g[0])
    if not dst_pts or not src_pts:
        return None
    cell = max(2.0 * m.median_edge, 1e-9)
    grid = Grid(cell)
    for p in dst_pts:
        grid.add(p, None)
    dists = [(p, grid.nearest_dist(p, max_rings=4)) for p in src_pts]
    vals = sorted(d for _p, d in dists if d is not None)
    if not vals:
        return None
    base = vals[len(vals) // 2]
    thr = max(2.0 * base, base + 0.6 * m.median_edge)
    anomalies = [(p, d) for p, d in dists if d is None or d > thr]
    return base, thr, anomalies, len(src_pts)


def check_groups(model, gap_tol=None):
    m = model
    F = []
    if gap_tol is None:
        gap_tol = 0.2 * m.median_edge
    cache = {}

    def faces_of(name):
        if name not in cache:
            surf = m.surfaces.get(name)
            if surf is not None and surf.kind == "ELEMENT":
                cache[name] = _resolve_surface_faces(m, surf)
            else:
                cache[name] = None  # analytical / node-based / khong ton tai
        return cache[name]

    pairs = [(sl, ms, "CONTACT PAIR", f, l)
             for sl, ms, _i, _s, f, l in m.contact_pairs]
    pairs += [(sl, ms, "TIE %s" % (nm or ""), f, l)
              for nm, sl, ms, _p, _s, f, l in m.ties]

    for sl, ms, label, f, l in pairs:
        sf = faces_of(sl)
        mf = faces_of(ms)
        # group rong / stale trong pair -> nghiem trong
        for name, faces in ((sl, sf), (ms, mf)):
            surf = m.surfaces.get(name)
            if surf is not None and surf.kind == "ELEMENT" and not faces:
                F.append(Finding("ERROR", CK_GROUP, f, l,
                                 "%s: group '%s' trong pair khong resolve duoc mat nao "
                                 "(rong hoac stale sau remesh)" % (label, name)))
        if not sf or not mf:
            continue  # analytical / rong da bao o tren
        ts, qs, a_s = _surface_area_stats(m, sf)
        tm, qm, a_m = _surface_area_stats(m, mf)
        n_s = ts + qs
        n_m = tm + qm
        if a_m <= 0:
            continue
        ratio = a_s / a_m
        note = ""
        if n_s != n_m and abs(ratio - 1.0) <= 0.05:
            note = " -> so mat lech nhung DIEN TICH KHOP: do chia loai mat khac nhau (hop ly)"
        elif ratio < 0.98:
            note = " (master rong hon slave - thuong la co y)"
        F.append(Finding("INFO", CK_GROUP, f, l,
                         "%s %s<->%s: slave %s (dt %.6g) | master %s (dt %.6g) | "
                         "ti le dt slave/master = %.3f%s"
                         % (label, sl, ms, _breakdown(ts, qs), a_s,
                            _breakdown(tm, qm), a_m, ratio, note)))
        # ---- do "khoang cach nen" toi phia doi dien de tim VUNG THIEU ----
        # (chiu duoc ca pattern tile XEN KE: nen deu, thieu element -> vot len)
        n_warn_clusters = 0
        base_txt = []
        for direction, src, dst, thieu_ben in (
                ("slave->master", sf, mf, "master"),
                ("master->slave", mf, sf, "slave")):
            gp = _opposite_gaps(m, src, dst)
            if gp is None:
                continue
            base, thr, anoms, total = gp
            base_txt.append("%s %.3g" % (direction, base))
            if not anoms:
                continue
            pts = [p for p, _d in anoms]
            big_lim = max(10, int(0.05 * total))
            for ci, idxs in enumerate(cluster_points(pts, 3.0 * m.median_edge)[:8], 1):
                ds = [anoms[i][1] for i in idxs]
                dmax = max((d for d in ds if d is not None), default=None)
                d_str = ("~%.3g" % dmax) if dmax is not None else (">%.3g" % (8.0 * m.median_edge))
                cc = centroid([pts[i] for i in idxs])
                if len(idxs) <= big_lim:
                    n_warn_clusters += 1
                    F.append(Finding("WARN", CK_GROUP, f, l,
                                     "%s %s<->%s: VUNG THIEU DOI DIEN (%s): %d mat quanh %s, "
                                     "khoang cach toi phia kia %s (nen ~%.3g) - thieu element "
                                     "ben %s?"
                                     % (label, sl, ms, direction, len(idxs), _fmt_pt(cc),
                                        d_str, base, thieu_ben)))
                else:
                    F.append(Finding("INFO", CK_GROUP, f, l,
                                     "%s %s<->%s: %d mat %s xa phia kia (%s, nen ~%.3g) "
                                     "- vung lien mach lon, thuong la VIEN do 1 phia rong hon "
                                     "(binh thuong)"
                                     % (label, sl, ms, len(idxs), direction, d_str, base)))
        area_anomaly = (ratio > 1.02) or (label.startswith("TIE")
                                          and abs(ratio - 1.0) > 0.05)
        if area_anomaly:
            if n_warn_clusters == 0:
                F.append(Finding("INFO", CK_GROUP, f, l,
                                 "%s %s<->%s: dien tich lech %.1f%% nhung KHONG co vung "
                                 "thieu doi dien (khoang cach nen: %s) -> loai element/tiling "
                                 "khac nhau (hop le)"
                                 % (label, sl, ms, abs(ratio - 1.0) * 100.0,
                                    "; ".join(base_txt) or "-")))
            elif ratio > 1.02:
                F.append(Finding("WARN", CK_GROUP, f, l,
                                 "%s %s<->%s: dien tich slave (%.6g) LON HON master (%.6g) "
                                 "%.1f%% VA co %d VUNG THIEU DOI DIEN (xem dong tren) "
                                 "- master hut/chon thieu element?"
                                 % (label, sl, ms, a_s, a_m, (ratio - 1.0) * 100.0,
                                    n_warn_clusters)))
            else:
                F.append(Finding("WARN", CK_GROUP, f, l,
                                 "%s %s<->%s: TIE nhung dien tich 2 phia lech %.1f%% VA co "
                                 "%d VUNG THIEU DOI DIEN - vung tie 2 ben phai trum nhau"
                                 % (label, sl, ms, abs(ratio - 1.0) * 100.0,
                                    n_warn_clusters)))
        # khuyen nghi slave = luoi min
        if n_s and n_m:
            avg_s = a_s / n_s
            avg_m = a_m / n_m
            if avg_s > 2.5 * avg_m:
                F.append(Finding("INFO", CK_GROUP, f, l,
                                 "%s %s<->%s: luoi slave THO hon master ~%.1f lan "
                                 "- thong thuong nen de luoi min lam slave"
                                 % (label, sl, ms, avg_s / avg_m)))

    # ---- surface bi tach thanh nhieu mang roi rac (chon nham/sot element) ----
    for name in sorted(m.surfaces):
        faces = faces_of(name)
        if not faces or len(faces) < 2:
            continue
        edge_map = {}
        for i, (_key, ordered, _eid) in enumerate(faces):
            for e in _face_edges(ordered):
                edge_map.setdefault(e, []).append(i)
        adj = [[] for _ in faces]
        for e, idxs in edge_map.items():
            for i in range(len(idxs)):
                for j in range(i + 1, len(idxs)):
                    adj[idxs[i]].append(idxs[j])
                    adj[idxs[j]].append(idxs[i])
        seen = [False] * len(faces)
        comps = []
        for start in range(len(faces)):
            if seen[start]:
                continue
            stack = [start]
            seen[start] = True
            size = 0
            while stack:
                cur = stack.pop()
                size += 1
                for nb in adj[cur]:
                    if not seen[nb]:
                        seen[nb] = True
                        stack.append(nb)
            comps.append(size)
        if len(comps) > 1:
            comps.sort(reverse=True)
            med = comps[len(comps) // 2]
            if len(comps) >= 4 and comps[0] <= 3 * max(1, med):
                # nhieu mang deu nhau = surface dang TILE PATTERN (co chu dich)
                F.append(Finding("INFO", CK_GROUP, "", 0,
                                 "SURFACE '%s': dang tile pattern - %d mang deu nhau "
                                 "(~%d mat/mang) - hop le, da kiem vung thieu bang "
                                 "khoang cach nen o phan pair" % (name, len(comps), med)))
            else:
                F.append(Finding("WARN", CK_GROUP, "", 0,
                                 "SURFACE '%s': bi tach thanh %d mang roi rac (kich thuoc: %s) "
                                 "- chon nham element o xa hoac sot element noi giua?"
                                 % (name, len(comps),
                                    ", ".join(str(x) for x in comps[:8])
                                    + (" ..." if len(comps) > 8 else ""))))

    # ---- 2 group dung chung mat (vung contact chong len nhau) ----
    used_names = set()
    for sl, ms, _label, _f, _l in pairs:
        used_names.add(sl)
        used_names.add(ms)
    face_owners = {}
    for name in sorted(used_names):
        faces = faces_of(name)
        if not faces:
            continue
        for key, _ordered, eid in faces:
            face_owners.setdefault(key, {})[name] = eid
    overlap = {}   # (nameA, nameB) -> [so mat chung, vd eid]
    for key, owners in face_owners.items():
        if len(owners) < 2:
            continue
        names = sorted(owners)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                k2 = (names[i], names[j])
                rec = overlap.get(k2)
                if rec is None:
                    overlap[k2] = [1, owners[names[i]]]
                else:
                    rec[0] += 1
    for (na, nb), (n, eid0) in sorted(overlap.items()):
        F.append(Finding("WARN", CK_GROUP, "", 0,
                         "GROUP CHONG NHAU: '%s' va '%s' dung chung %d mat (vd elem %d) "
                         "- 2 vung contact chong len nhau, solver co the double-count "
                         "(neu 1 group la tap con co chu dich thi xac nhan)"
                         % (na, nb, n, eid0)))
    return F


# ==================================================================== #
# 8. SETUP DANG TAT
# ==================================================================== #
def check_commented(reader):
    F = []
    if reader.commented_keywords:
        F.append(Finding("INFO", CK_OFF, "", 0,
                         "tong %d dong keyword dang bi comment - xac nhan la TAT CO CHU DICH:"
                         % len(reader.commented_keywords)))
    for f, l, txt in reader.commented_keywords:
        F.append(Finding("INFO", CK_OFF, f, l, txt[:100]))
    return F


# ==================================================================== #
# 9. TONG QUAN STEP
# ==================================================================== #
def step_report(model):
    m = model
    F = []
    if m.model_boundaries:
        tg = sorted(set(t for _op, t, _d in m.model_boundaries))
        F.append(Finding("INFO", CK_STEP, "", 0,
                         "BC muc model (ngoai step): %d dong, target: %s"
                         % (len(m.model_boundaries), ", ".join(tg[:8]))))
    for st in m.steps:
        ops = sorted(set(op for op, _t, _d in st.boundaries))
        targets = []
        seen = set()
        for _op, t, _d in st.boundaries:
            if t not in seen:
                seen.add(t)
                targets.append(t)
        extra = []
        if st.n_interference:
            extra.append("interference x%d" % st.n_interference)
        if st.n_modelchange:
            extra.append("model-change x%d" % st.n_modelchange)
        F.append(Finding("INFO", CK_STEP, st.file, st.line,
                         "STEP '%s': BC %d dong [%s] tren %s%s | CLOAD %d dong%s | DLOAD %s%s"
                         % (st.name, len(st.boundaries), "; ".join(ops) or "-",
                            ", ".join(targets[:6]),
                            " ..." if len(targets) > 6 else "",
                            st.cload_lines,
                            " (OP=%s)" % ",".join(sorted(st.cload_ops)) if st.cload_ops else "",
                            ",".join(sorted(st.dload_types)) or "-",
                            " | " + ", ".join(extra) if extra else "")))
    return F
