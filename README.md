Sekai-FModding

Bộ công cụ hỗ trợ mod font chữ trong tựa game nhịp điệu Miku (hiện tương thích với máy chủ JP, có thể hoạt động trên EN).

1. Yêu cầu chuẩn bị

Đảm bảo bạn đã cài đặt Python trên máy. Mở terminal và cài đặt các thư viện cần thiết bằng lệnh sau:

pip install UnityPy fonttools


2. Cấu trúc thư mục

Vui lòng tổ chức các file theo đúng cấu trúc sau để script hoạt động mượt mà:

fontMerging/

merge_fonts.py: Script dùng để gộp các ký tự tiếng Việt/Latinh vào font gốc tiếng Nhật.

Hãy đặt font gốc và font tùy chỉnh của bạn vào đây.

script/

inject_font.py: Script dùng để tiêm (inject) font đã gộp và các tài nguyên cập nhật vào file AssetBundle của game.

Đặt file common.bak (bundle gốc của game) vào thư mục này.

3. Hướng dẫn thực hiện

Bước A: Gộp Font

Kết hợp font chữ tiếng Việt/Latinh của bạn vào font gốc tiếng Nhật của game.

cd fontMerging
# Mở terminal và chạy lệnh sau (hoặc cấu hình đường dẫn sẵn trong script):
# Cú pháp: python merge_fonts.py [Font_Gốc] [Font_Ghi_Đè] [Font_Đầu_Ra]
python merge_fonts.py


Sau khi chạy, công cụ sẽ tự động xuất ra file font đã gộp hoàn chỉnh.

Bước B: Tạo AssetBundle thay thế (Bằng Unity)

(Lưu ý: Yêu cầu cài đặt Unity Editor bản 2022.3.62f2, có cài module Android Build Support và AssetBundle Browser).

Kéo thả file font đã gộp ở Bước A vào Unity.

Trên thanh menu của Unity, chọn Window -> TextMesh Pro -> Font Asset Creator.

Thiết lập thông số (Config):

Sampling Point Size: Chọn Custom và nhập 42.

Padding: 5.

Atlas Res: 4096 x 2048 (Độ phân giải gốc).

Character Set: Chọn Custom hoặc Character from file (Tham khảo các file .txt trong thư mục unityMisc để lấy bảng ký tự).

Render Mode: SFDAA.

Nhấn Generate Font Atlas, sau đó Save. Tên file lưu bắt buộc phải là:

FOT-RodinNTLGPro-EB-OnDemand (Tên hiển thị nhân vật trong cốt truyện).

FOT-RodinNTLGPro-DB-OnDemand (Văn bản hiển thị trong cốt truyện).

Build file font:

Copy file BuildAssetBundles.cs vào thư mục /Assets/Editor.

Trên thanh menu, chọn Assets -> Build Font AssetBundle (Android).

Khi hoàn tất, copy file font_replacement vừa tạo sang thư mục script/.

Bước C: Nhúng (Inject) Font vào Bundle của Game

Tiêm các asset font và texture mới vào file bundle gốc.

cd ../script
# Cú pháp: python inject_font.py [Đường_Dẫn_Bundle_Mới]
python inject_font.py font_replacement


Quá trình này sẽ tạo ra một file common đã được mã hóa, sẵn sàng đưa vào game.

Bước D: Cài đặt và Kiểm tra

Đổi tên file common vừa tạo thành 4ad9182d51b21d790af3f73d72ddc193.

Truy cập vào đường dẫn điện thoại Android: Android/data/com.sega.pjsekai/files/data/47a2 và dán đè file này vào.

Mở game lên. Nếu làm đúng các bước, font chữ mới sẽ xuất hiện ở phần Rank và Level!