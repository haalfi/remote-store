"""In-process moto S3 server for the test suite and benchmarks.

``start_moto_server`` binds port 0 on ``host`` in the calling thread, then
serves from a daemon thread. It does not use ``ThreadedMotoServer``: that class
binds a caller-chosen port inside its server thread, and its ``start()`` waits
without a timeout on an event only a successful bind sets, so a failed bind
hangs the caller. Choosing the port beforehand left a window in which another
server could take it, and on Windows werkzeug's ``SO_REUSEADDR`` let both bind
it. One bind of port 0 chooses and claims the port, and a failed bind raises
``OSError`` here. The evidence for both failure modes is BUG-315's dossier.

Stop a server with ``server.shutdown()``, ``thread.join()``,
``server.server_close()``; read its port from ``server.server_port``. Moto keeps
S3 state per process, so servers started in one process share buckets.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from werkzeug.serving import BaseWSGIServer


def start_moto_server(host: str = "127.0.0.1") -> tuple[BaseWSGIServer, threading.Thread]:
    """Bind a moto server to port 0 on ``host`` and serve it from a daemon thread.

    Raises:
        OSError: The bind failed. werkzeug reports a failed bind by printing it
            and calling ``sys.exit(1)``; this re-raises the ``OSError`` that
            exit carries, so a caller fails instead of ending the process.
    """
    from moto.moto_server.werkzeug_app import DomainDispatcherApplication, create_backend_app
    from werkzeug.serving import make_server

    try:
        server = make_server(host, 0, DomainDispatcherApplication(create_backend_app), threaded=True)
    except SystemExit as exc:
        bind_error = exc.__context__
        if isinstance(bind_error, OSError):
            raise OSError(bind_error.errno, f"moto server could not bind {host}:0: {bind_error}") from bind_error
        raise
    thread = threading.Thread(target=server.serve_forever, name="moto-server", daemon=True)
    thread.start()
    return server, thread
