# -*- coding: utf-8 -*-
"""Model builder: gom keyword block thanh data model de check.

Tham chieu (refs) duoc thu thap NGAY khi parse — moi ref la tuple
(name, context, file, line) de bao loi kem vi tri chinh xac.
"""
import re
from collections import Counter

from .geometry import dist

_RE_PARAM_REF = re.compile(r"<([^<>\s,]+)>")

# keyword biet-va-bo-qua (khong tinh vao "unknown")
_IGNORE = {
    "HEADING", "PREPRINT", "STATIC", "CONTACTCONTROLS", "OUTPUT",
    "NODEOUTPUT", "ELEMENTOUTPUT", "CONTACTOUTPUT", "NODEFILE", "ELFILE",
    "CONTACTFILE", "RESTART", "SYSTEM", "NODEPRINT", "ELPRINT",
    "DENSITY", "ELASTIC", "PLASTIC", "EXPANSION", "SURFACEBEHAVIOR",
    "FRICTION", "DISTRIBUTING", "KINEMATIC", "ENDSTEP", "SOLVER",
    "MODALDAMPING", "VISCO", "CONTROLS",
}


class Surface(object):
    __slots__ = ("name", "kind", "items", "defs")

    def __init__(self, name, kind):
        self.name = name
        self.kind = kind          # "ELEMENT" | "NODE" | "ANALYTICAL"
        self.items = []           # ELEMENT: (ref int|str, face str|None, file, line)
        self.defs = []            # [(file, line)]


class Step(object):
    __slots__ = ("name", "file", "line", "boundaries", "cload_lines",
                 "cload_ops", "dload_types", "n_interference", "n_modelchange")

    def __init__(self, name, file, line):
        self.name = name
        self.file = file
        self.line = line
        self.boundaries = []      # (op_label, target, dofs_text)
        self.cload_lines = 0
        self.cload_ops = set()
        self.dload_types = set()
        self.n_interference = 0
        self.n_modelchange = 0


