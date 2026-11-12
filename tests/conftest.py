"""Qt lifetime hygiene for the GUI tests.

Qt objects still alive at interpreter shutdown can be freed twice, once by Python's
garbage collector and once by Qt's own teardown, in no defined order. On Linux that
aborts the test run after every test has passed ("double free or corruption", exit
code 134). So pending deletions are processed after each test, and any remaining
windows are destroyed while the QApplication still exists.
"""
import gc


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
