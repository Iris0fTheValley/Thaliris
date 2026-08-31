"""Report the declared A/B fixture without pretending it is a live experiment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and report the Thaliris A/B workflow fixture.")
    parser.add_argument("--fixture", type=Path, default=Path("tests/fixtures/workflow_ab.json"))
    args = parser.parse_args(argv)
    data = json.loads(args.fixture.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or set(data.get("workflows", {})) != {"A", "B"}:
        raise ValueError("invalid A/B workflow fixture")
    native = data.get("metrics", {}).get("native_run")
    if not isinstance(native, dict) or native.get("status") != "UNAVAILABLE":
        raise ValueError("fixture must declare unavailable native metrics until a live run is supplied")
    print(json.dumps({"ok": True, "fixture": data["workload"]["id"], "workflows": data["workflows"], "metrics": native}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
