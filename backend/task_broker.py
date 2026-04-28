import json
import os
import threading
import time
import uuid
from typing import Callable

try:
    import pika
except Exception:  # pragma: no cover - keeps the app bootable before deps install.
    pika = None

from cache_store import get_json, set_json


_memory_jobs: dict[str, dict] = {}
_worker_started = False


def _queue_name() -> str:
    return os.getenv("RABBITMQ_QUEUE", "elephant.rag.ingest").strip() or "elephant.rag.ingest"


def _rabbitmq_url() -> str:
    return os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F").strip()


def _connect():
    if pika is None:
        raise RuntimeError("pika is not installed")
    params = pika.URLParameters(_rabbitmq_url())
    params.heartbeat = int(os.getenv("RABBITMQ_HEARTBEAT", "30"))
    params.blocked_connection_timeout = int(os.getenv("RABBITMQ_BLOCKED_TIMEOUT", "30"))
    return pika.BlockingConnection(params)


def _store_job(job_id: str, payload: dict, ttl_seconds: int = 24 * 60 * 60) -> None:
    _memory_jobs[job_id] = payload
    set_json(f"jobs:ingest:{job_id}", payload, ttl_seconds)


def set_job_status(job_id: str, status: str, **extra) -> None:
    payload = {"job_id": job_id, "status": status, "updated_at": int(time.time()), **extra}
    _store_job(job_id, payload)


def get_job_status(job_id: str) -> dict:
    cached = get_json(f"jobs:ingest:{job_id}")
    if isinstance(cached, dict):
        return cached
    return _memory_jobs.get(job_id, {"job_id": job_id, "status": "unknown"})


def publish_ingest_job(payload: dict) -> dict:
    job_id = str(uuid.uuid4())
    message = {"job_id": job_id, "payload": payload}
    set_job_status(job_id, "queued")

    connection = _connect()
    try:
        channel = connection.channel()
        channel.queue_declare(queue=_queue_name(), durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=_queue_name(),
            body=json.dumps(message, ensure_ascii=False).encode("utf-8"),
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )
    finally:
        connection.close()

    return {"queued": True, "job_id": job_id, "queue": _queue_name()}


def start_ingest_worker(handler: Callable[[dict], dict]) -> bool:
    global _worker_started
    if _worker_started:
        return False
    enabled = os.getenv("RABBITMQ_WORKER_ENABLED", "true").strip().lower() not in {"0", "false", "no"}
    if not enabled:
        return False
    _worker_started = True

    def run() -> None:
        while True:
            try:
                connection = _connect()
                channel = connection.channel()
                channel.queue_declare(queue=_queue_name(), durable=True)
                channel.basic_qos(prefetch_count=1)

                def on_message(ch, method, properties, body) -> None:
                    job_id = "unknown"
                    try:
                        message = json.loads(body.decode("utf-8"))
                        job_id = str(message.get("job_id") or "unknown")
                        payload = message.get("payload") or {}
                        set_job_status(job_id, "processing")
                        result = handler(payload)
                        set_job_status(job_id, "done", result=result)
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                    except Exception as exc:
                        set_job_status(job_id, "failed", error=str(exc))
                        ch.basic_ack(delivery_tag=method.delivery_tag)

                channel.basic_consume(queue=_queue_name(), on_message_callback=on_message)
                channel.start_consuming()
            except Exception as exc:
                print(f"RabbitMQ ingest worker reconnecting after error: {exc}")
                time.sleep(5)

    thread = threading.Thread(target=run, name="rabbitmq-ingest-worker", daemon=True)
    thread.start()
    return True


def rabbitmq_status() -> dict:
    if pika is None:
        return {"enabled": False, "ok": False, "error": "pika is not installed"}
    try:
        connection = _connect()
        try:
            channel = connection.channel()
            channel.queue_declare(queue=_queue_name(), durable=True)
        finally:
            connection.close()
        return {"enabled": True, "ok": True, "queue": _queue_name(), "worker_started": _worker_started}
    except Exception as exc:
        return {"enabled": True, "ok": False, "queue": _queue_name(), "error": str(exc)}
