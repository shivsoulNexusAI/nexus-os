import time
from collections import defaultdict
from app.core.config import settings

request_history = defaultdict(list)

class SecurityLayer:
    @staticmethod
    def is_admin(user_id: int) -> bool:
        return user_id == settings.ADMIN_TELEGRAM_ID

    @staticmethod
    def check_rate_limit(user_id: int, max_requests: int = 5, window_seconds: int = 60) -> bool:
        current_time = time.time()
        request_history[user_id] = [
            req_time for req_time in request_history[user_id] 
            if current_time - req_time < window_seconds
        ]
        if len(request_history[user_id]) >= max_requests:
            return False
        request_history[user_id].append(current_time)
        return True

    @staticmethod
    def validate_image(file_size: int, file_path: str) -> bool:
        # Telegram's filters.PHOTO already guarantees this is an image.
        # We only check the size to prevent system crashes.
        max_size_bytes = 20 * 1024 * 1024 # 20 MB limit
        if file_size is None:
            file_size = 0
        return file_size <= max_size_bytes
