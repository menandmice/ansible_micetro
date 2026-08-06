"""Test-time shim for the collection's fully-qualified import path.

The collection's own code always imports via the installed-collection path
(``ansible_collections.menandmice.ansible_micetro...``), but these tests
run straight out of a checked-out repo with no collection installed
anywhere on ``sys.path``. Register the same module objects under that
fully-qualified name so `import ansible_collections.menandmice.ansible_micetro...`
statements inside plugins/ resolve to the real files in this repo.
"""

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

NAMESPACE_PACKAGES = [
    "ansible_collections",
    "ansible_collections.menandmice",
    "ansible_collections.menandmice.ansible_micetro",
    "ansible_collections.menandmice.ansible_micetro.plugins",
    "ansible_collections.menandmice.ansible_micetro.plugins.module_utils",
    "ansible_collections.menandmice.ansible_micetro.plugins.modules",
    "ansible_collections.menandmice.ansible_micetro.plugins.lookup",
]

for name in NAMESPACE_PACKAGES:
    if name not in sys.modules:
        pkg = types.ModuleType(name)
        pkg.__path__ = []
        sys.modules[name] = pkg


def _load(fqcn, relpath):
    if fqcn in sys.modules:
        return sys.modules[fqcn]
    spec = importlib.util.spec_from_file_location(
        fqcn, str(REPO_ROOT / relpath)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[fqcn] = module
    spec.loader.exec_module(module)
    return module


_load(
    "ansible_collections.menandmice.ansible_micetro.plugins.module_utils.micetro",
    "plugins/module_utils/micetro.py",
)
_load(
    "ansible_collections.menandmice.ansible_micetro.plugins.modules.group",
    "plugins/modules/group.py",
)
_load(
    "ansible_collections.menandmice.ansible_micetro.plugins.modules.props",
    "plugins/modules/props.py",
)
