"""Loading a published command as a module.

The scripts under `scripts/` are commands, not a package: they are run as
`uv run python scripts/<name>.py` and never imported by the service (a unit
test proves that). A test that wants to run one exactly as the documentation
prints it therefore loads it by file path — and has to give it the one thing
running it as a script would give it for free, its own directory on `sys.path`,
or the script's `import bench_schema` raises `ModuleNotFoundError`.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def script_module(name: str) -> ModuleType:
    """The named script under `scripts/`, imported as a module."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
