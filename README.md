# Sekai-FModding

Bộ công cụ hỗ trợ mod font chữ trong tựa game nhịp điệu **Hatsune Miku: Colorful Stage!** (tương thích với máy chủ JP, có thể hoạt động trên EN).

---

## 1. Yêu cầu chuẩn bị

Đảm bảo bạn đã cài **Python 3.x** trên máy, sau đó cài các thư viện cần thiết:

```bash
pip install UnityPy fonttools
```

---

## 2. Cấu trúc thư mục

```
Sekai-FModding/
├── fontMerging/
│   ├── merge_fonts.py              # Gộp ký tự tiếng Việt/Latin vào font gốc tiếng Nhật
│   ├── FOT-RodinNTLG Pro EB.otf   # Font gốc của game (tự chuẩn bị)
│   ├── FOT-RodinNTLG Pro DB.otf   # Font gốc của game (tự chuẩn bị)
│   ├── YourFont1.ttf              # Font tùy chỉnh cho EB (tự chuẩn bị)
│   └── YourFont2.ttf              # Font tùy chỉnh cho DB (tự chuẩn bị)
├── script/
│   ├── inject_font.py             # Nhúng font đã gộp vào AssetBundle của game
│   ├── decrypt_bundle.py          # Giải mã file bundle gốc của game
│   ├── encrypt_bundle.py          # Mã hóa lại bundle sau khi inject
│   └── common.bak                 # Bundle gốc của game (tự chuẩn bị, đổi tên thành .bak)
└── unityMisc/
    ├── BuildAssetBundles.cs        # Editor script để build AssetBundle trong Unity
    ├── characters.txt              # Bảng ký tự đầy đủ (bao gồm kanji)
    └── characters_no_kanji.txt     # Bảng ký tự không có kanji
```

---

## 3. Hướng dẫn thực hiện

### Bước A — Gộp Font

Kết hợp font tiếng Việt/Latin vào font gốc tiếng Nhật của game.

Mở `fontMerging/merge_fonts.py` và đặt tên file font của bạn vào các biến `YourFont1.ttf` / `YourFont2.ttf`, sau đó chạy:

```bash
cd fontMerging
python merge_fonts.py
```

> **Chế độ tùy chỉnh:** Bạn cũng có thể chỉ định đường dẫn thủ công:
> ```bash
> python merge_fonts.py <font_gốc> <font_ghi_đè> [font_đầu_ra]
> ```

Kết quả xuất ra:
- `FOT-RodinNTLGPro-EB-OnDemand.otf`
- `FOT-RodinNTLGPro-DB-OnDemand.otf`

---

### Bước B — Giải mã Bundle gốc

File bundle của game được mã hóa. Giải mã trước khi xử lý:

```bash
cd script
python decrypt_bundle.py common.bak
```

Kết quả tạo ra file `common.bak.decrypted`.

---

### Bước C — Tạo AssetBundle thay thế (Unity)

> **Yêu cầu:** Unity Editor **2022.3.62f2** với module **Android Build Support** và **AssetBundle Browser**.

1. Kéo thả hai file font `.otf` vừa tạo ở Bước A vào Unity.
2. Trên thanh menu, chọn **Window → TextMesh Pro → Font Asset Creator**.
3. Thiết lập thông số:
   | Thông số | Giá trị |
   |---|---|
   | Sampling Point Size | Custom — nhập `42` |
   | Padding | `5` |
   | Atlas Resolution | `4096 × 2048` |
   | Character Set | Custom / Characters from File (dùng file `.txt` trong `unityMisc/`) |
   | Render Mode | `SDFAA` |
4. Nhấn **Generate Font Atlas**, sau đó **Save**. Tên file lưu **bắt buộc** phải là:
   - `FOT-RodinNTLGPro-EB-OnDemand` (font hiển thị tên nhân vật trong cốt truyện)
   - `FOT-RodinNTLGPro-DB-OnDemand` (font văn bản trong cốt truyện)
5. Build AssetBundle: copy `BuildAssetBundles.cs` vào `/Assets/Editor/`, sau đó chọn **Assets → Build Font AssetBundle (Android)**.
6. Copy file `font_replacement` vừa tạo sang thư mục `script/`.

---

### Bước D — Nhúng (Inject) Font vào Bundle

Tiêm các asset font và texture mới vào file bundle đã giải mã:

```bash
cd script
python inject_font.py font_replacement
```

Kết quả tạo ra file bundle đã được inject (chưa mã hóa).

---

### Bước E — Mã hóa lại Bundle

```bash
python encrypt_bundle.py <file_bundle_sau_inject>
```

Kết quả tạo ra file `.encrypted`, sẵn sàng đưa vào game.

---

### Bước F — Cài đặt và Kiểm tra

1. Đổi tên file `.encrypted` vừa tạo thành `4ad9182d51b21d790af3f73d72ddc193`.
2. Trên điện thoại Android, điều hướng đến:
   ```
   Android/data/com.sega.pjsekai/files/data/47a2/
   ```
3. Dán đè file này vào thư mục trên.
4. Mở game lên. Nếu thực hiện đúng các bước, font chữ mới sẽ xuất hiện ở phần **Rank** và **Level**!

---

## Lưu ý

- Các file font gốc (`.otf`, `.ttf`) và dữ liệu bundle game **không được** đưa vào repository này do kích thước lớn và bản quyền.
- Script `decrypt_bundle.py` / `encrypt_bundle.py` cũng có thể dùng bằng cách **kéo thả** file bundle thẳng vào file `.py` (drag & drop).