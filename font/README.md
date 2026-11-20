# Mod Font — Sekai-Modding

Hướng dẫn gộp font tiếng Việt / tiếng Anh và đóng gói file font bundle (`font/common`) cho Project Sekai (hoạt động trên cả bản **JP** và **EN**).

> **Lưu ý:** Nếu chỉ cần mod nhanh, bạn có thể chạy giao diện đơn giản bằng `uv run app.py` → tab **MOD FONT**.

---

## Cấu trúc thư mục `font/`

- `font/assets/` — File gốc của game (`FOT-RodinNTLG Pro DB/EB.otf`, `common.bak`, `characters.txt`)
- `font/merge_fonts.py` — Script gộp glyph Latin/tiếng Việt vào font gốc
- `font/build_font_bundle.py` — Script tạo SDF atlas và đóng gói + mã hóa bundle
- `font/output/` — Chứa file font đã gộp và file bundle kết quả (tự tạo khi chạy)
- `font/tools/` — Chứa `msdf-atlas-gen.exe` (tự tải lần đầu trên Windows)

---

## Bước 1 — Chọn font

- Tải một font hỗ trợ tiếng Việt (chép vào `font/` hoặc để ở bất kỳ thư mục nào).
  - Game dùng 2 độ đậm: **DB** (chữ vừa — SemiBold/Medium) và **EB** (chữ đậm — Bold/ExtraBold).
    - **DB** dùng cho hầu hết chữ trong game, bao gồm cả story.
    - **EB** dùng cho thông báo, tên nhân vật,... trong story.
  - Bạn có thể chọn 2 file khác nhau, hoặc dùng **1 file duy nhất** cho cả hai (nếu là Variable Font, script sẽ tự lấy độ đậm `600` cho DB và `800` cho EB).

---

## Bước 2 — Gộp chữ tiếng Việt / tiếng Anh vào 2 font gốc của game

Trong cửa sổ PowerShell (đang ở thư mục gốc `Sekai-Modding`), chạy 2 lệnh sau (thay `MyFont-SemiBold.ttf` và `MyFont-Bold.ttf` bằng đường dẫn file font của bạn):

```powershell
uv run font/merge_fonts.py "font/assets/FOT-RodinNTLG Pro DB.otf" "MyFont-SemiBold.ttf" "font/output/FOT-RodinNTLGPro-DB-OnDemand.otf" --verify
uv run font/merge_fonts.py "font/assets/FOT-RodinNTLG Pro EB.otf" "MyFont-Bold.ttf" "font/output/FOT-RodinNTLGPro-EB-OnDemand.otf" --verify
```

> **Lưu ý tùy chọn (có thể bỏ qua):**
> - Nếu font bạn chọn bị thiếu chữ tiếng Việt, script sẽ hiện dòng `WARNING` báo thiếu chữ nào.
> - Nếu vào game thấy chữ Latin/tiếng Việt hơi nhỏ hơn chữ Nhật (như Calibri...), thêm cờ `--match-cap-height` vào cuối 2 lệnh trên.
> - Nếu muốn chỉnh độ đậm của Variable Font thủ công, thêm `--weight 600` (hoặc `700`, `800`...).
> - Nếu dùng file `.ttc`/`.otc`, thêm `--font-index 0` (hoặc `1`, `2`...).

---

## Bước 3 — Đóng gói ra file game

Chạy lệnh sau trong PowerShell:

```powershell
uv run font/build_font_bundle.py
```

- Lần đầu chạy trên Windows, script sẽ tự động tải `msdf-atlas-gen` về thư mục `font/tools/`.
- Quá trình tạo font SDF và mã hóa mất khoảng **15–20 giây**.
- Kết quả là file đã mã hóa nằm tại **`font/output/common`**.

---

## Bước 4 — Chép vào điện thoại Android

1. Đổi tên file `font/output/common` thành:
   ```text
   4ad9182d51b21d790af3f73d72ddc193
   ```
   *(Lưu ý: không có đuôi `.txt` hay gì phía sau. Nếu chạy qua GUI `app.py`, file đã đổi tên sẵn nằm tại `font/output/47a2/4ad9182d51b21d790af3f73d72ddc193`.)*
2. Cắm điện thoại vào máy tính (chọn chế độ **Truyền tệp / File Transfer**), hoặc dùng trình quản lý file hỗ trợ `Android/data` (như ZArchiver + Shizuku trên Android 11+).
3. Tìm đến thư mục dữ liệu của game:
   - **Bản JP:** `Android/data/com.sega.pjsekai/files/data/47a2/`
   - **Bản EN:** `Android/data/com.sega.ColorfulStage.en/files/data/47a2/`
4. **Sao lưu file gốc** `4ad9182d51b21d790af3f73d72ddc193` (nếu muốn khôi phục sau này), sau đó chép đè file mới vào.
5. Mở lại game. Font mới sẽ hiển thị ngay (dễ kiểm tra nhất ở phần Rank, Level và tên người chơi).

---

## Tham số nâng cao

### `font/merge_fonts.py`

| Tham số | Công dụng |
| :--- | :--- |
| `--verify` | Tự kiểm tra file `.otf` sau khi gộp (khuyên luôn bật) |
| `--match-cap-height` | Tự scale chiều cao chữ hoa khớp với font Nhật gốc |
| `--scale 1.05` | Phóng to / thu nhỏ thêm theo tỷ lệ tùy chỉnh |
| `--y-offset 20` | Dịch chuyển vị trí cao/thấp của chữ |
| `--weight 700` | Chọn độ đậm (`wght`) khi dùng Variable Font |
| `--axes "wght=700,wdth=90"` | Tùy chỉnh nhiều trục (axis) cùng lúc cho Variable Font |
| `--font-index 0` | Chọn font con khi dùng `.ttc` / `.otc` |

### `font/build_font_bundle.py`

| Tham số | Mặc định | Công dụng |
| :--- | :--- | :--- |
| `--db` / `--eb` | `font/output/FOT-RodinNTLGPro-*-OnDemand.otf` | Đường dẫn 2 file font đã gộp |
| `--original` | `font/assets/common.bak` | Đường dẫn file bundle gốc |
| `--output` / `-o` | `font/output/common` | Đường dẫn file bundle mã hóa xuất ra |
| `--point-size` | `42` | Kích thước lấy mẫu SDF (font gốc là `35`) |
| `--padding` | `5` | Độ rộng vùng biên SDF |
| `--charset` | `font/assets/characters.txt` (2,640 ký tự: bộ ký tự gốc của `common.bak` + ASCII + tiếng Việt) | Sửa trực tiếp `font/assets/characters.txt` hoặc truyền file `.txt` khác nếu muốn tự chọn bảng ký tự |
| `--msdf-bin` | Tự tìm / tự tải trên Windows | Trỏ thủ công tới `msdf-atlas-gen` (dùng trên macOS/Linux) |