class Model(object):
    def __init__(self):
        self.nodes = {}           # id -> (x,y,z)
        self.elements = {}        # id -> (etype, nodes tuple)
        self.elem_elset = {}      # id -> elset cua block *ELEMENT (primary)
        self.elsets = {}          # name -> {"ids":[], "refs":[(name,f,l)], "defs":[(f,l)]}
        self.nsets = {}
        self.surfaces = {}        # name -> Surface
        self.interactions = {}    # name -> (f,l)
        self.materials = {}
        self.amplitudes = {}
        self.parameters = {}      # name -> (f,l)
        self.sections = []        # (kind, elset, material, f, l)
        self.contact_pairs = []   # (slave, master, interaction, step, f, l)
        self.ties = []            # (name, slave, master, postol, step, f, l)
        self.clearances = []      # (slave, master, value, f, l)
        self.interferences = []   # ((s1,s2)|None, shrink, step, f, l)
        self.modelchanges = []    # ((s1,s2)|None, type, step, f, l)
        self.couplings = []       # (cname, refnode_str, surface, f, l)
        self.rigidbodies = []     # (refnode_str, analyticalsurface, f, l)
        self.pretensions = []     # (node_str, surface, f, l)
        self.initialconds = []    # (type, file_param, step_param, f, l)
        self.steps = []
        self.model_boundaries = []          # BOUNDARY ngoai step
        self.cload_nodes = {}     # node id -> (f,l) lan dau
        self.cload_total_lines = 0
        self.boundary_nodes = {}  # node id (BC tro truc tiep) -> (f,l)
        # refs: (name, context, file, line)
        self.surface_refs = []
        self.nset_refs = []
        self.elset_refs = []
        self.interaction_refs = []
        self.material_refs = []
        self.amplitude_refs = []
        self.param_refs = {}      # name -> (context, f, l) lan dau
        self.unknown_keywords = Counter()
        self.malformed = []       # (f, l, msg)
        # dien sau finalize()
        self.node_used = set()
        self.median_edge = 1.0
        self._set_cache = {}

    # -------------------------------------------------------------- #
    def _set_get(self, table, name):
        rec = table.get(name)
        if rec is None:
            rec = {"ids": [], "refs": [], "defs": []}
            table[name] = rec
        return rec

    def add_set_ids(self, table, name, ids, file, line):
        rec = self._set_get(table, name)
        rec["ids"].extend(ids)
        rec["defs"].append((file, line))

    def _resolve_set(self, table, name, seen):
        key = (id(table), name)
        if key in self._set_cache:
            return self._set_cache[key]
        if name in seen:
            return []
        rec = table.get(name)
        if rec is None:
            return []
        out = list(rec["ids"])
        seen = seen | {name}
        for ref_name, _f, _l in rec["refs"]:
            out.extend(self._resolve_set(table, ref_name, seen))
        self._set_cache[key] = out
        return out

    def elset_ids(self, name):
        return self._resolve_set(self.elsets, name, frozenset())

    def nset_ids(self, name):
        return self._resolve_set(self.nsets, name, frozenset())

    # -------------------------------------------------------------- #
    def finalize(self):
        used = set()
        for etype, nds in self.elements.values():
            used.update(nds)
        used.discard(0)
        self.node_used = used
        # uoc luong chieu dai canh dien hinh: khoang cach 2 corner node dau
        # cua toi da 2000 element (voi moi loai element deck nay, node 1-2 la 1 canh)
        samples = []
        for eid in self.elements:
            etype, nds = self.elements[eid]
            if len(nds) >= 2 and nds[0] in self.nodes and nds[1] in self.nodes:
                d = dist(self.nodes[nds[0]], self.nodes[nds[1]])
                if d > 0:
                    samples.append(d)
            if len(samples) >= 2000:
                break
        if samples:
            samples.sort()
            self.median_edge = samples[len(samples) // 2]
        return self


# ------------------------------------------------------------------ #
def _records(data):
    """Gop dong continuation (ket thuc bang dau phay) thanh record."""
    pend = []
    start_ln = None
    for ln, txt in data:
        t = txt.rstrip()
        cont = t.endswith(",")
        toks = [x.strip() for x in t.rstrip(",").split(",") if x.strip() != ""]
        if start_ln is None:
            start_ln = ln
        pend.extend(toks)
        if not cont:
            if pend:
                yield start_ln, pend
            pend = []
            start_ln = None
    if pend:
        yield start_ln, pend


def _split_pos(txt):
    """Split giu vi tri (cho NODE/CLOAD/BOUNDARY)."""
    return [x.strip() for x in txt.split(",")]


def _is_int(tok):
    try:
        int(tok)
        return True
    except ValueError:
        return False


class Builder(object):
    def __init__(self):
        self.m = Model()
        self.cur_step = None

    # -------------------------------------------------------------- #
    def feed(self, kw):
        m = self.m
        # quet tham chieu parameter <ten> trong data + param value
        for ln, txt in kw.data:
            if "<" in txt:
                for mt in _RE_PARAM_REF.finditer(txt):
                    m.param_refs.setdefault(mt.group(1), (kw.name, kw.file, ln))
        for v in kw.params.values():
            if isinstance(v, str) and "<" in v:
                for mt in _RE_PARAM_REF.finditer(v):
                    m.param_refs.setdefault(mt.group(1), (kw.name, kw.file, kw.line))
        # tham chieu amplitude tu bat ky keyword nao
        amp = kw.params.get("AMPLITUDE")
        if isinstance(amp, str) and amp:
            m.amplitude_refs.append((amp, kw.name, kw.file, kw.line))

        handler = getattr(self, "_kw_" + kw.name.lower(), None)
        if handler is not None:
            handler(kw)
        elif kw.name not in _IGNORE:
            m.unknown_keywords[kw.name] += 1

    # ----------------------------- mesh ---------------------------- #
    def _kw_node(self, kw):
        m = self.m
        nset = kw.params.get("NSET")
        ids = []
        for ln, txt in kw.data:
            t = _split_pos(txt)
            try:
                nid = int(t[0])
            except (ValueError, IndexError):
                m.malformed.append((kw.file, ln, "dong *NODE khong doc duoc: " + txt[:60]))
                continue
            c = []
            for tok in t[1:4]:
                try:
                    c.append(float(tok))
                except ValueError:
                    c.append(0.0)
            while len(c) < 3:
                c.append(0.0)
            m.nodes[nid] = (c[0], c[1], c[2])
            if nset:
                ids.append(nid)
        if nset:
            m.add_set_ids(m.nsets, nset, ids, kw.file, kw.line)

    def _kw_element(self, kw):
        m = self.m
        etype = kw.params.get("TYPE", "") or ""
        elset = kw.params.get("ELSET") or ""
        ids = []
        for ln, toks in _records(kw.data):
            try:
                eid = int(toks[0])
            except (ValueError, IndexError):
                m.malformed.append((kw.file, ln, "record *ELEMENT khong doc duoc"))
                continue
            nds = []
            for tok in toks[1:]:
                try:
                    v = int(tok)
                except ValueError:
                    continue
                if v > 0:
                    nds.append(v)
            m.elements[eid] = (etype, tuple(nds))
            m.elem_elset[eid] = elset
            if elset:
                ids.append(eid)
        if elset:
            m.add_set_ids(m.elsets, elset, ids, kw.file, kw.line)

    # ----------------------------- sets ---------------------------- #
    def _feed_set(self, kw, table, name_key):
        m = self.m
        name = kw.params.get(name_key)
        if not name:
            m.malformed.append((kw.file, kw.line, "*%s thieu %s=" % (kw.name, name_key)))
            return
        rec = m._set_get(table, name)
        rec["defs"].append((kw.file, kw.line))
        generate = "GENERATE" in kw.params
        for ln, txt in kw.data:
            toks = [x.strip() for x in txt.rstrip(",").split(",") if x.strip() != ""]
            if generate:
                nums = []
                for tok in toks:
                    try:
                        nums.append(int(tok))
                    except ValueError:
                        pass
                if len(nums) >= 2:
                    inc = nums[2] if len(nums) >= 3 and nums[2] != 0 else 1
                    if (nums[1] - nums[0]) // inc <= 5000000:
                        rec["ids"].extend(range(nums[0], nums[1] + 1, inc))
                    else:
                        m.malformed.append((kw.file, ln, "GENERATE range qua lon - bo qua"))
                continue
            for tok in toks:
                if _is_int(tok):
                    rec["ids"].append(int(tok))
                else:
                    rec["refs"].append((tok, kw.file, ln))

    def _kw_nset(self, kw):
        self._feed_set(kw, self.m.nsets, "NSET")
        # nested nset refs -> kiem tra ton tai
        rec = self.m.nsets.get(kw.params.get("NSET") or "", None)
        if rec:
            for name, f, l in rec["refs"]:
                self.m.nset_refs.append((name, "*NSET nested", f, l))

    def _kw_elset(self, kw):
        self._feed_set(kw, self.m.elsets, "ELSET")
        rec = self.m.elsets.get(kw.params.get("ELSET") or "", None)
        if rec:
            for name, f, l in rec["refs"]:
                self.m.elset_refs.append((name, "*ELSET nested", f, l))

    # --------------------------- surface --------------------------- #
    def _kw_surface(self, kw):
        m = self.m
        name = kw.params.get("NAME")
        if not name:
            m.malformed.append((kw.file, kw.line, "*SURFACE thieu NAME="))
            return
        tval = str(kw.params.get("TYPE", "ELEMENT")).upper()
        if tval.startswith("ELEM"):
            kind = "ELEMENT"
        elif tval.startswith("NODE"):
            kind = "NODE"
        else:
            kind = "ANALYTICAL"      # REVOLUTION / CYLINDER / SEGMENTS / SPHERE...
        surf = m.surfaces.get(name)
        if surf is None:
            surf = Surface(name, kind)
            m.surfaces[name] = surf
        surf.defs.append((kw.file, kw.line))
        if kind == "ELEMENT":
            for ln, txt in kw.data:
                toks = [x.strip() for x in txt.rstrip(",").split(",") if x.strip() != ""]
                if not toks:
                    continue
                ref = int(toks[0]) if _is_int(toks[0]) else toks[0]
                face = toks[1].upper() if len(toks) > 1 else None
                surf.items.append((ref, face, kw.file, ln))
                if isinstance(ref, str):
                    m.elset_refs.append((ref, "*SURFACE %s" % name, kw.file, ln))
        elif kind == "NODE":
            for ln, txt in kw.data:
                toks = [x.strip() for x in txt.rstrip(",").split(",") if x.strip() != ""]
                for tok in toks:
                    if not _is_int(tok):
                        m.nset_refs.append((tok, "*SURFACE %s" % name, kw.file, ln))

    def _kw_surfaceinteraction(self, kw):
        name = kw.params.get("NAME")
        if name:
            self.m.interactions.setdefault(name, (kw.file, kw.line))

    # --------------------------- contact ---------------------------- #
    def _kw_contactpair(self, kw):
        m = self.m
        inter = kw.params.get("INTERACTION")
        if isinstance(inter, str) and inter:
            m.interaction_refs.append((inter, "*CONTACT PAIR", kw.file, kw.line))
        step = self.cur_step.name if self.cur_step else None
        for ln, toks in _records(kw.data):
            if len(toks) >= 2:
                m.contact_pairs.append((toks[0], toks[1], inter, step, kw.file, ln))
                m.surface_refs.append((toks[0], "*CONTACT PAIR (slave)", kw.file, ln))
                m.surface_refs.append((toks[1], "*CONTACT PAIR (master)", kw.file, ln))
            else:
                m.malformed.append((kw.file, ln, "*CONTACT PAIR: dong data thieu cap surface"))

    def _kw_tie(self, kw):
        m = self.m
        name = kw.params.get("NAME")
        postol = None
        pt = kw.params.get("POSITION TOLERANCE")
        if isinstance(pt, str):
            try:
                postol = float(pt)
            except ValueError:
                postol = None
        step = self.cur_step.name if self.cur_step else None
        for ln, toks in _records(kw.data):
            if len(toks) >= 2:
                m.ties.append((name, toks[0], toks[1], postol, step, kw.file, ln))
                m.surface_refs.append((toks[0], "*TIE %s (slave)" % (name or ""), kw.file, ln))
                m.surface_refs.append((toks[1], "*TIE %s (master)" % (name or ""), kw.file, ln))

    def _kw_clearance(self, kw):
        m = self.m
        sl = kw.params.get("SLAVE")
        ms = kw.params.get("MASTER")
        m.clearances.append((sl, ms, kw.params.get("VALUE"), kw.file, kw.line))
        if isinstance(sl, str) and sl:
            m.surface_refs.append((sl, "*CLEARANCE (slave)", kw.file, kw.line))
        if isinstance(ms, str) and ms:
            m.surface_refs.append((ms, "*CLEARANCE (master)", kw.file, kw.line))

    def _kw_contactinterference(self, kw):
        m = self.m
        shrink = "SHRINK" in kw.params
        step = self.cur_step.name if self.cur_step else None
        if self.cur_step:
            self.cur_step.n_interference += 1
        for ln, toks in _records(kw.data):
            if len(toks) >= 2:
                m.interferences.append(((toks[0], toks[1]), shrink, step, kw.file, ln))
                m.surface_refs.append((toks[0], "*CONTACT INTERFERENCE", kw.file, ln))
                m.surface_refs.append((toks[1], "*CONTACT INTERFERENCE", kw.file, ln))

    def _kw_modelchange(self, kw):
        m = self.m
        ctype = str(kw.params.get("TYPE", ""))
        step = self.cur_step.name if self.cur_step else None
        if self.cur_step:
            self.cur_step.n_modelchange += 1
        if ctype.upper().startswith("CONTACT"):
            for ln, toks in _records(kw.data):
                if len(toks) >= 2:
                    m.modelchanges.append(((toks[0], toks[1]), ctype, step, kw.file, ln))
                    m.surface_refs.append((toks[0], "*MODEL CHANGE", kw.file, ln))
                    m.surface_refs.append((toks[1], "*MODEL CHANGE", kw.file, ln))

    # -------------------------- property ---------------------------- #
    def _feed_section(self, kw, kind):
        m = self.m
        elset = kw.params.get("ELSET")
        mat = kw.params.get("MATERIAL")
        m.sections.append((kind, elset, mat, kw.file, kw.line))
        if isinstance(elset, str) and elset:
            m.elset_refs.append((elset, "*%s" % kind, kw.file, kw.line))
        if isinstance(mat, str) and mat:
            m.material_refs.append((mat, "*%s" % kind, kw.file, kw.line))

    def _kw_solidsection(self, kw):
        self._feed_section(kw, "SOLID SECTION")

    def _kw_membranesection(self, kw):
        self._feed_section(kw, "MEMBRANE SECTION")

    def _kw_shellsection(self, kw):
        self._feed_section(kw, "SHELL SECTION")

    def _kw_material(self, kw):
        name = kw.params.get("NAME")
        if name:
            self.m.materials.setdefault(name, (kw.file, kw.line))

    def _kw_parameter(self, kw):
        for ln, txt in kw.data:
            if "=" in txt:
                name = txt.partition("=")[0].strip()
                if name:
                    self.m.parameters.setdefault(name, (kw.file, ln))

    def _kw_pretensionsection(self, kw):
        m = self.m
        node = kw.params.get("NODE")
        surf = kw.params.get("SURFACE")
        m.pretensions.append((node, surf, kw.file, kw.line))
        if isinstance(node, str) and node and not _is_int(node):
            m.nset_refs.append((node, "*PRE-TENSION SECTION", kw.file, kw.line))
        if isinstance(surf, str) and surf:
            m.surface_refs.append((surf, "*PRE-TENSION SECTION", kw.file, kw.line))

    def _kw_coupling(self, kw):
        m = self.m
        cname = kw.params.get("CONSTRAINT NAME")
        ref = kw.params.get("REF NODE")
        surf = kw.params.get("SURFACE")
        m.couplings.append((cname, ref, surf, kw.file, kw.line))
        if isinstance(ref, str) and ref and not _is_int(ref):
            m.nset_refs.append((ref, "*COUPLING", kw.file, kw.line))
        if isinstance(surf, str) and surf:
            m.surface_refs.append((surf, "*COUPLING", kw.file, kw.line))

    def _kw_rigidbody(self, kw):
        m = self.m
        ref = kw.params.get("REFNODE") or kw.params.get("REF NODE")
        asurf = kw.params.get("ANALYTICALSURFACE") or kw.params.get("ANALYTICAL SURFACE")
        m.rigidbodies.append((ref, asurf, kw.file, kw.line))
        if isinstance(ref, str) and ref and not _is_int(ref):
            m.nset_refs.append((ref, "*RIGID BODY", kw.file, kw.line))
        if isinstance(asurf, str) and asurf:
            m.surface_refs.append((asurf, "*RIGID BODY", kw.file, kw.line))

    def _kw_transform(self, kw):
        nset = kw.params.get("NSET")
        if isinstance(nset, str) and nset:
            self.m.nset_refs.append((nset, "*TRANSFORM", kw.file, kw.line))

    def _kw_amplitude(self, kw):
        name = kw.params.get("NAME")
        if name:
            self.m.amplitudes.setdefault(name, (kw.file, kw.line))

    def _kw_initialconditions(self, kw):
        self.m.initialconds.append((kw.params.get("TYPE"), kw.params.get("FILE"),
                                    kw.params.get("STEP"), kw.file, kw.line))

    # ---------------------------- steps ----------------------------- #
    def _kw_step(self, kw):
        st = Step(kw.params.get("NAME") or "(khong ten)", kw.file, kw.line)
        self.m.steps.append(st)
        self.cur_step = st

    def _kw_endstep(self, kw):
        self.cur_step = None

    def _kw_boundary(self, kw):
        m = self.m
        op = kw.params.get("OP")
        fixed = "FIXED" in kw.params
        label = ("OP=%s" % op if isinstance(op, str) else "") + (" FIXED" if fixed else "")
        label = label.strip() or "(mod)"
        bucket = self.cur_step.boundaries if self.cur_step else m.model_boundaries
        for ln, txt in kw.data:
            t = _split_pos(txt)
            if not t or not t[0]:
                continue
            target = t[0]
            dofs = ",".join(x for x in t[1:] if x)
            bucket.append((label, target, dofs))
            if _is_int(target):
                m.boundary_nodes.setdefault(int(target), (kw.file, ln))
            else:
                m.nset_refs.append((target, "*BOUNDARY", kw.file, ln))

    def _kw_cload(self, kw):
        m = self.m
        op = kw.params.get("OP")
        if self.cur_step:
            if isinstance(op, str):
                self.cur_step.cload_ops.add(op)
        for ln, txt in kw.data:
            t = _split_pos(txt)
            if not t or not t[0]:
                continue
            m.cload_total_lines += 1
            if self.cur_step:
                self.cur_step.cload_lines += 1
            if _is_int(t[0]):
                m.cload_nodes.setdefault(int(t[0]), (kw.file, ln))
            else:
                m.nset_refs.append((t[0], "*CLOAD", kw.file, ln))

    def _kw_dload(self, kw):
        m = self.m
        for ln, txt in kw.data:
            t = _split_pos(txt)
            if not t or not t[0]:
                continue
            if not _is_int(t[0]):
                m.elset_refs.append((t[0], "*DLOAD", kw.file, ln))
            if len(t) > 1 and t[1]:
                if self.cur_step:
                    self.cur_step.dload_types.add(t[1].upper())

    # -------------------------------------------------------------- #
    def finalize(self):
        return self.m.finalize()
