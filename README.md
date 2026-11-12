# 🎬 AI Video Content & Copyright Reviewer

Công cụ đa tầng giúp xem, phân tích và thẩm định nội dung video:
1. **Tầng 1: Soi nguồn gốc thị giác (Kiểu Google Lens / Re-up Check)**:
   - Trích xuất tự động các khung hình (Keyframes) đại diện bằng thuật toán phát hiện chuyển cảnh, lọc bỏ khung hình mờ (blur) và khung hình tối.
   - Nhận diện watermark (TikTok, Douyin, CapCut, logo truyền hình), diễn viên, địa danh, vật phẩm và phong cách biên tập qua Gemini Vision.
   - Tự động tra cứu ngược hình ảnh (Google Lens, Yandex, Bing).
2. **Tầng 2: Kiểm tra kịch bản & Ý tưởng (Content & Semantic Check)**:
   - "Xem" video bằng mô hình Gemini Flash (hoặc trích xuất Audio siêu tốc).
   - Tóm tắt câu mở đầu (Hook 3 giây đầu), phân đoạn kịch bản và thông điệp cốt lõi.
   - Tự động sinh ra các cụm từ khóa tìm kiếm (Search queries) tối ưu nhất cho YouTube và Facebook.
3. **Tầng 3: Quét đối thủ cạnh tranh trên YouTube & Facebook**:
   - Quét trực tiếp các video cùng chủ đề trên YouTube bằng `yt-dlp` (hoàn toàn miễn phí, không tốn quota API).
   - Trích xuất tiêu đề, kênh, lượt xem, thời lượng và ngày đăng của đối thủ.
   - Tạo sẵn các truy vấn tìm kiếm chuyên sâu (Google Dorks) cho Facebook Reels & Facebook Watch.
4. **Tầng 4: Báo cáo & Lời khuyên chiến lược**:
   - Đánh giá Điểm độc đáo (Originality Score /100).
   - Đánh giá Nguy cơ Re-up (Thấp / Trung bình / Rất cao).
   - Đánh giá Mức độ bão hòa nội dung và lời khuyên tối ưu hóa hook, thumbnail và góc tiếp cận.

---

## 🚀 Hướng Dẫn Sử Dụng

### 1. Cài đặt thư viện (Đã cài sẵn trên môi trường)
```bash
pip install google-genai opencv-python streamlit yt-dlp python-dotenv requests
```

### 2. Chạy giao diện Web App (Streamlit)
Chạy lệnh sau tại thư mục dự án:
```bash
streamlit run app.py
```
Giao diện sẽ tự động mở trên trình duyệt tại `http://localhost:8501`. Tại đây bạn có thể:
- Nhập **Gemini API Key** ở thanh Sidebar.
- Tải file video lên (MP4, MKV, MOV) hoặc dán link TikTok, YouTube, Facebook Reel.
- Bấm nút **"Bắt đầu quét & Review toàn diện"** để xem toàn bộ kết quả trực quan trên các Tab.

### 3. Chạy bằng dòng lệnh (CLI)
```bash
python cli.py --video "test.mp4" --gemini-key "AIzaSy..."
```
Hoặc quét trực tiếp từ đường link:
```bash
python cli.py --url "https://www.tiktok.com/@creator/video/12345" --gemini-key "AIzaSy..."
```

---

## 📁 Cấu trúc thư mục

```
video-content-checker/
├── app.py                      # Giao diện Web App Streamlit
├── cli.py                      # Giao diện dòng lệnh CLI
├── .env.example                # File mẫu cấu hình API Keys
├── README.md                   # Tài liệu hướng dẫn
└── modules/
    ├── __init__.py
    ├── keyframe_extractor.py   # Thuật toán trích xuất frame thông minh & lọc mờ
    ├── visual_search.py        # Soi dấu vết watermark & kết nối Google Lens
    ├── content_analyzer.py     # Gemini AI phân tích kịch bản & sinh từ khóa
    ├── platform_search.py      # Quét đối thủ YouTube (yt-dlp) & Facebook
    └── duplicate_evaluator.py  # Đánh giá độ độc đáo & lập báo cáo
```
