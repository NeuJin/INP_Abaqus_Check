# INP_Abaqus_Check

Bộ tool **validator cho deck Abaqus .inp** xuất từ HyperMesh — phát hiện các lỗi "xót" trong quá trình mesh/setup mà mắt thường và solver đều dễ bỏ qua: mất share node giữa các khối mesh riêng, chọn thiếu element vào surface contact, biến thể file lệch nhau, include chết, tham chiếu tới entity không tồn tại...

> **Triết lý:** *Không tin mắt, chỉ tin query.* Mọi setup nhìn được trên Model browser đều phải kiểm chứng được bằng lệnh. Validator chạy trên chính file .inp — tức là kiểm **đúng cái solver sẽ nhìn thấy** (bắt được cả lỗi kiểu "Do Not Export": entity trong HyperMesh nhìn vẫn có nhưng vắng mặt trong deck).

**Yêu cầu:** Python 3.9+ — **stdlib only**, không cần cài thêm gì.

---

## GUI: `inp_check_gui.py` — giao diện kiểu HyperMesh

```powershell
python inp_check_gui.py                    # roi bam "Mo file .inp..."
python inp_check_gui.py duong\dan\master.inp   # mo san file
```

Bố cục mô phỏng HyperMesh 14 cho quen mắt:
- **Trái — Model browser**: cây entity (Files/Components/Node Sets/Surfaces/Contact/Materials/Parameters/Steps) với ô màu component + cột ID/Count; file include thiếu tô **đỏ** ngay trên cây.
- **Dưới trái — bảng Name/Value**: click entity là thấy chi tiết (element count, type, section, material, định nghĩa ở file:dòng nào) — giống property table của HM.
- **Phải — Check Results**: 9 nhóm check, **LỖI đỏ / CẢNH BÁO cam / info xám**, cột vị trí `file:dòng`; lọc theo mức bằng checkbox; click finding → panel chi tiết + nút **Copy vị trí**.
- **Double-click** (finding hoặc entity trên cây) → **mở sakura ngay tại dòng đó** (`sakura -Y=<dòng>`). Lưu ý: chỉ dòng nào có cột **Vị trí** (file:dòng) mới mở được — các dòng VÙNG share node/hình học không gắn file, dùng tọa độ trong message để tìm trong HyperMesh.

### Chỉ định đường dẫn sakura (nếu double-click không bật editor)

Thứ tự tool tìm editor, cái nào có trước dùng cái đó:

1. **`gui_config.json`** nằm cạnh `inp_check_gui.py` — cách chắc nhất, bấm nút **"Editor..."** trên toolbar để chọn `sakura.exe`, tool tự ghi file này. Hoặc tự tạo file với nội dung (dùng `/` hoặc `\\\\`):
   ```json
   {"editor": "F:/Software/Sakura/Sakura/sakura-v2.4.1/sakura.exe"}
   ```
