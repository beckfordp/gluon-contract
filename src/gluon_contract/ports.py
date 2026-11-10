# SPDX-License-Identifier: MIT

"""Free TCP ports on 127.0.0.1 for the processes a run starts."""

import socket


def free_port() -> int:
    """A port nothing is listening on right now, chosen by the kernel.

    Another process could take it before it is used; runs are short and local,
    so the window is accepted rather than engineered around.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port
