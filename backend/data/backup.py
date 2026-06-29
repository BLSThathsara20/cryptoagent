"""Automatic database backups — no cron or manual steps required."""

import logging
import gzip
import os
import subprocess
from datetime import datetime
from glob import glob

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_last_backup_at: str | None = None
_last_backup_file: str | None = None


def get_backup_status() -> dict:
    backup_dir = settings.backup_dir
    files = sorted(glob(os.path.join(backup_dir, "cryptoagent_*.sql.gz")), reverse=True)
    return {
        "enabled": settings.auto_backup_enabled,
        "last_run_at": _last_backup_at,
        "last_file": _last_backup_file,
        "backup_count": len(files),
        "backup_dir": backup_dir,
    }


def run_auto_backup() -> dict:
    """Dump PostgreSQL to compressed file. Runs inside backend container."""
    global _last_backup_at, _last_backup_file

    if not settings.auto_backup_enabled:
        return {"skipped": True, "reason": "AUTO_BACKUP_ENABLED=false"}

    backup_dir = settings.backup_dir
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(backup_dir, f"cryptoagent_{timestamp}.sql.gz")

    # Parse credentials from DATABASE_URL or env
    db_url = settings.database_url
    try:
        result = subprocess.run(
            ["pg_dump", db_url, "--no-owner", "--no-acl"],
            capture_output=True,
            check=True,
            timeout=300,
        )
        with open(filepath, "wb") as f:
            with gzip.GzipFile(fileobj=f, mode="wb") as gz:
                gz.write(result.stdout)

        _last_backup_at = datetime.utcnow().isoformat()
        _last_backup_file = filepath
        logger.info("Auto backup saved: %s (%.1f MB)", filepath, os.path.getsize(filepath) / 1e6)

        # Rotate old backups
        files = sorted(glob(os.path.join(backup_dir, "cryptoagent_*.sql.gz")))
        while len(files) > settings.auto_backup_retain_count:
            os.remove(files.pop(0))

        return {"ok": True, "file": filepath, "size_mb": round(os.path.getsize(filepath) / 1e6, 2)}
    except FileNotFoundError:
        logger.error("pg_dump not found — install postgresql-client in backend image")
        return {"ok": False, "error": "pg_dump not available"}
    except subprocess.CalledProcessError as e:
        logger.error("Backup failed: %s", e.stderr.decode() if e.stderr else e)
        return {"ok": False, "error": "pg_dump failed"}
    except Exception as e:
        logger.error("Backup error: %s", e)
        return {"ok": False, "error": str(e)}


def start_backup_scheduler():
    if not settings.auto_backup_enabled:
        logger.info("Auto backup disabled")
        return
    scheduler.add_job(
        run_auto_backup,
        "cron",
        hour=2,
        minute=0,
        id="auto_backup",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
    logger.info("Auto backup scheduler started (daily 02:00 UTC)")


def stop_backup_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
