"""Codex adapter for explicit handoff delivery and native lifecycle hooks."""
from __future__ import annotations

import json
import hashlib
from functools import lru_cache
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib

from . import codex_app_server, core, lifecycle, roles
from .lifecycle import (
    MANAGED_HOOKS_DESCRIPTION,
    MANAGED_HOOK_ABI,
    HOST_HOOK_SCRIPT_NAME,
    PROJECT_ACTIVATION_MARKER,
    handle_hook,
    host_hook_script_bytes,
    merge_host_hooks,
    remove_hooks,
    remove_host_hooks,
)

# This adapter-owned vocabulary is a CLI ingress contract. Core receives an
# opaque actor marker after this boundary has authorized the operation.
# This is the complete public CLI ingress vocabulary. Native identifiers are
# translated only at the native adapter boundary and never accepted as roles.
ROLE_CHOICES = roles.role_choices()
_PROJECT_ACTIVATION_BYTES = b'{"format":"thaliris-project-activation-v1"}\n'

def role_choices() -> tuple[str, ...]:
    return roles.role_choices()


def _role_choices() -> tuple[str, ...]:
    return role_choices()


def _native_codex_role_map() -> dict[str, str]:
    return roles.native_codex_role_map()


def _role_model_defaults() -> dict[str, tuple[str, str | None]]:
    return {
        role: (binding.model, binding.reasoning_effort)
        for role in roles.role_choices()
        for binding in (roles.get_codex_binding(role),)
        if binding is not None
    }


def _agent_profiles() -> dict[str, tuple[str, str | None, str]]:
    return roles.agent_profiles()


# Compatibility aliases retained for existing callers. Runtime paths below
# use the registry accessors so adding a role does not require another set.
_NATIVE_CODEX_ROLE_MAP = _native_codex_role_map()
_ROLE_MODEL_DEFAULTS = _role_model_defaults()
_AGENT_PROFILES = _agent_profiles()
_NATIVE_PROFILE_NAMES = roles.native_profile_names()
_KNOWN_GENERATED_AGENT_PROFILE_HASHES = {
    binding.profile_filename: binding.legacy_profile_hashes
    for binding in roles.iter_codex_bindings()
    if binding.profile_filename is not None
}
# Exact SHA-256 identities of the complete eleven-profile set rendered by the
# immutable ba84553 adapter/registry revision (source blobs
# e1262c3440bdb5f6007a0cab5d78b49141cecbd9 and
# 151f4ea6a403062fcc070acfd8b5fd1f830600f0). These hashes were independently
# compared with the effective CODEX_HOME files before being recorded here.
# They are historical generated ownership evidence, never a claim made by the
# current renderer, and remain keyed by the exact native profile filename.
_BA84553_GENERATED_AGENT_PROFILE_HASHES = {
    "thaliris-curator.toml": "25b4addb9686086fe406076a122423b64017bff12bb8a49b7ef3940562a02791",
    "thaliris-focused-implementer-astra-medium.toml": "a47c1cdca975dd10c4a0260f0a4b470b08c24b09d78ce58f40b49ac0f2cf031c",
    "thaliris-focused-implementer-xhigh.toml": "9a508f3a20aa0ead6dfe5a497a28360bb80fcbae0b517449328ad72082459ed0",
    "thaliris-focused-implementer.toml": "78adaf70f2719f7d1eae4f77fd59510f26ae4390e9143e33bfd97e940dece36b",
    "thaliris-implementer.toml": "652bc0ec379f699307f52acdd8f3112f423aa885c19bff0244ac294ee4ae1d35",
    "thaliris-investigator.toml": "1dbe2cca46484bcd31e13ebf6f3e7422dd477d4522d72da00360b8fd558d28b4",
    "thaliris-reasoning-specialist-astra-medium.toml": "cf81e133c7382584a16852c22eedffe7a5c6a67388f64421b073ec721754fadd",
    "thaliris-reasoning-specialist-xhigh.toml": "b88730b4bd7d9a18d5e57c95db2316c895f44c74cea32f0eba5810bbdee38211",
    "thaliris-reasoning-specialist.toml": "ed9b227397dabf75552067d54663f6cac853d96f592e07b511e564493ee13d51",
    "thaliris-reviewer.toml": "39c4396ea903bc58477dc329f670a34cc8e2b553c7a9e604fb85c8bfdfba0624",
    "thaliris-verifier.toml": "67f965ebb7566330cdf771bfb78da20d4a0248c34c231b6ec336657bb529df0f",
}
for _profile_name, _profile_hash in _BA84553_GENERATED_AGENT_PROFILE_HASHES.items():
    _KNOWN_GENERATED_AGENT_PROFILE_HASHES[_profile_name] = (
        _KNOWN_GENERATED_AGENT_PROFILE_HASHES.get(_profile_name, frozenset())
        | frozenset({_profile_hash})
    )
# Exact SHA-256 identities of the complete eleven-profile set rendered by the
# immutable 1f98dae adapter/registry revision immediately before the focused
# role wording update (source blobs
# b7e26ce90a940ba874390ab4cfa72982c2d0f813 and
# c0ec3ad81b5461bff4d09aaf3e7a5357f2a3d407). These hashes were independently
# compared with the effective CODEX_HOME files before being recorded here.
# These hashes are historical generated ownership evidence, never a claim made
# by the current renderer, and remain keyed by the exact native profile filename.
_1F98DAE_GENERATED_AGENT_PROFILE_HASHES = {
    "thaliris-curator.toml": "0ddddf8aae4cdbd2ccc49b455712ee9861c203e054333d418ff4f39fd9c898ae",
    "thaliris-focused-implementer-astra-medium.toml": "4ba712ecb415700ce05bedbd0860d9d180d87baff0919143977e2969092b58b7",
    "thaliris-focused-implementer-xhigh.toml": "62c946403f45b0cdc2e278fe4b37cdaf09a84ec6535a65e9885c2636967c6484",
    "thaliris-focused-implementer.toml": "42042dbc7564432c5864c4c6faf6f58c1821da3c47041402faa979b69904286a",
    "thaliris-implementer.toml": "c3e6fd2d10452a0d15e145decba7189d2a71db2d7e599b0de25c6875a6b44e59",
    "thaliris-investigator.toml": "a787e046a558eb25c5e0cefe8aa933727beacbc5460c131dde5347cb532f01ad",
    "thaliris-reasoning-specialist-astra-medium.toml": "723d032ec7f431acd899730cfae55af98756c5925712be863b08719dc932521a",
    "thaliris-reasoning-specialist-xhigh.toml": "8a00c1fd917f795892af67b10c1a9acdaf8cd24c0d6f57cf3d9d22947e4d25f6",
    "thaliris-reasoning-specialist.toml": "077c5037dade5a6a53a5247bc25bcddc6a895258d3dbce0e63c7c74e1fb399d3",
    "thaliris-reviewer.toml": "01f1b4163a98bdf752c1bda84f45c6d53c662f86350739ac720d8027e680eff2",
    "thaliris-verifier.toml": "44fb8af36bb7b668b71eccd73aa8a21f9870f252c17c07cc41753499136a35da",
}
for _profile_name, _profile_hash in _1F98DAE_GENERATED_AGENT_PROFILE_HASHES.items():
    _KNOWN_GENERATED_AGENT_PROFILE_HASHES[_profile_name] = (
        _KNOWN_GENERATED_AGENT_PROFILE_HASHES.get(_profile_name, frozenset())
        | frozenset({_profile_hash})
    )
_KNOWN_GENERATED_ROLE_PACK_HASHES = frozenset({
    # 5e6554196d27c4d6bc87c2a8008bd3c37ef01b31, blob 7dfd7ab321c4ec1f1c32bd02b1d87f1b88d2aef7.
    "0a51833bf936b14053c08a6502a6a1d27ecd1518263e7eea5c4e43f53fa1c5f1",
    "b6dba8d5d5e855face02667993601f84c4a54e77d7c33012d542a6b91483ec6c",
    "c019c41505c8bc000a5d00151fe837d4d1e9000f242bdb9f98bb7add905104bc",
    "844a2278b311c253c2da3a06133b503edb822a2929eeb082b50ecd2925e4cd30",
    "e14a01cfb3444ed553e43472581b6bf59b5858d6bdc279f61fda17823b4670b0",
    "e3473113697a9343d0ca108468434b26a53b8d8175a4f344e86067e93bf2c853",
    "ea1f1c8386b41a0138bcdf3691cae95cc9c816db47bfa14dcdcbf36d2e87f0d9",
    "cc609291e31edb07d89784a1fe6f6d933dc8351229c1e66f5eb909da2db99e34",
    "2636a41ddd2f5cc3c9ee4efc522acc891b36068b67c1839593a1336c155497e8",
    "5d798d5a45e522db623a4d22b618e1e674905aa46da95acba6733a51f9d63a9d",
    "df6daef7e33c0032179c462f25afdc9af8883d2677c3d34c98b735039c0ad3e0",
})
# Exact SHA-256 identity of the mechanical role-registry document emitted by
# the first registry generator.  This is historical install metadata captured
# from immutable commit b1d517f (blob 9c410a4d2af5d3780f4b415429227150d08626bd),
# not an ownership claim derived from the current registry.
_KNOWN_GENERATED_ROLE_REGISTRY_DOC_HASHES = frozenset({
    "b55b370ac265e4802f19d4034b234d8725437ade2e286eb52d1f0c4142a04e91",
})
# Exact managed spans from immutable repository revisions that carried the
# renderer equality test. A marker alone never establishes generated ownership.
# 3485ec4 is the predecessor release, not the candidate's generated output.
_KNOWN_GENERATED_MANAGED_INSTRUCTION_HASHES = frozenset({
    "d249d418ccf38ca3f159065715c3930d492682e93402025d067e99e2225b91fd",  # 3485ec4
    "1b1cb7331dddc504a0908af91e32fba2b72cced74af1b56007099bb088b36c56",  # a33db5b
    "c0072af2e11ee5ed315712c301a33c39a993af13d6243816b319700b432ef2ed",  # 729809f
    "0238e56f242ca68c31d8b63c6d34ffcecc88ace6e245cad986ca3bd1c21e78d2",  # 3ae1b21
    "66c1ac81e010fba307cb579b519142124ddca128e028890f48c7e33f8fac6a11",  # 8eb1707
    "bc47c81d7004bc8a4095cc5d9079068af9ca3d2804a5a557d17a5abaf371f494",  # f316910
    "943c67bb7683785403429063bec0a0174119e8c2dbbe70f6684b8c46d1434c0b",  # e02b953
})
_KNOWN_HOST_WAIT_CAPABILITIES = {
    # These are release-pinned observations, not a cross-version assumption.
    "0.153.4": {"min": 10_000, "default": 30_000, "max": 3_600_000, "explicit_timeout_supported": True, "native_completion_reenters_root": "UNSUPPORTED"},
    "0.154.0": {"min": 10_000, "default": 30_000, "max": 3_600_000, "explicit_timeout_supported": True, "native_completion_reenters_root": "UNSUPPORTED"},
    "0.155.1": {"min": 10_000, "default": 30_000, "max": 3_600_000, "explicit_timeout_supported": True, "native_completion_reenters_root": "UNSUPPORTED"},
    # Exact source verification confirms explicit wait_agent timeout support
    # on this prerelease.  Its live child-completion behavior remains unknown.
    "0.155.0-alpha.9.2": {"min": 10_000, "default": 30_000, "max": 3_600_000, "explicit_timeout_supported": True, "native_completion_reenters_root": "UNKNOWN"},
}


def _agent_profile(name: str, role: str, model: str, effort: str) -> bytes:
    # JSON string escaping is compatible with TOML basic strings; native
    # isolation instructions contain quotes that must not terminate the value.
    spec = roles.get_role(role)
    binding = roles.get_codex_binding(role)
    if spec is None or binding is None or not binding.generated_profile:
        raise ValueError(f"unknown generated role: {role}")
    instructions = spec.instructions
    return (
        f'name = "{name}"\n'
        f'description = "Thaliris {role} execution role"\n'
        f'model = "{model}"\n'
        f'model_reasoning_effort = "{effort}"\n'
        + f'developer_instructions = {json.dumps(instructions, ensure_ascii=False)}\n'
    ).encode("utf-8")