2. Tự dò: `sakura` trong PATH → `F:\Software\Sakura\Sakura\sakura-v2.4.1\sakura.exe` → `C:\Program Files (x86)\sakura\` → App Paths registry (danh sách hardcode nằm trong hàm `_detect_sakura()` đầu file `inp_check_gui.py` — thêm đường dẫn máy bạn vào đó cũng được).
3. Không thấy gì → lần double-click đầu sẽ hiện dialog hỏi; Cancel thì mở bằng editor mặc định Windows (không nhảy dòng).
- Toolbar: chọn `tol` / `gap-tol` / bỏ qua check hình học, nút **Xuất báo cáo** ra file text.
- Parse và check chạy nền (thread) — deck 1 triệu dòng không treo giao diện.

Selftest không cần thao tác tay: `python inp_check_gui.py --selftest tests\deck\master.inp`

## CLI: `inp_check.py`

Đưa vào **file master**, tool tự lần theo toàn bộ `*INCLUDE` và chạy 9 nhóm check một lượt:

```powershell
python inp_check.py C:\duong\dan\K12E_DITC_Comb_6000rpm.inp --report bao_cao.txt
```

| Tùy chọn | Mặc định | Ý nghĩa |
|---|---|---|
| `--tol X` | `1e-4` | dung sai trùng tọa độ cho check share-node (đơn vị model) |
| `--gap-tol X` | `0.2 × cạnh element` | khe hở cho phép khi check độ phủ contact (riêng *TIE dùng `POSITION TOLERANCE` khai trong deck) |
| `--no-geom` | — | bỏ qua nhóm check hình học (nhanh hơn với deck rất lớn) |
| `--report FILE` | — | ghi báo cáo **đầy đủ** ra file (console chỉ in tối đa `--max-print` dòng/nhóm) |
| `--max-print N` | `15` | số dòng in ra console mỗi nhóm |
| `--strict` | — | WARN cũng làm exit code = 1 |

Exit code: `0` = sạch, `1` = có ERROR (dùng được trong batch: check tự động trước khi submit job).

### 9 nhóm check

| # | Nhóm | Bắt lỗi gì | Mức |
|---|---|---|---|
| 1 | **CẤU TRÚC / INCLUDE** | include trỏ file không tồn tại; include bị comment mà file đích cũng không còn (bỏ comment là crash); file bị include 2 lần | ERROR/WARN |
| 2 | **THAM CHIẾU** (symbol table xuyên file) | surface/nset/elset/interaction/material/amplitude được tham chiếu nhưng không định nghĩa; **surface trỏ element không tồn tại (stale sau remesh)**; định nghĩa trùng; định nghĩa không ai dùng | ERROR |
| 3 | **PARAMETER** | tham chiếu `<tên>` chưa được `*PARAMETER` định nghĩa — kể cả `<tên>` nằm trong dòng comment (bỏ comment là fail) | ERROR/WARN |
| 4 | **SECTION / MATERIAL** | element không thuộc section nào; section gắn vào elset rỗng; elset có 2 section | ERROR |
| 5 | **TẢI / BC ↔ MESH** | `*BOUNDARY`/`*CLOAD` trỏ node không tồn tại (điểm ghép với tool map lực ngoài — **mesh đổi mà file lực chưa sinh lại**); CLOAD vào node "lơ lửng" không truyền lực đi đâu; nhắc phụ thuộc `*INITIAL CONDITIONS, FILE=odb` | ERROR/WARN |
| 6 | **SHARE NODE** | cặp node ID khác nhau trùng tọa độ mà cả 2 đều được element dùng = **mất share node**; tự loại ref node coupling/node mồ côi; **gom thành VÙNG lỗi** kèm tọa độ tâm để dán vào HyperMesh | ERROR |
| 7 | **HÌNH HỌC CONTACT/SURFACE** | (a) **lỗ thủng** trong surface — element bị chọn sót giữa vùng (mặt tự do giáp ≥2 cạnh với surface); (b) **độ phủ** — mặt slave không có mặt master đối diện trong khe hở cho phép (miễn nhiễm hexa–tetra khác cỡ lưới); (c) **mặt tự do áp nhau** ngoài mọi surface — mất share node dạng lệch node / quên khai contact; (d) **PATTERN MISMATCH** — 2 khối đã share node nhưng chia tam giác theo đường chéo khác nhau tại mặt tiếp giáp (mặt tự do cả 2 phía mà 100% node dùng chung); (e) **LỆCH BIÊN DẠNG contact** — đo khoảng cách CÓ DẤU slave→master tại từng đỉnh mặt contact: báo VÙNG XUYÊN THẤU (2 mặt cắt nhau, ngưỡng `--pen-tol`) + thống kê xuyên/TB/hở từng cặp để so với clearance/interference thiết kế; (f) **GHÉP SHARE-NODE KHÔNG KHỚP** — không cần contact pair: 2 khối đã share node ở nơi khác (= cùng solid ghép lại) mà vẫn còn mặt tự do 2 phía đối nhau trong cự ly < 1 cạnh element → biên dạng 2 bên chia lưới không khớp, ghép bị xót | WARN / ERROR (d,f) |
| 8 | **SETUP ĐANG TẮT** | inventory mọi keyword bị comment (`** *TIE`, `**clearance`, `**INCLUDE`...) để xác nhận tắt có chủ đích | INFO |
| 10 | **GROUP CONTACT/TIE** | (a) group rỗng/stale nằm trong pair → ERROR; (b) so 2 phía mỗi pair: số mặt + loại (tri/quad) + **DIỆN TÍCH** — số mặt lệch nhưng diện tích khớp (vd 320 tri vs 160 quad) = hợp lý và ghi rõ logic; TIE mà diện tích 2 phía lệch >5% → WARN; slave lớn hơn master → WARN master hụt; (c) surface bị tách **mảng rời rạc** (chọn nhầm element ở xa / sót element nối giữa); (d) khuyến nghị lưới mịn làm slave; group assign mà không dùng → WARN (nhóm 2) | ERROR/WARN/INFO |
| 9 | **TỔNG QUAN STEP** | bảng BC/CLOAD/DLOAD/interference của từng step (kèm `OP=NEW`) để soát step quên khai lại BC | INFO |

### Đọc kết quả nhóm 6 (share node)

```
[LOI ] VUNG 1: 5 cap node trung toa do quanh (12.4, -8.1, 95.2) | vd node 10/210 | Conrod_Tetra <-> Conrod_SE_Bore
```
- Mỗi VÙNG = một vết mất share node (nhiều cặp node liền kề gom làm một).
- Dán tọa độ tâm vào HyperMesh (mask by sphere / find nodes) để nhảy đúng chỗ cần equivalence.
- Cặp giữa 2 mặt tie cố ý (vd `_tie_1 <-> _tie_2`) thì bỏ qua — cột elset cho biết ngay.

### Test

```powershell
python tests\run_test.py
```
Chạy tool trên deck tổng hợp (`tests/deck/`) có cài sẵn 16 lỗi đủ loại và assert bắt đủ.

---

## Tool phụ: `check_shared_nodes.py` (standalone)

Bản độc lập chỉ check share-node, 1 file duy nhất — tiện copy sang máy khác chạy nhanh không cần cả repo:

```powershell
python check_shared_nodes.py model.inp [--tol 1e-4] [--csv report.csv]
```

## Cấu trúc repo

```
INP_Abaqus_Check/
├── inp_check_gui.py           # GUI kieu HyperMesh (tkinter)
├── inp_check.py               # CLI - chay 9 nhom check, dung duoc trong batch
├── inpcheck/
│   ├── reader.py              # doc deck, resolve *INCLUDE, phan loai comment
│   ├── model.py               # builder: keyword -> data model + refs
│   ├── checks.py              # 9 nhom check
│   └── geometry.py            # bang mat element, spatial hash, clustering
├── check_shared_nodes.py      # ban standalone chi check share-node
├── tests/
│   ├── deck/                  # test deck cai san 16 loi
│   └── run_test.py            # regression test
├── docs/K12E_DECK_FORMAT.md   # ban do format deck K12E (co so thiet ke parser)
└── DEVLOG.md
```

## Bài học thiết kế parser (đúc kết từ khảo sát deck thật)

1. **Case-insensitive tuyệt đối** — cùng 1 deck trộn `*CONTACT PAIR`, `*surface`, `*Coupling`.
2. **Tham số cho phép viết tắt** — `TYPE=ISO` ≡ `TYPE=ISOTROPIC` → so khớp kiểu prefix.
3. **Continuation** — dòng data kết thúc bằng `,` thì record tiếp tục ở dòng sau (C3D8I, C3D10M đều wrap).
4. **Không suy loại entity từ ID** — element membrane và node có thể trùng nguyên dải số.
5. **Comment `**` có 3 loại** cần phân biệt: trang trí/ghi chú, metadata `**HMNAME`, và **keyword bị comment** (phải inventory, không được lờ đi).
6. **`*PARAMETER` + tham chiếu `<tên>`** — mọi `<tên>` phải được định nghĩa; kể cả trong dòng comment cũng cảnh báo.
7. **`OP=NEW`** xóa thay toàn bộ BC/tải cũ — bảng hiệu lực đổi theo từng step.
