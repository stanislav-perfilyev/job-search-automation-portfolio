"""
app/routers/brief.py

POST /brief/run — запускает morning_brief.py как subprocess и возвращает вывод.

Timeout: 180 секунд (утренний бриф парсит 33+ источника параллельно).
"""
import asyncio
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import verify_token

router = APIRouter(prefix="/brief", tags=["brief"])

# Путь к morning_brief.py — рядом с директорией app/
_BRIEF_SCRIPT = Path(__file__).parent.parent.parent / "morning_brief.py"
_TIMEOUT = 180


class BriefResult(BaseModel):
    success: bool
    returncode: int
    stdout: str
    stderr: str
    elapsed_sec: float


@router.post("/run", response_model=BriefResult)
async def run_brief(
    _: str = Depends(verify_token),
):
    """Запускает morning_brief.py и возвращает stdout/stderr."""
    if not _BRIEF_SCRIPT.exists():
        raise HTTPException(status_code=500,
                            detail=f"morning_brief.py не найден: {_BRIEF_SCRIPT}")

    import time
    t0 = time.monotonic()
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
            raise HTTPException(
                status_code=504,
                detail=f"morning_brief.py не завершился за {_TIMEOUT}с",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка запуска: {e}")

    elapsed = time.monotonic() - t0
    rc = proc.returncode or 0
    return BriefResult(
        success=rc == 0,
        returncode=rc,
        stdout=stdout_b.decode("utf-8", errors="replace"),
        stderr=stderr_b.decode("utf-8", errors="replace"),
        elapsed_sec=round(elapsed, 2),
    )
