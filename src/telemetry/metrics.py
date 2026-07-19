"""Бизнес-метрики Prometheus (не HTTP-трафик — тот берёт instrumentator).

Отдельный модуль, чтобы метрики были синглтонами процесса независимо от
того, из какого сервиса (lifespan-таск, консьюмер, роут) их обновляют —
``prometheus_client`` сам мультиплексирует по лейблам, регистрация метрики
дважды с тем же именем — ошибка, поэтому здесь единственное место объявления.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

worker_jobs_pending = Gauge(
    "worker_jobs_pending",
    "Число джоб в processing/queued по последнему известному состоянию",
    ["kind"],
)

worker_jobs_reclaimed_total = Counter(
    "worker_jobs_reclaimed_total",
    "Джобы, помеченные stale после превышения MEDIA_JOB_STALE_AFTER_SEC",
    ["kind"],
)

worker_jobs_failed_total = Counter(
    "worker_jobs_failed_total",
    "Джобы, завершившиеся ошибкой",
    ["kind", "op"],
)

lua_script_duration_seconds = Histogram(
    "lua_script_duration_seconds",
    "Время выполнения lua-скрипта (полный RPC через LuaBus, включая ожидание ответа)",
    ["slug"],
)

bus_signature_rejected_total = Counter(
    "bus_signature_rejected_total",
    "Сообщения шины (Valkey Stream), отклонённые из-за неверной HMAC-подписи",
    ["bus"],
)

__all__ = [
    "worker_jobs_pending",
    "worker_jobs_reclaimed_total",
    "worker_jobs_failed_total",
    "lua_script_duration_seconds",
    "bus_signature_rejected_total",
]
