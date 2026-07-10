#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inp_check_gui.py - GUI kieu HyperMesh cho validator deck Abaqus .inp.

Bo cuc mo phong HyperMesh 14:
  - trai  : Model browser (cay entity: Files/Components/Sets/Surfaces/Contact/
            Materials/Parameters/Steps, o mau nhu component HM)
  - duoi trai: bang Name/Value cua entity dang chon (giong property table HM)
  - phai  : ket qua 9 nhom check, to mau theo muc (LOI do / CANH BAO cam / info xam)

Chay:  python inp_check_gui.py [file.inp]
Selftest (khong can thao tac tay):  python inp_check_gui.py --selftest tests\\deck\\master.inp
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
import traceback

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_SCRIPT_DIR, "gui_config.json")


def _load_config():
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_config(cfg):
    try:
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
    except OSError:
        pass


def _detect_sakura():
    """Tim sakura.exe: PATH -> thu muc cai chuan -> App Paths registry."""
    import shutil
    p = shutil.which("sakura")
    if p:
        return p
    for c in (r"F:\Software\Sakura\Sakura\sakura-v2.4.1\sakura.exe",
              r"C:\Program Files (x86)\sakura\sakura.exe",
              r"C:\Program Files\sakura\sakura.exe"):
        if os.path.isfile(c):
            return c
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for sub in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\sakura.exe",
                        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\sakura.exe"):
                try:
                    with winreg.OpenKey(hive, sub) as k:
                        v = winreg.QueryValue(k, None)
                        if v and os.path.isfile(v):
                            return v
                except OSError:
                    continue
    except ImportError:
        pass
    return None

from inpcheck.reader import DeckReader
from inpcheck.model import Builder
from inpcheck import checks as C
from inpcheck import __version__

# ---- bang mau kieu HyperMesh classic ----
HM_BG = "#d6d3ce"        # nen xam panel
HM_PANEL = "#ece9e2"
HM_TREE_BG = "#ffffff"
HM_SEL = "#316ac5"       # xanh selection kieu Win/HM
COL_ERR = "#c00000"
COL_WARN = "#b25900"
COL_INFO = "#606060"
COL_GROUP = "#000080"
COL_MISS = "#c00000"

# mau o vuong component (xoay vong nhu HM)
COMP_COLORS = ["#00c8c8", "#c0c0c0", "#ff8040", "#ff2020", "#4080ff", "#ffff00",
               "#803050", "#ff40ff", "#30d030", "#3030ff", "#a06030", "#8080ff",
               "#ff8080", "#40ff90", "#d0d060", "#b070e0"]

SEV_LABEL = {"ERROR": "LOI", "WARN": "CANH BAO", "INFO": "info"}


