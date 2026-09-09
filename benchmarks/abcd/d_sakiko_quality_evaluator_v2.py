"""Independent D-sakiko behavior-contract evaluator for the V1/V2 runtime.

This evaluator intentionally imports public behavior boundaries instead of
model-authored tests.  It is kept benchmark-local and does not participate in
Thaliris runtime routing.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _result(name: str, passed: int, failed: int = 0, *, detail: str = "") -> dict:
    total = passed + failed
    return {
        "status": "PASS" if failed == 0 and passed else "FAIL",
        "tests": total,
        "passed": passed,
        "failed": failed,
        "detail": detail[-4000:],
    }


def _import_root(root: Path) -> None:
    paths = [str(root / "GPT_SoVITS"), str(root)]
    for path in reversed(paths):
        if path not in sys.path:
            sys.path.insert(0, path)


def evaluate_core(root: Path) -> dict:
    try:
        _import_root(root)
        from live2d_support.behavior_contract import (
            DesktopLive2DQueueAdapter,
            Live2DBehaviorContractV1,
            SegmentSchedulerV1,
            resolve_model_target,
        )
        checks = 0
        common = dict(
            character_id="sakiko",
            default_model_id="default",
            default_model_url="/default",
            known_models={"alt": {"model_url": "/alt"}},
        )
        selection, target = resolve_model_target(**common)
        assert (selection["mode"], target["status"], target["model_id"]) == ("inherit", "ready", "default")
        checks += 1
        selection, target = resolve_model_target(**common, selection=None)
        assert (selection["mode"], target["status"]) == ("none", "none")
        checks += 1
        selection, target = resolve_model_target(**common, selection="missing")
        assert (selection["mode"], target["status"], target["model_url"]) == ("model", "invalid", None)
        checks += 1

        contract = Live2DBehaviorContractV1(chat_id="chat", character_id="sakiko")
        scheduler = SegmentSchedulerV1()
        first = contract.segment_event(segment_id="b", index=1, speaker_id="sakiko", text="b", emotion="x", audio_url="b.wav", turn_id="t")
        second = contract.segment_event(segment_id="a", index=0, speaker_id="sakiko", text="a", emotion="x", audio_url="a.wav", turn_id="t")
        assert scheduler.reduce(first)[0]["segment"]["segment_id"] == "b"
        assert scheduler.reduce(second) == []
        assert scheduler.complete()[0]["segment"]["segment_id"] == "a"
        assert scheduler.reduce(second) == []
        checks += 1
        contract.invalidate()
        assert scheduler.reduce(contract.event("interrupt")) == []
        assert scheduler.reduce(first) == []
        checks += 1

        shutdown = contract.shutdown_event()
        assert shutdown and scheduler.reduce(shutdown) == [{"type": "bye"}]
        assert contract.shutdown_event() is None
        checks += 1

        import queue
        emotions, audio = queue.Queue(), queue.Queue()
        producer = DesktopLive2DQueueAdapter(emotions, audio)
        published = producer.publish_segment(emotion="happiness", audio_path="voice.wav")
        consumed = DesktopLive2DQueueAdapter(emotions, audio).consume_next_event()
        assert published["kind"] == "segment_ready"
        assert consumed["data"]["audio_url"] == "voice.wav"
        checks += 1
        return _result("core_behavior", checks)
    except Exception as exc:  # evaluator reports a bounded failure, never a self-report
        return _result("core_behavior", 0, 1, detail=f"{type(exc).__name__}: {exc}")


def evaluate_backend(root: Path) -> dict:
    try:
        _import_root(root)
        from dsakiko_webui.backend.assets import AssetRegistry
        from dsakiko_webui.backend.runtime import HeadlessRuntime
        import dsakiko_webui.backend.assets as assets_module
        import live2d_support.runtime_adapter as runtime_adapter
        import live2d_support.motion_capabilities as motion_capabilities
        with tempfile.TemporaryDirectory() as directory:
            model_root = Path(directory)
            default = model_root / "default.model.json"
            selected = model_root / "selected.model.json"
            default.write_text("{}", encoding="utf-8")
            selected.write_text("{}", encoding="utf-8")
            with patch.object(assets_module, "LIVE2D_ROOT", model_root):
                assets = AssetRegistry()
                default_id = assets.register_live2d_model(default, model_id="default")
                selected_id = assets.register_live2d_model(selected, model_id="selected")
                runtime = HeadlessRuntime(assets)
                runtime.character_entities = {"sakiko": {"model_id": default_id, "model_url": assets.live2d_model(default_id)["model_url"]}}
                character = SimpleNamespace(character_name="Sakiko", character_folder_name="sakiko", live2d_json=str(default))
                chat = SimpleNamespace(chat_id="chat", meta=SimpleNamespace(live2d_models={"Sakiko": selected_id}))
                with patch.object(runtime_adapter, "detect_live2d_runtime_version", return_value="v2"), patch.object(
                    motion_capabilities,
                    "get_live2d_motion_capabilities",
                    return_value=SimpleNamespace(supported_positions_by_group={"idle": set()}),
                ) as capabilities:
                    runtime._ensure_live2d_context(chat, character)
                assert runtime.live2d.target["model_id"] == selected_id
                assert runtime.live2d.selection["mode"] == "model"
                assert runtime.live2d.target["status"] == "ready"
                capabilities.assert_called_once_with(str(selected.resolve()))
                chat.meta.live2d_models["Sakiko"] = "missing-model"
                runtime._ensure_live2d_context(chat, character)
                assert runtime.live2d.target["status"] == "invalid"
                assert runtime.live2d.target["model_url"] is None
                while not runtime.events.empty():
                    runtime.events.get_nowait()
                runtime.shutdown()
                event = runtime.events.get_nowait()
                assert event["type"] == "live2d_event"
                assert event["data"]["kind"] == "shutdown"
        return _result("backend_ingress", 7)
    except Exception as exc:
        return _result("backend_ingress", 0, 1, detail=f"{type(exc).__name__}: {exc}")


def evaluate_frontend(root: Path) -> dict:
    frontend = root / "dsakiko_webui" / "frontend"
    node = "node.exe" if os.name == "nt" else "node"
    module = (frontend / "src" / "live2d" / "behaviorReducer.js").resolve().as_uri()
    script = f"""
