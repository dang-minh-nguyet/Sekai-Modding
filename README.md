# Sekai-Modding

Bộ script nhỏ để mod font chữ tiếng Việt / tiếng Anh (và logo) cho một game Miku tap tap nào đó.
- Hoạt động trên cả bản **JP** và **EN**.

---

# Disclaimer

Mọi hành động can thiệp đến file game đều là vi phạm TOS của Sega/Colorful Palette, cân nhắc trước khi sử dụng.


## Hướng dẫn

### Bước 0 — Tải công cụ và tải repo

1. **Cài `uv`**:
   - Nhấn phím **Windows**, gõ **PowerShell**, mở **Windows PowerShell**.
   - Dán lệnh sau rồi nhấn **Enter**:
     ```powershell
     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
     ```
   - Đóng PowerShell rồi **mở lại** để máy nhận lệnh `uv`.

2. **Tải bộ script này về máy**:
   - Trên trang GitHub này, bấm nút màu xanh **Code → Download ZIP**, rồi giải nén ra một thư mục (ví dụ `Desktop\Sekai-Modding`).
   - Mở thư mục vừa giải nén, bấm vào thanh địa chỉ ở trên cùng, gõ `powershell` rồi nhấn **Enter** (cửa sổ PowerShell sẽ mở sẵn đúng thư mục đó).
   - Nếu dùng git:
     ```git
     git clone https://github.com/dang-minh-nguyet/Sekai-Modding
     ```

---

### Bước 1 — Chọn font

- Tải một font hỗ trợ tiếng Việt.
- Chép file font vào thư mục `fontMerging/`.
  - Game dùng 2 độ đậm: **DB** (chữ vừa — SemiBold/Medium) và **EB** (chữ đậm — Bold/ExtraBold). **DB** là dùng cho hầu hết chữ trong game, bao gồm cả story. **EB** dùng cho phần thông báo, tên nhân vật,... trong phần story.
  - Bạn có thể chọn 2 file khác nhau, hoặc dùng **1 file duy nhất** cho cả hai (nếu là Variable Font, script sẽ tự lấy độ đậm `600` cho DB và `800` cho EB).

---

### Bước 2 — Gộp chữ tiếng Việt / tiếng Anh vào 2 font gốc của game

Trong cửa sổ PowerShell (đang ở thư mục `Sekai-Modding`), chạy 2 lệnh sau (thay `MyFont-SemiBold.ttf` và `MyFont-Bold.ttf` bằng tên file font của bạn):

```powershell
uv run fontMerging/merge_fonts.py "fontMerging/FOT-RodinNTLG Pro DB.otf" "fontMerging/MyFont-SemiBold.ttf" "fontMerging/FOT-RodinNTLGPro-DB-OnDemand.otf" --verify
uv run fontMerging/merge_fonts.py "fontMerging/FOT-RodinNTLG Pro EB.otf" "fontMerging/MyFont-Bold.ttf" "fontMerging/FOT-RodinNTLGPro-EB-OnDemand.otf" --verify
```

> **Note (dành cho người muốn customize thêm, có thể bỏ qua):**
> - Nếu font bạn chọn bị thiếu chữ tiếng Việt, script sẽ hiện dòng `WARNING` báo thiếu chữ nào.
> - Nếu vào game thấy chữ Latin/tiếng Việt hơi nhỏ hơn chữ Nhật (như Calibri...), thêm cờ `--match-cap-height` vào cuối 2 lệnh trên.
> - Nếu muốn chỉnh độ đậm của Variable Font thủ công, thêm `--weight 600` (hoặc `700`, `800`...).
> - Nếu dùng file `.ttc`/`.otc`, thêm `--font-index 0` (hoặc `1`, `2`...).

---

### Bước 3 — Đóng gói ra file game

Chạy lệnh sau trong powershell:

```powershell
uv run script/build_font_bundle.py
```

- Lần đầu chạy trên Windows, script sẽ tự động tải `msdf-atlas-gen` về thư mục `script/tools/`.
- Quá trình tạo font SDF và mã hóa mất khoảng **15–20 giây**.
- Kết quả là file đã mã hóa nằm tại **`script/common`**.

