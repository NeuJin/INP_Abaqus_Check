# INP_Abaqus_Check

Bộ tool **validator cho deck Abaqus .inp** xuất từ HyperMesh — phát hiện các lỗi "xót" trong quá trình mesh/setup mà mắt thường và solver đều dễ bỏ qua: mất share node giữa các khối mesh riêng, chọn thiếu element vào surface contact, biến thể file lệch nhau, include chết, tham chiếu tới entity không tồn tại...

> **Triết lý:** *Không tin mắt, chỉ tin query.* Mọi setup nhìn được trên Model browser đều phải kiểm chứng được bằng lệnh. Validator chạy trên chính file .inp — tức là kiểm **đúng cái solver sẽ nhìn thấy** (bắt được cả lỗi kiểu "Do Not Export": entity trong HyperMesh nhìn vẫn có nhưng vắng mặt trong deck).

**Yêu cầu:** Python 3.9+ — **stdlib only**, không cần cài thêm gì.

---

## Module đã có

### 1. `check_shared_nodes.py` — phát hiện mất share node

**Bài toán:** tách 1 khối solid thành nhiều khối nhỏ để mesh riêng (do biên dạng phức tạp), sau đó share node lại tại mặt tiếp giáp. Vì biên dạng phức tạp nên vài điểm bị xót — hai khối vẫn "dính" ở phần lớn mặt tiếp giáp nhưng hở ngầm ở vài node.

**Nguyên lý:** share node thành công = 2 khối dùng **chung 1 node ID**. Chỗ bị xót = tồn tại **2 node ID khác nhau nhưng trùng tọa độ**, và cả hai đều được element sử dụng. Tool quét toàn bộ `*NODE`, gom vào lưới không gian (spatial hash — 1 triệu dòng chạy trong vài giây), báo từng cặp kèm tọa độ và ELSET 2 phía.

```
python check_shared_nodes.py model.inp [--tol 1e-4] [--csv report.csv]
```

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `inp` | (bắt buộc) | đường dẫn file .inp (master đã ghép, hoặc file mesh) |
| `--tol` | `1e-4` | dung sai trùng tọa độ (đơn vị model). Mesh từ cùng bề mặt geometry thì node trùng gần tuyệt đối; nghi lệch do remesh thì tăng `1e-2` quét rộng |
| `--csv` | — | ghi report đầy đủ ra CSV |

**Đọc kết quả:**

- **"Cặp mà CẢ 2 node đều dùng"** = ứng viên mất share node. Bảng "Phân bố theo cặp ELSET" cho biết cặp thuộc component nào:
  - cặp giữa 2 khối lẽ ra share node (vd `Conrod_Tetra ↔ Conrod_SE_Bore`) → **lỗi thật**;
  - cặp giữa 2 mặt tie/contact cố ý để 2 lớp node (vd `_tie_1 ↔ _tie_2`) → bỏ qua.
- Console in 10 cặp đầu kèm tọa độ `(x, y, z)` — dán vào HyperMesh (mask by sphere / nodes by id) để nhảy đúng chỗ cần equivalence lại.
- Node trùng tọa độ nhưng **không thuộc element nào** (reference node của coupling, node mồ côi) được tự loại khỏi danh sách critical.
- Exit code: `0` = sạch, `1` = có ứng viên lỗi (dùng được trong batch/CI).

**Parser đã xử lý đúng các đặc thù deck HyperMesh–Abaqus:** keyword hoa/thường lẫn lộn, element wrap nhiều dòng (continuation dấu phẩy cuối dòng — C3D8I, C3D10M), `*NODE` có tham số (`SYSTEM=R`), số dạng khoa học, comment `**`.

---

## Roadmap — các module tiếp theo (theo ưu tiên)

Thiết kế dựa trên khảo sát format deck thật (xem [docs/K12E_DECK_FORMAT.md](docs/K12E_DECK_FORMAT.md)):

| # | Module | Bắt lỗi gì |
|---|---|---|
| 1 | **Include resolver + symbol table xuyên file** | Đọc master, lần theo `*INCLUDE`; mọi surface/nset/elset/interaction/parameter: định nghĩa ở đâu, tham chiếu ở đâu → báo *tham chiếu tới thứ không tồn tại*, *định nghĩa 2 lần*, *định nghĩa không ai dùng*, *tham chiếu trước định nghĩa*, *include trỏ file không tồn tại* |
| 2 | **CLOAD ↔ mesh** | Khối `*CLOAD` hàng chục nghìn node sinh từ tool ngoài (map lực theo góc quay): mọi node nhận lực phải tồn tại và thuộc đúng lưới membrane — mesh đổi mà file lực chưa sinh lại là sai âm thầm nguy hiểm nhất |
| 3 | **Surface thủng / độ phủ contact** | Chọn thiếu element vào surface contact (hexa–tetra, master–slave khác cỡ lưới): (a) *hole check* — face bề mặt không thuộc surface nhưng giáp ≥2 face thuộc surface; (b) *coverage check* — so tâm face + pháp tuyến 2 phía, mọi face slave phải được master phủ |
| 4 | **Inventory setup bị comment** | Liệt kê mọi keyword bị tắt bằng `**` (BC, contact, tie, clearance, include) để xác nhận "tắt có chủ đích" — không phải quên bật |
| 5 | **Bảng BC/tải hiệu lực per-step** | Xử lý semantics `OP=NEW` (xóa thay toàn bộ) — dựng bảng BC/load thực tế của từng step, soát step quên khai lại BC |
| 6 | **Đối chiếu section** | Mọi ELSET có element phải có `*SOLID SECTION`/`*MEMBRANE SECTION`; mọi section phải có `*MATERIAL`; material không ai dùng |

## Cấu trúc repo

```
INP_Abaqus_Check/
├── check_shared_nodes.py      # module 3 (share node) — đã chạy được
├── docs/
│   └── K12E_DECK_FORMAT.md    # bản đồ format deck K12E conrod (khảo sát đầy đủ)
├── DEVLOG.md                  # nhật ký phát triển
└── README.md
```

## Bài học thiết kế parser (đúc kết từ khảo sát deck thật)

1. **Case-insensitive tuyệt đối** — cùng 1 deck trộn `*CONTACT PAIR`, `*surface`, `*Coupling`.
2. **Tham số cho phép viết tắt** — `TYPE=ISO` ≡ `TYPE=ISOTROPIC` → so khớp kiểu prefix.
3. **Continuation** — dòng data kết thúc bằng `,` thì record tiếp tục ở dòng sau (C3D8I, C3D10M đều wrap).
4. **Không suy loại entity từ ID** — element membrane và node có thể trùng nguyên dải số (M3D4 elem 500000–517999 = đúng dải node ID).
5. **Comment `**` có 3 loại** cần phân biệt: trang trí/ghi chú, metadata `**HMNAME` (map ngược về group ID HyperMesh — rất quý), và **keyword bị comment** (setup đang tắt — phải inventory, không được lờ đi).
6. **`*PARAMETER` + tham chiếu `<tên>`** — mọi `<tên>` xuất hiện trong data phải được định nghĩa; kể cả trong dòng comment cũng nên cảnh báo mức thấp (ngày nào đó bỏ comment là fail).
