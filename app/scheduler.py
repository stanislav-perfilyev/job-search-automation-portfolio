"""
app/scheduler.py — APScheduler: запуск morning_brief.py по расписанию.

Время берётся из settings.scheduler_brief_time (формат "HH:MM", UTC).
По умолчанию 05:15 UTC = 08:15 Алматы / 08:15 MSK.

После выполнения:
- новые вакансии рассылаются через WebSocket (broadcast)
- результат отправляется в Telegram
"""
import asyncio
import logging
import sys
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

log = logging.getLogger("scheduler")

_BRIEF_SCRIPT = Path(__file__).parent.parent / "morning_brief.py"
_TIMEOUT      = 300   # 5 минут максимум


async def _run_morning_brief() -> None:
    """Запускает morning_brief.py и рассылает результаты."""
    log.info("⏰ Scheduler: запускаем morning_brief.py")

    if not _BRIEF_SCRIPT.exists():
        log.error("morning_brief.py не найден: %s", _BRIEF_SCRIPT)
        return

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(_BRIEF_SCRIPT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            log.error("morning_brief.py timeout (%ds)", _TIMEOUT)
            await _tg_notify(f"⚠️ morning\\_brief.py завис (timeout {_TIMEOUT}s)")
            return

        rc      = proc.returncode or 0
        stdout  = stdout_b.decode("utf-8", errors="replace")
        stderr  = stderr_b.decode("utf-8", errors="replace")

        log.info("morning_brief.py rc=%d, stdout=%d chars", rc, len(stdout))

        # Попытка разобрать вакансии из вывода (ищем строки с 💾 DB:)
        saved = _parse_saved_count(stdout)

        # Push по WebSocket
        if saved > 0:
            from app.ws import broadcast_new_vacancies
            await broadcast_new_vacancies([{"count": saved, "source": "morning_brief"}])

        # Telegram-уведомление
        status = "✅" if rc == 0 else "❌"
        short  = stdout[:800] if stdout else stderr[:400]
        msg    = (
            f"{status} *morning\\_brief.py* завершён\n"
            f"RC: `{rc}` | Сохранено вакансий: `{saved}`\n\n"
            f"```\n{short}\n```"
        )
        await _tg_notify(msg)

        # Инвалидируем кэш статистики (новые данные)
        if saved > 0:
            from app.cache import cache
            await cache.delete_pattern("stats:*")
            log.info("Кэш статистики сброшен после brief")

    except Exception as e:
        log.exception("Scheduler job failed: %s", e)
        await _tg_notify(f"❌ Scheduler error: `{e}`")


def _parse_saved_count(stdout: str) -> int:
    """Парсит '💾 DB: hh=N, habr=M вакансий сохранено' из вывода brief."""
    import re
    total = 0
    for match in re.finditer(r"hh=(\d+).*?habr=(\d+)", stdout):
        total += int(match.group(1)) + int(match.group(2))
    return total


async def _tg_notify(text: str) -> None:
    """Отправить уведомление в Telegram (без raise при ошибке)."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return
    try:
        import httpx
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(url, json={
                "chat_id":    settings.telegram_chat_id,
                "text":       text,
                "parse_mode": "Markdown",
            })
    except Exception as e:
        log.warning("TG notify failed: %s", e)


def create_scheduler() -> AsyncIOScheduler:
    """Создаёт и возвращает настроенный планировщик."""
    hour, minute = _parse_time(settings.scheduler_brief_time)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _run_morning_brief,
        trigger=CronTrigger(hour=hour, minute=minute, timezone="UTC"),
        id="morning_brief",
        name="Morning Brief",
        replace_existing=True,
        misfire_grace_time=600,   # если пропустил — запустить в течение 10 мин
    )
    log.info("Scheduler: morning_brief в %02d:%02d UTC ежедневно", hour, minute)
    return scheduler


def _parse_time(t: str) -> tuple[int, int]:
    try:
        h, m = t.split(":")
        return int(h), int(m)
    except Exception:
        log.warning("Неверный SCHEDULER_BRIEF_TIME='%s', используем 05:15", t)
        return 5, 15
