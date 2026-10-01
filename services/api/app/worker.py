"""背景 worker：python -m app.worker

- 開 WORKER_CONCURRENCY 條執行緒，各自從 tasks 表領取任務執行
- 每 30 秒為執行中的任務延長租約；每 10 秒更新 /tmp/worker-heartbeat 供容器健康檢查
- 收到 SIGTERM（docker stop / 部署）時中止 FFmpeg，把執行中的任務放回佇列
- 每小時清理放棄的上傳暫存檔與過期的任務記錄
"""

import logging
import os
import signal
import socket
import threading
import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_sessionmaker
from app.models import Task, Upload, utcnow
from app.services import asset_analyzer, media, script_writer, speech, tasks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("starfly.worker")

HEARTBEAT_FILE = Path("/tmp/worker-heartbeat")

HANDLERS: dict[str, Callable[[Session, Task], dict]] = {
    asset_analyzer.TASK_TYPE: asset_analyzer.analyze_task,
    script_writer.TASK_TYPE: script_writer.generate_task,
}


class Worker:
    def __init__(self, concurrency: int):
        self.concurrency = concurrency
        self.worker_id = f"{socket.gethostname()}-{os.getpid()}"
        self.active: set[str] = set()
        self.lock = threading.Lock()

    def run_one(self, db: Session) -> bool:
        """領取並執行一個任務；沒有任務時回傳 False。"""
        task = tasks.claim(db, self.worker_id)
        if task is None:
            return False
        with self.lock:
            self.active.add(task.id)
        log.info("開始任務 %s %s（第 %d 次）", task.type, task.id, task.attempts)
        started = time.monotonic()
        try:
            handler = HANDLERS.get(task.type)
            if handler is None:
                tasks.fail(db, task, f"不支援的任務類型：{task.type}", retryable=False)
                return True
            result = handler(db, task)
            tasks.complete(db, task, result)
            log.info("完成任務 %s（%.1f 秒）", task.id, time.monotonic() - started)
        except media.Interrupted:
            db.rollback()
            tasks.release(db, task)
            log.info("任務 %s 因 worker 停止而放回佇列", task.id)
        except Exception as exc:
            db.rollback()
            retryable = getattr(exc, "retryable", True)
            message = str(exc) or type(exc).__name__
            retrying = tasks.fail(db, task, message, retryable=retryable)
            log.warning("任務 %s 失敗%s：%s", task.id, "，稍後重試" if retrying else "", message)
        finally:
            with self.lock:
                self.active.discard(task.id)
        return True

    def _slot(self) -> None:
        while not media.SHUTDOWN.is_set():
            try:
                with get_sessionmaker()() as db:
                    worked = self.run_one(db)
            except Exception:
                log.exception("領取任務失敗")
                worked = False
            if not worked:
                media.SHUTDOWN.wait(2)

    def _heartbeat(self) -> None:
        last_lease = last_cleanup = 0.0
        while not media.SHUTDOWN.is_set():
            HEARTBEAT_FILE.touch()
            now = time.monotonic()
            try:
                if now - last_lease >= 30:
                    with self.lock:
                        ids = list(self.active)
                    with get_sessionmaker()() as db:
                        tasks.heartbeat(db, self.worker_id, ids)
                    last_lease = now
                if now - last_cleanup >= 3600:
                    with get_sessionmaker()() as db:
                        cleanup(db)
                    last_cleanup = now
            except Exception:
                log.exception("背景維護失敗")
            media.SHUTDOWN.wait(10)

    def run(self) -> None:
        log.info("worker %s 啟動，同時處理 %d 個任務", self.worker_id, self.concurrency)
        threads = [threading.Thread(target=self._slot, name=f"slot-{i}") for i in range(self.concurrency)]
        threads.append(threading.Thread(target=self._heartbeat, name="heartbeat"))
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        log.info("worker 已停止")


def cleanup(db: Session) -> None:
    """刪除 3 天沒有進度的未完成上傳、30 天前已完成的任務記錄、7 天前的配音試聽檔。"""
    stale = db.scalars(
        select(Upload).where(Upload.completed.is_(False), Upload.updated_at < utcnow() - timedelta(days=3))
    ).all()
    for upload in stale:
        (media.uploads_dir() / f"{upload.id}.part").unlink(missing_ok=True)
        db.delete(upload)
    db.execute(
        delete(Task).where(Task.status == "succeeded", Task.finished_at < utcnow() - timedelta(days=30))
    )
    db.commit()
    if stale:
        log.info("清除 %d 個放棄的上傳", len(stale))
    if removed := speech.cleanup_previews():
        log.info("清除 %d 個過期的配音試聽檔", removed)


def main() -> None:
    def stop(signum, _frame):
        log.info("收到停止訊號 %s，結束執行中的任務…", signum)
        media.SHUTDOWN.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # 降低優先權：轉檔吃滿 CPU 時，網頁與 API 仍然保持流暢
    os.nice(10)
    Worker(get_settings().worker_concurrency).run()


if __name__ == "__main__":
    main()
