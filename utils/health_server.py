"""
خادم فحص صحة اختياري (HTTP خفيف) لاستضافات تشترط منفذاً مفتوحاً مثل Render Web Service.

يعمل **فقط** إن وُجد المتغير `PORT`. لا يكشف أي بيانات حسّاسة: الاستجابة حالة عامة + رقم الإصدار.
المسارات: `GET /` و`GET /health` و`GET /healthz` ⇒ 200 JSON؛ غيرها ⇒ 404؛ غير GET ⇒ 405.
الحماية: حجم الطلب ≤ 4KB ومهلة قراءة 5ث وإغلاق الاتصال بعد كل رد (لا اتصالات معلّقة).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: أقصى حجم لرأس الطلب المقبول (بايت)
MAX_REQUEST_BYTES = 4096
#: مهلة قراءة الطلب (ثانية)
READ_TIMEOUT_SECONDS = 5.0
HEALTH_PATHS = frozenset({"/", "/health", "/healthz"})


class HealthServer:
    """خادم صحة ينتج حالة من دالة يمررها المشغّل (بلا أسرار)."""

    def __init__(self, port: int, status: Callable[[], dict], *, host: str = "0.0.0.0") -> None:  # noqa: S104
        """
        تهيئة الخادم (لا يبدأ قبل `start`).

        المدخلات:
            status : دالة تُرجع قاموساً قابلاً لـJSON يصف الحالة العامة.
        """
        self.port = port
        self.host = host
        self._status = status
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> int:
        """بدء الاستماع وإرجاع المنفذ الفعلي (مفيد حين يكون `port=0` في الاختبارات)."""
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        sockets = self._server.sockets or []
        actual = sockets[0].getsockname()[1] if sockets else self.port
        logger.info("خادم الصحة يعمل على %s:%s", self.host, actual)
        return int(actual)

    async def stop(self) -> None:
        """إيقاف الخادم وانتظار إغلاق اتصالاته."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """قراءة سطر الطلب والرد عليه ثم إغلاق الاتصال."""
        try:
            try:
                raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), READ_TIMEOUT_SECONDS)
            except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
                return
            if len(raw) > MAX_REQUEST_BYTES:
                return
            line = raw.split(b"\r\n", 1)[0].decode("latin-1", errors="replace").split()
            method, path = (line[0], line[1].split("?", 1)[0]) if len(line) >= 2 else ("", "")
            if not method:
                code, body = 400, {"error": "bad request"}
            elif method not in {"GET", "HEAD"}:
                code, body = 405, {"error": "method not allowed"}
            elif path not in HEALTH_PATHS:
                code, body = 404, {"error": "not found"}
            else:
                code, body = 200, self._status()
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            reasons = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed"}
            head = (
                f"HTTP/1.1 {code} {reasons[code]}\r\nContent-Type: application/json; charset=utf-8\r\n"
                f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n"
            ).encode("latin-1")
            writer.write(head + (b"" if method == "HEAD" else payload))
            await writer.drain()
        except (ConnectionError, OSError):
            logger.debug("انقطع اتصال فحص الصحة قبل اكتمال الرد")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                logger.debug("تعذّر إغلاق اتصال فحص الصحة بنظافة")
