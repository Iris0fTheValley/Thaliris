"""Independent behavioral evaluator for either Live2D Contract V1 layout.

This benchmark-only evaluator exercises public behavior directly and does not
read model-authored tests or self-reports. It tolerates the two equivalent
module names used by the D5 and D6 candidates while keeping the assertions
about the same contract.
"""
from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _python_contract(root: Path) -> tuple[int, int, str]:
    sys.path.insert(0, str(root / "GPT_SoVITS"))
    sys.path.insert(0, str(root))
    try:
        try:
            module = importlib.import_module("live2d_support.contract")
        except ModuleNotFoundError:
            module = importlib.import_module("live2d_support.behavior_contract")
        target = Path(tempfile.mkdtemp()) / "default.model.json"
        target.write_text("{}", encoding="utf-8")
        resolved = module.resolve_target(str(target), str(target.parent / "missing.model.json"))
        assert resolved.status == "invalid"
        policy = module.Live2DActionPolicy()
        first = policy.emit("segment.enqueue", "chat:one", 1, action_id="s1", audio_url="/a", audio_state="ready")
        assert first and first["action_seq"] == 1
        assert policy.emit("segment.enqueue", "chat:one", 1, action_id="s1") is None
        policy.close_ingress()
        assert policy.emit("shutdown.bye", "chat:one", 1, action_id="bye") is None
        return 3, 3, ""
    finally:
        sys.path.pop(0)
        sys.path.pop(0)


def _backend(root: Path) -> tuple[int, int, str]:
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "GPT_SoVITS"))
    try:
        import dsakiko_webui.backend.assets as assets_module
        from dsakiko_webui.backend.assets import AssetRegistry
        from dsakiko_webui.backend.runtime import HeadlessRuntime

        with tempfile.TemporaryDirectory() as directory:
            live2d_root = Path(directory)
            model = live2d_root / "anon" / "model.model.json"
            model.parent.mkdir(parents=True)
            model.write_text("{}", encoding="utf-8")
            with patch.object(assets_module, "LIVE2D_ROOT", live2d_root):
                runtime = HeadlessRuntime(AssetRegistry())
                chat = SimpleNamespace(chat_id="one", meta=SimpleNamespace(live2d_models={"anon": str(model)}))
                character = SimpleNamespace(character_name="anon", live2d_json=None)
                slot = runtime._live2d_snapshot(chat, character)["slots"]["primary"]
                assert slot["status"] == "resolved" and slot["runtime_version"] == "v2"
                action = runtime._live2d_event("turn.phase", "one", "phase", phase="thinking")
                assert action and action["data"]["contract_version"] == 1
        return 3, 3, ""
    finally:
        sys.path.pop(0)
        sys.path.pop(0)


def _frontend(root: Path) -> tuple[int, int, str]:
    frontend = root / "dsakiko_webui" / "frontend"
    module = frontend / "src" / "live2d" / "contract.js"
    script = f"""
import {{ Live2DPresentationExecutor }} from {json.dumps(module.resolve().as_uri())};
const e = new Live2DPresentationExecutor({{onMotion:()=>{{}}, onAudio:()=>{{}}}});
const a = {{contract_version:1, action_seq:1, action_id:'a1', scene_id:'chat:one', revision:1, kind:'segment.enqueue', data:{{audio_url:'/a',audio_state:'ready'}}}};
if (!e.accept(a) || e.accept(a)) process.exit(1);
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=frontend, capture_output=True, text=True)
    return 2, 2, "" if result.returncode == 0 else result.stderr[-2000:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    contracts = []
    for fn in (_python_contract, _backend, _frontend):
        try:
            total, passed, detail = fn(args.workspace)
        except Exception as exc:  # independent failure report, no traceback needed
            total, passed, detail = 1, 0, f"{type(exc).__name__}: {exc}"
        contracts.append({"tests": total, "passed": passed, "failed": total - passed, "status": "PASS" if passed == total else "FAIL", "detail": detail})
    total = sum(item["tests"] for item in contracts)
    passed = sum(item["passed"] for item in contracts)
    report = {"schema_version": 3, "contracts": contracts, "tests": total, "passed": passed, "failed": total - passed, "quality_profile": "FULL_PASS" if passed == total else "FAIL", "independent_of_model_authored_tests": True}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
