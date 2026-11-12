"""Runs solves off the GUI thread, in a persistent worker process that can be cancelled."""
import multiprocessing as mp
import time
import warnings

from PySide6.QtCore import QObject, QTimer, Signal

from gmode.project import Project

from .solver_process import serve


class SolveRunner(QObject):
    started = Signal()
    finished = Signal(object, list)  # ModeSet, warnings
    failed = Signal(str, str)  # message, traceback
    cancelled = Signal()

    def __init__(self, parent=None, in_process: bool = False):
        """in_process=True solves synchronously on the calling thread (for tests and debugging)."""
        super().__init__(parent)
        self.in_process = in_process
        self._proc = None
        self._conn = None
        self._busy = False
        self.t_start = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._poll)

    @property
    def busy(self) -> bool:
        return self._busy

    def elapsed(self) -> float:
        return time.perf_counter() - self.t_start if self._busy else 0.0

    def solve(self, project: Project):
        if self._busy:
            return
        self._busy = True
        self.t_start = time.perf_counter()
        self.started.emit()
        if self.in_process:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                try:
                    result = project.solve()
                except Exception as e:
                    import traceback

                    self._busy = False
                    self.failed.emit(f"{type(e).__name__}: {e}", traceback.format_exc())
                    return
            self._busy = False
            self.finished.emit(result, [str(w.message) for w in caught])
            return
        self._ensure_process()
        self._conn.send(("solve", project.model_dump_json()))
        self._timer.start()

    def cancel(self):
        if not self._busy:
            return
        self._timer.stop()
        self._kill()
        self._busy = False
        self.cancelled.emit()

    def shutdown(self):
        self._timer.stop()
        self._kill()

    def _ensure_process(self):
        if self._proc is not None and self._proc.is_alive():
            return
        ctx = mp.get_context("spawn")  # fork is unsafe once Qt has started threads
        self._conn, child = ctx.Pipe()
        self._proc = ctx.Process(target=serve, args=(child,), daemon=True, name="gmode-solver")
        self._proc.start()
        child.close()

    def _kill(self):
        if self._proc is not None:
            self._proc.terminate()
            self._proc.join(timeout=2)
        if self._conn is not None:
            self._conn.close()
        self._proc = self._conn = None

    def _poll(self):
        try:
            if not self._conn.poll():
                if not self._proc.is_alive():
                    raise EOFError
                return
            msg = self._conn.recv()
        except (EOFError, OSError):
            self._timer.stop()
            self._busy = False
            self._kill()
            self.failed.emit("The solver process stopped unexpectedly (out of memory?)", "")
            return
        self._timer.stop()
        self._busy = False
        if msg[0] == "ok":
            self.finished.emit(msg[1], msg[2])
        else:
            self.failed.emit(msg[1], msg[2])