def _agent_profile_state(value: bytes, name: str) -> str:
    profile = _agent_profiles().get(name)
    if profile is None:
        return "user"
    expected = _agent_profile(name.removesuffix(".toml"), profile[2], profile[0], profile[1])
    if value == expected:
        return "current"
    hashes = _KNOWN_GENERATED_AGENT_PROFILE_HASHES.get(name, frozenset())
    binding = roles.get_codex_binding(profile[2])
    if binding is not None and binding.profile_filename == name:
        hashes |= binding.legacy_profile_hashes
    return "legacy" if hashlib.sha256(value).hexdigest() in hashes else "user"


def _host_profile_definition_present(codex_home: Path | None = None) -> str:
    """Report exact generated role definitions in the effective Host directory."""
    home = _codex_home(codex_home)
    agents = home / "agents"
    if home.is_symlink() or agents.is_symlink() or not agents.is_dir():
        return "NO"
    try:
        return "YES" if all(
            not (agents / name).is_symlink()
            and (agents / name).is_file()
            and _agent_profile_state((agents / name).read_bytes(), name) == "current"
            for name in _agent_profiles()
        ) else "NO"
    except OSError:
        return "UNKNOWN"


def _project_local_profile_files_present(root: Path) -> str:
    """Report only whether known Thaliris profile filenames exist in this project."""
    agents = root / ".codex" / "agents"
    if agents.is_symlink() or not agents.is_dir():
        return "NO"
    return "YES" if any(
        not (agents / name).is_symlink() and (agents / name).is_file()
        for name in _agent_profiles()
    ) else "NO"


def _project_activation_marker_present(root: Path) -> str:
    marker = core._safe(root, PROJECT_ACTIVATION_MARKER.replace("\\", "/"))
    if marker.is_symlink() or not marker.is_file():
        return "NO"
    try:
        return "YES" if marker.read_bytes() == _PROJECT_ACTIVATION_BYTES else "NO"
    except OSError:
        return "UNKNOWN"


def role_profile_inventory(root: Path) -> dict[str, str]:
    """Report generated profile states keyed by registry-owned filenames."""
    root = core._repo_root(root)
    agents = root / ".codex" / "agents"
    if agents.is_symlink() or not agents.is_dir():
        return {name: "missing" for name in _agent_profiles()}
    return {
        name: (
            _agent_profile_state((agents / name).read_bytes(), name)
            if (agents / name).is_file() and not (agents / name).is_symlink()
            else "missing"
        )
        for name in _agent_profiles()
    }


def _activation_fields(
    root: Path,
    profile_native_active: str = "UNKNOWN",
    project_layer_activation: str = "UNKNOWN",
    compatible_profile_observed: str = "UNKNOWN",
    host_hook_runtime_observed: str = "UNKNOWN",
) -> dict[str, str]:
    return {
        "host_profile_definition_present": _host_profile_definition_present(),
        "project_local_profile_files_present": _project_local_profile_files_present(root),
        "project_activation_marker_present": _project_activation_marker_present(root),
        "profile_native_active": profile_native_active,
        "host_role_catalog_status": lifecycle.HOST_ROLE_CATALOG_UNKNOWN,
        "project_layer_activation": project_layer_activation,
        "compatible_profile_observed": compatible_profile_observed,
        "host_hook_runtime_observed": host_hook_runtime_observed,
    }


def _project_definition_facts(root: Path) -> dict[str, str]:
    """Return explicit adapter-owned facts used by the startup contract."""
    root = core._repo_root(root)
    instruction = _effective_root_instruction_path(root)
    instruction_present = "NO"
    if instruction.is_file():
        try:
            current = _read_text(instruction)
            span = _managed_span(current, instruction.name)
            if span is not None:
                start, end = span
                # Only the adapter-owned span participates in definition
                # validity. User-owned text may use different line endings;
                # normalize the owned block before comparing it to the
                # canonical LF-rendered definition.
                expected = _normalize_line_endings(render_managed()).removesuffix("\n")
                instruction_present = "YES" if _normalize_line_endings(current[start:end]) == expected else "NO"
        except (OSError, UnicodeError, ValueError):
            instruction_present = "NO"
    activation = _project_activation_marker_present(root)
    host_hooks = lifecycle.host_hooks_health(_codex_home())
    # Host integration is installed once in CODEX_HOME before a session.
    # Project init adds only the marker that lets its stable trampoline enter
    # the current executable on subsequent tool events in that same session.
    initialized = "YES" if instruction_present == "YES" and activation == "YES" else "NO"
    return {
        "project_definition_present": initialized,
        "instruction_definition_present": instruction_present,
        "project_activation_marker_present": activation,
        "project_local_profile_files_present": _project_local_profile_files_present(root),
        "host_profile_definition_present": _host_profile_definition_present(),
        "host_role_catalog_status": lifecycle.HOST_ROLE_CATALOG_UNKNOWN,
        "host_hook_registration_present": host_hooks["hooks_configured"],
        "legacy_project_hook_registration_present": lifecycle.legacy_project_hook_registration_present(root),
    }


def semantic_role(runtime_role: str) -> str:
    if runtime_role in _role_choices():
        return runtime_role
    raise ValueError(f"unknown Thaliris role: {runtime_role}")


def controller_actor(runtime_role: str) -> str:
    """Authorize a Controller-only adapter operation and return its marker."""
    actor = semantic_role(runtime_role)
    if actor != "controller":
        raise ValueError("only Controller may perform this operation")
    return actor


