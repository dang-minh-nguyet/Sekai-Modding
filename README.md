# Sekai-Modding

Bộ script nhỏ để mod font chữ tiếng Việt / tiếng Anh (và logo) cho Project Sekai.
- **Không cần cài Unity Editor** — chỉ cần chạy script bằng [`uv`](https://docs.astral.sh/uv/) và `msdf-atlas-gen` (tự tải sẵn trên Windows).
- Hoạt động trên cả bản **JP** và **EN**.

---

## Hướng dẫn nhanh cho người mới (Windows)

Nếu bạn chưa từng dùng Python hay dòng lệnh bao giờ, chỉ cần làm đúng theo từng bước dưới đây:

### Bước 0 — Tải công cụ và tải repo

1. **Cài `uv`** (công cụ tự quản lý Python & thư viện, không cần tự cài Python):
   - Nhấn phím **Windows**, gõ **PowerShell**, mở **Windows PowerShell**.
   - Dán lệnh sau rồi nhấn **Enter**:
     ```powershell
     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
     ```
   - Đóng PowerShell rồi **mở lại** để máy nhận lệnh `uv`.

2. **Tải bộ script này về máy**:
   - Trên trang GitHub này, bấm nút màu xanh **Code → Download ZIP**, rồi giải nén ra một thư mục (ví dụ `Desktop\Sekai-Modding`).
   - Mở thư mục vừa giải nén, bấm vào thanh địa chỉ ở trên cùng, gõ `powershell` rồi nhấn **Enter** (cửa sổ PowerShell sẽ mở sẵn đúng thư mục đó).

---

### Bước 1 — Chọn font chữ bạn muốn dùng

- Tải một font hỗ trợ tiếng Việt (ví dụ từ [Google Fonts](https://fonts.google.com/?subset=vietnamese) như **Be Vietnam Pro**, **Inter**, **Lexend**, **Nunito**, **Montserrat**...).
- Hỗ trợ mọi định dạng phổ biến: `.ttf`, `.otf`, `.ttc`/`.otc`, và cả **Variable Font** (1 file duy nhất có đủ độ đậm).
- Chép file font vào thư mục `fontMerging/` cho gọn.
  - Game dùng 2 độ đậm: **DB** (chữ vừa — SemiBold/Medium) và **EB** (chữ đậm — Bold/ExtraBold).
  - Bạn có thể chọn 2 file khác độ đậm (ví dụ `Font-SemiBold.ttf` và `Font-Bold.ttf`), hoặc dùng **1 file duy nhất** cho cả hai (nếu là Variable Font, script sẽ tự lấy độ đậm `600` cho DB và `800` cho EB).

---

### Bước 2 — Gộp chữ tiếng Việt / tiếng Anh vào 2 font gốc của game

Trong cửa sổ PowerShell (đang đứng ở thư mục `Sekai-Modding`), chạy 2 lệnh sau (thay `MyFont-SemiBold.ttf` và `MyFont-Bold.ttf` bằng tên file font của bạn):

```powershell
uv run fontMerging/merge_fonts.py "fontMerging/FOT-RodinNTLG Pro DB.otf" "fontMerging/MyFont-SemiBold.ttf" "fontMerging/FOT-RodinNTLGPro-DB-OnDemand.otf" --verify
uv run fontMerging/merge_fonts.py "fontMerging/FOT-RodinNTLG Pro EB.otf" "fontMerging/MyFont-Bold.ttf" "fontMerging/FOT-RodinNTLGPro-EB-OnDemand.otf" --verify
```

> **Mẹo:**
> - Nếu font bạn chọn bị thiếu chữ tiếng Việt, script sẽ hiện dòng `WARNING` báo rõ thiếu chữ nào.
> - Nếu vào game thấy chữ Latin/tiếng Việt hơi nhỏ hơn chữ Nhật (như Calibri...), thêm cờ `--match-cap-height` vào cuối 2 lệnh trên.
> - Nếu muốn chỉnh độ đậm của Variable Font thủ công, thêm `--weight 600` (hoặc `700`, `800`...).
> - Nếu dùng file `.ttc`/`.otc`, thêm `--font-index 0` (hoặc `1`, `2`...).

---

### Bước 3 — Đóng gói ra file mod game (không cần Unity)

Chạy đúng 1 lệnh:

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
3. Tìm đến thư mục dữ liệu của game:
   - **Bản JP:** `Android/data/com.sega.pjsekai/files/data/47a2/`
   - **Bản EN:** thay `com.sega.pjsekai` bằng thư mục package của bản EN (`com.sega.ColorfulStage.en`) rồi vào `files/data/47a2/`
4. **Sao lưu file gốc** `4ad9182d51b21d790af3f73d72ddc193` (nếu muốn hoàn tác sau này), sau đó chép đè file mới vào.
5. Mở lại game — font mới sẽ hiển thị ngay (dễ kiểm tra nhất ở phần Rank, Level và tên người chơi).

---

## Tùy chọn nâng cao

### `fontMerging/merge_fonts.py`

| Tham số | Công dụng |
| :--- | :--- |
| `--verify` | Tự kiểm tra toàn vẹn file `.otf` sau khi gộp (khuyên luôn bật) |
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

---

<details>
<summary>Cách cũ (dùng Unity Editor 2022.3.62f2 — không còn bắt buộc)</summary>

Nếu vẫn muốn tự bake Font Asset bằng Unity Editor 2022.3.62f2:
1. Kéo 2 file `.otf` đã gộp vào Unity, mở **Window → TextMesh Pro → Font Asset Creator** (point size `42`, padding `5`, atlas `4096×2048`, render mode `SDFAA`, bảng ký tự từ `unityMisc/`).
2. Lưu đúng tên `FOT-RodinNTLGPro-EB-OnDemand` và `FOT-RodinNTLGPro-DB-OnDemand` vào `Assets/Fonts/`.
3. Copy `unityMisc/BuildAssetBundles.cs` vào `Assets/Editor/` và build qua **Assets → Build Font AssetBundle (Android)**.
4. Copy `font_replacement` vào `script/` rồi chạy:
   ```powershell
   cd script
   uv run inject_font.py font_replacement
   ```
</details>
