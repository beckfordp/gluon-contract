# SPDX-License-Identifier: MIT

"""Every check names its source, and the capture files it cites exist (gluon TD-41).

A check's docstring holds a `Source:` paragraph. Where its source is the
capture, it says `capture <file>`, or a list (`capture http/a.txt, b.txt and
asyncapi-html/index.html`): each name is relative to the capture, and a bare
name is in the directory of the name before it (`b.txt` is `http/b.txt`; after
`asyncapi-html/`, `index.html` is `asyncapi-html/index.html`), so a file at the
capture root after one in a directory is written `./openapi.yaml`. A
name ending `/` is a directory, `*` is a glob that must match a file, and a
`<placeholder>` is skipped. Each name is looked up in the latest capture of
every service the module is marked for (`check_markers`). Read with `ast`, so
nothing is imported.
"""

import ast
import re
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from gluon_contract.check_markers import module_services

_SEGMENT = r"[A-Za-z0-9_<>*-]+"
_NAME = rf"(?:\./)?(?:{_SEGMENT}/)*{_SEGMENT}(?:\.[a-z]+)+/?|(?:{_SEGMENT}/)+"
_CITATION = re.compile(rf"\bcapture ((?:{_NAME})(?:(?:, | and )(?:{_NAME}))*)")


def cited_files(docstring: str) -> list[str]:
    """The capture files the docstring's Source: paragraph cites, in order."""
    lines = docstring.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip().startswith("Source:")), None)
    if start is None:
        return []
    paragraph = []
    for line in lines[start:]:
        if not line.strip():
            break
        paragraph.append(line.strip())
    files = []
    for citation in _CITATION.finditer(" ".join(paragraph)):
        directory = PurePosixPath()
        for name in re.findall(_NAME, citation.group(1)):
            if name.startswith("./"):
                name = name.removeprefix("./")
                directory = PurePosixPath()
            elif name.endswith("/"):
                directory = PurePosixPath(name)
            elif "/" in name:
                directory = PurePosixPath(name).parent
            elif directory != PurePosixPath():
                name = f"{directory}/{name}"
            if "<" not in name:
                files.append(name)
    return files


def source_problems(module: str, source: str, capture_of: Callable[[str], Path]) -> list[str]:
    """One line per check in the module (by name, its source given) without a Source:
    line, and per cited file a service's capture (`capture_of(service)`) lacks."""
    services = module_services(source) or ()
    problems = []
    for node in ast.parse(source).body:
        if not (isinstance(node, ast.FunctionDef) and node.name.startswith("test_")):
            continue
        docstring = ast.get_docstring(node) or ""
        if not any(line.strip().startswith("Source:") for line in docstring.splitlines()):
            problems.append(f"{module}::{node.name}: no Source: line")
            continue
        for name in cited_files(docstring):
            for service in services:
                capture = capture_of(service)
                if not _holds(capture, name):
                    problems.append(
                        f"{module}::{node.name} cites {name}, which {service}'s capture "
                        f"{capture.name} lacks"
                    )
    return problems


def _holds(capture: Path, name: str) -> bool:
    if name.endswith("/"):
        return (capture / name).is_dir()
    if "*" in name:
        return any(path.is_file() for path in capture.glob(name))
    return (capture / name).is_file()
