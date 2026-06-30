"""Точка входа для сервиса scheduler в docker-compose."""
import asyncio
import signal
import sys

from app.scheduler import create_scheduler


async def main():
    scheduler = create_scheduler()
    scheduler.start()
    print("⏰ Scheduler запущен. Ожидаю задачи...", flush=True)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    scheduler.shutdown(wait=False)
    print("🔌 Scheduler остановлен.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
