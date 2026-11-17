"""Initial-setup runner: executes ordered steps in the background and broadcasts progress.

A run keeps going even if the browser disconnects; any client can (re)attach and
replay its events from the start. One run at a time.

Events:
  plan  {steps: [{id, title}]}
  step  {id, status: running|ok|warn|fail|skip, message, hint?, detail?}
  log   {id, line}
  done  {ok, counts, finished_at}
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable

log = logging.getLogger("avtaar.setup")

PASSING = {"ok", "warn"}


@dataclass
class StepResult:
    status: str  # ok | warn | fail | skip
    message: str
    hint: str | None = None
    detail: dict | None = None


def ok(message: str, **kw) -> StepResult:
    return StepResult("ok", message, **kw)


def warn(message: str, hint: str | None = None, **kw) -> StepResult:
    return StepResult("warn", message, hint, **kw)


def fail(message: str, hint: str | None = None, **kw) -> StepResult:
    return StepResult("fail", message, hint, **kw)


def skip(message: str, **kw) -> StepResult:
    return StepResult("skip", message, **kw)


class StepContext:
    def __init__(self, run: "SetupRun", step_id: str):
        self._run = run
        self.step_id = step_id
        self.state = run.state  # shared between steps

    def log(self, line: str) -> None:
        line = line.rstrip()
        if line:
            self._run.emit("log", {"id": self.step_id, "line": line[:500]})

    def progress(self, message: str) -> None:
        self._run.emit("step", {"id": self.step_id, "status": "running", "message": message})


StepFn = Callable[[StepContext], Awaitable[StepResult]]


@dataclass
class Step:
    id: str
    title: str
    fn: StepFn
    needs: list[str] = field(default_factory=list)


class SetupRun:
    def __init__(self, steps: list[Step]):
        self.steps = steps
        self.events: list[tuple[str, dict]] = []
        self.results: dict[str, StepResult] = {}
        self.state: dict = {}
        self.done = False
        self.started_at = time.time()
        self._cond = asyncio.Condition()

    def emit(self, event: str, data: dict) -> None:
        self.events.append((event, data))
        asyncio.get_running_loop().create_task(self._notify())

    async def _notify(self) -> None:
        async with self._cond:
            self._cond.notify_all()

    async def execute(self) -> None:
        self.emit("plan", {"steps": [{"id": s.id, "title": s.title} for s in self.steps]})
        for step in self.steps:
            blocked = [n for n in step.needs if self.results.get(n, StepResult("skip", "")).status not in PASSING]
            if blocked:
                titles = ", ".join(s.title for s in self.steps if s.id in blocked)
                res = skip(f"Skipped because an earlier step did not pass ({titles}).")
            else:
                self.emit("step", {"id": step.id, "status": "running", "message": "Working…"})
                try:
                    res = await step.fn(StepContext(self, step.id))
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001 - report, never crash the run
                    log.exception("setup step %s crashed", step.id)
                    res = fail(f"Unexpected error: {e or type(e).__name__}")
            self.results[step.id] = res
            self.emit("step", {"id": step.id, **{k: v for k, v in asdict(res).items() if v is not None}})

        counts: dict[str, int] = {}
        for r in self.results.values():
            counts[r.status] = counts.get(r.status, 0) + 1
        self.emit(
            "done",
            {"ok": counts.get("fail", 0) == 0, "counts": counts, "finished_at": time.time()},
        )
        self.done = True
        await self._notify()

    async def subscribe(self) -> AsyncIterator[tuple[str, dict]]:
        i = 0
        while True:
            while i < len(self.events):
                yield self.events[i]
                i += 1
            if self.done:
                return
            async with self._cond:
                await self._cond.wait_for(lambda: len(self.events) > i or self.done)

    def report(self) -> dict:
        return {
            "started_at": self.started_at,
            "done": self.done,
            "steps": [
                {"id": s.id, "title": s.title, **(asdict(self.results[s.id]) if s.id in self.results else {"status": "pending"})}
                for s in self.steps
            ],
        }


class SetupManager:
    """Owns the current/last run. Starting while a run is active attaches to it."""

    def __init__(self, report_path: Path, steps_factory: Callable[[], list[Step]]):
        self.report_path = report_path
        self.steps_factory = steps_factory
        self.current: SetupRun | None = None
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self.current is not None and not self.current.done

    def start(self) -> tuple[SetupRun, bool]:
        """Returns (run, started_new)."""
        if self.running:
            return self.current, False  # type: ignore[return-value]
        run = SetupRun(self.steps_factory())
        self.current = run
        self._task = asyncio.get_running_loop().create_task(self._execute(run))
        return run, True

    async def _execute(self, run: SetupRun) -> None:
        try:
            await run.execute()
        finally:
            try:
                self.report_path.write_text(json.dumps(run.report(), indent=2))
            except OSError:
                log.warning("could not save setup report")

    def last_report(self) -> dict | None:
        if self.current:
            return self.current.report()
        try:
            return json.loads(self.report_path.read_text())
        except (FileNotFoundError, ValueError):
            return None
