# Sekai-Modding

Một bộ script nhỏ mình để mod font chữ (và một số thứ khác) trong một game Miku tap tap nào đó. Hiện tại đang hoạt động ổn trên JP, EN thì chưa chắc.

Cần cài Python và một số thư viện trước:

```
pip install UnityPy fonttools Pillow
```

---

## Font modding

Mục tiêu là nhét chữ Latin/tiếng Việt vào font gốc tiếng Nhật của game mà không làm mất các ký tự cũ.

**Bước 1 — Gộp font**

Đặt font gốc của game (`FOT-RodinNTLG Pro EB.otf`, `FOT-RodinNTLG Pro DB.otf`) và font tùy chỉnh vào thư mục `fontMerging/`, rồi sửa tên file trong `merge_fonts.py` cho đúng. Chạy:

```
python merge_fonts.py
```

Nếu muốn chỉ định đường dẫn thủ công thì: `python merge_fonts.py <base> <override> [output]`

Script sẽ xuất ra hai file `FOT-RodinNTLGPro-EB-OnDemand.otf` và `FOT-RodinNTLGPro-DB-OnDemand.otf`.

**Bước 2 — Tạo Font Asset trong Unity**

Phần này cần Unity Editor 2022.3.62f2 với Android Build Support. Kéo hai file `.otf` vào Unity, mở **Window → TextMesh Pro → Font Asset Creator** rồi tạo font asset với các thông số: point size 42, padding 5, atlas 4096×2048, render mode SDFAA. Bảng ký tự thì lấy từ mấy file `.txt` trong `unityMisc/`.

Tên file khi save **bắt buộc** phải là `FOT-RodinNTLGPro-EB-OnDemand` và `FOT-RodinNTLGPro-DB-OnDemand` — game đọc theo tên này.

Sau đó copy `BuildAssetBundles.cs` vào `/Assets/Editor/` và build qua **Assets → Build Font AssetBundle (Android)**. Copy file `font_replacement` ra vào thư mục `script/`.

**Bước 3 — Inject vào bundle game**

```
cd script
python inject_font.py font_replacement
```

Output là file `common` đã được mã hóa, đổi tên thành `4ad9182d51b21d790af3f73d72ddc193` rồi đẩy vào `Android/data/com.sega.pjsekai/files/data/47a2/` trên điện thoại là xong.

Nếu làm đúng thì font mới sẽ hiện ở phần Rank và Level trong game.

---

## Logo modding

Ngoài font, mình cũng có thể thay logo hiển thị trong game bằng ảnh tùy chỉnh bằng script `logoModding/replace_logo.py`

Đặt ảnh thay thế vào cùng thư mục với script (`alt.png` hoặc `alt.webp`), chạy script, lấy file output đổi tên rồi đẩy vào game tương tự như font.

---

## Decrypt / Encrypt riêng lẻ

`decrypt_bundle.py` và `encrypt_bundle.py` có thể dùng độc lập nếu chỉ cần giải mã hoặc mã hóa một file bundle bất kỳ.

---