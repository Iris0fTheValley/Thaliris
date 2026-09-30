"""Run reviewed repository source; never import the damaged installed runtime.

The assertions below are operator statements, not cryptographic user consent.
All automated actors must disconnect global integration before this route.
"""
from __future__ import annotations

import argparse
import importlib.abc
import importlib.util
import json
from pathlib import Path
import sys


class ReviewedSource(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "thaliris" or fullname.startswith("thaliris."):
            source = Path(__file__).resolve().parents[1] / "src" / Path(*fullname.split("."))
            package = source.is_dir()
            source = source / "__init__.py" if package else source.with_suffix(".py")
            return importlib.util.spec_from_file_location(fullname, source, loader=self,
                submodule_search_locations=[str(source.parent)] if package else None)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        source = Path(module.__spec__.origin)
        exec(compile(source.read_bytes(), str(source), "exec"), module.__dict__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--codex-home", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--revision", type=int, required=True)
    parser.add_argument("--state-sha256", required=True)
    parser.add_argument("--lifecycle-sha256", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--operator-asserted-user-delegation", action="store_true")
    parser.add_argument("--integration-disconnected", action="store_true")
    args = vars(parser.parse_args())
    sys.meta_path.insert(0, ReviewedSource())
    from thaliris.offline_recovery import recover
    try:
        print(json.dumps(recover(**args), sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