class App(object):
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("INP Abaqus Check v%s  -  (chua mo file)" % __version__)
        self.root.geometry("1280x760")
        self.root.configure(bg=HM_BG)

        self.path = None
        self.reader = None
        self.model = None
        self.findings = []
        self.detail_map = {}      # tree item id -> list (name, value)
        self.loc_map = {}         # tree item id -> (file, line) de double-click mo editor
        self.finding_map = {}     # findings item id -> Finding
        self.config = _load_config()
        self.editor_path = self.config.get("editor")
        if not (self.editor_path and os.path.isfile(self.editor_path)):
            self.editor_path = _detect_sakura()
        self._swatches = []       # giu tham chieu PhotoImage
        self._swatch_cache = {}
        self.q = queue.Queue()
        self.busy = False

        self._build_style()
        self._build_toolbar()
        self._build_body()
        self._build_statusbar()
        self.root.after(100, self._poll_queue)

    # ------------------------------------------------------------- UI --
    def _build_style(self):
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=HM_BG, font=("Segoe UI", 9))
        st.configure("TNotebook", background=HM_BG)
        st.configure("TNotebook.Tab", padding=(10, 2))
        st.configure("Treeview", background=HM_TREE_BG, fieldbackground=HM_TREE_BG,
                     rowheight=19, font=("Segoe UI", 9))
        st.configure("Treeview.Heading", background=HM_PANEL, font=("Segoe UI", 9))
        st.map("Treeview", background=[("selected", HM_SEL)],
               foreground=[("selected", "#ffffff")])
        st.configure("TButton", padding=(8, 2))
        st.configure("TCheckbutton", background=HM_BG)
        st.configure("TLabel", background=HM_BG)

    def _build_toolbar(self):
        bar = tk.Frame(self.root, bg=HM_BG, bd=1, relief="raised")
        bar.pack(side="top", fill="x")
        self.btn_open = ttk.Button(bar, text="Mo file .inp...", command=self.on_open)
        self.btn_open.pack(side="left", padx=(6, 2), pady=3)
        self.btn_run = ttk.Button(bar, text="Chay check", command=self.on_run,
                                  state="disabled")
        self.btn_run.pack(side="left", padx=2, pady=3)
        self.btn_export = ttk.Button(bar, text="Xuat bao cao...",
                                     command=self.on_export, state="disabled")
        self.btn_export.pack(side="left", padx=2, pady=3)

        ttk.Label(bar, text="   tol:").pack(side="left")
        self.var_tol = tk.StringVar(value="1e-4")
        tk.Entry(bar, textvariable=self.var_tol, width=8).pack(side="left")
        ttk.Label(bar, text="  gap-tol:").pack(side="left")
        self.var_gap = tk.StringVar(value="")
        tk.Entry(bar, textvariable=self.var_gap, width=8).pack(side="left")
        ttk.Label(bar, text="(trong = tu dong)").pack(side="left")
        self.var_nogeom = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Bo qua check hinh hoc",
                        variable=self.var_nogeom).pack(side="left", padx=8)
        ttk.Button(bar, text="Editor...",
                   command=self.on_set_editor).pack(side="right", padx=6, pady=3)

    def _build_body(self):
        paned = ttk.Panedwindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=2, pady=2)

        # ============ TRAI: Model browser kieu HyperMesh ============
        left = tk.Frame(paned, bg=HM_BG)
        paned.add(left, weight=1)
        nb_l = ttk.Notebook(left)
        nb_l.pack(fill="both", expand=True)
        tabm = tk.Frame(nb_l, bg=HM_BG)
        nb_l.add(tabm, text="Model")

        pl = ttk.Panedwindow(tabm, orient="vertical")
        pl.pack(fill="both", expand=True)

        fr_tree = tk.Frame(pl, bg=HM_BG)
        pl.add(fr_tree, weight=3)
        self.tree = ttk.Treeview(fr_tree, columns=("id",), selectmode="browse")
        self.tree.heading("#0", text="Entities", anchor="w")
        self.tree.heading("id", text="ID / Count", anchor="w")
        self.tree.column("#0", width=260, stretch=True)
        self.tree.column("id", width=90, stretch=False)
        vsb = ttk.Scrollbar(fr_tree, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("missing", foreground=COL_MISS)
        self.tree.tag_configure("cat", foreground=COL_GROUP,
                                font=("Segoe UI", 9, "bold"))
        self.tree.bind("<<TreeviewSelect>>", self.on_select_entity)
        self.tree.bind("<Double-1>", self.on_dbl_entity)

        fr_det = tk.Frame(pl, bg=HM_BG)
        pl.add(fr_det, weight=2)
        self.detail = ttk.Treeview(fr_det, columns=("val",), selectmode="none")
        self.detail.heading("#0", text="Name", anchor="w")
        self.detail.heading("val", text="Value", anchor="w")
        self.detail.column("#0", width=130, stretch=False)
        self.detail.column("val", width=220, stretch=True)
        vsb2 = ttk.Scrollbar(fr_det, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=vsb2.set)
        self.detail.pack(side="left", fill="both", expand=True)
        vsb2.pack(side="right", fill="y")

        # ============ PHAI: ket qua check ============
        right = tk.Frame(paned, bg=HM_BG)
        paned.add(right, weight=3)
        nb_r = ttk.Notebook(right)
        nb_r.pack(fill="both", expand=True)
        tabc = tk.Frame(nb_r, bg=HM_BG)
        nb_r.add(tabc, text="Check Results")

        fbar = tk.Frame(tabc, bg=HM_BG)
        fbar.pack(fill="x")
        ttk.Label(fbar, text="Hien thi:").pack(side="left", padx=(6, 2))
        self.var_show = {"ERROR": tk.BooleanVar(value=True),
                         "WARN": tk.BooleanVar(value=True),
                         "INFO": tk.BooleanVar(value=True)}
        for sev, txt in (("ERROR", "LOI"), ("WARN", "CANH BAO"), ("INFO", "info")):
            ttk.Checkbutton(fbar, text=txt, variable=self.var_show[sev],
                            command=self.populate_findings).pack(side="left", padx=4)

        pr = ttk.Panedwindow(tabc, orient="vertical")
        pr.pack(fill="both", expand=True)
        fr_res = tk.Frame(pr, bg=HM_BG)
        pr.add(fr_res, weight=4)
        self.res = ttk.Treeview(fr_res, columns=("sev", "where"), selectmode="browse")
        self.res.heading("#0", text="Phat hien", anchor="w")
        self.res.heading("sev", text="Muc", anchor="w")
        self.res.heading("where", text="Vi tri (file:dong)", anchor="w")
        self.res.column("#0", width=560, stretch=True)
        self.res.column("sev", width=75, stretch=False)
        self.res.column("where", width=210, stretch=False)
        vsb3 = ttk.Scrollbar(fr_res, orient="vertical", command=self.res.yview)
        self.res.configure(yscrollcommand=vsb3.set)
        self.res.pack(side="left", fill="both", expand=True)
        vsb3.pack(side="right", fill="y")
        self.res.tag_configure("ERROR", foreground=COL_ERR)
        self.res.tag_configure("WARN", foreground=COL_WARN)
        self.res.tag_configure("INFO", foreground=COL_INFO)
        self.res.tag_configure("group", foreground=COL_GROUP,
                               font=("Segoe UI", 9, "bold"))
        self.res.bind("<<TreeviewSelect>>", self.on_select_finding)
        self.res.bind("<Double-1>", self.on_dbl_finding)

        fr_txt = tk.Frame(pr, bg=HM_BG)
        pr.add(fr_txt, weight=1)
        tbar = tk.Frame(fr_txt, bg=HM_BG)
        tbar.pack(fill="x")
        ttk.Label(tbar, text="Chi tiet:  (double-click 1 dong de mo editor "
                             "ngay tai dong loi)").pack(side="left", padx=4)
        ttk.Button(tbar, text="Copy vi tri",
                   command=self.on_copy_loc).pack(side="right", padx=4, pady=1)
        self.txt = tk.Text(fr_txt, height=4, wrap="word", font=("Consolas", 9),
                           bg="#fffff4", state="disabled")
        self.txt.pack(fill="both", expand=True, padx=2, pady=(0, 2))

    def _build_statusbar(self):
        self.status = tk.Label(self.root, text="Mo file .inp master de bat dau",
                               bg=HM_PANEL, anchor="w", bd=1, relief="sunken")
        self.status.pack(side="bottom", fill="x")

    # -------------------------------------------------------- helpers --
    def _swatch(self, color):
        img = self._swatch_cache.get(color)
        if img is None:
            img = tk.PhotoImage(width=11, height=11)
            img.put("#404040", to=(0, 0, 11, 11))
            img.put(color, to=(1, 1, 10, 10))
            self._swatch_cache[color] = img
            self._swatches.append(img)
        return img

    def _set_status(self, txt):
        self.status.config(text=txt)

    def _set_detail(self, rows):
        self.detail.delete(*self.detail.get_children())
        for name, val in rows:
            self.detail.insert("", "end", text=str(name), values=(str(val),))

    def _rel(self, path):
        if not path:
            return ""
        base = os.path.dirname(self.path) if self.path else ""
        try:
            return os.path.relpath(path, base)
        except ValueError:
            return path

    # -------------------------------------------------------- actions --
    def on_open(self):
        p = filedialog.askopenfilename(
            title="Chon file .inp master",
            filetypes=[("Abaqus input", "*.inp *.inc"), ("Tat ca", "*.*")])
        if p:
            self.load_path(p)

    def load_path(self, path, sync=False):
        if self.busy:
            return
        self.path = os.path.abspath(path)
        self.root.title("INP Abaqus Check v%s  -  %s"
                        % (__version__, os.path.basename(self.path)))
        self._set_status("Dang doc deck: %s ..." % self.path)
        self.btn_run.config(state="disabled")
        self.btn_export.config(state="disabled")
        self.busy = True
        if sync:
            self._work_parse()
            self._poll_queue()
        else:
            threading.Thread(target=self._work_parse, daemon=True).start()

    def _work_parse(self):
        try:
            t0 = time.time()
            reader = DeckReader()
            builder = Builder()
            for kw in reader.read(self.path):
                builder.feed(kw)
            model = builder.finalize()
            self.q.put(("parsed", reader, model, time.time() - t0))
        except Exception:
            self.q.put(("error", traceback.format_exc()))

    def on_run(self):
        if self.busy or self.model is None:
            return
        try:
            tol = float(self.var_tol.get())
        except ValueError:
            tol = 1e-4
            self.var_tol.set("1e-4")
        gap = None
        if self.var_gap.get().strip():
            try:
                gap = float(self.var_gap.get())
            except ValueError:
                gap = None
                self.var_gap.set("")
        self.busy = True
        self._set_status("Dang chay check ...")
        self.btn_run.config(state="disabled")
        threading.Thread(target=self._work_check, args=(tol, gap),
                         daemon=True).start()

    def run_checks_sync(self, tol=1e-4, gap=None):
        self.busy = True
        self._work_check(tol, gap)
        self._poll_queue()

    def _work_check(self, tol, gap):
        try:
            t0 = time.time()
            F = []
            F += C.check_structure(self.reader)
            F += C.check_symbols(self.model)
            F += C.check_parameters(self.model, self.reader)
            F += C.check_sections(self.model)
            F += C.check_loads(self.model)
            F += C.check_shared_nodes(self.model, tol)
            if not self.var_nogeom.get():
                F += C.check_geometry(self.model, gap_tol=gap)
            F += C.check_groups(self.model)
            F += C.check_commented(self.reader)
            F += C.step_report(self.model)
            self.q.put(("checked", F, time.time() - t0))
        except Exception:
            self.q.put(("error", traceback.format_exc()))

    def on_export(self):
        if not self.findings:
            return
        p = filedialog.asksaveasfilename(
            title="Luu bao cao", defaultextension=".txt",
            filetypes=[("Text", "*.txt")],
            initialfile="inp_check_report.txt")
        if not p:
            return
        with open(p, "w", encoding="utf-8") as f:
            f.write("inp_check v%s - %s\n" % (__version__, self.path))
            for check in C.CHECK_ORDER:
                group = [fd for fd in self.findings if fd.check == check]
                if not group:
                    continue
                f.write("\n=== %s ===\n" % check)
                for fd in group:
                    loc = ""
                    if fd.file:
                        loc = "  (%s:%d)" % (self._rel(fd.file), fd.line)
                    f.write("  [%s] %s%s\n" % (SEV_LABEL[fd.sev], fd.msg, loc))
        self._set_status("Da luu bao cao: %s" % p)

    def on_copy_loc(self):
        sel = self.res.selection()
        if not sel:
            return
        fd = self.finding_map.get(sel[0])
        if fd and fd.file:
            loc = "%s:%d" % (fd.file, fd.line)
            self.root.clipboard_clear()
            self.root.clipboard_append(loc)
            self._set_status("Da copy: %s" % loc)

    # ------------------------------------------------- mo editor ------
    def on_set_editor(self):
        """Nut Editor... tren toolbar: chi dinh sakura.exe, luu gui_config.json."""
        cur = self.editor_path or "(chua co)"
        p = filedialog.askopenfilename(
            title="Chon sakura.exe (hien tai: %s)" % cur,
            filetypes=[("Executable", "*.exe"), ("Tat ca", "*.*")])
        if p:
            self.editor_path = p
            self.config["editor"] = p
            _save_config(self.config)
            self._set_status("Editor: %s (da luu vao gui_config.json)" % p)
        else:
            self._set_status("Editor hien tai: %s" % cur)

    def _ask_editor(self):
        """Hoi duong dan sakura.exe 1 lan, luu vao gui_config.json."""
        messagebox.showinfo(
            "Chon editor",
            "Chua tim thay sakura.exe tren may nay.\n"
            "Chon file sakura.exe (hoac editor khac) de mo file tai dong loi.\n"
            "Chon xong se duoc nho cho cac lan sau (gui_config.json).\n"
            "Bam Cancel de mo bang editor mac dinh cua Windows (khong nhay dong).")
        p = filedialog.askopenfilename(
            title="Chon sakura.exe",
            filetypes=[("Executable", "*.exe"), ("Tat ca", "*.*")])
        if p:
            self.editor_path = p
            self.config["editor"] = p
            _save_config(self.config)
        return p

    def _open_editor(self, path, line):
        if not path or not os.path.isfile(path):
            self._set_status("File khong ton tai: %s" % (path or "?"))
            return
        if not (self.editor_path and os.path.isfile(self.editor_path)):
            self._ask_editor()
        if self.editor_path and os.path.isfile(self.editor_path):
            # sakura ho tro -Y=<dong> -X=<cot>; editor khac nhan file la duoc
            try:
                subprocess.Popen([self.editor_path, "-Y=%d" % max(1, line),
                                  "-X=1", path])
                self._set_status("Mo %s:%d bang %s" %
                                 (self._rel(path), line,
                                  os.path.basename(self.editor_path)))
                return
            except OSError as e:
                self._set_status("Khong chay duoc editor: %s" % e)
        try:
            os.startfile(path)
            self._set_status("Mo %s bang editor mac dinh (khong nhay dong duoc)"
                             % self._rel(path))
        except OSError as e:
            self._set_status("Khong mo duoc file: %s" % e)

    def on_dbl_finding(self, _ev=None):
        sel = self.res.selection()
        if not sel:
            return
        fd = self.finding_map.get(sel[0])
        if fd is None:
            return  # dong header nhom
        if fd.file:
            self._open_editor(fd.file, fd.line)
        else:
            self._set_status(
                "Finding nay khong gan voi dong file cu the (cot 'Vi tri' rong) "
                "- vd VUNG share node: dung toa do trong message de tim trong HyperMesh")

    def on_dbl_entity(self, _ev=None):
        sel = self.tree.selection()
        if not sel:
            return
        if sel[0] in self.loc_map:
            f, l = self.loc_map[sel[0]]
            self._open_editor(f, l)
        else:
            self._set_status("Muc nay khong co vi tri file de mo")

    # ------------------------------------------------------ populate --
    def _poll_queue(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "parsed":
                    _tag, self.reader, self.model, dt = msg
                    self.busy = False
                    self.populate_model()
                    m = self.model
                    self._set_status(
                        "Doc xong (%.1fs): %d file | %d node | %d element | "
                        "%d elset | %d surface | %d step  ->  bam 'Chay check'"
                        % (dt, len(self.reader.files), len(m.nodes),
                           len(m.elements), len(m.elsets), len(m.surfaces),
                           len(m.steps)))
                    self.btn_run.config(state="normal")
                elif msg[0] == "checked":
                    _tag, self.findings, dt = msg
                    self.busy = False
                    self.populate_findings()
                    ne = sum(1 for f in self.findings if f.sev == "ERROR")
                    nw = sum(1 for f in self.findings if f.sev == "WARN")
                    ni = len(self.findings) - ne - nw
                    self._set_status("Check xong (%.1fs):  %d LOI  |  %d CANH BAO"
                                     "  |  %d info" % (dt, ne, nw, ni))
                    self.btn_run.config(state="normal")
                    self.btn_export.config(state="normal")
                elif msg[0] == "error":
                    self.busy = False
                    self.btn_run.config(
                        state="normal" if self.model else "disabled")
                    self._set_status("LOI: xem hop thoai")
                    messagebox.showerror("inp_check", msg[1][-2000:])
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def populate_model(self):
        t = self.tree
        t.delete(*t.get_children())
        self.detail_map.clear()
        self.loc_map.clear()
        m, rd = self.model, self.reader

        # ---- Files ----
        nf = t.insert("", "end", text="Files (%d)" % len(rd.files),
                      values=("",), tags=("cat",), open=True)
        for p in rd.files:
            iid = t.insert(nf, "end", text=self._rel(p) or os.path.basename(p),
                           values=("",))
            self.detail_map[iid] = [("File", p)]
            self.loc_map[iid] = (p, 1)
        for f, l, target in rd.missing_includes:
            iid = t.insert(nf, "end", text="%s  (KHONG TON TAI)" % target,
                           values=("",), tags=("missing",))
            self.detail_map[iid] = [("Include o", "%s:%d" % (self._rel(f), l)),
                                    ("Trang thai", "FILE KHONG TON TAI")]
            self.loc_map[iid] = (f, l)

        # ---- Components (ELSET co element) ----
        comp_names = sorted(n for n in m.elsets if m.elsets[n]["ids"])
        sec_by_elset = {}
        for kind, elset, mat, f, l in m.sections:
            if elset:
                sec_by_elset[elset] = (kind, mat)
        nc = t.insert("", "end", text="Components / ELSET (%d)" % len(comp_names),
                      values=("",), tags=("cat",), open=True)
        for i, name in enumerate(comp_names):
            ids = m.elset_ids(name)
            etypes = sorted(set(m.elements[e][0] for e in ids[:200]
                                if e in m.elements))
            img = self._swatch(COMP_COLORS[i % len(COMP_COLORS)])
            iid = t.insert(nc, "end", text=name, values=(len(ids),), image=img)
            kind, mat = sec_by_elset.get(name, ("(KHONG CO SECTION)", "-"))
            rows = [("Name", name), ("Elements", len(ids)),
                    ("Type", ", ".join(etypes)), ("Section", kind),
                    ("Material", mat)]
            for f, l in m.elsets[name]["defs"][:3]:
                rows.append(("Dinh nghia", "%s:%d" % (self._rel(f), l)))
            self.detail_map[iid] = rows
            if m.elsets[name]["defs"]:
                self.loc_map[iid] = m.elsets[name]["defs"][0]

        # ---- Node sets ----
        nn = t.insert("", "end", text="Node Sets (%d)" % len(m.nsets),
                      values=("",), tags=("cat",))
        for name in sorted(m.nsets):
            ids = m.nset_ids(name)
            iid = t.insert(nn, "end", text=name, values=(len(ids),))
            rows = [("Name", name), ("Nodes", len(ids))]
            if ids:
                rows.append(("Vi du", ", ".join(str(x) for x in ids[:8])))
            self.detail_map[iid] = rows
            if m.nsets[name]["defs"]:
                self.loc_map[iid] = m.nsets[name]["defs"][0]

        # ---- Surfaces ----
        ns = t.insert("", "end", text="Surfaces (%d)" % len(m.surfaces),
                      values=("",), tags=("cat",))
        for name in sorted(m.surfaces):
            s = m.surfaces[name]
            iid = t.insert(ns, "end", text=name, values=(len(s.items),))
            rows = [("Name", name), ("Type", s.kind),
                    ("Items (dong data)", len(s.items))]
            for f, l in s.defs[:3]:
                rows.append(("Dinh nghia", "%s:%d" % (self._rel(f), l)))
            self.detail_map[iid] = rows
            if s.defs:
                self.loc_map[iid] = s.defs[0]

        # ---- Contact ----
        ncc = t.insert("", "end",
                       text="Contact (%d pair / %d tie)"
                       % (len(m.contact_pairs), len(m.ties)),
                       values=("",), tags=("cat",))
        for sl, ms, inter, step, f, l in m.contact_pairs:
            iid = t.insert(ncc, "end", text="PAIR  %s  <->  %s" % (sl, ms),
                           values=("",))
            self.detail_map[iid] = [
                ("Slave", sl), ("Master", ms), ("Interaction", inter or "-"),
                ("Step", step or "(model)"),
                ("Dinh nghia", "%s:%d" % (self._rel(f), l))]
            self.loc_map[iid] = (f, l)
        for name, sl, ms, postol, step, f, l in m.ties:
            iid = t.insert(ncc, "end", text="TIE   %s  <->  %s" % (sl, ms),
                           values=("",))
            self.detail_map[iid] = [
                ("Name", name or "-"), ("Slave", sl), ("Master", ms),
                ("Position tol", postol if postol is not None else "-"),
                ("Dinh nghia", "%s:%d" % (self._rel(f), l))]
            self.loc_map[iid] = (f, l)

        # ---- Materials ----
        nm = t.insert("", "end", text="Materials (%d)" % len(m.materials),
                      values=("",), tags=("cat",))
        for name in sorted(m.materials):
            f, l = m.materials[name]
            iid = t.insert(nm, "end", text=name, values=("",))
            self.detail_map[iid] = [("Name", name),
                                    ("Dinh nghia", "%s:%d" % (self._rel(f), l))]
            self.loc_map[iid] = (f, l)

        # ---- Parameters ----
        np_ = t.insert("", "end", text="Parameters (%d)" % len(m.parameters),
                       values=("",), tags=("cat",))
        for name in sorted(m.parameters):
            f, l = m.parameters[name]
            iid = t.insert(np_, "end", text=name, values=("",))
            self.detail_map[iid] = [("Name", name),
                                    ("Dinh nghia", "%s:%d" % (self._rel(f), l))]
            self.loc_map[iid] = (f, l)

        # ---- Steps ----
        nst = t.insert("", "end", text="Steps (%d)" % len(m.steps),
                       values=("",), tags=("cat",))
        for st in m.steps:
            iid = t.insert(nst, "end", text=st.name, values=("",))
            self.detail_map[iid] = [
                ("Name", st.name),
                ("BC", "%d dong" % len(st.boundaries)),
                ("CLOAD", "%d dong" % st.cload_lines),
                ("DLOAD", ", ".join(sorted(st.dload_types)) or "-"),
                ("Interference", st.n_interference),
                ("Model change", st.n_modelchange),
                ("Vi tri", "%s:%d" % (self._rel(st.file), st.line))]
            self.loc_map[iid] = (st.file, st.line)

    def populate_findings(self):
        r = self.res
        r.delete(*r.get_children())
        self.finding_map.clear()
        show = {s for s, v in self.var_show.items() if v.get()}
        for check in C.CHECK_ORDER:
            group = [fd for fd in self.findings if fd.check == check]
            if not group:
                continue
            vis = [fd for fd in group if fd.sev in show]
            ne = sum(1 for fd in group if fd.sev == "ERROR")
            nw = sum(1 for fd in group if fd.sev == "WARN")
            ni = len(group) - ne - nw
            gid = r.insert("", "end",
                           text="%s   (%d loi / %d canh bao / %d info)"
                           % (check, ne, nw, ni),
                           values=("", ""), tags=("group",),
                           open=(ne > 0 or nw > 0))
            order = {"ERROR": 0, "WARN": 1, "INFO": 2}
            for fd in sorted(vis, key=lambda x: order[x.sev]):
                loc = "%s:%d" % (self._rel(fd.file), fd.line) if fd.file else ""
                iid = r.insert(gid, "end", text=fd.msg,
                               values=(SEV_LABEL[fd.sev], loc), tags=(fd.sev,))
                self.finding_map[iid] = fd

    # ------------------------------------------------------- events --
    def on_select_entity(self, _ev=None):
        sel = self.tree.selection()
        if sel and sel[0] in self.detail_map:
            self._set_detail(self.detail_map[sel[0]])

    def on_select_finding(self, _ev=None):
        sel = self.res.selection()
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        if sel:
            fd = self.finding_map.get(sel[0])
            if fd:
                self.txt.insert("end", "[%s] %s\n" % (SEV_LABEL[fd.sev], fd.msg))
                if fd.file:
                    self.txt.insert("end", "File: %s\nDong: %d" % (fd.file, fd.line))
        self.txt.config(state="disabled")

    # -------------------------------------------------------------- --
    def run(self):
        self.root.mainloop()


def selftest(path):
    """Load + check khong can thao tac tay; in tong ket roi thoat."""
    app = App()
    app.root.update()
    app.load_path(path, sync=True)
    app.root.update()
    assert app.model is not None, "parse that bai"
    app.run_checks_sync()
    app.root.update()
    ne = sum(1 for f in app.findings if f.sev == "ERROR")
    nw = sum(1 for f in app.findings if f.sev == "WARN")
    n_tree = len(app.tree.get_children())
    n_res = len(app.res.get_children())
    print("SELFTEST: %d nhom entity, %d nhom finding, %d LOI, %d CANH BAO"
          % (n_tree, n_res, ne, nw))
    ok = app.model.nodes and app.findings and n_tree >= 6 and n_res >= 5
    app.root.destroy()
    if not ok:
        print("SELFTEST: FAIL")
        return 1
    print("SELFTEST: PASS")
    return 0


def main():
    args = sys.argv[1:]
    if args and args[0] == "--selftest":
        sys.exit(selftest(args[1] if len(args) > 1
                          else os.path.join("tests", "deck", "master.inp")))
    app = App()
    if args and os.path.isfile(args[0]):
        app.root.after(200, lambda: app.load_path(args[0]))
    app.run()


if __name__ == "__main__":
    main()
