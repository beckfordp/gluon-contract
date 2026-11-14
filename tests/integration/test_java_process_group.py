# SPDX-License-Identifier: MIT

"""Java processes' loopback and process-group plumbing (gluon TD-45), with real
sockets and processes."""

import signal
import socket
from pathlib import Path

from gluon_contract.java_processes import JavaProcesses, port_open, signal_group


def test_port_open_sees_a_listener() -> None:
    """True while something listens, False once it's gone."""
    with socket.create_server(("127.0.0.1", 0)) as server:
        port = server.getsockname()[1]
        assert port_open(port)
    assert not port_open(port)


def test_a_spawned_process_is_stopped_with_its_group(tmp_path: Path) -> None:
    """SIGTERM to the group; signalling a group that's gone is not an error."""
    processes = JavaProcesses(tmp_path, tmp_path, "java")
    process = processes.spawn(["sleep", "30"], "sleep.log")
    processes.stop_all()
    assert process.poll() is not None
    signal_group(process.pid, signal.SIGTERM)
