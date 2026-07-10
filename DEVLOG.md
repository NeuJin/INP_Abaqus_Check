# DEVLOG — INP_Abaqus_Check

> **🔄 HANDOFF:** Validator Python (stdlib only, 3.9+) cho deck Abaqus .inp xuất từ HyperMesh 14 — project K12E conrod.
> Đọc `docs/K12E_DECK_FORMAT.md` = bản đồ format deck ĐẦY ĐỦ (§9 = bẫy parser).
> **Trạng thái: tool CHÍNH `inp_check.py` đã viết xong đủ 9 nhóm check, regression test 16/16 PASS trên deck synthetic. CHƯA chạy trên deck K12E thật** (file nằm máy khác) — việc tiếp theo là user chạy trên deck thật, gửi output về để tinh chỉnh (ngưỡng gap-tol, false positive nhóm 7, keyword unknown nếu có). Test: `python tests\run_test.py`.

---

## 2026-07-10 (chiều) — Viết xong tool chính `inp_check.py` v0.2.0

- **Kiến trúc**: package `inpcheck/` — `reader.py` (resolve *INCLUDE đệ quy + chống cycle, phân loại comment 3 loại, normalize keyword bỏ space/`-`/case) → `model.py` (Builder dispatch `_kw_*`, thu refs kèm file:line ngay khi parse, continuation dấu phẩy, GENERATE, nested set refs, step context với OP) → `checks.py` (9 nhóm) → `geometry.py` (bảng mặt S1–S6 chuẩn Abaqus theo corner node, spatial hash Grid, union-find clustering).
- **9 nhóm check**: structure/include → symbol table (kể cả surface stale trỏ element đã xóa) → parameter `<tên>` (cả trong comment) → section/material → CLOAD/BC↔mesh (node ma + node lơ lửng, loại trừ ref node coupling/pretension/rigidbody) → share node (gom VÙNG theo 3×cạnh element) → hình học (7a lỗ thủng ≥2 cạnh giáp; 7b độ phủ slave↔master bằng khoảng cách pháp tuyến + in-plane ≤ 1.1×bán kính mặt master, TIE dùng POSITION TOLERANCE riêng; 7c mặt tự do áp nhau ngoài mọi surface, pháp tuyến ngược) → inventory comment → step report.
- **Quyết định thiết kế**: gap-tol mặc định = 0.2×cạnh element điển hình (median 2000 mẫu); nhóm 7b nếu >60% slave không phủ → nghi pair sai chứ không liệt kê từng mặt; console cap `--max-print`, full ra `--report`; exit 1 khi có ERROR (`--strict` tính cả WARN).
- **Test**: `tests/deck/` cài sẵn 16 lỗi (include chết ×2, symbol ma ×4, surface stale, param ×2, section thiếu, BC/CLOAD node ma ×2, share node, lỗ thủng surface, master không phủ, mặt áp nhau) — `tests/run_test.py` PASS 16/16, không false positive trên deck test.
- Message console toàn ASCII không dấu (tránh lỗi encoding console Nhật cp932).

### Next
1. Chạy trên deck K12E thật → tinh chỉnh (đặc biệt nhóm 7 với mặt cong bán kính lớn, và performance ~500k element).
2. Cân nhắc: diff cấu trúc cp0 vs cp1 (so pair-by-pair 2 file contact); cảnh báo mtime mesh mới hơn odb của *INITIAL CONDITIONS.

## 2026-07-10 — Khởi tạo repo

- **`check_shared_nodes.py`** (module phát hiện mất share node giữa các khối mesh riêng):
  - Parse `*NODE`/`*ELEMENT` (case-insensitive, continuation dấu phẩy, `*NODE` có param), spatial hash tìm cặp node trùng tọa độ trong `--tol`.
  - Chỉ báo critical khi **cả 2 node đều được element dùng** → tự loại reference node coupling trùng tọa độ cố ý (900005–900034 trong deck K12E) và node mồ côi.
  - Report kèm ELSET 2 phía (= tên component HyperMesh) để lọc cặp tie cố ý vs lỗi thật; console + CSV; exit 1 khi có finding.
  - Test pass với file synthetic (cặp lỗi giữa 2 block, cặp orphan bị loại đúng).
- **`docs/K12E_DECK_FORMAT.md`**: bản đồ format hoàn chỉnh — cấu trúc master+include, 3 loại element solid (C3D8I/C3D6/C3D10M) + membrane M3D4, 3 dạng surface, diff cp0/cp1, chuỗi phụ thuộc BUSH.odb→Comb, xương sống truyền tải MR_7→S_CONTACT_7→TIE→S_BE_SURFACE, inventory setup bị comment, 9 bẫy parser.
- Nguồn gốc: script viết đầu tiên trong `Result_Capture/inp_checker/`, đã move sang repo riêng này.

### Next (chờ user ra lệnh, theo ưu tiên)
1. Include resolver + symbol table xuyên file
2. CLOAD ↔ mesh (node 5xxxxx phải tồn tại & thuộc membrane)
3. Surface thủng / độ phủ contact hexa–tetra
4. Inventory comment + parameter `<tên>` không định nghĩa (`<cl_se>`!)
5. Bảng BC/tải hiệu lực per-step (OP=NEW) + ELSET↔SECTION↔MATERIAL
