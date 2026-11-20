# Sekai-Modding

Bộ công cụ mod **Project Sekai: Colorful Stage!** (Hiện tại hỗ trợ mod font và dịch story).
- Hỗ trợ cả bản **JP** và **EN**.

> **Disclaimer:** Mọi hành động can thiệp vào file game đều vi phạm Điều khoản Dịch vụ (TOS) của Sega / Colorful Palette. Hãy cân nhắc và sao lưu file gốc trước khi sử dụng.
---

## Cách dùng

- **GUI:** Chạy `uv run app.py` để mở giao diện (gồm hướng dẫn cho cả Mod Story và Mod Font).
- **CLI:** Nên dùng trực tiếp **CLI** nếu muốn chỉnh các tham số nâng cao (`--match-cap-height`, `--scale`, `--y-offset`, `--weight`, `--charset`, batch patch, giải mã/mã hóa bundle riêng,...).

| Module | Mô tả | Hướng dẫn chi tiết (CLI) |
| :--- | :--- | :--- |
| **Giao diện** (`app.py`) | UI tối giản cho người dùng bình thường (Mod Story & Mod Font) | Chạy `uv run app.py` |
| **Mod Font** (`font/`) | Gộp font tiếng Việt / tiếng Anh và đóng gói bundle (`font/common`) | [font/README.md](font/README.md) |
| **Mod Story** (`story/`) | Tải bundle Main Story / Event Story, xuất `.txt` dịch, patch và mã hóa | [story/README.md](story/README.md) |
| **Bundle Crypto** (`script/`) | Giải mã / mã hóa riêng lẻ một file bundle bất kỳ (`decrypt_bundle.py`, `encrypt_bundle.py`) | Kéo thả file vào script hoặc truyền đường dẫn qua CLI |

---

## Lưu ý thêm
Ở Android 11+, mặc định sẽ chặn truy cập `Android/data`, nên cần quyền root hoặc ZArchiver + Shizuku. Những công cụ này có thể gây ảnh hưởng đến một số ứng dụng ngân hàng.

## Cài đặt

1. **Cài `uv`:**
   - Mở **Windows PowerShell**, dán lệnh sau rồi nhấn **Enter**:
     ```powershell
     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
     ```
   - Đóng PowerShell rồi **mở lại** để máy nhận lệnh `uv`.

2. **Tải repo về máy:**
   - Bấm **Code → Download ZIP** trên GitHub rồi giải nén, hoặc dùng Git:
     ```powershell
     git clone https://github.com/dang-minh-nguyet/Sekai-Modding
     cd Sekai-Modding
     ```

3. **Bắt đầu:**
   - Mở giao diện đơn giản: `uv run app.py`
   - Hoặc xem hướng dẫn CLI chi tiết tại [font/README.md](font/README.md) và [story/README.md](story/README.md).
