#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inp_check.py - validator deck Abaqus .inp (HyperMesh export). Stdlib only.

Chay:
    python inp_check.py duong\\dan\\master.inp [tuy chon]

Tuy chon:
    --tol X         dung sai trung toa do cho check share-node (mac dinh 1e-4)
    --gap-tol X     khe ho cho phep khi check do phu contact
                    (mac dinh 0.2 x canh element dien hinh; TIE dung POSITION TOLERANCE rieng)
    --no-geom       bo qua nhom check hinh hoc (nhanh hon voi deck rat lon)
    --report FILE   ghi FULL bao cao ra file text (console chi in tom tat)
    --max-print N   so dong toi da in ra console cho moi nhom check (mac dinh 15)
    --strict        WARN cung lam exit code = 1

Exit code: 0 = khong co ERROR; 1 = co ERROR (hoac WARN neu --strict).
"""
import argparse
import os
import sys
import time

from inpcheck.reader import DeckReader
from inpcheck.model import Builder
from inpcheck import checks as C
from inpcheck import __version__

_SEV_TAG = {"ERROR": "[LOI ]", "WARN": "[CANH]", "INFO": "[info]"}
_SEV_RANK = {"ERROR": 0, "WARN": 1, "INFO": 2}


def _fmt(finding, base_dir):
    loc = ""
    if finding.file:
        rel = os.path.relpath(finding.file, base_dir) if base_dir else finding.file
        loc = " (%s:%d)" % (rel, finding.line) if finding.line else " (%s)" % rel
    return "%s %s%s" % (_SEV_TAG[finding.sev], finding.msg, loc)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Validator deck Abaqus .inp - phat hien loi xot trong setup")
    ap.add_argument("inp", help="file .inp master (se tu lan theo *INCLUDE)")
    ap.add_argument("--tol", type=float, default=1e-4)
    ap.add_argument("--gap-tol", type=float, default=None)
    ap.add_argument("--pen-tol", type=float, default=None,
                    help="nguong bao xuyen thau giua 2 mat contact "
                         "(mac dinh 0.1 x canh element dien hinh)")
    ap.add_argument("--no-geom", action="store_true")
    ap.add_argument("--report", default=None)
    ap.add_argument("--max-print", type=int, default=15)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)

    t0 = time.time()
    print("inp_check v%s" % __version__)
    print("Dang doc deck: %s" % args.inp)
    reader = DeckReader()
    builder = Builder()
    for kw in reader.read(args.inp):
        builder.feed(kw)
    m = builder.finalize()
    print("  %d file | %d node | %d element | %d elset | %d nset | %d surface | %d step"
          % (len(reader.files), len(m.nodes), len(m.elements), len(m.elsets),
             len(m.nsets), len(m.surfaces), len(m.steps)))
    print("  canh element dien hinh ~ %.4g (don vi model)  (%.1fs)"
          % (m.median_edge, time.time() - t0))

    findings = []
    findings += C.check_structure(reader)
    findings += C.check_symbols(m)
    findings += C.check_parameters(m, reader)
    findings += C.check_sections(m)
    findings += C.check_loads(m)
    print("Dang check share node (tol=%g)..." % args.tol)
    findings += C.check_shared_nodes(m, args.tol)
    if not args.no_geom:
        print("Dang check hinh hoc contact/surface...")
        findings += C.check_geometry(m, gap_tol=args.gap_tol, pen_tol=args.pen_tol)
    findings += C.check_groups(m)
    findings += C.check_commented(reader)
    findings += C.step_report(m)

    base_dir = reader.base_dir
    by_check = {}
    for fd in findings:
        by_check.setdefault(fd.check, []).append(fd)

    lines_console = []
    lines_full = []
    for check in C.CHECK_ORDER:
        group = by_check.get(check)
        if not group:
            continue
        group.sort(key=lambda fd: _SEV_RANK[fd.sev])
        ne = sum(1 for fd in group if fd.sev == "ERROR")
        nw = sum(1 for fd in group if fd.sev == "WARN")
        ni = len(group) - ne - nw
        head = "=== %s === (%d loi / %d canh bao / %d info)" % (check, ne, nw, ni)
        lines_console.append("")
        lines_console.append(head)
        lines_full.append("")
        lines_full.append(head)
        for i, fd in enumerate(group):
            line = "  " + _fmt(fd, base_dir)
            lines_full.append(line)
            if i < args.max_print:
                lines_console.append(line)
        if len(group) > args.max_print:
            lines_console.append("  ... (%d dong nua - xem --report)"
                                 % (len(group) - args.max_print))

    total_e = sum(1 for fd in findings if fd.sev == "ERROR")
    total_w = sum(1 for fd in findings if fd.sev == "WARN")
    total_i = len(findings) - total_e - total_w
    summary = [
        "",
        "=" * 60,
        "TONG KET: %d LOI | %d CANH BAO | %d info  (%.1fs)"
        % (total_e, total_w, total_i, time.time() - t0),
        "=" * 60,
    ]

    out = "\n".join(lines_console + summary)
    try:
        print(out)
    except UnicodeEncodeError:
        print(out.encode("ascii", "replace").decode("ascii"))

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write("inp_check v%s - %s\n" % (__version__, args.inp))
            f.write("\n".join(lines_full + summary))
            f.write("\n")
        print("Da ghi bao cao day du: %s" % args.report)

    if total_e > 0 or (args.strict and total_w > 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
