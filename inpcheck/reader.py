# -*- coding: utf-8 -*-
"""Doc deck .inp: resolve *INCLUDE de quy, phan loai comment, tach keyword block.

Dac thu deck HyperMesh-Abaqus da khao sat (docs/K12E_DECK_FORMAT.md):
- keyword hoa/thuong lan lon -> normalize UPPER, bo het khoang trang va '-'
  trong ten ("*contact interference" -> CONTACTINTERFERENCE,
  "*PRE-TENSION SECTION" -> PRETENSIONSECTION, "*rigidbody" -> RIGIDBODY)
- comment `**` co 3 loai: ghi chu thuong, `**HMNAME ...` (metadata HyperMesh),
  va keyword bi comment (`** *TIE`, `**clearance, ...`, `**INCLUDE, ...`)
- include 1 cap la chuan, nhung reader van ho tro long nhau + chong cycle
"""
import os
import re

# tu dau tien cua 1 dong comment de coi la "keyword bi comment"
_VOCAB = {
    "INCLUDE", "CLEARANCE", "CONTACT", "TIE", "BOUNDARY", "CLOAD", "DLOAD",
    "SURFACE", "FRICTION", "COUPLING", "NSET", "ELSET", "MODEL", "AMPLITUDE",
    "TRANSFORM", "RIGIDBODY", "STEP", "PRETENSION", "PRE-TENSION", "MPC",
}

_RE_SPACES = re.compile(r"\s+")
_RE_NAME = re.compile(r"[\s\-]+")


class Keyword(object):
    __slots__ = ("name", "params", "file", "line", "data")

    def __init__(self, name, params, file, line):
        self.name = name        # normalized: UPPER, bo space va '-'
        self.params = params    # dict UPPER-key (space don) -> value|True
        self.file = file
        self.line = line
        self.data = []          # list (lineno, text_stripped)

    def __repr__(self):
        return "<*%s %s:%d>" % (self.name, os.path.basename(self.file), self.line)


def parse_keyword_line(s):
    parts = s.split(",")
    name = _RE_NAME.sub("", parts[0].lstrip("*")).upper()
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, _, v = p.partition("=")
            params[_RE_SPACES.sub(" ", k.strip()).upper()] = v.strip()
        else:
            flag = _RE_SPACES.sub(" ", p.strip()).upper()
            if flag:
                params[flag] = True
    return name, params


class DeckReader(object):
    def __init__(self):
        self.files = []                 # cac file da doc (theo thu tu)
        self.includes = []              # (file, line, target, resolved_path|None)
        self.missing_includes = []      # (file, line, target)
        self.commented_includes = []    # (file, line, target, exists)
        self.commented_keywords = []    # (file, line, text)
        self.hmnames = []               # (file, line, text)
        self.comment_param_refs = []    # (name, file, line)  <ten> trong comment
        self.orphan_data = []           # (file, line, text)  data khong thuoc keyword nao
        self.read_errors = []           # (path, msg)
        self.base_dir = ""

    # ------------------------------------------------------------------ #
    def read(self, master):
        """Generator: yield Keyword theo dung thu tu xuat hien (da resolve include)."""
        master = os.path.abspath(master)
        self.base_dir = os.path.dirname(master)
        for kw in self._read_file(master, frozenset()):
            yield kw

    # ------------------------------------------------------------------ #
    def _resolve(self, target, cur_dir):
        target = target.strip().strip('"').strip("'")
        cands = []
        if os.path.isabs(target):
            cands.append(target)
        else:
            cands.append(os.path.join(self.base_dir, target))
            if cur_dir != self.base_dir:
                cands.append(os.path.join(cur_dir, target))
        for p in cands:
            p = os.path.normpath(p)
            if os.path.isfile(p):
                return p
        return None

    def _handle_comment(self, path, lineno, s):
        body = s[2:].strip()
        if not body:
            return
        up = body.upper()
        if up.startswith("HMNAME"):
            self.hmnames.append((path, lineno, body))
            return
        # keyword bi comment?
        kw_like = False
        if body.startswith("*"):
            kw_like = True
        else:
            first = re.split(r"[,\s]", body, 1)[0].upper()
            if first in _VOCAB and ("," in body or "=" in body):
                kw_like = True
        if not kw_like:
            return
        self.commented_keywords.append((path, lineno, body))
        for mt in re.finditer(r"<([^<>\s,]+)>", body):
            self.comment_param_refs.append((mt.group(1), path, lineno))
        # include bi comment -> kiem tra file dich
        stripped = body.lstrip("*").strip()
        if stripped.upper().startswith("INCLUDE"):
            m = re.search(r"INPUT\s*=\s*([^,\s]+)", stripped, re.IGNORECASE)
            target = m.group(1) if m else "(khong ro INPUT=)"
            exists = bool(m and self._resolve(target, os.path.dirname(path)))
            self.commented_includes.append((path, lineno, target, exists))

    def _read_file(self, path, stack):
        rp = os.path.normcase(os.path.abspath(path))
        if rp in stack:
            self.read_errors.append((path, "include vong lap (cycle) - bo qua"))
            return
        stack = stack | {rp}
        self.files.append(path)
        try:
            f = open(path, "r", errors="replace")
        except OSError as e:
            self.read_errors.append((path, "khong mo duoc file: %s" % e))
            return
        kw = None
        with f:
            for lineno, raw in enumerate(f, 1):
                s = raw.strip()
                if not s:
                    continue
                if s.startswith("**"):
                    self._handle_comment(path, lineno, s)
                    continue
                if s.startswith("*"):
                    if kw is not None:
                        yield kw
                        kw = None
                    name, params = parse_keyword_line(s)
                    if name == "INCLUDE":
                        target = params.get("INPUT")
                        if isinstance(target, str) and target:
                            resolved = self._resolve(target, os.path.dirname(path))
                            self.includes.append((path, lineno, target, resolved))
                            if resolved:
                                for sub_kw in self._read_file(resolved, stack):
                                    yield sub_kw
                            else:
                                self.missing_includes.append((path, lineno, target))
                        else:
                            self.missing_includes.append((path, lineno, "(khong co INPUT=)"))
                        continue
                    kw = Keyword(name, params, path, lineno)
                    continue
                # data line
                if kw is not None:
                    kw.data.append((lineno, s))
                else:
                    self.orphan_data.append((path, lineno, s))
        if kw is not None:
            yield kw
