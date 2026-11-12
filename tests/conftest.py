"""Qt lifetime hygiene for the GUI tests.

Qt objects still alive at interpreter shutdown can be freed twice, once by Python's
garbage collector and once by Qt's own teardown, in no defined order. On Linux that
aborts the test run after every test has passed ("double free or corruption", exit
code 134). So pending deletions are processed after each test, and any remaining
windows are destroyed while the QApplication still exists.

That fixed the crash on Python 3.12, but the Python 3.10 job (older scipy, different
shutdown order) still aborted after all tests passed. Since the results are final by
then, the test process ends with pytest's exit status once reporting is done, skipping
interpreter teardown. The desktop app's own shutdown is still checked: CI runs
`gmode-gui --self-test`, which goes through the app's normal exit.
"""
import gc
import os
import sys

import pytest


def _flush_deletions():
    try:
        from PySide6.QtCore import QCoreApplication, QEvent
    except ImportError:  # environments without the GUI extra
        return None
    app = QCoreApplication.instance()
    if app is not None:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    return app


def pytest_runtest_teardown(item, nextitem):
    _flush_deletions()


def pytest_sessionfinish(session, exitstatus):
    session.config._gmode_exitstatus = int(exitstatus)
    app = _flush_deletions()
    if app is None:
        return
    from PySide6.QtWidgets import QApplication

    for w in QApplication.topLevelWidgets():
        w.close()
        w.deleteLater()
    _flush_deletions()
    gc.collect()
    _flush_deletions()


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    status = getattr(config, "_gmode_exitstatus", None)
    if status is None or os.environ.get("GMODE_TEST_NORMAL_EXIT"):
        return  # set GMODE_TEST_NORMAL_EXIT=1 to debug teardown crashes
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)
