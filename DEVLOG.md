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

## 2026-07-10 (tối) — GUI kiểu HyperMesh `inp_check_gui.py`

- tkinter, bố cục mô phỏng HM14: trái = Model browser (Treeview Entities|ID/Count, ô màu component bằng PhotoImage swatch, file include thiếu tô đỏ) + bảng Name/Value dưới trái (property table); phải = Check Results 9 nhóm (tag màu ERROR đỏ/WARN cam/info xám, cột vị trí file:dòng, filter checkbox, panel chi tiết + nút Copy vị trí — KHÔNG mở editor ngoài theo external-call policy); toolbar tol/gap-tol/no-geom + Xuất báo cáo.
- Parse & check chạy thread + queue poll (`after(100)`) — không treo UI với deck lớn.
- `--selftest <deck>`: load + check headless, assert đủ nhóm entity/finding → PASS (khớp CLI 11 LỖI/6 CẢNH BÁO trên test deck). Đã verify trực quan bằng screenshot 2 trạng thái.
- Style: theme clam + màu xám HM classic (#d6d3ce), selection xanh #316ac5.

## 2026-07-10 (tối, tiếp) — Double-click mở sakura tại dòng lỗi

- User cho phép external call này. Double-click finding HOẶC entity trên Model browser → `subprocess.Popen([sakura, "-Y=<dòng>", "-X=1", file])` (sakura hỗ trợ -Y/-X nhảy dòng/cột).
- Dò sakura: PATH → `Program Files (x86)\sakura` → App Paths registry (HKCU/HKLM + WOW6432Node). Máy dev KHÔNG có sakura (nó ở máy công ty) → không thấy thì dialog hỏi đường dẫn 1 lần, lưu `gui_config.json` (đã gitignore); cancel → `os.startfile` fallback (không nhảy dòng).
- `loc_map`: mọi entity trên cây (file/elset/nset/surface/contact/tie/material/parameter/step) đều mang (file, line) định nghĩa đầu tiên.
- Verified: selftest + regression PASS; cơ chế Popen test bằng notepad giả sakura (spawn OK, status đúng). Tham số -Y thật chỉ verify được trên máy có sakura.

## 2026-07-10 (tối, tiếp 2) — Phân loại vùng share-node: lỗi thật vs contact có chủ đích

- **Bối cảnh**: user chạy trên deck K12E thật → nhóm 6 báo 19 "lỗi" nhưng phần lớn là vùng 2 lớp node CỐ Ý (contact thay share node: Bush↔SE_Bore, Upper↔Lower mặt aws, Bolt↔Conrod bore...).
- **Giải pháp**: mỗi cặp node trùng → tra node thuộc surface nào (`_resolve_surface_faces`) → nếu 2 node nằm trên 2 surface của cùng một *CONTACT PAIR/*TIE ⇒ có chủ đích. Phân loại vùng: **INFO** (100% cặp thuộc contact, in tên cặp), **WARN** (một phần cặp NGOÀI surface contact → mép contact chọn thiếu element hoặc mất share cạnh vùng contact), **ERROR** (không contact nào phủ → nghi mất share thật). Sort ERROR trước.
- Đổi cách gom vùng: nhóm theo CẶP ELSET trước rồi mới cluster không gian → Upper↔Lower không bị trộn với Bush↔Bore dù sát nhau.
- Test deck thêm BLOCK_D (2 lớp node + contact s_side_A/s_side_D) → 18/18 PASS: vùng contact ra INFO, node 10/210 vẫn ERROR.

## 2026-07-10 (tối, tiếp 3) — Check 7d: PATTERN MISMATCH tại mặt share-node

- User yêu cầu (vẽ hình 2 cặp tam giác chia chéo ngược nhau): 2 khối share đủ node quad nhưng chia diagonal khác nhau → mặt tiếp giáp không liên tục.
- Signature: mặt khớp pattern = count 2 (internal); mặt lệch = **mặt tự do (count 1) mà 100% node của mặt được cả 2 component dùng** + phải có bằng chứng từ CẢ 2 phía trong cùng cụm không gian → ERROR (độ tin cao, tránh false positive ở mép/exterior vì mặt ngoài luôn có ≥1 node riêng).
- Cũng trong đợt này: nút **Editor...** trên toolbar (chọn sakura.exe, lưu `gui_config.json`), double-click dòng không có file:line giờ báo status thay vì im lặng (VUNG share-node không gắn file — dùng tọa độ tìm trong HM).
- Test: fixture BLOCK_E/F (2 tetra pair chéo ngược, share node 51–54) → 19/19 PASS.
- Hạn chế đã biết: 7d cần bằng chứng 2 phía nên KHÔNG bắt hanging-node (1 mặt to vs 4 mặt nhỏ, node giữa không share) — ứng viên check tương lai.

## 2026-07-10 (tối, tiếp 4) — Check 7e: LỆCH BIÊN DẠNG contact (penetration/gap có dấu)

- User gửi ảnh 2 part mesh riêng tại vùng cong phức tạp: facet 2 bên tessellate khác nhau → lát xuyên/hở xen kẽ. Giải pháp: với mỗi cặp contact/tie, đo **khoảng cách có dấu** từ đỉnh+tâm mặt slave tới mặt master (pháp tuyến master hướng RA NGOÀI — xác định bằng tâm element, không tin thứ tự node); âm = xuyên, dương = hở.
- Output: INFO thống kê từng cặp (xuyên sâu nhất/TB/hở lớn nhất — user so với clearance/interference thiết kế, vd mc_interferense=-0.0396) + WARN "VUNG XUYEN THAU" gom cụm khi sâu hơn `--pen-tol` (mặc định 0.1×cạnh element).
- Master là membrane (skin) → bỏ phần dấu (không xác định được hướng ngoài).
- Fixture G/H (mặt master nghiêng: xuyên 0.15/hở 0.25): đo ra −0.1393/+0.2321 = đúng giá trị chiếu theo pháp tuyến, vị trí đúng → 21/21 PASS.

## 2026-07-10 (tối, tiếp 5) — Check 7f: GHÉP SHARE-NODE KHÔNG KHỚP (không cần pair)

- User chỉ ra điểm mù của 7e: vùng lệch biên dạng giữa 2 KHỐI CÙNG SOLID ghép share-node — không thuộc contact pair nào → 7e không thấy.
- Tín hiệu thay thế: 2 khối đã share node ở nơi ghép OK (≥3 node ID chung) = "join pair". Giữa đúng cặp khối đó, mặt tự do 2 phía **đối diện nhau** (dot pháp tuyến < −0.2) trong cự ly < 0.75×cạnh element, không thuộc surface nào, có bằng chứng CẢ 2 phía → ERROR kèm độ lệch ước tính.
- Lọc tự nhiên: cặp contact 2 lớp node (Upper/Lower, bush...) dùng node ID RIÊNG → không phải join pair → không báo nhầm; mặt ngoài gặp nhau ở góc lồi/lõm có pháp tuyến không đối nhau → loại.
- Fixture BLOCK_I/J (tầng dưới share OK, tầng trên lệch 0.05) → bắt đúng vị trí, lech ~0.025; G/H (contact, không share) không bị báo → 22/22 PASS.
- Lưu ý: 7f cũng bắt lại vùng của share-node check (A/B) và 7d (E/F) — trùng lặp có chủ đích, 3 lăng kính cùng chỉ 1 chỗ lỗi.

### Next
1. Chạy lại trên deck K12E thật → xác nhận phân loại share-node + 7d/7e/7f trên mặt cong thật (bore/bush). 7f trên model thật có thể ồn nếu có khe thiết kế < 1 cạnh element giữa 2 khối share-node — nếu ồn thì hạ prox hoặc thêm ngưỡng --join-tol. Verify double-click sakura.
2. Cân nhắc: diff cấu trúc cp0 vs cp1 (so pair-by-pair 2 file contact); cảnh báo mtime mesh mới hơn odb của *INITIAL CONDITIONS; GUI thêm nút re-run 1 nhóm check riêng.

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
