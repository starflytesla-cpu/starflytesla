"""統一錯誤：handler 只丟 AppError，由 main.py 轉成 {code, data, msg, reason}。

HTTP status 與業務 code 都表達真實失敗；reason 是給前端判斷用的機器可讀原因，
msg 是可以直接顯示給使用者的中文訊息。
"""


class AppError(Exception):
    def __init__(self, status: int, reason: str, message: str):
        super().__init__(message)
        self.status = status
        self.reason = reason
        self.message = message


def bad_request(message: str, reason: str = "bad_request") -> AppError:
    return AppError(400, reason, message)


def unauthorized(message: str = "請先登入", reason: str = "unauthorized") -> AppError:
    return AppError(401, reason, message)


def forbidden(message: str = "沒有權限執行這個操作", reason: str = "forbidden") -> AppError:
    return AppError(403, reason, message)


def not_found(message: str = "找不到資料", reason: str = "not_found") -> AppError:
    return AppError(404, reason, message)


def conflict(message: str, reason: str = "conflict") -> AppError:
    return AppError(409, reason, message)


def too_many_requests(message: str, reason: str = "rate_limited") -> AppError:
    return AppError(429, reason, message)


def upstream_error(message: str, reason: str = "upstream_error") -> AppError:
    return AppError(502, reason, message)
