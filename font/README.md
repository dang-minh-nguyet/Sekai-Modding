# Mod Font — Sekai-Modding

Hướng dẫn gộp font tiếng Việt / tiếng Anh và đóng gói file font bundle (`font/common`) cho Project Sekai (hoạt động trên cả bản **JP** và **EN**).

> **Lưu ý:** Nếu chỉ cần mod nhanh, bạn có thể chạy giao diện đơn giản bằng `uv run app.py` → tab **MOD FONT**.

---

## Cấu trúc thư mục `font/`

- `font/assets/` — File gốc của game (`FOT-RodinNTLG Pro DB/EB.otf`, `common.bak`, `characters.txt`)
- `font/merge_fonts.py` — Script gộp glyph Latin/tiếng Việt vào font gốc
- `font/build_font_bundle.py` — *(Cách 1 — Bundle cũ)* Tạo SDF atlas và đóng gói + mã hóa bundle `font/common` chép vào `Android/data`
- `font/patch_xapk_font.py` — *(Cách 2 — XAPK trực tiếp)* Patch font thẳng vào file `.xapk` và ký số sẵn (không cần `Android/data` / Shizuku / Root)
- `font/output/` — Chứa file font đã gộp và file bundle / `.xapk` kết quả (tự tạo khi chạy)
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

## Bước 3 — Chọn 1 trong 2 cách đóng gói

### Cách 1 (Truyền thống — chép vào `Android/data`, giữ nguyên bản game gốc)

Chạy lệnh sau trong PowerShell:

```powershell
uv run font/build_font_bundle.py
```

- Lần đầu chạy trên Windows, script sẽ tự động tải `msdf-atlas-gen` về thư mục `font/tools/`.
- Quá trình tạo font SDF và mã hóa mất khoảng **15–20 giây**.
- Kết quả là file đã mã hóa nằm tại **`font/output/common`**.

#### Cài đặt Cách 1 lên Android

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

### Cách 2 (Mới — Patch thẳng vào file `.xapk`, KHÔNG cần `Android/data` / Shizuku / Root)

Yêu cầu thêm **Java (JRE/JDK 8+)** để ký số APK bằng `uber-apk-signer` (giống [speed_change/README.md](../speed_change/README.md)).

```powershell
# Patch font trực tiếp vào XAPK bản JP (dùng chung cache XAPK với speed_change/)
uv run font/patch_xapk_font.py

# Bản EN
uv run font/patch_xapk_font.py --region en

# Kết hợp Mod Font + Đổi tốc độ chạy chữ (35ms) vào chung 1 file XAPK duy nhất!
uv run font/patch_xapk_font.py --speed-ms 35

# Dùng file .xapk đã tải sẵn trên máy
uv run font/patch_xapk_font.py --input "D:\Downloads\com.sega.pjsekai.xapk"
```

- Script tự động patch đủ 3 tầng font trong `UnityDataAssetPack.apk`:
  1. Hai file OTF nhúng `font/fot-rodinntlgpro-db` & `eb` (cho `SDF_Dynamic`).
  2. Hai atlas khởi động/Title `font/fot-rodinntlgpro-db-builtin` & `eb-builtin` (`1024×1024`).
  3. Hai atlas chính `font/fot-rodinntlgpro-db sdf_base` & `eb sdf_base` (`1024×1024`, đầy đủ ASCII + 134 ký tự tiếng Việt) cùng toàn bộ ~36 preset Material (`sdf_base_scenario`, `sdf_base_outline_*`, `sdf_base gacha`, độ khó bài hát...) — chữ Nhật vẫn fallback mượt về `font/common` & `SDF_Dynamic`.
- File kết quả nằm tại `font/output/<package>_font_signed.xapk` → cài bằng **SAI (Split APKs Installer)** hoặc **XAPK Installer** (cùng debug keystore với `speed_change.py`, cài đè qua lại thoải mái).

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

### `font/patch_xapk_font.py`

| Tham số | Mặc định | Công dụng |
| :--- | :--- | :--- |
| `--db` / `--eb` | `font/output/FOT-RodinNTLGPro-*-OnDemand.otf` | Đường dẫn 2 file font đã gộp |
| `--region` | `jp` | Server game (`jp` hoặc `en`) |
| `--input` | Tự tải & dùng chung cache với `speed_change/cache/` | Đường dẫn file `.xapk` có sẵn trên máy |
| `--output` / `-o` | `font/output/<pkg>_font_signed.xapk` | Đường dẫn file `.xapk` xuất ra |
| `--refresh` | Tắt | Buộc tải lại XAPK mới nhất từ APKPure |
| `--speed-ms` | Không bật | Tùy chọn gộp chung mod tốc độ chạy chữ (ms/ký tự, VD: `35`) |
| `--auto-delay` | Không bật | Tùy chọn đổi thêm thời gian chờ Auto (giây, đi kèm `--speed-ms`) |
| `--no-sdf-base` | Tắt | Chỉ patch OTF nhúng + Builtin atlas (bỏ qua `SDF_Base`) |
| `--point-size` / `--builtin-point-size` | `42` / `36` | Kích thước lấy mẫu SDF cho `SDF_Base` và `Builtin` (`1024×1024`) |
