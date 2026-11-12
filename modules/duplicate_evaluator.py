"""
Module: duplicate_evaluator.py
Tổng hợp & Đánh giá mức độ trùng lặp:
- Tính điểm độc đáo (Originality Score)
- Đánh giá nguy cơ Re-up / Vi phạm bản quyền hình ảnh
- Phân tích mức độ bão hòa chủ đề dựa trên số lượng đối thủ quét được
- Đưa ra lời khuyên hành động (Actionable Advice) cho nhà sáng tạo nội dung
"""


RISK_LABELS = {
    -1: ("Chưa xác định (AI không đủ bằng chứng để kết luận nguồn gốc hình ảnh)", "gray"),
    0: ("Thấp (Khả năng cao là video tự quay/nội dung mới)", "green"),
    1: ("Trung Bình (Có dấu hiệu cắt ghép hoặc sử dụng tư liệu có sẵn)", "orange"),
    2: ("RẤT CAO (Phát hiện hình ảnh hoặc dấu vết đã xuất hiện trên mạng)", "red"),
}


def evaluate_video_report(
    visual_data: dict,
    content_data: dict,
    youtube_results: list[dict],
    lens_matches: list[dict] = None,
    youtube_scan_ok: bool = True,
    facebook_results: list[dict] = None
) -> dict:
    """
    Tổng hợp dữ liệu từ Visual Search + Content Analysis + Competitor Search để xuất báo cáo.
    """
    total_yt = len(youtube_results)
    total_fb = len(facebook_results) if facebook_results else 0
    total_lens = len(lens_matches) if lens_matches else 0
    
    # 1. Nguy cơ Re-up: dùng verdict có cấu trúc, vì văn xuôi luôn nhắc TikTok/Douyin kể cả khi kết luận là không có watermark.
    verdict = visual_data.get("verdict")
    try:
        confidence = int(float(visual_data.get("reup_confidence", 0)))
    except (TypeError, ValueError):
        confidence = 0
    confidence = max(0, min(100, confidence))

    if verdict == "reup":
        risk_level = 2 if confidence >= 70 else 1
    elif verdict == "original":
        risk_level = 0
    else:
        risk_level = -1

    # Bằng chứng tra cứu ngược độc lập với phán đoán của AI: ảnh đã có trên mạng là dấu hiệu mạnh.
    if total_lens >= 3:
        risk_level = 2
    elif total_lens > 0:
        risk_level = max(risk_level, 1)

    reup_risk, reup_badge_color = RISK_LABELS[risk_level]

    # 2. Đánh giá mức độ bão hòa ý tưởng trên YouTube
    if not youtube_scan_ok:
        saturation_level = "Không xác định (Không quét được YouTube nên chưa rõ mức độ cạnh tranh)"
        saturation_color = "gray"
    elif total_yt >= 8:
        saturation_level = "Bão hòa cao (Đã có rất nhiều người làm chủ đề này)"
        saturation_color = "red"
    elif total_yt >= 3:
        saturation_level = "Cạnh tranh vừa phải (Đã có một số kênh khai thác)"
        saturation_color = "orange"
    else:
        saturation_level = "Thị trường ngách / Ý tưởng mới (Rất ít hoặc chưa có ai làm)"
        saturation_color = "green"
        
    # 3. Tính điểm độc đáo (Originality Score)
    # Gemini có thể trả điểm dạng chuỗi ("75") hoặc null nên phải ép kiểu trước khi so sánh.
    try:
        base_score = int(float(content_data.get("estimated_originality_score", 70)))
    except (TypeError, ValueError):
        base_score = 70
    base_score = max(0, min(100, base_score))
    if risk_level == 2:
        base_score = min(base_score, 25)
    elif risk_level == 1:
        base_score = min(base_score, 55)
        
    # Quét lỗi thì không thưởng điểm "chưa ai làm", cũng không phạt vì thiếu đối thủ.
    if youtube_scan_ok:
        if total_yt > 6:
            base_score = max(10, base_score - 20)
        elif total_yt == 0:
            base_score = min(98, base_score + 10)
        
    # 4. Tạo lời khuyên hành động (Actionable Advice)
    recommendations = []
    if risk_level == 2:
        recommendations.append("⚠️ **Cảnh báo Re-up:** Không nên đăng lại nguyên si video này lên kênh chính vì rất dễ dính bản quyền hoặc bị bóp tương tác do thuật toán quét bản quyền tự động.")
        recommendations.append("💡 **Giải pháp:** Nếu thích nội dung này, hãy tự quay lại bằng người thật / góc máy mới, hoặc làm video dạng Reaction / Phân tích kèm dẫn nguồn.")
    elif risk_level == 1:
        recommendations.append("🟠 **Về hình ảnh:** Có dấu hiệu sử dụng tư liệu sẵn có. Hãy xác minh nguồn gốc từng đoạn trước khi đăng, hoặc tự quay lại phần hình ảnh chính.")
    elif risk_level == 0:
        recommendations.append("✅ **Về hình ảnh:** Video có chất lượng thị giác tốt và ít dấu hiệu bị quét trùng lặp trực tiếp.")
    else:
        recommendations.append("❔ **Về hình ảnh:** AI chưa đủ bằng chứng để kết luận nguồn gốc. Hãy tự tra cứu Google Lens / Yandex bằng các keyframe ở Tầng 1 trước khi đăng.")
        
    if not youtube_scan_ok:
        recommendations.append("🌐 **Chưa quét được đối thủ:** Không có dữ liệu YouTube nên chưa thể kết luận chủ đề này bão hòa hay còn ngách. Kiểm tra mạng rồi quét lại, đừng dựa vào điểm số hiện tại để quyết định sản xuất.")
    elif total_yt >= 4:
        recommendations.append(f"🎯 **Chiến lược cạnh tranh:** Đã có ít nhất {total_yt} video cùng chủ đề trên YouTube. Để nổi bật hơn, bạn nên:")
        recommendations.append("   - Đổi **Hook 3 giây đầu**: Tập trung vào câu hỏi gây tò mò hoặc kết quả bất ngờ mà các video đối thủ chưa chỉ ra.")
        recommendations.append("   - Tối ưu **Tiêu đề & Thumbnail**: Tránh dùng từ khóa chung chung, thêm yếu tố định lượng (ví dụ: 'Thử nghiệm trong 7 ngày', 'Cách làm trong 5 phút').")
    else:
        recommendations.append("🚀 **Cơ hội vàng:** Chủ đề này còn rất ít đối thủ khai thác! Bạn nên nhanh chóng sản xuất và đăng tải sớm để chiếm vị trí top tìm kiếm.")
        
    return {
        "originality_score": base_score,
        "reup_risk": reup_risk,
        "reup_badge_color": reup_badge_color,
        "saturation_level": saturation_level,
        "saturation_color": saturation_color,
        "competitor_count": total_yt + total_fb,
        "youtube_count": total_yt,
        "facebook_count": total_fb,
        "recommendations": recommendations
    }
