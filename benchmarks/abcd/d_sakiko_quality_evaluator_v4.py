"""Frozen, model-independent Live2D behavior-contract evaluator.

The checks exercise observable Python and browser-facing APIs only.  They do
not import candidate tests, inspect model self-reports, or require a specific
implementation layout beyond the public contract surfaces.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _import_root(root: Path) -> None:
    for value in (str(root / "GPT_SoVITS"), str(root)):
        if value not in sys.path:
            sys.path.insert(0, value)


def _result(name: str, checks: int, detail: str = "") -> dict:
    return {"name": name, "tests": checks, "passed": checks if not detail else 0,
            "failed": 0 if not detail else checks, "status": "PASS" if not detail else "FAIL",
            "detail": detail[-4000:]}


def _python(root: Path) -> dict:
    added = [str(root / "GPT_SoVITS"), str(root)]
    _import_root(root)
    try:
        try:
            module = importlib.import_module("live2d_support.contract")
        except ModuleNotFoundError:
            module = importlib.import_module("live2d_support.behavior_contract")
        checks = 0
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            v2 = base / "default.model.json"; v2.write_text("{}", encoding="utf-8")
            v3 = base / "modern.model3.json"; v3.write_text("{}", encoding="utf-8")
            missing = base / "missing.model.json"
            invalid = module.resolve_target(str(v2), str(missing))
            assert invalid.status == "invalid"; checks += 1
            resolved = module.resolve_target(str(v2), None)
            assert resolved.status == "resolved" and resolved.runtime_version == "v2"; checks += 1
            resolved3 = module.resolve_target(str(v3), None)
            assert resolved3.status == "resolved" and resolved3.runtime_version == "v3"; checks += 1
            policy = module.Live2DActionPolicy()
            first = policy.emit("segment.enqueue", "chat:one", 1, action_id="s1", segment_id="seg", audio_url="/a", audio_state="ready")
            assert first and first["action_seq"] == 1; checks += 1
            assert policy.emit("segment.enqueue", "chat:one", 1, action_id="s1") is None; checks += 1
            policy.close_ingress()
            assert policy.emit("shutdown.bye", "chat:one", 1, action_id="bye") is None; checks += 1
        return _result("python_contract", checks)
    except Exception as exc:
        return _result("python_contract", 1, f"{type(exc).__name__}: {exc}")
    finally:
        for value in reversed(added):
            if value in sys.path:
                sys.path.remove(value)


def _backend(root: Path) -> dict:
    added = [str(root / "GPT_SoVITS"), str(root)]
    _import_root(root)
    try:
        import dsakiko_webui.backend.assets as assets_module
        from dsakiko_webui.backend.assets import AssetRegistry
        from dsakiko_webui.backend.runtime import HeadlessRuntime
        checks = 0
        with tempfile.TemporaryDirectory() as directory:
            model_root = Path(directory)
            model = model_root / "anon" / "model.model.json"
            model.parent.mkdir(parents=True); model.write_text("{}", encoding="utf-8")
            with patch.object(assets_module, "LIVE2D_ROOT", model_root):
                registry = AssetRegistry()
                runtime = HeadlessRuntime(registry)
                chat = SimpleNamespace(chat_id="one", meta=SimpleNamespace(live2d_models={"anon": str(model)}))
                character = SimpleNamespace(character_name="anon", live2d_json=None)
                slot = runtime._live2d_snapshot(chat, character)["slots"]["primary"]
                assert slot["status"] == "resolved" and slot["runtime_version"] == "v2"; checks += 1
                chat.meta.live2d_models["anon"] = str(model_root / "missing.model.json")
                slot = runtime._live2d_snapshot(chat, character)["slots"]["primary"]
                assert slot["status"] == "invalid"; checks += 1
                event = runtime._live2d_event("turn.phase", "one", "phase", phase="thinking")
                assert event and event["data"]["contract_version"] == 1; checks += 1
        return _result("backend_contract", checks)
    except Exception as exc:
        return _result("backend_contract", 1, f"{type(exc).__name__}: {exc}")
    finally:
        for value in reversed(added):
            if value in sys.path:
                sys.path.remove(value)


def _frontend(root: Path) -> dict:
    frontend = root / "dsakiko_webui" / "frontend"
    module = (frontend / "src" / "live2d" / "contract.js").resolve().as_uri()
    script = f"""
import {{ Live2DPresentationExecutor, normalizeLive2DAction }} from {json.dumps(module)};
let audio = 0, motion = 0, disposed = 0;
const e = new Live2DPresentationExecutor({{onAudio:()=>audio++, onMotion:()=>motion++, onDispose:()=>disposed++}});
const action = (kind, seq, rev=1, scene='chat:one', data={{}}) => ({{contract_version:1, kind, action_seq:seq, action_id:kind+seq, scene_id:scene, revision:rev, data}});
if (normalizeLive2DAction({{}}) !== null) throw new Error('malformed action accepted');
if (!e.accept(action('segment.enqueue', 1, 1, 'chat:one', {{audio_url:'/a', audio_state:'ready'}}))) throw new Error('segment rejected');
if (e.accept(action('segment.enqueue', 1, 1, 'chat:one'))) throw new Error('duplicate accepted');
if (audio !== 1 || motion !== 1) throw new Error('segment payload lost');
if (e.accept(action('segment.enqueue', 2, 0, 'chat:one'))) throw new Error('stale revision accepted');
if (e.accept(action('segment.enqueue', 3, 1, 'chat:two'))) throw new Error('stale scene accepted');
if (!e.accept(action('shutdown.dispose', 4, 1, 'chat:one'))) throw new Error('dispose rejected');
if (!e.closed || disposed !== 1) throw new Error('dispose state missing');
"""
    node = "node.exe" if os.name == "nt" else "node"
    proc = subprocess.run([node, "--input-type=module", "-e", script], cwd=frontend, capture_output=True, text=True, timeout=30)
    return _result("frontend_contract", 7, "" if proc.returncode == 0 else proc.stdout + proc.stderr)


def evaluate(root: Path) -> dict:
    contracts = [_python(root), _backend(root), _frontend(root)]
    total = sum(item["tests"] for item in contracts)
    passed = sum(item["passed"] for item in contracts)
    return {"schema_version": 4, "contract_version": "d-sakiko-live2d-behavior-v2",
            "workspace": str(root.resolve()), "contracts": contracts, "tests": total,
            "passed": passed, "failed": total - passed,
            "quality_profile": "FULL_PASS" if total and passed == total else "FAIL",
            "independent_of_model_authored_tests": True}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("workspace", type=Path)
    parser.add_argument("--output", type=Path); args = parser.parse_args()
    rendered = json.dumps(evaluate(args.workspace), ensure_ascii=False, indent=2) + "\n"
    if args.output: args.output.write_text(rendered, encoding="utf-8")
    else: print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
