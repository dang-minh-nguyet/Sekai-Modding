# Mod Tốc Độ Chạy Chữ (Speed Change) — Sekai-Modding

CLI only, giúp thay đổi **tốc độ chạy chữ hội thoại** trong Project Sekai (**JP** và **EN**).

1. Tải file `.xapk` từ APKPure.
2. Patch tốc độ chạy chữ.
3. Tự động tải `uber-apk-signer`, **zipalign** và **ký số (v1 / v2 / v3)** toàn bộ split APK.
4. Đóng gói lại thành 1 file `.xapk` hoàn chỉnh tại `speed change/output/`.

---

## Mốc tốc độ tham khảo

Trong code gốc của game, tốc độ chạy chc được cố định ở **60** ms/kí tự, tức ~16,6 ký tự/giây). **Số càng nhỏ thì chạy càng nhanh:**

| Giá trị (ms) | Tốc độ so với gốc | Cảm nhận |
| :--- | :--- | :--- |
| **`60`** | **1.0x (Mặc định gốc)** | Tốc độ gốc của game |
| **`45`** | ~1.33x | Nhanh hơn nhẹ, vẫn giữ nhịp tự nhiên |
| **`35`** | ~1.71x | Nhanh vừa phải, dễ đọc tiếng Việt *(gợi ý)* |
| **`30`** | 2.0x | Nhanh gấp đôi gốc *(gợi ý)* |
| **`20`** | 3.0x | Rất nhanh |

---

## Yêu cầu trước khi chạy

1. Đã cài `uv` theo hướng dẫn tại [README.md](../README.md).
2. Có **Java (JRE/JDK 8 trở lên)** trên máy để ký số APK bằng `uber-apk-signer`.
   - Nếu máy chưa có Java, mở PowerShell và chạy:
     ```powershell
     winget install EclipseAdoptium.Temurin.21.JRE
     ```
   - Đóng và mở lại PowerShell sau khi cài.

---

## Cách dùng (1 lệnh duy nhất)

Mở PowerShell tại thư mục gốc `Sekai-Modding` và chạy:

```powershell
# Đổi tốc độ chạy chữ bản JP thành 35ms/ký tự (gốc là 60ms)
uv run "speed change/speed_change.py" 35
```

### Các tùy chọn bổ sung

```powershell
# Đổi tốc độ bản EN thành 30ms/ký tự
uv run "speed change/speed_change.py" 30 --region en

# Buộc tải lại XAPK bản mới nhất (dùng khi game vừa cập nhật phiên bản)
uv run "speed change/speed_change.py" 35 --refresh

# Dùng file .xapk bạn đã tải sẵn trên máy
uv run "speed change/speed_change.py" 35 --input "D:\Downloads\com.sega.pjsekai.xapk"

# Tùy chọn: chỉnh luôn thời gian nghỉ sang câu mới ở chế độ Auto (giây, mặc định gốc: 2.0)
uv run "speed change/speed_change.py" 35 --auto-delay 1.0

# Chỉ định đường dẫn file xuất ra
uv run "speed change/speed_change.py" 35 --output "D:\sekai_35ms.xapk"
```

File kết quả mặc định nằm tại:
```text
speed change/output/com.sega.pjsekai_<số>ms_signed.xapk
```

---

## Cách cài đặt lên Android

1. Chép file `.xapk` trong `speed change/output/` sang điện thoại.
2. Cài đặt bằng **SAI (Split APKs Installer)** hoặc **XAPK Installer**:
   - Mở SAI → **Install APKs** → **Internal file picker** → chọn file `.xapk` vừa tạo.
3. **Lưu ý quan trọng về chữ ký ứng dụng:**
   - **Lần đầu tiên** chuyển từ bản gốc (CH Play / QooApp) sang bản tự ký:
     - **Máy chưa Root:** Bắt buộc **gỡ bản game gốc trước** rồi mới cài bản `.xapk` này (hãy chắc chắn đã **liên kết tài khoản / lưu Transfer ID** trước khi gỡ!).
     - **Máy đã Root (có LSPosed + Core Patch):** Có thể cài đè trực tiếp không cần gỡ.
   - **Từ lần thứ 2 trở đi** (ví dụ bạn muốn đổi từ `20ms` sang `35ms`, `40ms` hoặc khi game update và bạn chạy lại `--refresh` trên cùng máy tính):
     - `uber-apk-signer` dùng cùng một khóa debug cố định của máy (`~/.android/debug.keystore`), nên bạn chỉ cần **cài đè (Update) trực tiếp**, không cần gỡ game và không mất dữ liệu!

---

## Cơ chế kỹ thuật (Dành cho người muốn tìm hiểu)

- Trường `TalkData.Speed` trong các file kịch bản story (`event_xxx.asset`) là trường không được client sử dụng.
- Tốc độ hiển thị thực tế do component `TalkWindow` (Unity `MonoBehaviour`, kích thước serialize 204 byte) quản lý qua trường `[SerializeField] float wordInterval` tại offset `0x84` (mặc định `0.06f` = 60ms) và `autoTextNextPageDelay` tại offset `0xC8` (mặc định `2.0f`).
- Script tự động quét mọi split APK trong XAPK để tìm chính xác các prefab chứa `TalkWindow` (nên hoạt động được cho cả JP, EN và các bản cập nhật sau), patch giá trị float mới, cập nhật CRC-32 rồi ký lại đồng bộ toàn bộ gói APK.