---

### Bước 4 — Chép vào điện thoại Android

1. Đổi tên file `script/common` thành:
   ```text
   4ad9182d51b21d790af3f73d72ddc193
   ```
   *(Lưu ý: không có đuôi `.txt` hay gì phía sau.)*
2. Cắm điện thoại vào máy tính (chọn chế độ **Truyền tệp / File Transfer**), hoặc dùng trình quản lý file hỗ trợ `Android/data` (như ZArchiver + Shizuku trên Android 11+).
   **Note:** Ở các phiên bản Android 11+, mặc định sẽ chặn truy cập `Android/data`, nên bắt buộc có quyền root hoặc ZArchiver + Shizuku. Những cái này có thể sẽ gây ảnh hưởng đến app ngân hàng
4. Tìm đến thư mục dữ liệu của game:
   - **Bản JP:** `Android/data/com.sega.pjsekai/files/data/47a2/`
   - **Bản EN:** `Android/data/com.sega.ColorfulStage.en/files/data/47a2/`
5. **Sao lưu file gốc** `4ad9182d51b21d790af3f73d72ddc193` (nếu muốn về lại như cũ sau này), sau đó chép đè file mới vào.
6. Mở lại game. Font mới sẽ hiển thị ngay (dễ kiểm tra nhất ở phần Rank, Level và tên người chơi).

---

## Nâng cao

### `fontMerging/merge_fonts.py`

| Tham số | Công dụng |
| :--- | :--- |
| `--verify` | Tự kiểm tra file `.otf` sau khi gộp (khuyên luôn bật) |
| `--match-cap-height` | Tự scale chiều cao chữ hoa khớp với font Nhật gốc |
| `--scale 1.05` | Phóng to / thu nhỏ thêm theo tỷ lệ tùy chỉnh |
| `--y-offset 20` | Dịch chuyển vị trí cao/thấp của chữ |
| `--weight 700` | Chọn độ đậm (`wght`) khi dùng Variable Font |
| `--font-index 0` | Chọn font con khi dùng `.ttc` / `.otc` |

### `script/build_font_bundle.py`

| Tham số | Mặc định | Công dụng |
| :--- | :--- | :--- |
| `--db` / `--eb` | `fontMerging/FOT-RodinNTLGPro-*-OnDemand.otf` | Đường dẫn 2 file font đã gộp |
| `--output` / `-o` | `script/common` | Đường dẫn file bundle mã hóa xuất ra |
| `--point-size` | `42` | Kích thước lấy mẫu SDF (font gốc là `35`) |
| `--padding` | `5` | Độ rộng vùng biên SDF |
| `--charset` | Bộ ký tự gốc của `common.bak` + ASCII + tiếng Việt (~2,642 ký tự) | Truyền file `.txt` khác (vd `unityMisc/characters_no_kanji.txt`) nếu muốn tự chọn bảng ký tự |
| `--msdf-bin` | Tự tìm / tự tải trên Windows | Trỏ thủ công tới `msdf-atlas-gen` (dùng trên macOS/Linux) |

---

## Logo modding

Thay logo hiển thị trong game bằng ảnh tùy chỉnh với `logoModding/replace_logo.py`:

1. Đặt ảnh thay thế vào `logoModding/` với tên `alt.png` hoặc `alt.webp`.
2. Đặt bundle logo gốc (`426774ceaca2c93196cdb9e2c551d1ff`) vào cùng thư mục `logoModding/`.
3. Chạy:
   ```powershell
   uv run logoModding/replace_logo.py
   ```
4. Đổi tên file `.modded` xuất ra thành `426774ceaca2c93196cdb9e2c551d1ff` rồi chép vào thư mục `47a2/` của game.

---

## Decrypt / Encrypt riêng lẻ

`script/decrypt_bundle.py` và `script/encrypt_bundle.py` dùng để giải mã hoặc mã hóa lại một file bundle bất kỳ (kéo thả file vào script hoặc truyền đường dẫn qua dòng lệnh).
