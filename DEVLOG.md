# DEVLOG — INP_Abaqus_Check

> **🔄 HANDOFF:** Validator Python (stdlib only, 3.9+) cho deck Abaqus .inp xuất từ HyperMesh 14 — project K12E conrod.
> Đọc `docs/K12E_DECK_FORMAT.md` = bản đồ format deck ĐẦY ĐỦ (khảo sát xong 2026-07-10, §9 = bẫy parser, §10 = danh sách check đã chốt).
> Trạng thái: module share-node chạy được; các module còn lại **chưa viết — user dặn chờ lệnh**. File .inp thật chưa có trên máy này (khảo sát qua nội dung user gửi); khi test được trên deck thật thì ưu tiên verify parser trước.

---

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
