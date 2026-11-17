"""Subprocess helpers for setup steps. Commands are always argv lists (never a shell)."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable


class CmdResult:
    def __init__(self, code: int, lines: list[str]):
        self.code = code
        self.lines = lines

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def output(self) -> str:
        return "\n".join(self.lines)

    def tail(self, n: int = 6) -> str:
        return "\n".join(self.lines[-n:])


async def run_cmd(
    argv: list[str],
    timeout: float = 60,
    on_line: Callable[[str], None] | None = None,
    env: dict | None = None,
    idle_timeout: float | None = None,
) -> CmdResult:
    """Run a command, streaming merged stdout/stderr lines. Returns code 127 if not found, 124 on timeout.

    `idle_timeout`: also give up if the command prints nothing for this many seconds.
    """
    if not shutil.which(argv[0]) and not Path(argv[0]).is_file():
        return CmdResult(127, [f"{argv[0]}: command not found"])
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL,
        env={**os.environ, **(env or {})},
    )
    lines: list[str] = []

    async def pump():
        assert proc.stdout
        buf = b""
        while True:
            try:
                chunk = await asyncio.wait_for(proc.stdout.read(4096), idle_timeout)
            except asyncio.TimeoutError:
                lines.append(f"(no output for {int(idle_timeout or 0)} s; giving up)")
                proc.kill()
                break
            if not chunk:
                break
            buf += chunk
            # Progress bars use \r; treat it as a line break too.
            parts = buf.replace(b"\r", b"\n").split(b"\n")
            buf = parts.pop()
            for p in parts:
                line = p.decode(errors="replace").rstrip()
                if line:
                    lines.append(line)
                    del lines[:-300]
                    if on_line:
                        on_line(line)
        if buf.strip():
            lines.append(buf.decode(errors="replace").rstrip())

    try:
        await asyncio.wait_for(asyncio.gather(pump(), proc.wait()), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        lines.append(f"(timed out after {int(timeout)} s)")
        return CmdResult(124, lines)
    return CmdResult(proc.returncode or 0, lines)


def spawn_detached(argv: list[str], log_path: Path, env: dict | None = None) -> int:
    """Start a long-running process that outlives this request (and the gateway). Returns its PID."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logf = open(log_path, "ab")  # noqa: SIM115 - handed to the child
    p = subprocess.Popen(
        argv,
        stdout=logf,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env={**os.environ, **(env or {})},
    )
    return p.pid
