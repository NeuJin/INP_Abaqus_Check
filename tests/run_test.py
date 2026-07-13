#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression test: chay inp_check tren test deck va kiem tra du 15 finding cai san.

Chay:  python tests/run_test.py   (tu thu muc goc repo)
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DECK = os.path.join(HERE, "deck", "master.inp")
REPORT = os.path.join(HERE, "deck", "_test_report.txt")

EXPECTED = [
    # (chuoi phai xuat hien trong report, mo ta)
    ("missing_file.inp", "include tro file khong ton tai"),
    ("old_stuff.inp", "include bi comment + file dich khong ton tai"),
    ("'s_ghost'", "surface ma trong contact pair"),
    ("'nd_ghost'", "nset ma trong boundary"),
    ("'FRICT_missing'", "interaction ma"),
    ("'STEEL_missing'", "material ma"),
    ("'s_stale' tro toi 1 element KHONG ton tai", "surface stale sau remesh"),
    ("<Pmiss>", "parameter chua dinh nghia (active)"),
    ("<cl_test>", "parameter chua dinh nghia (trong comment)"),
    ("element cua 'BLOCK_B' KHONG thuoc section", "elset thieu section"),
    ("*BOUNDARY tro node 88888", "BC node khong ton tai"),
    ("*CLOAD tro node 99999", "cload node khong ton tai"),
    ("node 10/210 | BLOCK_A <-> BLOCK_B", "mat share node"),
    ("nghi MAT SHARE NODE", "vung khong thuoc contact -> ERROR"),
    ("CONTACT s_side_A<->s_side_D (2 lop node CO CHU DICH)",
     "vung 2 lop node co contact -> phan loai INFO"),
    ("nghi thieu element 102", "lo thung trong surface"),
    ("vd elem 203) - master thung/hut?", "mat slave khong duoc master phu"),
    ("vd elem 102/202", "cap mat tu do ap nhau ngoai surface"),
    ("PATTERN MISMATCH BLOCK_E <-> BLOCK_F", "pattern mismatch tai mat share node"),
    ("s_top_G<->s_bot_H: lech bien dang", "stats khoang cach co dau slave->master"),
    ("VUNG XUYEN THAU", "2 mat contact cat nhau (lech bien dang)"),
    ("GHEP SHARE-NODE KHONG KHOP BLOCK_I <-> BLOCK_J",
     "ghep share-node lech bien dang, khong can contact pair"),
    ("group 's_stale' trong pair khong resolve duoc mat nao",
     "group rong/stale nam trong pair -> ERROR"),
    ("LON HON master", "dien tich slave > master (master hut)"),
    ("bi tach thanh 2 mang roi rac", "surface tach mang (chon sot/nham element)"),
    ("ti le dt slave/master", "thong ke dien tich 2 phia moi pair"),
    ("GROUP CHONG NHAU: 's_top_B' va 's_top_B2'", "2 group dung chung mat"),
    ("loai element/tiling khac nhau (hop le)",
     "dien tich lech nhung khong co vung thieu -> hop le (tile co khe)"),
    ("s_top_L<->s_tile_L: VUNG THIEU DOI DIEN",
     "thieu 1 tile giua pattern -> track duoc bang khoang cach nen"),
    ("dang tile pattern", "surface nhieu mang deu nhau = tile, khong bao nham"),
]


def main():
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "inp_check.py"), DECK,
         "--report", REPORT],
        cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 1:
        print("FAIL: exit code = %d (mong doi 1 vi deck co loi cai san)" % proc.returncode)
        print(proc.stdout)
        print(proc.stderr)
        return 1
    with open(REPORT, "r", encoding="utf-8") as f:
        report = f.read()
    failed = 0
    for needle, desc in EXPECTED:
        if needle in report:
            print("  OK  : %s" % desc)
        else:
            print("  FAIL: %s (khong thay: %r)" % (desc, needle))
            failed += 1
    print()
    if failed:
        print("FAIL: %d/%d finding khong xuat hien" % (failed, len(EXPECTED)))
        return 1
    print("PASS: du %d/%d finding, exit code dung" % (len(EXPECTED), len(EXPECTED)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
