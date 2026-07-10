#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_shared_nodes.py - Tim cac cap node trung toa do trong file Abaqus .inp
(phat hien cho bi MAT share node giua cac khoi mesh rieng).

Nguyen ly:
  - Share node thanh cong  -> 2 khoi dung CHUNG 1 node ID tai mat tiep giap.
  - Bi xot                 -> ton tai 2 node ID khac nhau, toa do trung nhau
                              (trong dung sai --tol), va ca 2 deu duoc element su dung.
  - Cap node giua 2 mat *TIE / *CONTACT PAIR la CO Y -> loc bang cot elset trong report.

Chay:  python check_shared_nodes.py model.inp [--tol 1e-4] [--csv report.csv]

Python 3.9+ stdlib only.
"""

import argparse
import csv
import math
import sys
import time
from collections import defaultdict


def parse_inp(path):
    """Doc file .inp: tra ve (nodes, node_elsets, used_nodes).

    nodes       : {node_id: (x, y, z)}
    node_elsets : {node_id: set(ten ELSET tu header *ELEMENT)}
    used_nodes  : set(node_id duoc it nhat 1 element tham chieu)
    """
    nodes = {}
    node_elsets = defaultdict(set)
    used_nodes = set()

    mode = None          # None | "node" | "element"
    cur_elset = ""
    pending = []         # token cua element record dang doc do (dong ket thuc bang ",")

    def flush_element(tokens, elset):
        # record: elem_id, n1, n2, ... (node id 0 = bo trong)
        for tok in tokens[1:]:
            try:
                nid = int(tok)
            except ValueError:
                continue
            if nid > 0:
                used_nodes.add(nid)
                if elset:
                    node_elsets[nid].add(elset)

    with open(path, "r", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("**"):
                continue

            if line.startswith("*"):
                # dong keyword moi -> ket thuc record element dang do (neu co)
                if pending:
                    flush_element(pending, cur_elset)
                    pending = []
                upper = line.upper()
                keyword = upper.split(",")[0].strip()
                if keyword == "*NODE":
                    mode = "node"
                elif keyword == "*ELEMENT":
                    mode = "element"
                    cur_elset = ""
                    for part in line.split(",")[1:]:
                        k, _, v = part.partition("=")
                        if k.strip().upper() == "ELSET":
                            cur_elset = v.strip()
                else:
                    mode = None
                continue

            if mode == "node":
                toks = [t.strip() for t in line.split(",")]
                try:
                    nid = int(toks[0])
                    x = float(toks[1]) if len(toks) > 1 and toks[1] else 0.0
                    y = float(toks[2]) if len(toks) > 2 and toks[2] else 0.0
                    z = float(toks[3]) if len(toks) > 3 and toks[3] else 0.0
                except (ValueError, IndexError):
                    continue
                nodes[nid] = (x, y, z)

            elif mode == "element":
                toks = [t.strip() for t in line.rstrip(",").split(",") if t.strip()]
                pending.extend(toks)
                if not line.endswith(","):   # record ket thuc o dong nay
                    flush_element(pending, cur_elset)
                    pending = []

    if pending:
        flush_element(pending, cur_elset)

    return nodes, node_elsets, used_nodes


def find_coincident(nodes, tol):
    """Spatial hash: tra ve list (id1, id2, distance) voi distance <= tol, id1 < id2."""
    cell = tol if tol > 0 else 1e-12
    grid = defaultdict(list)
    for nid, (x, y, z) in nodes.items():
        grid[(int(math.floor(x / cell)),
              int(math.floor(y / cell)),
              int(math.floor(z / cell)))].append(nid)

    pairs = []
    tol2 = tol * tol
    seen_cells = set()
    for (cx, cy, cz), ids in grid.items():
        # gom node cua cell nay + 26 cell lan can (chi xet moi cap cell 1 lan)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    nb = (cx + dx, cy + dy, cz + dz)
                    if nb < (cx, cy, cz):
                        continue  # cap cell nay se duoc xet tu phia ben kia
                    if nb == (cx, cy, cz):
                        cand = ids
                        for i in range(len(cand)):
                            xi, yi, zi = nodes[cand[i]]
                            for j in range(i + 1, len(cand)):
                                xj, yj, zj = nodes[cand[j]]
                                d2 = (xi - xj) ** 2 + (yi - yj) ** 2 + (zi - zj) ** 2
                                if d2 <= tol2:
                                    a, b = sorted((cand[i], cand[j]))
                                    pairs.append((a, b, math.sqrt(d2)))
                    elif nb in grid:
                        for na in ids:
                            xa, ya, za = nodes[na]
                            for nb_id in grid[nb]:
                                xb, yb, zb = nodes[nb_id]
                                d2 = (xa - xb) ** 2 + (ya - yb) ** 2 + (za - zb) ** 2
                                if d2 <= tol2:
                                    a, b = sorted((na, nb_id))
                                    pairs.append((a, b, math.sqrt(d2)))
    return pairs


def main():
    ap = argparse.ArgumentParser(description="Tim cap node trung toa do (mat share node) trong file Abaqus .inp")
    ap.add_argument("inp", help="duong dan file .inp")
    ap.add_argument("--tol", type=float, default=1e-4,
                    help="dung sai trung toa do, don vi cua model (mac dinh 1e-4)")
    ap.add_argument("--csv", default=None, help="ghi report chi tiet ra file CSV")
    args = ap.parse_args()

    t0 = time.time()
    print("Dang doc file: %s" % args.inp)
    nodes, node_elsets, used_nodes = parse_inp(args.inp)
    print("  %d node, %d node duoc element su dung  (%.1fs)"
          % (len(nodes), len(used_nodes), time.time() - t0))

    orphan = set(nodes) - used_nodes
    if orphan:
        print("  Canh bao: %d node khong thuoc element nao (orphan)" % len(orphan))

    print("Dang tim node trung toa do (tol = %g)..." % args.tol)
    pairs = find_coincident(nodes, args.tol)

    # phan loai
    rows = []
    for a, b, d in sorted(pairs):
        ea = ",".join(sorted(node_elsets.get(a, []))) or "(khong ro)"
        eb = ",".join(sorted(node_elsets.get(b, []))) or "(khong ro)"
        both_used = a in used_nodes and b in used_nodes
        x, y, z = nodes[a]
        rows.append({
            "node1": a, "node2": b, "dist": d,
            "x": x, "y": y, "z": z,
            "elsets1": ea, "elsets2": eb,
            "both_used": both_used,
        })

    critical = [r for r in rows if r["both_used"]]
    print()
    print("=== KET QUA ===")
    print("Tong cap node trung toa do : %d" % len(rows))
    print("Cap ma CA 2 node deu dung  : %d  <-- ung vien mat share node" % len(critical))

    # thong ke theo cap elset de loc nhanh vung tie co y vs vung loi
    by_pair = defaultdict(int)
    for r in critical:
        by_pair[(r["elsets1"], r["elsets2"])] += 1
    if by_pair:
        print()
        print("Phan bo theo cap ELSET (vung *TIE co y thi bo qua):")
        for (e1, e2), n in sorted(by_pair.items(), key=lambda kv: -kv[1]):
            print("  %5d cap : %s  <->  %s" % (n, e1, e2))

    if critical:
        print()
        print("10 cap dau tien (toa do de tim lai trong HyperMesh):")
        for r in critical[:10]:
            print("  node %d / %d  tai (%.4f, %.4f, %.4f)  [%s <-> %s]"
                  % (r["node1"], r["node2"], r["x"], r["y"], r["z"],
                     r["elsets1"], r["elsets2"]))

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["node1", "node2", "dist", "x", "y", "z",
                                              "elsets1", "elsets2", "both_used"])
            w.writeheader()
            w.writerows(rows)
        print()
        print("Da ghi report: %s (%d dong)" % (args.csv, len(rows)))

    print()
    print("Xong. (%.1fs)" % (time.time() - t0))
    return 0 if not critical else 1


if __name__ == "__main__":
    sys.exit(main())
