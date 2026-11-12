"""Worker process that runs solves for the GUI. Must not import Qt.

Solving in a separate process keeps the interface responsive and makes Cancel
real: the process is terminated, which is the only way to stop scipy mid-solve.
"""
import traceback
import warnings


def serve(conn):
    """Answer ("solve", project_json) requests on `conn` until it closes."""
    from gmode.project import Project

    while True:
        try:
            cmd, payload = conn.recv()
        except EOFError:
            return
        if cmd != "solve":
            continue
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                result = Project.model_validate_json(payload).solve()
                msg = ("ok", result)
            except Exception as e:  # report every failure to the GUI rather than dying
                msg = ("error", f"{type(e).__name__}: {e}", traceback.format_exc())
        conn.send((*msg, [str(w.message) for w in caught]))
