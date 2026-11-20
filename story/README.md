# Mod Story — Sekai-Modding

Công cụ tải, trích xuất, dịch và đóng gói lại **Main Story** (gồm cả 5 nhóm và 5 nhánh VIRTUAL SINGER) và **Event Story** cho Project Sekai (bản **JP** và **EN**) thông qua `sssekai` và `UnityPy`, không cần Unity Editor.

> **Lưu ý:** Nếu bạn dịch story sang **tiếng Việt có dấu**, hãy làm theo hướng dẫn [Mod Font](../font/README.md) trước để game hiển thị được đầy đủ dấu tiếng Việt.

---

## Cách dùng nhanh (Chế độ tương tác — khuyên dùng)

Mở PowerShell tại thư mục gốc `Sekai-Modding` và chạy:

```powershell
uv run story/story_mod.py
```

Làm theo menu hướng dẫn trên màn hình:

1. **Chọn server:** `JP` (mặc định) hoặc `EN`.
2. **Chọn `[1] Tải & Extract story ra file .txt để dịch`**:
   - Chọn **Main Story** (Leo/need, MORE MORE JUMP!, Vivid BAD SQUAD, Wonderlands×Showtime, 25-ji Nightcord de., và 5 nhánh VIRTUAL SINGER theo từng SEKAI) hoặc **Event Story** (tìm theo từ khóa hoặc nhập trực tiếp ID dạng `ID: Tên event`).
   - Chọn chapter muốn dịch (`1`, `1-4`, `1,3` hoặc `all`).
   - Script sẽ tự động dùng `sssekai` tải bundle gốc (lưu đệm tại `story/cache/`) và xuất ra file `.txt` trong `story/work/<jp|en>/<tên_story>/`.
3. **Dịch file `.txt`**:
   - Mở file `.txt` bằng Notepad / VS Code (đảm bảo lưu ở định dạng **UTF-8**).
   - **Chỉ sửa nội dung** bên dưới các thẻ `[TALK #...]`, `[TELOP #...]`, `[PLACE #...]`, `[FULLSCREEN #...]`, `[CHOICE #...]`.
   - **Không sửa/xóa** các dòng `# ...` ở đầu file và các dòng thẻ `[...]` (dùng để định vị chính xác khi ghép ngược vào bundle).
   - Với `[TALK #...]`: dòng `Speaker: ...` là tên nhân vật (có thể dịch hoặc giữ nguyên), các dòng bên dưới là lời thoại (được phép xuống dòng tự do).
4. **Chọn `[2] Patch file .txt đã dịch -> bundle mã hóa`**:
   - Chọn thư mục story bạn vừa dịch (script sẽ tự động nạp lại toàn bộ các chapter `.txt` trong thư mục đó, đóng gói LZ4 và mã hóa lại).
   - File kết quả xuất ra tại:
     ```text
     story/output/<jp|en>/<thư_mục_4_ký_tự>/<tên_file_md5>
     ```
   - Script sẽ in sẵn **đường dẫn chính xác trên Android** để bạn chép vào.

---

## Chép vào điện thoại Android

1. Dùng máy tính (USB File Transfer) hoặc ZArchiver + Shizuku (Android 11+) để vào thư mục dữ liệu game:
   - **Bản JP:** `Android/data/com.sega.pjsekai/files/data/<thư_mục_4_ký_tự>/`
   - **Bản EN:** `Android/data/com.sega.ColorfulStage.en/files/data/<thư_mục_4_ký_tự>/`
2. Sao lưu file gốc (nếu đã có), rồi chép đè file kết quả `<tên_file_md5>` từ `story/output/...` vào đúng `<thư_mục_4_ký_tự>/` mà script đã báo.
   - **Main Story** luôn nằm ở thư mục `a6c5/`.
   - **Event Story** mỗi event có một thư mục 4 ký tự riêng (script tự tính và tạo sẵn thư mục đúng tên trong `story/output/`).
3. Mở game và đọc lại tập story đó để kiểm tra.

---

## Dùng bằng dòng lệnh (CLI)

Phù hợp khi muốn thao tác nhanh không cần qua menu:

```powershell
# Xem danh sách Main Story & hash
uv run story/story_mod.py list --region jp --type main

# Tìm Event Story theo từ khóa (hoặc bỏ --search để liệt kê hết)
uv run story/story_mod.py list --region jp --type event --search addcolor

# Tải & extract Main Story (key: leo, mmj, vbs, wxs, n25, vs-leo, vs-mmj, vs-vbs, vs-wxs, vs-n25)
uv run story/story_mod.py extract --region jp --main leo --chapter 1

# Tải & extract Event Story theo ID (VD: event #210, tập 1 đến 3)
uv run story/story_mod.py extract --region jp --event 210 --chapter 1-3

# Patch 1 file .txt hoặc toàn bộ các tập .txt trong thư mục story
uv run story/story_mod.py patch story/work/jp/event_210_event_addcolor_2026/

# Cập nhật danh sách event & version game mới nhất từ GitHub
uv run story/story_mod.py refresh --region jp
```

---

## Định dạng file `.txt` ví dụ

```text
[FULLSCREEN #0]
Từ nhỏ mình đã có những người bạn rất thân.

[TELOP #2]
Vài năm sau

[PLACE #3]
Phòng của Ichika

[TALK #0]
Speaker: Ichika
……Được rồi, hôm nay cũng cố lên nào.
```

Các thẻ được hỗ trợ đầy đủ:
- `[TALK #n]` — Hội thoại (`TalkData[n]`: `WindowDisplayName` + `Body`)
- `[TELOP #n]` — Bảng chuyển cảnh / thời gian / địa điểm (`SpecialEffectType = 8`)
- `[PLACE #n]` — Dòng tên địa điểm (`SpecialEffectType = 18`)
- `[CHOICE #n]` — Lựa chọn (`SpecialEffectType = 23`)
- `[FULLSCREEN #n]` — Chữ trắng toàn màn hình (`SpecialEffectType = 24`)
