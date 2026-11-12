# video-content-checker modules

import os
import re

from google import genai
from google.genai import errors

# Chỉ các lỗi quá tải / tạm thời phía server mới đáng đổi model; lỗi 400/403 phải ném ngay.
RETRYABLE_API_CODES = (429, 500, 503)


def is_retryable_api_error(exc: Exception) -> bool:
    return isinstance(exc, errors.APIError) and exc.code in RETRYABLE_API_CODES


def create_gemini_client(api_key: str) -> genai.Client:
    # httpx ném InvalidURL với entry NO_PROXY dạng "[::1]"; bỏ ngoặc để nó tự chuẩn hóa lại.
    for var in ("NO_PROXY", "no_proxy"):
        value = os.environ.get(var)
        if value and "[" in value:
            os.environ[var] = re.sub(r"\[([0-9a-fA-F:]+)\]", r"\1", value)
    return genai.Client(api_key=api_key)