@lru_cache(maxsize=8)
def _host_wait_mode_cached(runner: str) -> dict[str, object]:
    """Return a conservative, version-bound wait capability for this host."""
    try:
        completed = subprocess.run([runner, "--version"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return {"status": "UNSUPPORTED", "version": "UNKNOWN", "reason": "Codex executable is unavailable"}
    # A capability pin is useful only when the executable identifies itself
    # with its complete exact version, including any prerelease suffix.  The
    # lookup below never promotes an unpinned suffix from its numeric prefix.
    match = re.fullmatch(
        r"(?:codex(?:-cli)?\s+)?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)",
        ((completed.stdout or "") + (completed.stderr or "")).strip(),
        flags=re.IGNORECASE,
    )
    if completed.returncode != 0 or match is None:
        return {"status": "UNSUPPORTED", "version": "UNKNOWN", "reason": "Codex version could not be determined"}
    version = match.group(1)
    capability = _KNOWN_HOST_WAIT_CAPABILITIES.get(version)
    if capability is None:
        return {"status": "UNSUPPORTED", "version": version, "reason": "no version-pinned wait capability is recorded for this Codex host"}
    return {"status": "PASS", "version": version, **capability}


def host_wait_mode(executable: str | None = None) -> dict[str, object]:
    return dict(_host_wait_mode_cached(executable or os.environ.get("THALIRIS_CODEX_EXECUTABLE") or "codex"))


def host_explicit_blocking_wait(executable: str | None = None) -> dict[str, object]:
    """Return version-pinned support for an explicit, bounded native wait.

    Release defaults and hard ceilings do not prove the active turn's
    effective maximum. The Host does not currently expose that maximum bound
    to the current session, so report it as unavailable until it does.
    """
    host = host_wait_mode(executable)
    if host.get("status") != "PASS":
        status = "UNSUPPORTED" if host.get("version") == "UNKNOWN" else "UNKNOWN"
        return {"status": status, "host": host}
    if host.get("explicit_timeout_supported") is not True:
        return {"status": "UNSUPPORTED", "host": host}
    return {
        "status": "PASS",
        "version": host["version"],
        "min_wait_timeout_ms": host["min"],
        "default_wait_timeout_ms": host["default"],
        # The exact release pin supplies a hard ceiling only. A configurable
        # per-turn effective maximum is not exposed by the current Host hook.
        "release_hard_max_wait_timeout_ms": host["max"],
        "effective_max_wait_timeout_ms": "UNAVAILABLE",
        "explicit_timeout_supported": True,
    }


def native_child_completion_reenters_root(executable: str | None = None) -> str:
    """Return only PASS, UNSUPPORTED, or UNKNOWN for native re-entry."""
    capability = host_wait_mode(executable)
    result = capability.get("native_completion_reenters_root")
    return result if result in {"PASS", "UNSUPPORTED", "UNKNOWN"} else "UNKNOWN"


def selected_continuation_mode(root: Path, executable: str | None = None) -> str:
    continuation = native_child_completion_reenters_root(executable)
    if continuation == "PASS":
        return "EVENT_DRIVEN"
    if host_explicit_blocking_wait(executable).get("status") == "PASS":
        return "BLOCKING_WAIT"
    return "UNAVAILABLE"


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _normalize_line_endings(value: str) -> str:
    """Normalize all newline spellings for owned-block comparisons."""
    return value.replace("\r\n", "\n").replace("\r", "\n")

MANAGED_START = "<!-- thaliris:begin -->"
MANAGED_END = "<!-- thaliris:end -->"
GLOBAL_MANAGED_START = b"<!-- thaliris:global:begin -->"
GLOBAL_MANAGED_END = b"<!-- thaliris:global:end -->"
AUDIT_IGNORE_START = "# thaliris-codex:begin"
AUDIT_IGNORE_END = "# thaliris-codex:end"
AUDIT_IGNORE_RULE = ".context/audit/"


def _native_role_labels() -> list[str]:
    """Return display labels from the canonical role query boundary."""
    labels: list[str] = []
    for role in roles.role_choices():
        spec = roles.get_role(role)
        binding = roles.get_codex_binding(role)
        if spec is not None and binding is not None and binding.native_profile is not None:
            labels.append(spec.id.replace("-", " ").title())
    return labels


def _native_role_names_text(*, final_conjunction: str = "and", with_article: bool = False) -> str:
    # Compatibility prose: Fresh Investigator, Curator, Reasoning Specialist, Implementer, Verifier, and Reviewer sessions use values from this query boundary.
    labels = _native_role_labels()
    if not labels:
        return "no named roles"
    if len(labels) == 1:
        text = labels[0]
    elif len(labels) == 2:
        text = f"{labels[0]} {final_conjunction} {labels[1]}"
    else:
        text = ", ".join(labels[:-1]) + f", {final_conjunction} " + labels[-1]
    if with_article:
        article = "an" if labels[0][0].lower() in "aeiou" else "a"
        return f"{article} {text}"
    return text


def _controller_model() -> str:
    binding = roles.get_codex_binding("controller")
    return binding.model if binding is not None and binding.model is not None else "(host/task)"


def _native_profile_facts() -> str:
    """Render native model/reasoning facts without a second role list."""
    entries: list[tuple[str, str, str]] = []
    for role in roles.role_choices():
        spec = roles.get_role(role)
        binding = roles.get_codex_binding(role)
        if spec is None or binding is None or binding.native_profile is None:
            continue
        entries.append((spec.id.replace("-", " ").title(), binding.model or "(host/task)", binding.reasoning_effort or "(host/task)"))
    rendered = [f"{label} (`{model}`, `{effort}`)" for label, model, effort in entries]
    if not rendered:
        return "The native child profiles are not configured."
    if len(rendered) == 1:
        return f"The native child profiles are {rendered[0]}."
    if len(rendered) == 2:
        return f"The native child profiles are {rendered[0]} and {rendered[1]}."
    return f"The native child profiles are {', '.join(rendered[:-1])}, and {rendered[-1]}."


def render_managed() -> str:
    """Render marker-owned instructions from the current role registry."""
    return _render_managed()


def _controller_bridge() -> dict[str, str]:
    """Give Controller the exact managed text to acknowledge in this session.

    A CLI result cannot promote text to Host developer instruction authority.
    The digest is an explicit Controller receipt bound to a one-shot hook
    attestation; Host instruction activation remains unproved.
    """
    content = render_managed()
    return {
        "controller_bridge_content": content,
        "controller_bridge_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "host_instruction_activation": "UNKNOWN",
    }

def _render_managed() -> str:
    return f"""{MANAGED_START}
## Thaliris Router

Codex is the runtime. Thaliris provides durable records, identities, revisions,
hashes, provenance, objective freshness observations, explicit retrieval, and
native lifecycle binding. It is not a semantic decision engine.

The Controller is the sole task-specific semantic router. For every task,
whether ACTIVE or degraded, it selects the minimum necessary fresh roles.
Roles are capabilities, not mandatory workflow stages. A straightforward,
bounded, low-risk task with confirmed facts may follow Controller -> fresh
Implementer -> done. That Implementer may perform the bounded local reading,
implementation, and deterministic verification needed to complete the task.
For divisible work, the Controller chooses bounded semantic slices instead of
handing an entire multi-slice stage to a higher-capability Executor. Define
slice boundaries by semantic dependencies, decision coupling, implementation
uncertainty, and independent closure, not by token, file, or task-count
thresholds. Prefer slices that can each be independently understood,
implemented, verified, committed, and closed. A completed slice returns
distilled state, its commit reference, and verification evidence; discard its
working set when closed.
Make each Executor handoff decision-complete enough to close one semantic slice
without routine Controller steering. Do not keep an Executor as a long-lived
interactive workspace. If new decision-changing information invalidates the
slice, let the child close with distilled state and create a fresh correction
slice. `send_message` remains available for genuinely new decision-changing
information.
Use Investigator/Scanner for missing facts, large working sets, broad scans,
and factual compression, without transferring architecture decisions. Use a Reviewer only when independent semantic review adds real
value; it is not a default gate. Curator and Reasoning Specialist remain
optional and are selected only when they add actual value.
At task end, make one short semantic judgment about knowledge that could
change a future decision. Select a fresh Curator only when that knowledge
needs durable maintenance; pass a concise selected handoff. Do not turn
every task result into memory. Keep detailed evidence in Artifacts, Git,
or rollout records. Executors synchronize formal project documentation for
behavior changed within their slice; Reviewer challenges semantic drift when selected.

When Thaliris routing, roles, bootstrap, trust boundaries, or Controller
contracts change, check and synchronize both the repository-managed
instruction and the currently effective Codex global instruction.

Fresh {_native_role_names_text()} sessions use `fork_turns="none"`
and receive their tasks plus selected information in
their authorized parent's native spawn message. `SubagentStart` validates authorization,
identity, role, and session and binds lifecycle metadata; it never calls Core to
construct or inject task context. Task state, memory, milestones, prior reviews,
and Artifact bodies never enter {_native_role_names_text(final_conjunction="or", with_article=True)} automatically.
Child sessions keep their working set private by default. Do not send ordinary
progress, heartbeat, or partial-completion messages to the parent. Proactively
wake the parent only when completed, blocked and requiring a parent decision, or
when new decision-changing information arrives. Direct `send_message` remains
available for genuine decision-changing information, with no automatic wake
filter.

The persistent root Controller has no fixed model, reasoning effort, or native
profile; Host/user selection applies. {_native_profile_facts()}
Only Controller may explicitly select static Astra medium or xhigh profiles for
Focused Implementer or Reasoning Specialist before spawn for exceptional reasoning.
These fixed profiles retain the same stable role IDs; default profiles remain
on Luna or Sol. Per-spawn model/effort overrides are denied;
role sessions never select their own model or effort.
Choose the model per handoff and semantic slice difficulty. Deterministic
documentation, test, configuration, or reference cleanup and small defined
implementations default to standard Implementer on Luna, even within a large
project. Use Focused Implementer on Sol only when the current slice itself
requires complex lifecycle, ownership, compatibility, or multi-option reasoning.
Use Reasoning Specialist on Sol only when problem framing or slice decomposition
is unclear; it does not implement. Astra is an escalation for an already small,
unusually demanding slice or an evidenced Sol failure. Astra medium is the
default escalation; xhigh requires a clear reason.
Implementer and Focused Implementer both execute implementation work. Reasoning
Specialist reframes ill-defined problems; ordinary design and implementation
remain with the Executors. Verifier is retained read-only for compatibility
and is not recommended as a workflow stage.

Keep the working set focused. Delegate broad repository scanning, exhaustive
call-site search, residual-reference checks, and other large mechanical
investigation to the Scanner. Use Scanner output as evidence; retain
responsibility for implementation decisions.
Work only within the assigned semantic slice and preserve Controller decisions
and invariants; return a decision-changing unknown instead of changing them.
Controller may spawn registered roles. Implementer, Focused Implementer, and
Reviewer may each spawn only a fresh Investigator/Scanner. Investigator,
Reasoning Specialist, Curator, and Verifier cannot delegate. Maximum managed
depth is two: one Controller-direct child and its one Scanner, never siblings.
Scanner results belong to their requesting Executor/Reviewer.

An implementation handoff states Goal, confirmed facts, hard invariants,
Controller-decided boundaries/contracts, decision-changing unknowns,
non-binding recommendations/advice, and acceptance. Decisions, invariants, and
acceptance are contract; recommendations/advice are not. An unknown that can
change direction cannot be silently dropped, guessed, or frozen: prove Host
protocol, serialization, identity, and native-schema contracts first.

Before another correction packet, distinguish a local implementation defect
from a decision-basis failure. If review overturns an accepted invariant,
depends on an unverified external capability, makes feasibility uncertain, or
changes a Controller boundary or contract, reopen the Controller decision. If
facts are missing, route to a fresh Investigator; if relevant facts are known
but the problem needs reframing, route to a fresh Reasoning
Specialist; if the accepted design is unchanged and the defect is local, route
to a fresh Implementer correction. Reasoning Specialist is not for fact
gathering, implementation, or routine review, and difficulty alone is
insufficient when the Controller can decide confidently from established facts.
Do not use counters, thresholds, risk scores, classifiers, or a state machine
for this routing.
Semantic uncertainty that can change a decision routes to Investigator;
broad grep, exhaustive residual references, and call-site scans route to a
Scanner under an Executor or Reviewer.
Reviewer challenges a converged implementation slice; do not start it against
a still-mutating Executor to obtain parallel progress. Findings return to the
Controller, which decides whether a fresh correction slice is needed.

Each {_native_role_names_text()} keeps
its private working set private. By default it returns a distilled conclusion, key findings,
decision-changing unknowns or contradictions, verification performed, and
optional Artifact pointers. Detailed reusable material may be saved in a
repo-relative Artifact. The Controller decides whether to register or retrieve
it and whether any selected content belongs in a later handoff. Artifact
registration stores address, producer, revision, hash, provenance, and optional
supersession only; it does not interpret the body.

Memory and milestones are ordinary explicit storage. Search results are ordinary explicit inputs.
Status is a bounded mechanical record label. Legacy durable Markdown Status metadata remains readable
as opaque compatibility data, never routing authority. Freshness reports only FRESH, PARTIAL, RECORDED, CHANGED, MISSING, or
UNKNOWN mechanical facts. `.agent-memory/INDEX.md` and
`.milestones/INDEX.md` are model-maintained thin global maps of the durable
tree; Core does not reconstruct a second catalog by recursively scanning the
filesystem or impose a taxonomy. SessionStart only points to these maps; before
`task-start`, the Controller explicitly reads the root navigation, and if a map
is missing it establishes a minimal thin INDEX first. During an active task,
navigation is not reread automatically; the Controller may reread it when the
map changed, is insufficient, freshness is invalid, or work is resumed after
compaction. The Controller explicitly uses `catalog` or
`document-get` to retrieve selected durable material. A single bounded
`document-get` may name up to eight explicit paths; it never searches, ranks,
or supplements the selection.
`CHANGED` records an evidence change, not semantic invalidation. When a
decision depends on changed evidence and is no longer reliable, the Controller
may request revalidation. A selected Curator maintains a small, current,
non-conflicting, traceable corpus and its relevant index links by modifying,
merging, splitting, superseding, or deleting entries. It does not scan the
whole corpus or decide architecture.
When a promotion changes durable navigation, the Controller should include its
own optional `index_update` in the same `task-promote` call. Core does not
generate INDEX content; it validates the CAS, references, and atomic commit.

With NO_TASK, Thaliris leaves ordinary Codex tool use and spawn behavior
transparent. During an ACTIVE managed task the persistent Controller uses only
native spawn/wait/list/interrupt operations and an explicit allow-set of
trusted direct `thaliris` runtime commands. `init`, `codex-install`, `uninstall`, `rollback`, a
second `task-start`, and `task-show` are blocked for ACTIVE Root. `task-status`
is bounded; `task-get`, `artifact-get`, `catalog`, and `document-get`
retrieve explicitly selected objects.
With INVALID_STATE, the PreToolUse guard denies only mechanically recognized
Controller-owned state mutations: direct Thaliris task/lifecycle mutations and
obvious writes targeting `.context/state.json` or lifecycle state. Other
tools, including unknown tool names, coordination, diagnostics, and reads,
remain transparent. This hook behavior does not establish managed enforcement.
If `task-start` was attempted but managed enforcement is unavailable or
rejected, label the run unmanaged/degraded. Diagnose only the bootstrap cause:
Codex version, host capability, task schema, git/worktree identity,
hook/profile presence, and the `task-start` error are allowed reads. Use only
the direct canonical `thaliris` command or an absolute executable with an
explicit exact SHA-256 pin; never recommend or use a shell-wrapper fallback.
If neither trusted direct route is available, check canonical availability, the
explicit executable SHA-256 pin, and hook/install state, then report bootstrap
unavailable. Once the cause is known, do not read user-task repository source,
tests, docs, or search results. If work continues, apply the same minimum-role
routing policy defined above; degraded mode does not define a separate role
sequence. The Controller must not take over repository investigation,
implementation, or testing merely because NO_TASK applies. Damaged managed
state also does not transfer a child's semantic duties to Root. If an
Investigator or Implementer is unavailable, the Controller
may diagnose the managed failure, read only the evidence needed for that
diagnosis, coordinate, and report; it must not take over their substantial
repository investigation, implementation, or testing. Do not add a
mechanical Root-investigation detector. The final report must not claim
managed enforcement was verified.
If Codex reports a native spawn failure before `SubagentStart`, the Controller
may explicitly run `thaliris recover-pending-spawn <handoff-id>` for that exact
reservation. Core never infers failure from a missing event, timeout, or retry.
Decision-changing investigation belongs to Investigator. Bounded local reading
needed for implementation may stay inside either Executor. Execution, mutation,
and testing belong to fresh Implementer or Focused Implementer sessions. Existing native Codex child sessions are never resumed with follow-up/send tools.
An Investigator's or Executor's obvious direct control-context retrieval is allowed and recorded.
Investigator and Executor reads remain telemetry-only; Curator, Reasoning
Specialist, and Reviewer extra reads produce at most one bounded aggregate
Controller notice per pending batch. Obvious attempts to mutate
Controller-owned task or lifecycle state are denied, recorded, and included in
that aggregate notice. Reviewer independence is a
developer-instruction plus obvious-write hook guard, not a claimed native
read-only sandbox. Starting managed mode requires a current-session,
current-hook, one-shot PreToolUse attestation.

Managed native Codex child lifecycles permit one top-level child and one nested
Scanner. Nested authorization requires the exact bound parent's agent, role,
session, and turn identity; missing or conflicting identity fails closed.
SubagentStart consumes the unique reservation and binds the Scanner's own
identity. One live managed Codex CLI `0.155.0-alpha.9.2` probe on 2026-09-25
verified the exact reservation, SubagentStart, and bound Scanner PreToolUse
acceptance at depth two. The Scanner result returned and the Focused
Implementer parent continued. See the [durable probe evidence](docs/codex-nested-scanner-live-20260925.md).
This is evidence for that one CLI build and probe only. Raw Host wire-byte
equality, other Host builds or Desktop scenarios, and native child
`Completed`/`task-close` completion were not observed and remain UNKNOWN.
The identity binding and fail-closed mechanics above are unchanged.
Spawn authorization, native identity binding,
SubagentStart/Stop, missing-stop reconciliation, and explicit blocking waits are
mechanical. SubagentStop alone is not success; only an explicitly observed
native Completed status can satisfy lifecycle completion. When blocked on an
authorized managed child, use one blocking `wait_agent` call with `timeout_ms`
equal to the maximum advertised in the current turn's `wait_agent` tool
definition. The current turn's tool definition is the authority; never infer a
maximum from release defaults, configuration, history, or capability tables.
If that blocking wait returns early, continue only when it delivered new,
decision-changing information; otherwise resume the same wait without
re-reasoning. Do not periodically wake the Controller to poll. If no usable
current maximum is advertised, do not invent one.
Task closure requires the last
Controller-direct handoff's completed lifecycle and no pending or active
descendants; a later Scanner does not replace that top-level completion.
The Controller interprets {_native_role_names_text()} results,
verification observations, review findings, and task surface deltas and decides
the next handoff and when work is complete.

Startup contract: install Host integration once before sessions that use
Thaliris roles. `thaliris codex-install` places stable role identities and the
stable hook ABI trampoline under `CODEX_HOME`; it merges user hooks and keeps
project data out of the user layer. It uses the official Codex app-server
`hooks/list` and `config/batchWrite` path to trust only the seven exact
Thaliris handlers with Host-returned keys and current hashes; it never
calculates those identities locally or changes existing `enabled` state.
`host_hook_trust_status` and its counts report saved Host config, not what a
running session loaded. A changed Host installation is a disk fact until a
later session loads it. For each repository, project readiness
requires the managed Thaliris block in the effective root instruction and the
static `.codex/thaliris.json` activation marker. If either is absent, invoke
`thaliris --root <repo> init` directly, or invoke the absolute executable
named by the host's exact SHA-256 pin. Project `init` does not install Host
roles or Host hooks and does not require a session restart. Read the `init`
JSON result.
Read the canonical managed text and SHA-256 returned by `init` or
`bootstrap-check`. Explicitly acknowledge that digest with
`--controller-bridge-sha256` when calling `task-start`; the loaded current-ABI
PreToolUse hook binds that receipt to its session attestation. This is
Controller activation only: CLI output does not become Host developer
instruction, and Host instruction activation remains UNKNOWN. The stable Host
trampoline checks only the activation marker before dispatching into the
current executable; an inactive repository skips Thaliris Python and state
access. A registration on disk does not prove the current session loaded it.
SessionStart's role filename snapshot is disk presence evidence only. Without
a Host-native catalog signal, catalog status remains
`HOST_ROLE_CATALOG_UNKNOWN`; if a new role filename appears after the startup
snapshot, admission fails closed with `NEW_ROLE_CATALOG_IDENTITY_NOT_ACTIVE`.
Existing catalogued profile content updates by filename do not imply a restart.
If neither trusted
direct route is available, report bootstrap unavailable and do not continue.
If all facts are present, read `.agent-memory/INDEX.md` and
`.milestones/INDEX.md` (creating only a minimal missing map as instructed),
then proceed to normal managed startup.
{MANAGED_END}
"""


MANAGED = _render_managed()

def render_role_packs() -> str:
    """Render the role-pack document with current registry facts."""
    return _render_role_packs()


def _render_role_packs() -> str:
    return f"""<!-- thaliris-role-packs:v5 -->
# Thaliris Role Profiles

These profiles are working-style defaults, not routing rules or semantic
permissions. The authorized parent's explicit native spawn message is the sole
task-specific input to every {_native_role_names_text()}.

## Role Defaults

The persistent root Controller has no fixed model, effort, or native profile;
Host/user selection applies. {_native_profile_facts()}
Only Controller may select static Astra medium or xhigh profiles for Focused
Implementer or Reasoning Specialist before spawn for exceptional reasoning.
These fixed profiles map to the same stable roles; defaults remain on Luna or
Sol. Per-spawn model/effort overrides are denied. Role sessions never
override their own model or effort.

## Shared Role Result

Return a distilled result by default:

- Conclusion
- Key findings
- Decision-changing unknowns
- Contradictions, if any
- Verification performed
- Artifact refs, if detailed reusable material was retained

Keep repository reads, tool output, test logs, and intermediate exploration in
the role session's private working set. Do not copy an Artifact body into the result
unless the Controller explicitly requested that content.
Child sessions do not send ordinary progress, heartbeat, or partial-completion
messages. They proactively wake the parent only when completed, blocked and
requiring a parent decision, or when new decision-changing information arrives.
Direct `send_message` to the exact bound parent remains available for genuine
decision-changing information, with no automatic wake filter. Follow-up and
input tools remain denied for managed children.

## Investigator

Investigator/Scanner handles missing facts, broad scans, large working sets,
and factual compression, not architecture decisions. It cannot delegate.
Investigate the task in the handoff. Save detailed reusable evidence as
an optional repo-relative Artifact and return its pointer with a short result.

## Curator

Use only when the Controller identifies genuinely reusable knowledge and
explicitly supplies the material to curate. Do not automatically summarize a
task, select a next role, or route a result. Curator output is an ordinary
result or Artifact; Core has no Curator state machine.

Maintain only selected documents and their relevant index links. Keep the
corpus small, current, non-conflicting, and traceable: modify, merge, split,
supersede, or delete entries as evidence warrants. Do not scan the whole
corpus or decide architecture. Memory holds concise future decision-changing
conclusions; detailed evidence belongs in Artifacts, Git, or rollout records.

## Durable knowledge loop

At task start, the Controller reads the root INDEX map and then makes an exact
`document-get` request for the selected linked entries. At task end it makes
one short semantic judgment: whether a concise conclusion could change a
future decision and needs durable maintenance. A fresh Curator is selected
only when useful, never as an automatic step. `CHANGED` is an evidence change,
not semantic invalidation; the Controller may request revalidation when a
decision depends on changed evidence and has become unreliable. If the
Controller promotes a selected record that changes durable navigation, it
supplies the model-authored INDEX CAS update in that
same promotion. Otherwise it leaves INDEX bytes unchanged. A fresh later task
recovers only by reading INDEX and exact selected documents, not by broad
reinvention or recursive scanning.

## Reasoning Specialist

Use to reframe an ill-defined problem, not for ordinary design or implementation.
Resolve it from the selected information. Do not delegate. If a
decision-changing fact is missing, say what is missing. Do not reconstruct
unselected task history.

## Implementer and Focused Implementer

Both are Executors. Implementer is the general implementation role; Focused
Implementer handles concentrated reasoning and implementation with a focused
working set. Keep the working set focused. Delegate broad repository scanning,
exhaustive call-site search, residual-reference checks, and other large mechanical
investigation to the Scanner. Use Scanner output as evidence; retain responsibility
for implementation decisions. Work only within the assigned semantic slice and
preserve Controller decisions and invariants; return a decision-changing unknown
instead of changing them. Delegate only to Investigator with `fork_turns="none"`.
Synchronize formal project documentation for behavior changed within the
assigned slice and report any documentation boundary that needs a Controller
decision.

Focused Implementer uses only bounded local reading needed for semantic judgment
within the assigned slice. Preferentially delegate broad repository scanning,
exhaustive search, rollout/log scans, call-site enumeration, residual checks, and
large mechanical evidence collection to a fresh Investigator/Scanner. Use its
evidence while retaining responsibility for the focused implementation decision.
Do not routinely perform those broad collections yourself merely because you can.

The Controller chooses the model per handoff and semantic slice difficulty.
Deterministic documentation, test, configuration, or reference cleanup and
small defined implementations default to standard Implementer on Luna,
including slices inside a large project. Focused Implementer on Sol handles
only a current slice that requires complex lifecycle, ownership, compatibility,
or multi-option reasoning.
Reasoning Specialist on Sol is for unclear problem framing or slice decomposition
and does not implement. Astra is an escalation for an already small, unusually
demanding slice or an evidenced Sol failure; medium is the default escalation,
and xhigh requires a clear reason. After implementation, close the slice with
distilled state, its commit reference, and verification evidence, then discard
its detailed working set.

An implementation task packet contains Goal, confirmed facts, hard invariants,
Controller-decided boundaries/contracts, decision-changing unknowns,
non-binding recommendations/advice, and acceptance. Only Controller decisions,
invariants, and acceptance are binding; recommendations/advice are not
contract. Do not silently drop, guess, or freeze an unknown that changes
direction. Before implementation, prove Host protocol, serialization, identity,
or native schema through an Investigator, source, or real-shaped fixture.
For a straightforward, bounded task with confirmed facts, perform necessary
bounded local reading, implementation, and deterministic verification in this
fresh session; an Investigator is needed only when missing facts could change
how to implement. Preserve stated constraints and report verification as
observations. Close the assigned slice with distilled state, its commit
reference, and verification evidence, then discard its detailed working set.
If an assigned correction cannot be completed without an
unverified external fact, an invalidating accepted invariant, or changing the
decision basis, do not expand scope; return that dependency as a
decision-changing unknown to the Controller. Do not infer additional task
state from Core.

## Reviewer

Use when the Controller selects independent review because it adds value; it is
not a mechanical post-implementation gate. Independently inspect the candidate
identified in the handoff. Return findings
and a distilled verdict. Reviewer keeps only bounded local reading needed for
semantic judgment of the candidate. Preferentially delegate broad repository
scanning, exhaustive search, rollout/log scans, call-site enumeration, residual
checks, and large mechanical evidence collection to one fresh Investigator/Scanner
with `fork_turns="none"` and no model or effort override. Use its evidence while
retaining independent review responsibility. Do not routinely perform those broad
collections yourself merely because you can.
After finding a real problem, understand its invariant
and inspect adjacent legal states enough to return independent related blockers
in one pass. Challenge semantic drift between the candidate and its formal
project documentation when relevant. Finding classifications are model-authored
labels; the Controller
decides what workflow, if any, follows.

## Verifier

The Verifier is a read-only compatibility role, not recommended as a workflow
stage and never mandatory. It cannot delegate. After an Executor, check
acceptance coverage, the Controller-decided Modification Boundary,
source/generated/docs synchronization, call sites and residual references,
actual deterministic or focused test results, migration and compatibility
fixtures, generated versus user-owned ownership, lifecycle or protocol
inconsistencies, contradictions, decision-changing unknowns, and workspace
anomalies. Treat a workspace anomaly as an observation, not a candidate defect,
unless the candidate introduced it, the modification boundary owns it, or
acceptance requires changing it. Historical/generated ownership must come from
exact independent historical evidence; current HEAD must not establish its own
historical authority. A clean, low-risk task may finish without independent review.
Verifier does not replace independent
review when authority, provenance, Host lifecycle, identity, trust, migration,
or bootstrap semantics still warrant independent challenge. Model prose may describe READY,
LOCAL_DEFECTS, or DECISION_REOPEN; the Controller owns routing. LOCAL_DEFECTS
return through a fresh Executor. DECISION_REOPEN returns to the
Controller, then to Investigator or Reasoning Specialist as appropriate.

## Bounded delegation and Host evidence

Controller delegates registered roles. Only Implementer, Focused Implementer,
and Reviewer may delegate an Investigator/Scanner, at maximum depth two.
There is one active top-level child and at most one nested Scanner. Results
return to the requesting parent; no automatic result or Artifact propagation
is introduced. Exact parent agent/session/turn/role identity authorizes the
unique reservation; the matching Start binds the Scanner's own identity.
Missing or conflicting fields deny execution. Direct-child hook wire shapes
have been observed on the CLI. One live managed Codex CLI
`0.155.0-alpha.9.2` probe verified the exact reservation, `Start`, and bound
Scanner `PreToolUse` acceptance for a depth-two Scanner; the Scanner result
returned and the Focused parent continued. See the [durable probe evidence](codex-nested-scanner-live-20260925.md).
This scoped probe covers that one CLI build and probe only. Raw Host wire-byte
equality, other Host builds or Desktop scenarios, and native child
`Completed`/`task-close` completion were not observed and remain UNKNOWN.
"""


ROLE_PACKS = _render_role_packs()

# The role-pack document above intentionally remains the hand-maintained
# design/routing explanation. Mechanical role facts have a separate generated
# document so prose changes cannot silently change installation semantics.
ROLE_REGISTRY_DOC = roles.render_registry_document().decode("utf-8")


def _role_registry_document() -> bytes:
    return roles.render_registry_document()


def _role_registry_state(value: bytes) -> str:
    if value == _role_registry_document():
        return "current"
    # Historical generated bytes are recognized by exact independent evidence.
    # This lets registry additions regenerate the mechanical document while
    # still treating arbitrary edits as user-owned.
    return "legacy" if hashlib.sha256(value).hexdigest() in _KNOWN_GENERATED_ROLE_REGISTRY_DOC_HASHES else "user"


def _codex_config() -> dict[str, object]:
    base = Path(os.environ["CODEX_HOME"]) if os.environ.get("CODEX_HOME") else Path.home() / ".codex"
    path = base / "config.toml"
    if not path.is_file():
        return {}
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _fallback_instruction_names(codex_config: dict[str, object] | None = None) -> tuple[str, ...]:
    value = (codex_config or _codex_config()).get("project_doc_fallback_filenames")
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or Path(item).name != item or item in names:
            continue
        names.append(item)
    return tuple(names)


def _root_instruction_candidates(root: Path, codex_config: dict[str, object] | None = None) -> tuple[Path, ...]:
    names = ("AGENTS.override.md", "AGENTS.md", *_fallback_instruction_names(codex_config))
    return tuple(core._safe(root, name) for name in names)


def _effective_root_instruction_path(root: Path, codex_config: dict[str, object] | None = None) -> Path:
    """Match Codex root discovery: first non-empty candidate wins.

    The adapter intentionally manages only the repository-root layer, not the
    full root-to-cwd instruction hierarchy.
    """
    candidates = _root_instruction_candidates(root, codex_config)
    for path in candidates:
        if path.is_file() and _read_text(path).strip():
            return path
    return core._safe(root, "AGENTS.md")


def _strip_managed_agents(current: str) -> str:
    span = _managed_span(current, "AGENTS.md")
    if span is None:
        return current
    start, end = span
    suffix = current[end:]
    if suffix.startswith("\r\n"):
        suffix = suffix[2:]
    elif suffix.startswith("\n"):
        suffix = suffix[1:]
    return current[:start] + suffix


def _managed_span(current: str, label: str) -> tuple[int, int] | None:
    counts = current.count(MANAGED_START), current.count(MANAGED_END)
    if counts == (0, 0):
        return None
    if counts == (1, 1):
        start, end_start = current.index(MANAGED_START), current.index(MANAGED_END)
        end = end_start + len(MANAGED_END)
    else:
        raise ValueError(f"{label} has duplicate or damaged managed markers")
    if start >= end_start:
        raise ValueError(f"{label} has duplicate or damaged managed markers")
    return start, end


def _managed_agents(current: str) -> str:
    span = _managed_span(current, "AGENTS.md")
    if span is not None:
        start, end = span
        expected = _normalize_line_endings(render_managed()).removesuffix("\n")
        if _normalize_line_endings(current[start:end]) == expected:
            # Preserve the complete document when only user-owned content
            # differs (including its line-ending convention).
            return current
        if _managed_agents_state(current) == "user":
            return current
    newline = "\r\n" if "\r\n" in current else "\n"
    block = render_managed().replace("\n", newline)
    user_text = _strip_managed_agents(current) if span is not None else current
    return block if not user_text else block + user_text


def _managed_agents_state(current: str) -> str:
    span = _managed_span(current, "AGENTS.md")
    if span is None:
        return "absent"
    owned = _normalize_line_endings(current[span[0]:span[1]])
    if owned == _normalize_line_endings(render_managed()).removesuffix("\n"):
        return "current"
    return "legacy" if hashlib.sha256(owned.encode("utf-8")).hexdigest() in _KNOWN_GENERATED_MANAGED_INSTRUCTION_HASHES else "user"


def _role_pack_state(value: bytes) -> str:
    if value == render_role_packs().encode("utf-8"):
        return "current"
    return "legacy" if hashlib.sha256(value).hexdigest() in _KNOWN_GENERATED_ROLE_PACK_HASHES else "user"


def _audit_ignore(current: str, *, remove: bool = False) -> str:
    counts = tuple(current.count(marker) for marker in (AUDIT_IGNORE_START, AUDIT_IGNORE_END))
    if counts not in {(0, 0), (1, 1)}:
        raise ValueError(".gitignore has duplicate or damaged Codex managed markers")
    if counts == (0, 0):
        if remove:
            return current
        newline = "\r\n" if "\r\n" in current else "\n"
        block = newline.join((AUDIT_IGNORE_START, AUDIT_IGNORE_RULE, AUDIT_IGNORE_END)) + newline
        return current + ("" if not current or current.endswith(("\n", "\r")) else newline) + block
    start, end_start = current.index(AUDIT_IGNORE_START), current.index(AUDIT_IGNORE_END)
    if start >= end_start:
        raise ValueError(".gitignore has duplicate or damaged Codex managed markers")
    if not remove:
        return current
    end = end_start + len(AUDIT_IGNORE_END)
    suffix = current[end:]
    if suffix.startswith("\r\n"):
        suffix = suffix[2:]
    elif suffix.startswith("\n"):
        suffix = suffix[1:]
    return current[:start] + suffix


def _install_plan(root: Path) -> tuple[dict[str, bytes], list[str]]:
    """Plan Codex-owned files without taking a second lock or backup."""
    root = core._repo_root(root)
    codex_config = _codex_config()
    target_agents = _effective_root_instruction_path(root, codex_config)
    all_agents = _root_instruction_candidates(root, codex_config)
    for instruction in all_agents:
        if instruction.is_file():
            _managed_span(_read_text(instruction), instruction.name)
    ignore = core._safe(root, ".gitignore")
    _audit_ignore(_read_text(ignore) if ignore.is_file() else "")
    writes: dict[str, bytes] = {}
    manual: list[str] = []
    current_agents = _read_text(target_agents) if target_agents.is_file() else ""
    if _managed_agents_state(current_agents) == "user":
        manual.append(target_agents.relative_to(root).as_posix())
    rendered_agents = _managed_agents(current_agents)
    if current_agents != rendered_agents:
        writes[target_agents.relative_to(root).as_posix()] = rendered_agents.encode("utf-8")
    # If an override became active after an earlier install, remove only our
    # now-shadowed block from the inactive root file.
    for instruction in all_agents:
        if instruction == target_agents or not instruction.is_file():
            continue
        current = _read_text(instruction)
        if _managed_agents_state(current) == "user":
            manual.append(instruction.relative_to(root).as_posix())
            continue
        stripped = _strip_managed_agents(current)
        if stripped != current:
            writes[instruction.relative_to(root).as_posix()] = stripped.encode("utf-8")
    role_packs = core._safe(root, "docs/thaliris-role-packs.md")
    if not role_packs.exists():
        writes["docs/thaliris-role-packs.md"] = render_role_packs().encode("utf-8")
    elif _role_pack_state(role_packs.read_bytes()) == "legacy":
        writes["docs/thaliris-role-packs.md"] = render_role_packs().encode("utf-8")
    elif _role_pack_state(role_packs.read_bytes()) == "user":
        manual.append("docs/thaliris-role-packs.md")
    role_registry = core._safe(root, "docs/thaliris-role-registry.md")
    if not role_registry.exists():
        writes["docs/thaliris-role-registry.md"] = _role_registry_document()
    else:
        state = _role_registry_state(role_registry.read_bytes())
        if state == "legacy":
            writes["docs/thaliris-role-registry.md"] = _role_registry_document()
        elif state == "user":
            manual.append("docs/thaliris-role-registry.md")
    # Native role identities belong to the Host's user role catalog.  Project
    # init intentionally leaves any existing project-local profiles alone and
    # never creates new identities in this workspace.
    current_ignore = _read_text(ignore) if ignore.is_file() else ""
    rendered_ignore = _audit_ignore(current_ignore)
    if current_ignore != rendered_ignore:
        writes[".gitignore"] = rendered_ignore.encode("utf-8")
    marker = core._safe(root, PROJECT_ACTIVATION_MARKER.replace("\\", "/"))
    marker_name = marker.relative_to(root).as_posix()
    if marker.is_symlink():
        manual.append(marker_name)
    elif not marker.exists():
        writes[marker_name] = _PROJECT_ACTIVATION_BYTES
    else:
        try:
            if not marker.is_file() or marker.read_bytes() != _PROJECT_ACTIVATION_BYTES:
                manual.append(marker_name)
        except OSError:
            manual.append(marker_name)
    # Project hooks were the old lifecycle registration surface. Remove only
    # exact generated handlers; project init no longer installs or refreshes
    # Host hooks, and user handlers remain byte-for-byte JSON values.
    hooks = core._safe(root, ".codex/hooks.json")
    if hooks.exists():
        if hooks.is_symlink():
            manual.append(".codex/hooks.json")
        else:
            try:
                value = json.loads(_read_text(hooks))
                if not isinstance(value, dict):
                    raise ValueError("hooks root must be an object")
                if lifecycle.legacy_managed_handler_cleanup_required(value):
                    manual.append("legacy_project_hook_manual_cleanup_required")
                    manual.append(".codex/hooks.json")
                    return writes, manual
                merged, changed = remove_hooks(value)
                if changed:
                    writes[".codex/hooks.json"] = (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            except (OSError, ValueError, json.JSONDecodeError):
                manual.append(".codex/hooks.json")
    # The current Host hook does not expose the active turn's effective cap.
    # Preserve native wait arguments unless a future trusted Host contract
    # supplies that session-bound value.
    return writes, manual


def init(root: Path) -> dict[str, object]:
    resolved = core._repo_root(root)
    for instruction in _root_instruction_candidates(resolved):
        if instruction.is_file():
            _managed_span(_read_text(instruction), instruction.name)
    ignore = core._safe(resolved, ".gitignore")
    if ignore.is_file():
        _audit_ignore(_read_text(ignore))
    root = core._repo_root(root)
    generic_files, generic_manual = core._init_plan(root)
    adapter_files, adapter_manual = _install_plan(root)
    # Both layers contribute ignored private paths. Compose the adapter's
    # addition over the Core-rendered .gitignore before the single mutation.
    if ".gitignore" in generic_files:
        adapter_files[".gitignore"] = _audit_ignore(generic_files[".gitignore"].decode("utf-8")).encode("utf-8")
    files = generic_files | adapter_files
    manual = sorted(set(generic_manual) | set(adapter_manual))
    instruction_changed = any(path in {"AGENTS.md", "AGENTS.override.md"} for path in files)
    profile_changed = any(path.startswith(".codex/agents/") for path in files)
    new_profile_names: list[str] = []
    backup = None
    # Apply the generated files under one lock so the mutation is atomic.
    with core._lock(root):
        backup = core._apply_with_backup(root, files, [], "init") if files else None
        hooks = lifecycle.hooks_health(root)
    return {"ok": True, "changed": bool(files), "backup": backup, "files": sorted(files), "manual_action_required": manual, "instruction_definition_changed": instruction_changed, "hook_definition_changed": False, "project_activation_marker_changed": ".codex/thaliris.json" in files, "agent_profile_changed": profile_changed, "new_role_profile_files": new_profile_names, "role_catalog_changed": bool(new_profile_names), "hook_re_attestation_required": False, "managed_hook_abi": lifecycle.MANAGED_HOOK_ABI, "executable_adapter_protocol_version": lifecycle.CODEX_ADAPTER_PROTOCOL_VERSION, "canonical_executable_available": hooks["canonical_executable_available"], "canonical_executable_identity": hooks["canonical_executable_identity"], "session_restart_required": False, "hook_trust_required": False, "host_wait_mode": host_wait_mode(), **_project_definition_facts(root), **_activation_fields(root), **_controller_bridge()}


def _codex_home(codex_home: Path | None = None) -> Path:
    """Resolve the user's Codex home without consulting project state."""
    if codex_home is not None:
        return Path(codex_home).expanduser().absolute()
    configured = os.environ.get("CODEX_HOME")
    return (Path(configured).expanduser() if configured else Path.home() / ".codex").absolute()


def _host_install_executable(
    codex_home: Path,
    executable: str | Path | None,
    executable_sha256: str | None,
) -> tuple[Path | None, str | None, str | None]:
    """Resolve and exercise the direct executable route before installing hooks."""
    if (executable is None) != (executable_sha256 is None):
        return None, None, "host_executable_path_and_sha256_must_be_paired"
    configured = Path(executable).expanduser() if executable is not None else lifecycle._trusted_thaliris_executable()
    if configured is None and executable is None:
        found = shutil.which("thaliris")
        configured = Path(found) if found else None
    if configured is None or not configured.is_absolute() or configured.is_symlink() or not configured.is_file():
        return None, None, "host_executable_unavailable_or_not_absolute"
    try:
        resolved = configured.resolve(strict=True)
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    except (OSError, RuntimeError):
        return None, None, "host_executable_unavailable_or_not_absolute"
    expected = executable_sha256.lower() if isinstance(executable_sha256, str) else digest
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or digest != expected:
        return None, None, "host_executable_sha256_mismatch"
    # A process exit check prevents a stale installed launcher from being
    # embedded in the stable Host trampoline. This exact direct invocation
    # accepts no shell wrapper and runs from a disposable non-Thaliris repo.
    try:
        with tempfile.TemporaryDirectory(prefix="thaliris-host-abi-probe-") as probe_root:
            initialized = subprocess.run(
                ["git", "init", "-q", probe_root],
                capture_output=True,
                timeout=15,
                check=False,
            )
            if initialized.returncode != 0:
                return None, None, "host_executable_current_hook_abi_probe_failed"
            probe = subprocess.run(
                [str(resolved), "audit-hook", "PreToolUse", "--managed-hook-abi", MANAGED_HOOK_ABI],
                input=b"{}",
                cwd=probe_root,
                capture_output=True,
                timeout=15,
                check=False,
            )
    except (OSError, subprocess.SubprocessError):
        return None, None, "host_executable_current_hook_abi_probe_failed"
    if probe.returncode != 0 or probe.stderr:
        return None, None, "host_executable_current_hook_abi_probe_failed"
    if any(character in str(resolved) for character in ('"', "%", "!", "`", "\r", "\n")):
        return None, None, "host_executable_path_not_safe_for_cmd_trampoline"
    return resolved, digest, None


def _atomic_host_write(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", suffix=".thaliris-install-tmp",
            dir=path.parent, delete=False,
        ) as temporary:
            temporary.write(contents)
            temporary_name = temporary.name
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def _global_agents_block(executable: Path | None = None, executable_sha256: str | None = None) -> bytes:
    """Render the user-layer startup contract with an optional installed pin."""
    if (executable is None) != (executable_sha256 is None):
        raise ValueError("global instruction executable and SHA-256 must be paired")
    trusted_route = (
        f"Installed direct executable: `{executable}`\n"
        f"Expected SHA-256: `{executable_sha256}`\n"
        "Check the executable's current SHA-256 against this exact pin before use.\n"
        "Invoke that absolute executable directly for Thaliris commands; a different\n"
        "`thaliris` found on PATH is not evidence that it has the installed ABI.\n"
        if executable is not None else
        "If no trusted direct executable route is available, report bootstrap unavailable.\n"
    )
    return f"""<!-- thaliris:global:begin -->
## Thaliris project startup

For substantive work that creates or changes files in a Git repository,
including a README, unless the user explicitly opts out, check the repository root for
`.codex/thaliris.json` and the effective root AGENTS instruction for the
`<!-- thaliris:begin -->` project block. If readiness is not already confirmed,
run a trusted direct `--root <repo> bootstrap-check` once, including when both
project markers are absent. If it reports either project definition or activation
marker missing, run trusted direct `--root <repo> init` and read its result.
Do not repeat bootstrap for confirmed readiness or run `init` during an ACTIVE
managed task. Chatting, informational questions, read-only work, and non-Git
directories do not call for proactive project bootstrap.

{trusted_route}
Read the canonical managed instruction text and SHA-256 from `init` or
`bootstrap-check`, then acknowledge that digest with
`--controller-bridge-sha256` in `task-start` in the same session. Follow the
effective project instruction for task routing. A CLI result does not prove
Host instruction activation or a loaded current-session hook.
<!-- thaliris:global:end -->
""".encode("utf-8")


def _global_agents_span(current: bytes) -> tuple[int, int] | None:
    """Find one well-formed owned block, including its trailing line break."""
    start_count = current.count(GLOBAL_MANAGED_START)
    end_count = current.count(GLOBAL_MANAGED_END)
    if (start_count, end_count) == (0, 0):
        if b"<!-- thaliris:global:" in current:
            raise ValueError("AGENTS.md has damaged global Thaliris markers")
        return None
    if (start_count, end_count) != (1, 1) or current.count(b"<!-- thaliris:global:") != 2:
        raise ValueError("AGENTS.md has duplicate or damaged global Thaliris markers")
    start = current.index(GLOBAL_MANAGED_START)
    end_marker = current.index(GLOBAL_MANAGED_END)
    end = end_marker + len(GLOBAL_MANAGED_END)
    if start >= end_marker or (start and current[start - 1:start] != b"\n"):
        raise ValueError("AGENTS.md has misplaced global Thaliris markers")
    if current[end:end + 2] == b"\r\n":
        end += 2
    elif current[end:end + 1] == b"\n":
        end += 1
    elif end != len(current):
        raise ValueError("AGENTS.md has misplaced global Thaliris markers")
    return start, end


def _global_agents_update(
    current: bytes, *, remove: bool = False,
    executable: Path | None = None, executable_sha256: str | None = None,
) -> bytes:
    span = _global_agents_span(current)
    # Project-owned markers in the user layer indicate a different ownership
    # claim. Never silently replace or combine it with the global block.
    outside = current if span is None else current[:span[0]] + current[span[1]:]
    if MANAGED_START.encode() in outside or MANAGED_END.encode() in outside:
        raise ValueError("AGENTS.md has conflicting project Thaliris markers")
    if span is None:
        return current if remove else _global_agents_block(executable, executable_sha256) + current
    start, end = span
    return current[:start] + (b"" if remove else _global_agents_block(executable, executable_sha256)) + current[end:]


def _install_host_hook_trust(home: Path, executable: Path, executable_sha256: str) -> dict[str, Any]:
    return codex_app_server.trust_installed_host_hooks(home, executable, executable_sha256)


def _owned_host_hook_commands(data: dict[str, Any], home: Path) -> dict[str, set[str]]:
    commands: dict[str, set[str]] = {event: set() for event in lifecycle.HOOK_EVENTS}
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return commands
    for event in lifecycle.HOOK_EVENTS:
        entries = hooks.get(event)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            handlers = entry.get("hooks") if isinstance(entry, dict) else None
            if not isinstance(handlers, list):
                continue
            for handler in handlers:
                if lifecycle._host_hook_command_is_managed(handler, event, home):
                    command = handler.get("command")
                    if isinstance(command, str):
                        commands[event].add(command)
    return commands


def codex_install(
    codex_home: Path | None = None,
    executable: str | Path | None = None,
    executable_sha256: str | None = None,
) -> dict[str, object]:
    """Install stable Host integration and the global startup instruction."""
    home = _codex_home(codex_home)
    agents = home / "agents"
    global_agents = home / "AGENTS.md"
    hooks_path = home / "hooks.json"
    script_path = home / HOST_HOOK_SCRIPT_NAME
    manual: list[str] = []
    files: list[str] = []
    changed = False

    if home.is_symlink():
        manual.append(str(home))
    if agents.is_symlink() or (agents.exists() and not agents.is_dir()):
        manual.append(str(agents))
    role_writes: list[tuple[Path, bytes]] = []
    if str(agents) not in manual and not home.is_symlink():
        for name, (model, effort, role) in _agent_profiles().items():
            path = agents / name
            rendered = _agent_profile(name.removesuffix(".toml"), role, model, effort)
            if path.is_symlink():
                manual.append(str(path))
                continue
            if not path.exists():
                role_writes.append((path, rendered))
                continue
            try:
                current = path.read_bytes()
            except OSError:
                manual.append(str(path))
                continue
            state = _agent_profile_state(current, name)
            if state == "legacy":
                role_writes.append((path, rendered))
            elif state != "current":
                manual.append(str(path))

    executable_path, executable_hash, executable_problem = _host_install_executable(
        home, executable, executable_sha256
    )
    if executable_problem is not None:
        manual.append(executable_problem)
    script_bytes = host_hook_script_bytes()
    unsafe_script_path = any(character in str(script_path) for character in ('"', "%", "!", "\r", "\n"))
    script_safe = not home.is_symlink() and not script_path.is_symlink() and not unsafe_script_path
    if unsafe_script_path:
        manual.append("host_hook_script_path_not_safe_for_cmd_trampoline")
    if script_safe and script_path.exists():
        try:
            existing_script = script_path.read_bytes()
            if existing_script not in {script_bytes, lifecycle._legacy_host_hook_script_bytes()}:
                manual.append(str(script_path))
                script_safe = False
        except OSError:
            manual.append(str(script_path))
            script_safe = False
    elif script_path.is_symlink():
        manual.append(str(script_path))
        script_safe = False

    hook_bytes: bytes | None = None
    if executable_path is not None and executable_hash is not None and script_safe and not hooks_path.is_symlink() and not home.is_symlink():
        try:
            if hooks_path.exists():
                original = json.loads(hooks_path.read_text(encoding="utf-8"))
                if not isinstance(original, dict):
                    raise ValueError("Host hooks.json must contain an object")
            else:
                original = {}
            merged, hooks_changed, hook_manual = merge_host_hooks(
                original, home, executable_path, executable_hash
            )
            if hook_manual:
                manual.extend(str(hooks_path) + ":" + item for item in hook_manual)
            else:
                if hooks_changed:
                    hook_bytes = (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                if not script_path.exists() or script_path.read_bytes() != script_bytes:
                    _atomic_host_write(script_path, script_bytes)
                    changed = True
                    if HOST_HOOK_SCRIPT_NAME not in files:
                        files.append(HOST_HOOK_SCRIPT_NAME)
                if hook_bytes is not None:
                    _atomic_host_write(hooks_path, hook_bytes)
                    changed = True
                    files.append("hooks.json")
        except (OSError, ValueError, json.JSONDecodeError):
            manual.append(str(hooks_path))
    elif hooks_path.is_symlink():
        manual.append(str(hooks_path))

    for path, rendered in role_writes:
        try:
            _atomic_host_write(path, rendered)
            changed = True
            files.append(f"agents/{path.name}")
        except OSError:
            manual.append(str(path))

    global_instruction_ready = False
    if not home.is_symlink() and not global_agents.is_symlink() and (not global_agents.exists() or global_agents.is_file()):
        try:
            current_agents = global_agents.read_bytes() if global_agents.exists() else b""
            updated_agents = _global_agents_update(
                current_agents, executable=executable_path, executable_sha256=executable_hash
            )
            if updated_agents != current_agents:
                _atomic_host_write(global_agents, updated_agents)
                changed = True
                files.append("AGENTS.md")
            global_instruction_ready = True
        except (OSError, ValueError):
            manual.append(str(global_agents))
    else:
        manual.append(str(global_agents))

    health = lifecycle.host_hooks_health(home)
    trust_status = "NOT_REGISTERED"
    trusted_count = 0
    enabled_count = 0
    expected_count = len(lifecycle.HOOK_EVENTS)
    trust_error: str | None = None
    if health["hooks_configured"] == "YES" and executable_path is not None and executable_hash is not None:
        try:
            trust = _install_host_hook_trust(home, executable_path, executable_hash)
            trust_status = str(trust.get("status", "FAILED"))
            trusted_count = int(trust.get("trusted_count", 0))
            enabled_count = int(trust.get("enabled_count", 0))
            expected_count = int(trust.get("expected_count", expected_count))
            if trust.get("changed") is True:
                changed = True
                config_path = trust.get("config_path")
                if isinstance(config_path, str) and Path(config_path).name.casefold() == "config.toml":
                    files.append("config.toml")
        except (codex_app_server.CodexAppServerError, OSError, ValueError, RuntimeError) as exc:
            trust_status = "HOST_HOOK_TRUST_INSTALL_FAILED"
            trust_error = str(exc)
            manual.append("HOST_HOOK_TRUST_INSTALL_FAILED")
    else:
        trust_error = "Host hook registration is not complete"
    host_integration_ready = (
        health["hooks_configured"] == "YES"
        and trust_status == "TRUSTED"
        and trusted_count == expected_count == len(lifecycle.HOOK_EVENTS)
        and enabled_count == expected_count
        and _host_profile_definition_present(home) == "YES"
    )
    if trust_status == "TRUSTED" and enabled_count != expected_count:
        manual.append("one_or_more_Thaliris_Host_hooks_are_disabled_by_user_state")
    return {
        "ok": host_integration_ready and global_instruction_ready,
        "changed": changed,
        "target": str(home),
        "files": sorted(set(files)),
        "manual_action_required": sorted(set(manual)),
        "host_profile_definition_present": _host_profile_definition_present(home),
        "host_hook_registration_present": health["hooks_configured"],
        "host_hook_trust_status": trust_status,
        "host_hook_trusted_count": trusted_count,
        "host_hook_enabled_count": enabled_count,
        "host_hook_expected_count": expected_count,
        "host_integration_ready": "YES" if host_integration_ready else "NO",
        "global_instruction_ready": "YES" if global_instruction_ready else "NO",
        "host_hook_trust_error": trust_error,
        "managed_hook_abi": MANAGED_HOOK_ABI,
        "native_profile_names": sorted(roles.native_profile_names()),
        "host_role_catalog_status": lifecycle.HOST_ROLE_CATALOG_UNKNOWN,
        "host_session_load_status": "UNKNOWN",
        "host_setup_requires_session_start": any(path != "AGENTS.md" for path in files),
        "project_files_touched": [],
        **_controller_bridge(),
    }


def codex_uninstall(codex_home: Path | None = None) -> dict[str, object]:
    """Remove exact Thaliris-owned Host integration and global instruction."""
    home = _codex_home(codex_home)
    manual: list[str] = []
    removed: list[str] = []
    hooks_path = home / "hooks.json"
    script_path = home / HOST_HOOK_SCRIPT_NAME
    global_agents = home / "AGENTS.md"
    has_hook_manual = False
    owned_commands: dict[str, set[str]] = {event: set() for event in lifecycle.HOOK_EVENTS}
    host_hook_keys: list[str] = []
    trust_cleanup_status = "NOT_NEEDED"
    trust_cleanup_error: str | None = None
    trust_removed = 0
    if home.is_symlink():
        manual.append(str(home))
        has_hook_manual = True
    elif hooks_path.is_symlink():
        manual.append(str(hooks_path))
        has_hook_manual = True
    elif hooks_path.exists():
        try:
            original = json.loads(hooks_path.read_text(encoding="utf-8"))
            if not isinstance(original, dict):
                raise ValueError("Host hooks.json must contain an object")
            owned_commands = _owned_host_hook_commands(original, home)
            if any(owned_commands.values()):
                try:
                    host_hook_keys = codex_app_server.owned_hook_keys_from_host(home, owned_commands)
                    trust_cleanup_status = "CLEANED"
                except (codex_app_server.CodexAppServerError, OSError, ValueError, RuntimeError) as exc:
                    trust_cleanup_status = "FAILED"
                    trust_cleanup_error = str(exc)
                    manual.append("HOST_HOOK_TRUST_CLEANUP_FAILED")
            cleaned, changed, hook_manual = remove_host_hooks(original, home)
            if hook_manual:
                manual.extend(str(hooks_path) + ":" + item for item in hook_manual)
                has_hook_manual = True
            elif changed:
                _atomic_host_write(hooks_path, (json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
                removed.append("hooks.json")
        except (OSError, ValueError, json.JSONDecodeError):
            manual.append(str(hooks_path))
            has_hook_manual = True
    if not has_hook_manual and script_path.exists():
        if script_path.is_symlink():
            manual.append(str(script_path))
        else:
            try:
                if script_path.read_bytes() in {
                    host_hook_script_bytes(), lifecycle._legacy_host_hook_script_bytes()
                }:
                    script_path.unlink()
                    removed.append(HOST_HOOK_SCRIPT_NAME)
                else:
                    manual.append(str(script_path))
            except OSError:
                manual.append(str(script_path))
    agents = home / "agents"
    if home.is_symlink() or agents.is_symlink() or (agents.exists() and not agents.is_dir()):
        manual.append(str(agents))
    elif agents.is_dir():
        for name in _agent_profiles():
            path = agents / name
            if path.is_symlink():
                manual.append(str(path))
                continue
            if not path.is_file():
                continue
            try:
                state = _agent_profile_state(path.read_bytes(), name)
            except OSError:
                manual.append(str(path))
                continue
            if state in {"current", "legacy"}:
                try:
                    path.unlink()
                    removed.append(f"agents/{name}")
                except OSError:
                    manual.append(str(path))
    if host_hook_keys and "hooks.json" in removed:
        try:
            trust_removed = codex_app_server.remove_owned_hook_trust(home, host_hook_keys)
            if trust_removed:
                removed.append("config.toml")
        except (codex_app_server.CodexAppServerError, OSError, ValueError, RuntimeError) as exc:
            trust_cleanup_status = "FAILED"
            trust_cleanup_error = str(exc)
            manual.append("HOST_HOOK_TRUST_CLEANUP_FAILED")
    elif host_hook_keys and "hooks.json" not in removed:
        trust_cleanup_status = "SKIPPED_MANUAL"
    if home.is_symlink() or global_agents.is_symlink() or (global_agents.exists() and not global_agents.is_file()):
        manual.append(str(global_agents))
    elif global_agents.is_file():
        try:
            current_agents = global_agents.read_bytes()
            updated_agents = _global_agents_update(current_agents, remove=True)
            if updated_agents != current_agents:
                if updated_agents:
                    _atomic_host_write(global_agents, updated_agents)
                else:
                    global_agents.unlink()
                removed.append("AGENTS.md")
        except (OSError, ValueError):
            manual.append(str(global_agents))
    health = lifecycle.host_hooks_health(home)
    return {
        "ok": trust_cleanup_status != "FAILED" and str(global_agents) not in manual,
        "changed": bool(removed),
        "target": str(home),
        "files": sorted(removed),
        "manual_action_required": sorted(set(manual)),
        "host_hook_registration_present": health["hooks_configured"],
        "host_hook_trust_cleanup_status": trust_cleanup_status,
        "host_hook_trusted_state_removed": trust_removed,
        "host_hook_trust_cleanup_error": trust_cleanup_error,
        "host_profile_definition_present": _host_profile_definition_present(home),
        "host_role_catalog_status": lifecycle.HOST_ROLE_CATALOG_UNKNOWN,
        "project_files_touched": [],
    }


def _adapter_uninstall_plan(root: Path) -> tuple[dict[str, bytes], list[str], list[str], list[str]]:
    agent_paths = _root_instruction_candidates(root)
    ignore = core._safe(root, ".gitignore")
    for agents in agent_paths:
        if agents.is_file():
            _managed_span(_read_text(agents), agents.name)
    if ignore.is_file():
        _audit_ignore(_read_text(ignore))
    writes: dict[str, bytes] = {}
    deletes: list[str] = []
    kept: list[str] = []
    manual: list[str] = []
    for agents in agent_paths:
        if not agents.is_file():
            continue
        current = _read_text(agents)
        span = _managed_span(current, agents.name)
        if span is not None:
            if _managed_agents_state(current) == "user":
                kept.append(agents.relative_to(root).as_posix())
                continue
            stripped = _strip_managed_agents(current)
            name = agents.relative_to(root).as_posix()
            if stripped:
                writes[name] = stripped.encode("utf-8")
            else:
                deletes.append(name)
    audit_present = (root / ".context" / "audit").exists()
    if ignore.is_file() and not audit_present:
        current = _read_text(ignore)
        rendered = _audit_ignore(current, remove=True)
        if rendered != current:
            writes[".gitignore"] = rendered.encode("utf-8")
    marker = core._safe(root, PROJECT_ACTIVATION_MARKER.replace("\\", "/"))
    if marker.is_symlink():
        manual.append(PROJECT_ACTIVATION_MARKER.replace("\\", "/"))
    elif marker.exists():
        try:
            if marker.is_file() and marker.read_bytes() == _PROJECT_ACTIVATION_BYTES:
                deletes.append(PROJECT_ACTIVATION_MARKER.replace("\\", "/"))
            else:
                kept.append(PROJECT_ACTIVATION_MARKER.replace("\\", "/"))
        except OSError:
            manual.append(PROJECT_ACTIVATION_MARKER.replace("\\", "/"))
    packs = core._safe(root, "docs/thaliris-role-packs.md")
    if packs.is_file():
        if _role_pack_state(packs.read_bytes()) == "current":
            deletes.append("docs/thaliris-role-packs.md")
        else:
            kept.append("docs/thaliris-role-packs.md")
    role_registry = core._safe(root, "docs/thaliris-role-registry.md")
    if role_registry.is_file():
        if _role_registry_state(role_registry.read_bytes()) in {"current", "legacy"}:
            deletes.append("docs/thaliris-role-registry.md")
        else:
            kept.append("docs/thaliris-role-registry.md")
    hooks = core._safe(root, ".codex/hooks.json")
    if hooks.is_file():
        try:
            value = json.loads(_read_text(hooks))
            if not isinstance(value, dict):
                raise ValueError("hooks root must be an object")
            if lifecycle.legacy_managed_handler_cleanup_required(value):
                manual.append(".codex/hooks.json")
            else:
                cleaned, changed = remove_hooks(value)
                if changed:
                    owned_empty = value.get("description") == MANAGED_HOOKS_DESCRIPTION and set(cleaned) <= {"description", "hooks"} and cleaned.get("description") == MANAGED_HOOKS_DESCRIPTION and cleaned.get("hooks", {}) == {}
                    if owned_empty:
                        deletes.append(".codex/hooks.json")
                    else:
                        writes[".codex/hooks.json"] = (json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        except (OSError, ValueError, json.JSONDecodeError):
            manual.append(".codex/hooks.json")
    return writes, deletes, kept, manual


def uninstall(root: Path) -> dict[str, object]:
    root = core._repo_root(root)
    adapter = _adapter_uninstall_plan(root)
    generic_writes, generic_deletes, generic_kept, generic_manual = core._uninstall_plan(root)
    writes = generic_writes | adapter[0]
    deletes = sorted(set(generic_deletes) | set(adapter[1]))
    with core._lock(root):
        backup = core._apply_with_backup(root, writes, deletes, "uninstall") if writes or deletes else None
    return {"ok": True, "changed": bool(writes or deletes), "backup": backup, "kept": sorted(set(generic_kept) | set(adapter[2])), "manual_action_required": sorted(set(generic_manual) | set(adapter[3]))}


def task_start(
    root: Path,
    goal: str,
    milestone: str | None,
    input_file: str | None,
    hook_attestation: str | None = None,
    controller_bridge_sha256: str | None = None,
) -> dict[str, object]:
    root = core._repo_root(root)
    definition = _project_definition_facts(root)
    if definition["project_definition_present"] != "YES":
        bootstrap = {
            **definition,
            "init_required": True,
            "session_restart_required": "UNKNOWN",
            "same_session_task_start": "UNKNOWN",
            "managed_runtime_after_restart": "UNVERIFIED",
        }
        if definition.get("legacy_managed_handler_cleanup") == "MANUAL_CLEANUP_REQUIRED":
            bootstrap["manual_action_required"] = "legacy_managed_handler_manual_cleanup_required"
        return {
            "ok": False,
            "status": "BOOTSTRAP_REQUIRED",
            "bootstrap": bootstrap,
        }
    executable = lifecycle.managed_executable_health()
    # A missing trusted executable is an independent fail-closed bootstrap
    # fact. It is not represented by durable restart state.
    if hook_attestation is not None and executable["canonical_executable_available"] != "YES":
        return {
            "ok": False,
            "status": "BOOTSTRAP_REQUIRED",
            "bootstrap": {
                **definition,
                **executable,
                "init_required": False,
                "session_restart_required": False,
                "same_session_task_start": "UNKNOWN",
                "managed_runtime_after_restart": "UNVERIFIED",
                "manual_action_required": "canonical_executable_unavailable",
            },
        }
    # Direct Python callers retain the historical local API; the native hook
    # attestation path is the startup boundary whose trusted executable must
    # be explicit.
    bridge = _controller_bridge()
    if hook_attestation is not None and controller_bridge_sha256 != bridge["controller_bridge_sha256"]:
        return {"ok": False, "status": "CONTROLLER_BRIDGE_REQUIRED", "expected_controller_bridge_sha256": bridge["controller_bridge_sha256"], "host_instruction_activation": "UNKNOWN"}
    session_hash = lifecycle.consume_task_start_attestation(root, hook_attestation, controller_bridge_sha256)
    if hook_attestation is not None:
        catalog_status = lifecycle.role_catalog_session_status(root, session_hash)
        if catalog_status == "NEW_ROLE_CATALOG_IDENTITY_NOT_ACTIVE":
            return {"ok": False, "status": catalog_status, "new_role_profile_files": lifecycle.new_role_profile_files(root, session_hash), "host_instruction_activation": "UNKNOWN"}
    mode = selected_continuation_mode(root)
    readiness = {
        "status": "PASS" if mode in {"EVENT_DRIVEN", "BLOCKING_WAIT"} else "MANAGED_CONTINUATION_UNAVAILABLE",
        "NATIVE_CHILD_COMPLETION_REENTERS_ROOT": native_child_completion_reenters_root(),
        "HOST_EXPLICIT_BLOCKING_WAIT": host_explicit_blocking_wait().get("status"),
        "selected_continuation_mode": mode,
    }
    if mode == "UNAVAILABLE":
        return {"ok": False, "status": "MANAGED_CONTINUATION_UNAVAILABLE", "managed_readiness": readiness}
    result = core.task_start(root, goal, milestone, input_file, actor="controller")
    result["managed_readiness"] = {**readiness, **_activation_fields(root), "CONTROLLER_ACTIVATION_BRIDGE_ACTIVE": "YES" if hook_attestation is not None else "NOT_APPLICABLE", "HOST_INSTRUCTION_ACTIVE": "UNKNOWN", "controller_activation_bridge": "ACTIVE" if hook_attestation is not None else "NOT_APPLICABLE", "host_instruction_activation": "UNKNOWN", "role_catalog_session_status": catalog_status if hook_attestation is not None else "NOT_APPLICABLE"}
    return result


def bootstrap_check(root: Path) -> dict[str, object]:
    """Return the read-only facts needed by the external Codex bootstrap.

    This deliberately performs no initialization and creates no durable state;
    the host entrypoint uses it to decide whether one direct ``init`` call is
    necessary before handing control back to the Controller.
    """
    root = core._repo_root(root)
    return {"ok": True, **_project_definition_facts(root), **_controller_bridge(), "managed_hook_abi": lifecycle.MANAGED_HOOK_ABI, "executable_adapter_protocol_version": lifecycle.CODEX_ADAPTER_PROTOCOL_VERSION, "session_restart_required": False}


def task_close(root: Path, base_revision: int) -> dict[str, object]:
    state = core.task_show(root)["state"]
    task_id = str(state["task_id"])
    if not lifecycle.qualifying_child_completed(core._repo_root(root)):
        raise ValueError("task-close requires an authorized explicit handoff, a matching native SubagentStart/Stop identity, and no pending or active managed work")
    return core.task_close(root, base_revision, expected_task_id=task_id)


def audit_hook(root: Path, event: str, payload: object, managed_hook_abi: str | None = None) -> str:
    result = handle_hook(root, event, payload, managed_hook_abi)
    if result or event != "PreToolUse" or not isinstance(payload, dict):
        return result
    root = core._repo_root(root)
    parent = payload if payload.get("agent_id") is not None else None
    if parent is not None and not lifecycle._bound_managed_child(root, parent):
        return ""
    tool = payload.get("tool_name") or payload.get("tool")
    if not isinstance(tool, str) or lifecycle._tool_basename(tool) != "wait_agent":
        return ""
    if (
        lifecycle._active_task_id(root) is None
        or selected_continuation_mode(root) != "BLOCKING_WAIT"
        or not lifecycle.managed_dependency_pending(root, parent)
    ):
        return ""
    capability = host_explicit_blocking_wait()
    if capability.get("status") != "PASS":
        return ""
    original = payload.get("tool_input")
    if not isinstance(original, dict):
        return ""
    target = capability.get("effective_max_wait_timeout_ms")
    if not isinstance(target, int) or isinstance(target, bool) or target < 0:
        return ""
    if original.get("timeout_ms") == target:
        return ""
    # Copy rather than reconstruct: future native arguments survive unchanged.
    updated = dict(original)
    updated["timeout_ms"] = target
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "updatedInput": updated,
    }}, ensure_ascii=False, separators=(",", ":"))


def doctor(root: Path) -> dict[str, object]:
    from .doctor import report
    root = core._repo_root(root)
    result = report(root)
    registry_path = root / "docs" / "thaliris-role-registry.md"
    registry_state = (
        _role_registry_state(registry_path.read_bytes())
        if registry_path.is_file()
        else "missing"
    )
    result["role_registry"] = {
        "roles": list(_role_choices()),
        "native_profiles": sorted(roles.native_profile_names()),
        "host_profile_definition_present": _host_profile_definition_present(),
        "project_local_profile_files_present": _project_local_profile_files_present(root),
        "host_role_catalog_status": lifecycle.HOST_ROLE_CATALOG_UNKNOWN,
        "profile_inventory": role_profile_inventory(root),
        "generated_role_document": "CURRENT" if registry_state == "current" else "MISSING_OR_USER"
        if registry_state != "missing" else "MISSING",
    }
    result["durable_index_integrity"] = core.durable_index_check(root)
    result["managed_task_state"] = lifecycle.managed_task_state(root)[0]
    observations: list[tuple[int, int, dict[str, object]]] = []
    events: set[str] = set()
    compatible_profile_observed = False
    orchestration = {
        "wait_calls": 0,
        "wait_timeouts": 0,
        "list_agents_calls": 0,
        "blocked_spawn_calls": 0,
        "reconciliation_attempts": 0,
        "reconciliation_successes": 0,
        **{
            binding.orchestration_metric: 0
            for binding in roles.iter_codex_bindings()
            if binding.orchestration_metric is not None
        },
    }
    expected = lifecycle.managed_hook_spec_hash()
    for path in (root / ".context" / "audit").glob("*/runtime.json"):
        try:
            runtime = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        current = isinstance(runtime, dict) and runtime.get("managed_hook_spec_hash") == expected and runtime.get("adapter_protocol_version") == lifecycle.CODEX_ADAPTER_PROTOCOL_VERSION
        samples = runtime.get("execution_observations") if current else None
        if current and isinstance(runtime.get("events_observed"), dict):
            events.update(name for name, observed in runtime["events_observed"].items() if observed is True)
        if current and isinstance(runtime.get("subagent_start_agent_types"), list):
            compatible_profile_observed = compatible_profile_observed or any(
                isinstance(value, str) and value in roles.native_profile_names()
                for value in runtime["subagent_start_agent_types"]
            )
        if isinstance(samples, list):
            observations.extend((int(runtime.get("observed_at_ns", 0)), int(runtime.get("observation_sequence", 0)), item) for item in samples if isinstance(item, dict))
        metrics = runtime.get("orchestration_metrics") if current else None
        if isinstance(metrics, dict):
            orchestration["wait_calls"] += int(metrics.get("wait_agent_calls", 0))
            orchestration["wait_timeouts"] += int(metrics.get("wait_timeouts", 0))
            orchestration["list_agents_calls"] += int(metrics.get("list_agents_calls", 0))
    latest = max(observations, default=None, key=lambda item: (item[0], item[1]))
    latest_item = latest[2] if latest is not None else None
    health = lifecycle.hooks_health(root)
    lifecycle_start = lifecycle_stop = lifecycle_reconciled = False
    reconciliation_attempts = reconciliation_successes = 0
    for path in (root / ".context" / "audit" / "lifecycle").glob("*.json"):
        try:
            lifecycle_state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(lifecycle_state, dict) or lifecycle_state.get("version") != lifecycle.LIFECYCLE_STATE_VERSION or lifecycle_state.get("managed_hook_spec_hash") != expected or lifecycle_state.get("adapter_protocol_version") != lifecycle.CODEX_ADAPTER_PROTOCOL_VERSION:
            continue
        for child in lifecycle_state.get("children", []):
            if isinstance(child, dict) and isinstance(child.get("started"), int):
                lifecycle_start = True
                lifecycle_stop = lifecycle_stop or isinstance(child.get("stopped"), int)
                lifecycle_reconciled = lifecycle_reconciled or child.get("terminal_state") == "NATIVE_TERMINAL_RECONCILED"
                binding = roles.get_codex_binding(child.get("role")) if isinstance(child.get("role"), str) else None
                metric = binding.orchestration_metric if binding is not None else None
                if metric is not None:
                    orchestration[metric] += 1
        metrics = lifecycle_state.get("metrics")
        if isinstance(metrics, dict):
            reconciliation_attempts += int(metrics.get("reconciliation_attempts", 0))
            reconciliation_successes += int(metrics.get("reconciliation_successes", 0))
            orchestration["blocked_spawn_calls"] += int(metrics.get("blocked_spawn_calls", 0))
    result["verification_attestation"] = {
        "host_hook_registration_present": health["hooks_configured"],
        # Stored observations are intentionally useful diagnostics, but they
        # cannot prove that the session asking for this doctor report loaded
        # the current Host hook registration.
        "current_session_observed": "UNKNOWN",
        "task_start_attestation": "CURRENT_SESSION_REQUIRED",
        "adapter_protocol_current": "YES" if events or latest is not None else "UNKNOWN",
        "verification_shell_surface": "Bash",
        "verification_terminal_status": "UNAVAILABLE",
        "observed_outcome": latest_item.get("outcome") if latest_item is not None else "UNKNOWN",
        "hook_trust": "UNKNOWN",
        "detail": "No version-pinned terminal-status attestation is recorded; no automatic PASSED attestation is emitted.",
    }
    result["managed_readiness"] = {
        "CORE_READY": "YES",
        "HOST_HOOK_REGISTRATION_PRESENT": health["hooks_configured"],
        "CODEX_RUNTIME_OBSERVED": health["runtime_observed"],
        "CURRENT_SESSION_OBSERVED": "UNKNOWN",
        "TASK_START_ATTESTATION": "CURRENT_SESSION_REQUIRED",
        "CODEX_MANAGED_READY": "UNKNOWN",
        "spawn_pretool_observed": "YES" if "PreToolUse" in events else "UNKNOWN",
        "subagent_start_observed": "YES" if lifecycle_start else "UNKNOWN",
        "subagent_stop_observed": "YES" if lifecycle_stop else "UNKNOWN",
        "explicit_handoff_binding_observed": "YES" if lifecycle_start else "UNKNOWN",
        "CONTROLLER_ACTIVATION_BRIDGE_ACTIVE": "UNKNOWN",
        "HOST_INSTRUCTION_ACTIVE": "UNKNOWN",
        "controller_activation_bridge": "UNKNOWN",
        "NATIVE_CHILD_COMPLETION_REENTERS_ROOT": native_child_completion_reenters_root(),
        "HOST_EXPLICIT_BLOCKING_WAIT": host_explicit_blocking_wait().get("status"),
        "EFFECTIVE_WAIT_MAXIMUM": host_explicit_blocking_wait().get("effective_max_wait_timeout_ms", "UNAVAILABLE"),
        "BLOCKING_WAIT_MODE": "PASS" if selected_continuation_mode(root) == "BLOCKING_WAIT" else "FAIL",
        "selected_continuation_mode": selected_continuation_mode(root),
        **_activation_fields(
            root,
            profile_native_active="UNKNOWN",
            project_layer_activation="UNKNOWN",
            compatible_profile_observed="YES" if compatible_profile_observed else "UNKNOWN",
            host_hook_runtime_observed="YES" if events else "UNKNOWN",
        ),
    }
    # Keep Host registration and project marker disk facts separate from live
    # session observations; neither can stand in for a native hook run, a deny,
    # or a Reviewer sandbox observation.
    host = result.get("host_capability") if isinstance(result.get("host_capability"), dict) else {}
    host.update({
        "hook_runtime_observed": "YES" if events else "UNKNOWN",
        "controller_pretool_observed": "YES" if "PreToolUse" in events else "UNKNOWN",
        "subagent_lifecycle_observed": "YES" if lifecycle_start and lifecycle_stop else "UNKNOWN",
        "hook_hash_match": "YES" if events else host.get("hook_hash_match", "UNKNOWN"),
        "hook_trust_status": "UNKNOWN",
        "controller_deny_observed": "UNKNOWN",
        "controller_side_effect_prevented": "UNKNOWN",
        "reviewer_native_readonly_observed": "UNKNOWN",
        "trusted_runtime_isolation_observed": "UNKNOWN",
        "effective_wait_maximum": host_explicit_blocking_wait().get("effective_max_wait_timeout_ms", "UNAVAILABLE"),
    })
    result["host_capability"] = host
    posttool_schema = "PASS" if host_wait_mode().get("status") == "PASS" else "UNKNOWN"
    result["lifecycle_reconciliation"] = {
        "subagent_stop_path": "PASS" if lifecycle_stop else "UNKNOWN",
        # The pinned source supplies these shapes, but a
        # Host hook must observe a real payload before this is a live PASS.
        "native_terminal_reconciliation": "PASS" if lifecycle_reconciled else ("LIVE_NOT_OBSERVED" if posttool_schema == "PASS" else "UNKNOWN"),
        "PostToolUse_source_schema_support": posttool_schema,
        "PostToolUse_live_host_hook": "PASS" if events else "LIVE_NOT_OBSERVED",
        "reconciliation_attempts": reconciliation_attempts,
        "reconciliation_successes": reconciliation_successes,
    }
    orchestration["reconciliation_attempts"] = reconciliation_attempts
    orchestration["reconciliation_successes"] = reconciliation_successes
    result["cost_regression"] = {
        # This Hook surface has no model-turn/token/context counter.  Leaving
        # these unavailable is safer than deriving model cost from wait calls.
        "root_model_activations": "UNAVAILABLE",
        "child_model_activations": "UNAVAILABLE",
        "root_input_tokens": "UNAVAILABLE",
        "child_input_tokens": "UNAVAILABLE",
        "root_context_size_per_activation": "UNAVAILABLE",
        "ROOT_ACTIVATIONS_WITHOUT_NEW_INFORMATION": "UNAVAILABLE",
        "ROOT_MODEL_ACTIVATIONS_PER_CHILD": "UNAVAILABLE",
        **orchestration,
    }
    return result