import {{ initialLive2DState, reduceLive2DEvent, completeLive2DSegment }} from {json.dumps(module)};
let s = initialLive2DState;
const e = (kind, epoch, data={{}}) => ({{contract_version: 1, kind, playback_epoch: epoch, data}});
s = reduceLive2DEvent(s, e('phase_changed', 0, {{phase: 'tts'}}));
if (s.phase !== 'tts') throw new Error('tts phase was not retained');
s = reduceLive2DEvent(s, e('segment_ready', 0, {{segment_id:'b', index:1}}));
s = reduceLive2DEvent(s, e('segment_ready', 0, {{segment_id:'a', index:0}}));
if (s.currentSegment?.segment_id !== 'b' || s.queue.length !== 1) throw new Error('segment scheduling mismatch');
s = reduceLive2DEvent(s, e('context_changed', 1, {{context: {{chat_id:'new'}}}}));
if (s.epoch !== 1 || s.currentSegment !== null || s.queue.length !== 0) throw new Error('context did not invalidate playback');
s = reduceLive2DEvent(s, e('shutdown', 1));
if (!s.shutdown) throw new Error('shutdown was not retained');
"""
    try:
        proc = subprocess.run([node, "--input-type=module", "-e", script], cwd=frontend, capture_output=True, text=True, timeout=30)
        if proc.returncode:
            return _result("frontend_reducer", 0, 1, detail=proc.stdout + proc.stderr)
        return _result("frontend_reducer", 4)
    except Exception as exc:
        return _result("frontend_reducer", 0, 1, detail=f"{type(exc).__name__}: {exc}")


def evaluate(root: Path) -> dict:
    contracts = [evaluate_core(root), evaluate_backend(root), evaluate_frontend(root)]
    total = sum(item["tests"] for item in contracts)
    passed = sum(item["passed"] for item in contracts)
    failed = sum(item["failed"] for item in contracts)
    return {
        "schema_version": 2,
        "workspace": str(root.resolve()),
        "contracts": contracts,
        "tests": total,
        "passed": passed,
        "failed": failed,
        "trusted_test_pass_rate": passed / total if total else 0.0,
        "quality_profile": "FULL_PASS" if total and failed == 0 else ("PARTIAL" if passed else "FAIL"),
        "independent_of_model_authored_tests": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(evaluate(args.workspace), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
