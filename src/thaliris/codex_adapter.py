"""Codex adapter for explicit handoff delivery and native lifecycle hooks."""
from __future__ import annotations

import json
import hashlib
import base64
from functools import lru_cache
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib

from . import codex_app_server, core, lifecycle, roles, runtime_identity, host_preflight
from .lifecycle import (
    MANAGED_HOOKS_DESCRIPTION,
    MANAGED_HOOK_ABI,
    HOST_HOOK_SCRIPT_NAME,
    HOST_RUN_SCRIPT_NAME,
    PROJECT_ACTIVATION_MARKER,
    handle_hook,
    host_hook_script_bytes,
    host_run_script_bytes,
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
# Independently witnessed complete historical renders, not current HEAD's
# claim about its own output. 28e4297d2e489a8f893cb75aec7291cbb3518dcb:
# adapter blob443f92a103ba7bfb1e0ad1c14cd4eab7d8960bec; registry
# blobc3ded0e264771024f7cad71bccee0308a6f009a5. Filename binding is mandatory.
_HISTORICAL_28E4297_PROFILE_HASHES = {
    'thaliris-curator.toml': '55aed52f61396de5d75b430fa4a0d03d2487e084b9c54e0ced7c32493ea44cbe',
    'thaliris-implementer.toml': 'ebb2136a91990dfe855428b568a42b01a470494db14c3d3cc6c818c62fff23be',
    'thaliris-investigator.toml': '70238f39468e11ebedc5612056e4e11139f9c285cbc1b7c43c8d2da3f639d7ca',
    'thaliris-reasoning-specialist-astra-medium.toml': 'ef5e1521bedaeba7bb316042d28385700774d78f8d1c798eac308c175c5ba34b',
    'thaliris-reasoning-specialist-xhigh.toml': 'f42bc785a0c76c516fd0493b24c85d0e381cf6e5ac82808befa4a01e8baab3c0',
    'thaliris-reasoning-specialist.toml': 'd8a6f94789958424783f6de7154eb51d3fcb76cb4f00f6e7260bf06e3a93d011',
    'thaliris-reviewer.toml': 'e631e603f87405c5d21a31bfdb07eaf3c7a0553d937b3069e2d7ddea22decc12',
    'thaliris-verifier.toml': '3c598e8bb39c52682f6021505a8b37b71415ce9016e1b53a6741363e8a16a6e2',
}
# 69d9a33 historical renderer/registry witness for the previous current set.
_HISTORICAL_69D9A33_PROFILE_HASHES = {
    'thaliris-curator.toml': 'a3665bf571db75df3530fcea172bed154cfb7aac5f88b40bd847109e15459108',
    'thaliris-focused-implementer-astra-medium.toml': 'd4fef2b7b5e77d027b4d3e0807fdeb3a6bc6d81f3cf8aabf41affce7b912e573',
    'thaliris-focused-implementer-xhigh.toml': '8f6890bfa3ad76b2a0401a04f33a4e7494ea91b3cb266b749f1d72a7cbf8aba7',
    'thaliris-focused-implementer.toml': 'cca2ff3bf783baa3c8926efd42e2c5807c9db9ea1a6a64b7e34e30a791274b17',
    'thaliris-implementer.toml': '3d393a145c900749c33296550e740bf61af64b91d2b4cf3462cb2c44e1d65195',
    'thaliris-investigator.toml': 'd34b8571689c0ffc5e68cd5fb316ef1b26d41dfa8e2e363e34bf8b465ecca544',
    'thaliris-reasoning-specialist-astra-medium.toml': '31639f9b001b0b8ba88c6733e6c881f98b817513257c1921b67790c832f37b00',
    'thaliris-reasoning-specialist-xhigh.toml': '476a79f410a5f68bbae0a8c4257ac69873523f73cb8d4de6fb3de8725a638817',
    'thaliris-reasoning-specialist.toml': '3f2caaead9fbb239a3dd4d118762efb70a60b9954cfa287954033a4a9694d0fc',
    'thaliris-reviewer.toml': '58e4dce82be3a5fb2483f86ebc274c306eb8f1ede469a0794fc6b7eb545fa938',
    'thaliris-verifier.toml': 'fc1d73fec897f250125e3031d8c02ef0e035411467ed0126f62df193e8345188',
}
for _historical_profiles in (_HISTORICAL_28E4297_PROFILE_HASHES, _HISTORICAL_69D9A33_PROFILE_HASHES):
    for _profile_name, _profile_hash in _historical_profiles.items():
        _KNOWN_GENERATED_AGENT_PROFILE_HASHES[_profile_name] = (
            _KNOWN_GENERATED_AGENT_PROFILE_HASHES.get(_profile_name, frozenset()) | frozenset({_profile_hash})
        )

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
# The three exact focused-implementer profiles emitted by immutable revision
# 40fd5f2bcb928f8f9443b01389168f6a1b8e3054 (adapter blob
# d1badfc56feb2c65a72f80d158ce67d0ad88f30c, role registry blob
# 2e092e2e9293c6b51897a83e8b5de9d8326b2225). The effective Host files
# were independently SHA-256 checked against these historical renderer bytes.
# Preserve filename binding: a matching digest under another role is user-owned.
_40FD5F2_GENERATED_AGENT_PROFILE_HASHES = {
    "thaliris-focused-implementer.toml": "48b73ecaea2cd7b3c2515c0dfea69e1a7291c8e08599c1ddc9011208fcf3b6a2",
    "thaliris-focused-implementer-astra-medium.toml": "3f7142b441521aca5b978b38a7c5de081eab7326c327524bdc9214b20c5b2971",
    "thaliris-focused-implementer-xhigh.toml": "774b28e8a99a5f7396013cb94b2e183e57a940c482919526cf814fc54e018287",
}
for _profile_name, _profile_hash in _40FD5F2_GENERATED_AGENT_PROFILE_HASHES.items():
    _KNOWN_GENERATED_AGENT_PROFILE_HASHES[_profile_name] = (
        _KNOWN_GENERATED_AGENT_PROFILE_HASHES.get(_profile_name, frozenset())
        | frozenset({_profile_hash})
    )
# Exact SHA-256 identities of the eight non-focused profiles emitted by the
# immutable fd4fba36 adapter/registry revision (adapter blob
# 45b0e509dd491adfc2f55723036e4f1aab5a7cc2, roles blob
# 2e092e2e9293c6b51897a83e8b5de9d8326b2225). Each hash was independently
# matched to the historical renderer output. These remain exact-filename
# ownership evidence; edits and cross-role copies stay user-owned.
_FD4FBA36_GENERATED_AGENT_PROFILE_HASHES = {
    "thaliris-curator.toml": "74aebff8c07c2a3359461085d165d440e8c6b8e9ca2d5ac9bc6c57ca83e91653",
    "thaliris-implementer.toml": "bb0767422861b66e0becd3386d6f0d5faecf247bbda767c52118ee58184ed613",
    "thaliris-investigator.toml": "d14a5376c3644495746fedcf74f92dac62bdca2321419473fd0dc8407ce8bc1b",
    "thaliris-reasoning-specialist-astra-medium.toml": "f1d75968331cdcc6e3b3e447c79909b02070475cfc2d764b83c2f4515f290f6e",
    "thaliris-reasoning-specialist-xhigh.toml": "0d05efd7edcb17965a1c6f3dee7b1152dcdd9ced067e86d60b878b9f3f6b0705",
    "thaliris-reasoning-specialist.toml": "432517da403000383ecf9ee0793122c1fe03aae2a8ef3395d6b8449b6b6ab73a",
    "thaliris-reviewer.toml": "44e684ed9a49c1f4d5e50e12b483136e148c9969c1cbc9ae6495fcd1b5a90a62",
    "thaliris-verifier.toml": "571bdd8c11d06a2393f1554f48621892c652dd6c09660a5d9fffe97844e6d59f",
}
for _profile_name, _profile_hash in _FD4FBA36_GENERATED_AGENT_PROFILE_HASHES.items():
    _KNOWN_GENERATED_AGENT_PROFILE_HASHES[_profile_name] = (
        _KNOWN_GENERATED_AGENT_PROFILE_HASHES.get(_profile_name, frozenset())
        | frozenset({_profile_hash})
    )
# Exact generated profile bytes from immutable 8a3fe930 (roles blob
# 758a31568fb6b8755b68721028d9b4a912bb6ef0, adapter blob
# 7c7d7ea689461206502efe9fe4f521df5489dae4). Only these four profiles
# changed in the role-contract update; ownership remains filename-bound.
_8A3FE930_GENERATED_AGENT_PROFILE_HASHES = {
    "thaliris-focused-implementer.toml": "a929ec5bbbb748a880a95fea40aec4de05b225269e70473937c9deee3411608a",
    "thaliris-focused-implementer-astra-medium.toml": "e22136925d2bcaed111c687c47a8de1464014427a6c8bbed7e1021076bd20d8a",
    "thaliris-focused-implementer-xhigh.toml": "1f4311da03a5ee0185253156c3510ed3c2855f0a8091a4699a80b1ebe7b9ca9a",
    "thaliris-reviewer.toml": "4b1593d4269bccd7e86da5fabaa129f9da431302e072469e60f273abb36a05a0",
}
for _profile_name, _profile_hash in _8A3FE930_GENERATED_AGENT_PROFILE_HASHES.items():
    _KNOWN_GENERATED_AGENT_PROFILE_HASHES[_profile_name] = (
        _KNOWN_GENERATED_AGENT_PROFILE_HASHES.get(_profile_name, frozenset())
        | frozenset({_profile_hash})
    )
# Exact Focused Implementer profile bytes rendered by the immutable 99a58fc
# revision immediately before the focused-work guidance update. Keep each
# identity bound to its exact filename, including both exceptional profiles.
_99A58FC_FOCUSED_PROFILE_HASHES = {
    "thaliris-focused-implementer.toml": "b4ff152b4a3978f31c7b80891a839bf1bd8408336fe19b2c8c27d42bf88d0311",
    "thaliris-focused-implementer-astra-medium.toml": "9b412596980063afae0a4678043e09ca6f3509735e55f373119c3da3655831ef",
    "thaliris-focused-implementer-xhigh.toml": "501fc4fc95c883f9249c649e6477a7d98babd97e41942b036da94e0086c3f662",
}
for _profile_name, _profile_hash in _99A58FC_FOCUSED_PROFILE_HASHES.items():
    _KNOWN_GENERATED_AGENT_PROFILE_HASHES[_profile_name] = (
        _KNOWN_GENERATED_AGENT_PROFILE_HASHES.get(_profile_name, frozenset())
        | frozenset({_profile_hash})
    )
# Exact SHA-256 identities of all eleven generated profiles rendered by the
# immutable 210782b1d652e8266859e2999e558be8e061d46f revision. Its packaged
# roles.py and codex_adapter.py were byte-identical to those source files; the
# renderer output was independently matched against the prior immutable
# installed runtime and all eleven effective Host profiles. The focused test
# re-renders these bytes from that source revision. These filename-bound hashes
# establish historical generated ownership only.
_210782B1_GENERATED_AGENT_PROFILE_HASHES = {
    "thaliris-curator.toml": "828ff942256ffe8c1507023db6940069e7d88ef740edcd8ba01ad72fc4a0b115",
    "thaliris-focused-implementer-astra-medium.toml": "2bbcd612c4697025a5ca3948e0b07215995c9e5e0886e78e168c7a483a81882e",
    "thaliris-focused-implementer-xhigh.toml": "957d4bee345c4ad4dc9f65deabfdc87a1a8b8d32cf8d33da90846504af6b8300",
    "thaliris-focused-implementer.toml": "0f408384609c2a2217d7268a8c29afa28560299130c8de072d3bdd2cadcc0b1a",
    "thaliris-implementer.toml": "74bd3a8a9cfdc7d69c19060c0666dcc398a220f36955214a02121786c705becc",
    "thaliris-investigator.toml": "cc6cde5de4260746b590b6d8c603f69f4c2b9479a77505bc0d3631ae51510ad4",
    "thaliris-reasoning-specialist-astra-medium.toml": "e747753a31408500bb7f4eddf44348b5096e0d1d946163395edf4012fa2dbcea",
    "thaliris-reasoning-specialist-xhigh.toml": "9bbf7a90b54d5d850e262682128aa787d0c974f12c397fcb8e2c8b03f4ad1eb3",
    "thaliris-reasoning-specialist.toml": "4533322a06ee4b3bba7fb9d07e8eb2252b6a686884333324ebef3af6bf651a3e",
    "thaliris-reviewer.toml": "f0998da30f8029536151fdb155a80548b6093e1866b387d0dd98b459c9f0b3b2",
    "thaliris-verifier.toml": "81a9e2a9526962c0facf064e40b22b9ec261b1af9d2a6545bb41da21b1033f90",
}
for _profile_name, _profile_hash in _210782B1_GENERATED_AGENT_PROFILE_HASHES.items():
    _KNOWN_GENERATED_AGENT_PROFILE_HASHES[_profile_name] = (
        _KNOWN_GENERATED_AGENT_PROFILE_HASHES.get(_profile_name, frozenset())
        | frozenset({_profile_hash})
    )
# Exact output from immutable dde3d0f872d7b1b9ecb97d2aa59049ae104f6363.
# Re-rendered from that revision's source and matched byte-for-byte against
# all eleven effective Host profiles before changing their instructions.
_DDE3D0F_GENERATED_AGENT_PROFILE_HASHES = {
    "thaliris-investigator.toml": "96a633af50c1ddf32c8be39e744536a7c0f7368dd536400aa5a87b3766f065cf",
    "thaliris-curator.toml": "3740fdbedb75b7196aa4d5ce64afd6a46626ef5cd6128c7c80d58030e2615f42",
    "thaliris-reasoning-specialist.toml": "f74fb5f14bcd0addab1aa3c854ff1a89d319152b2e274293aea94c0cb8d478ad",
    "thaliris-implementer.toml": "bc01341e1380d7677e6404a4329b06e2412daf300b50b11ba45a983e5ea33039",
    "thaliris-focused-implementer.toml": "07402540f774fb554843915c104383eedb6646d14c51b41dc32f1e9a87a40883",
    "thaliris-verifier.toml": "2e7d71453611cfcfd956dc82c9727bb4f055492b417fce608264386f2d11c99d",
    "thaliris-reviewer.toml": "f94e08afe5021d1284839465964a91b2b550d392029725b6d6d6ba7ee991b699",
    "thaliris-reasoning-specialist-astra-medium.toml": "1f66a702a5dd8c58f5ccbade5e3cabeb8790cf29e1463ae072f0af41dfaebacc",
    "thaliris-reasoning-specialist-xhigh.toml": "bc9c4c5eb8a8b39015a9664728f1f16eeef516269b0d856408ff8071b5107e88",
    "thaliris-focused-implementer-astra-medium.toml": "2472c64230f3315c55a084d504c57cd117e9d743314cd6bd61c8d1a06e9fb9a7",
    "thaliris-focused-implementer-xhigh.toml": "0fa1303f77009d11f8e4932081b5a99f25ca9e025b2954a14065b4436511d855",
}
for _profile_name, _profile_hash in _DDE3D0F_GENERATED_AGENT_PROFILE_HASHES.items():
    _KNOWN_GENERATED_AGENT_PROFILE_HASHES[_profile_name] = (
        _KNOWN_GENERATED_AGENT_PROFILE_HASHES.get(_profile_name, frozenset())
        | frozenset({_profile_hash})
    )
# Exact focused profiles committed in immutable 8eb1707; each was independently
# re-rendered from that revision's roles and adapter source and matched bytewise.
_8EB1707_FOCUSED_PROFILE_HASHES = {
    "thaliris-focused-implementer.toml": "3b19e5d8a0e72e794f76883ad3242c83bb4d542388c076ffacf9a28e377bf86a",
    "thaliris-focused-implementer-astra-medium.toml": "7ae1bef593fc06fa4d8e5ee40a009718b0ca31358ed1a9de362dc3cfb65055e3",
    "thaliris-focused-implementer-xhigh.toml": "fe996dfb59c467d173d7da754bbe73ee9659d88b7bb27ff09cc32c730a6fd2e9",
}
for _profile_name, _profile_hash in _8EB1707_FOCUSED_PROFILE_HASHES.items():
    _KNOWN_GENERATED_AGENT_PROFILE_HASHES[_profile_name] = (
        _KNOWN_GENERATED_AGENT_PROFILE_HASHES.get(_profile_name, frozenset())
        | frozenset({_profile_hash})
    )
# Exact generated bytes for the four affected profiles rendered by immutable
# revision e4b6975889ef348e13e94521dc300f1e572b42a3 (adapter blob
# 16ad86097d0635c25f1a3acf936963930c7f310c, roles blob
# ca8daae4f2182028d7927daabcca917ff4b17447). The installed runtime and
# effective Host files were independently matched to this revision. These
# historical ownership hashes remain bound to their exact profile filenames.
_E4B6975_GENERATED_AGENT_PROFILE_HASHES = {
    "thaliris-implementer.toml": "88ea13ad079412a4569a2360731d4bb377d9b20cb313cc9a882065cdd5861f29",
    "thaliris-focused-implementer.toml": "1eb28a0b74e72fcf4e03f63ec3ddba12d4972ab3f7cfb71bd02efc1b748cbd45",
    "thaliris-focused-implementer-astra-medium.toml": "37dacbc67a27f3551d6e60b26bc520113c274d233c01fd85c2d507806f62e625",
    "thaliris-focused-implementer-xhigh.toml": "c66aa6e934a6fdc354eda44d60145d6e92a4e7c4b65be796a18094ce03817a3e",
}
for _profile_name, _profile_hash in _E4B6975_GENERATED_AGENT_PROFILE_HASHES.items():
    _KNOWN_GENERATED_AGENT_PROFILE_HASHES[_profile_name] = (
        _KNOWN_GENERATED_AGENT_PROFILE_HASHES.get(_profile_name, frozenset())
        | frozenset({_profile_hash})
    )
# The three project-local Focused Implementer files committed at ec1ad7b are
# exact output of that immutable revision's renderer.  The current files were
# independently compared byte-for-byte with that renderer.  This evidence is
# bound to each filename; it does not establish ownership of the other local
# profiles or of similarly named files in another directory.
_EC1AD7B_FOCUSED_PROFILE_HASHES = {
    "thaliris-focused-implementer.toml": "edeb1136eab3d7685552e7a8ec4da70a7cec22085dc236e203a7ef2c7d8f03a4",
    "thaliris-focused-implementer-astra-medium.toml": "6b255fa51ad04def5bbe248c30d5e247bb17af3913cffd815e283ec9178aae53",
    "thaliris-focused-implementer-xhigh.toml": "6484ff491175ebf56a63d65d7439c3c661f782e6401c09e43f6bfbf26a3f0ff1",
}
for _profile_name, _profile_hash in _EC1AD7B_FOCUSED_PROFILE_HASHES.items():
    _KNOWN_GENERATED_AGENT_PROFILE_HASHES[_profile_name] = (
        _KNOWN_GENERATED_AGENT_PROFILE_HASHES.get(_profile_name, frozenset())
        | frozenset({_profile_hash})
    )
_KNOWN_GENERATED_ROLE_PACK_HASHES = frozenset({
    "4e4a1af986df48f8c9e0e632506ef13636531dba163fa7ae7032a7d18ab2c36a",  # ec1ad7b committed generated role pack
    "4f6f4a41baedc5bc0b01fa8a37b86d3bdee2384846e260bf8f896cff12b650f4",  # e4b6975 committed generated role pack
    "7009fc69d97ca403404c57d739e354cc3ebf7656fdca690c0fd60b2cfa9f6267",  # 9b5bcf2
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
    "4ee70a3c36b2c76d74c03179359181dfd34c96bbfae5bf1e5e7ee1c71b6f13d7",  # 8a3fe930, blob 3253fc8
    "d2b3a1c5a776f6a1dbb3be52a907c1704903f64a92d2388f64dc2171096e92e8",  # 99a58fc renderer output before focused-work guidance update
    "44fad20e3e751dcaaa4d055d567bf3875242b158e62c58f312c4ea0bfdcb025c",  # dde3d0f exact committed generated role pack
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
    "df7c8832a47f59fac6ba2692bb54166a629cc4bdbc4b58661582a42bc04fb152",  # e4b6975 committed managed span
    "d249d418ccf38ca3f159065715c3930d492682e93402025d067e99e2225b91fd",  # 3485ec4
    "1b1cb7331dddc504a0908af91e32fba2b72cced74af1b56007099bb088b36c56",  # a33db5b
    "c0072af2e11ee5ed315712c301a33c39a993af13d6243816b319700b432ef2ed",  # 729809f
    "0238e56f242ca68c31d8b63c6d34ffcecc88ace6e245cad986ca3bd1c21e78d2",  # 3ae1b21
    "66c1ac81e010fba307cb579b519142124ddca128e028890f48c7e33f8fac6a11",  # 8eb1707
    "bc47c81d7004bc8a4095cc5d9079068af9ca3d2804a5a557d17a5abaf371f494",  # f316910
    "943c67bb7683785403429063bec0a0174119e8c2dbbe70f6684b8c46d1434c0b",  # e02b953
    "96102e74cd2812e2f06382173807939c79e856371180f94c1413ba8e26e8facb",  # 8a3fe930, blob 93d73da
    "3c1e3475797d0c9270d9adafa210492b8b305748f5e7bd7fc9411752f74d959d",  # 11e0cc9:AGENTS.md, exact published managed span
    "adebcedf67d1e3aa3e33d42da1174ea36d9e4199beb8453d8076a1de72cd638a",  # 9b5bcf2 renderer output
    "9b3ae3c7edbfc74255a3c743dc9a1c430c6c936ea3101b3f0777f2a78eb4c7b8",  # 99a58fc managed span before focused-work guidance update
    "3787a539d15224a357bc2703215dea7a474b43f8b3fe85f43f43b30cea854807",  # dde3d0f exact committed managed span
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
    instructions = roles.profile_instructions(role, name)
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
    instruction_state = "MISSING"
    instruction_sha256 = "UNKNOWN"
    if instruction.is_file():
        try:
            current = _read_text(instruction)
            span = _managed_span(current, instruction.name)
            if span is not None:
                owned = _normalize_line_endings(current[span[0]:span[1]])
                instruction_sha256 = hashlib.sha256(owned.encode("utf-8")).hexdigest()
                instruction_state = _managed_agents_state(current).upper()
                start, end = span
                # Only the adapter-owned span participates in definition
                # validity. User-owned text may use different line endings;
                # normalize the owned block before comparing it to the
                # canonical LF-rendered definition.
                expected = _normalize_line_endings(render_managed()).removesuffix("\n")
                instruction_present = "YES" if _normalize_line_endings(current[start:end]) == expected else "NO"
                if instruction_present == "YES":
                    instruction_state = "CURRENT"
        except (OSError, UnicodeError, ValueError):
            instruction_present = "NO"
            instruction_state = "UNKNOWN"
    activation = _project_activation_marker_present(root)
    host_hooks = lifecycle.host_hooks_health(_codex_home())
    # Host integration is installed once in CODEX_HOME before a session.
    # Project init adds only the marker that lets its stable trampoline enter
    # the current executable on subsequent tool events in that same session.
    initialized = "YES" if instruction_present == "YES" and activation == "YES" else "NO"
    return {
        "project_definition_present": initialized,
        "instruction_definition_present": instruction_present,
        "managed_instruction_state": instruction_state,
        "managed_instruction_sha256": instruction_sha256,
        "expected_managed_instruction_sha256": hashlib.sha256(
            _normalize_line_endings(render_managed()).removesuffix("\n").encode("utf-8")
        ).hexdigest(),
        "managed_instruction_recovery_action": (
            f"thaliris init --accept-managed-instruction-sha256 {instruction_sha256}"
            if instruction_state == "USER"
            else "thaliris init" if instruction_state == "LEGACY" else "NONE"
        ),
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
For divisible work, Root routes by semantic Workstream. Define Workstream
boundaries by semantic dependencies, decision coupling, implementation
uncertainty, and independent closure, not by token, file, or task-count
thresholds. A Workstream is held by Root and executed by one authorized child
session; it does not create another role or semantic Controller. A semantic
checkpoint is not necessarily a scheduling checkpoint. Root routes workstreams.
Executors close local loops inside them.

Within a stable Workstream, the same Implementer session may complete multiple
local closures: batch relevant reads, plan, implement, run focused verification,
fix ordinary in-scope failures, synchronize generated output and documentation,
run needed integration verification, inspect diff and status, and complete
assigned Git closure. A local verification PASS does not require returning to
Root. Ordinary test fixes, generated or documentation synchronization,
integration checks, and assigned Git closure are execution checkpoints inside
the Workstream, not separate semantic routing boundaries. The child retains
execution authority only within the assigned goal, scope, invariants, and
acceptance; this authority never expands Controller-assigned scope.

Root regains control at the semantic Workstream boundary. A child returns
distilled state, its commit reference, and verification evidence after its
assigned Workstream is complete. If new evidence changes task direction,
ownership, observable semantics, a hard invariant, compatibility contract, or
acceptance, or reveals an unverified external dependency that can change the
decision, the child stops and returns the concrete unknown in FINAL for Root to
decide. Only the Controller decides what follows; no child acts as a second
semantic Controller. Do not use file, tool, token, time, or local-closure
counts to end a Workstream or to choose the executor profile.
When completed Investigator discovery is selected for a later semantic slice,
the Controller handoff carries its confirmed facts, exact source locations and
affected surfaces, relevant unknowns or contradictions, and covered and
uncovered scope. This lets the next implementation role use the selected map
without reconstructing the same broad inventory.
Before choosing an opportunistic discovered slice, the Controller confirms that
each explicit user goal has been addressed, explicitly deferred, or has a
decision-changing blocker. This is a semantic rule, not a mechanical checklist
or state machine.
The Controller owns the complete user objective, its decomposition, role and
context choice, overall invariants, boundaries and acceptance, interpretation
of child results, and task-level decisions to reopen, review, continue, or end.
It may do bounded reading needed to frame a handoff and interpret evidence, but
does not perform broad repository scans, implementation, or the full task test
suite. The Investigator role gathers broad evidence, including through the
Scanner working pattern. Local code decisions and implementation within the
accepted packet belong to Implementer or Focused Implementer.
When an implementation handoff selects completed Investigator discovery from
an earlier slice, Implementer or Focused Implementer starts from that evidence
map. Reopen decision-critical originals, call chains, diffs, and tests as needed
for implementation; do not repeat broad discovery or delegate a Scanner over
the covered surface. A fresh Scanner may collect only a genuinely uncovered
decision-changing evidence gap needing independent broad discovery, limited to
that gap. Apply this by judgment about evidence coverage, without a cache,
threshold, state machine, or new evidence system.
The Focused Implementer can complete complex implementation as well as
focused judgment. It directly inspects known, decision-critical sources, including
source code, relevant call chains, the current diff, failed tests, and raw
evidence that bears on the decision. When the target is known, read it
directly. Delegate one independent discovery working set to a fresh
Investigator doing Scanner work when a larger or unknown evidence surface must be
discovered, enumerated, filtered, or classified. Ask the Scanner for key
conclusions, exceptions, UNKNOWNs, and accurate raw locations. The Scanner
narrows the search space; it does not replace reasoning-coupled reading. After
it returns, targeted reopening of relevant originals to verify findings is
useful. There is no per-read delegation deliberation or file, token, or
search-count threshold; small local searches may be direct. Delegate when
doing so removes the discovery working set and leaves reasoning and
implementation with the Focused Implementer. After delegating, it waits for the
distilled result and does not repeat the discovery pass. It continues complex
implementation within the assigned Workstream across local checkpoints when
that work still benefits from focused reasoning. A local verification PASS
does not force a return to Root. Close the Focused Workstream only at its
semantic boundary or when its assigned acceptance is complete; report a
deterministic remainder for Controller routing only when it is outside the
Workstream or independently closable without the Focused model's reasoning.
The Controller makes each child handoff decision-complete enough to close one
semantic Workstream without routine steering. Do not keep a child as a long-lived
interactive workspace. If new decision-changing information invalidates the
Workstream, the child closes with a distilled FINAL containing the unknown, and
the Controller decides what semantic work follows.
Use the Investigator role for missing facts, large working sets, broad scans,
and factual compression, without transferring architecture decisions. Its
Scanner working pattern batches related searches and reads, returns compact
facts, and once evidence is sufficient stops immediately; do not expand the
scan for one more confirmation.
Use a Reviewer only when independent semantic review adds real
value; it is not a default gate. Use Reasoning Specialist as an optional,
independent metacognitive challenger when a challenge may materially change
direction. Test framing, hidden assumptions, causal models, decomposition,
boundaries, decision basis, and premature convergence; this includes apparently
coherent framing and unexpected outcomes when a challenge could change direction.
The Specialist grounds critique in selected information, reports material
alternatives and critical missing facts, and does not make the final decision.
It does not perform broad fact gathering, implementation, routine review, or
ordinary hard-problem solving.
At task end, before `task-close`, make one short semantic judgment: did the task
add, change, or overturn durable knowledge that could affect a future decision
and would otherwise require reinvestigation? If no, silently skip Curator. If
yes, select a fresh Curator and provide the selected durable facts plus exact
relevant prior knowledge/documents. Curator is optional, never triggered by
task size, and not a mandatory stage. It keeps durable memory under
`.agent-memory/`; detailed evidence and task results remain in Artifacts, Git,
or rollout records. Implementer roles keep product/protocol documentation and
README aligned with current behavior; Reviewer challenges semantic drift when
selected.

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
when new decision-changing information arrives. A decision-changing unknown
requiring a Controller decision ends the child Workstream in FINAL. Do not send a
MESSAGE and stay ACTIVE for a wait.

The persistent root Controller has no fixed model, reasoning effort, or native
profile; Host/user selection applies. {_native_profile_facts()}
Only Controller may explicitly select static Astra medium or xhigh profiles for
Focused Implementer or Reasoning Specialist before spawn, and only with current-task
user authorization. Automatic routing stops at Sol, including when uncertainty
crosses surfaces. Each profile retains
the same semantic role identity and does not create another role.
These fixed profiles retain the same stable role IDs; default profiles remain
on Luna or Sol. Per-spawn model/effort overrides are denied;
role sessions never select their own model or effort.
Use Reasoning Specialist on Sol when an independent challenge may materially
change direction, including when the framing appears coherent or an outcome is
unexpected; difficulty alone is not a trigger. It challenges the decision basis
and reports its analysis without making the final decision.
Implementer and Focused Implementer make local code decisions and execute
implementation within their assigned packets. Verifier is retained read-only
for compatibility and is not recommended as a workflow stage.

Routing terminology: Investigator, Implementer, and Focused Implementer are semantic roles;
Scanner is a nested Investigator discovery working pattern, not a separate
role. Executor is a category covering Implementer and Focused Implementer, not
a selectable or spawnable role; route work by the actual role name. A native
execution profile selects model and effort for a semantic role and does not
create another role.

Choose one model/profile for the current Workstream from its work
shape, not as a ladder. The standard Implementer on Luna is the default for a
stable problem structure and direction, including remaining execution, local
code judgment, tests, synchronization, and mechanical consistency, regardless
of task size. Choose Focused Implementer on Sol when the smallest coherent
Workstream has a stable direction but inherently needs sustained reasoning
across coupled invariants, nonlocal effects, or constraints. Routine local
closures do not trigger a new role or profile choice. Astra medium and
xhigh remain exceptional profiles of
the same Focused Implementer role, available only with current-task user
authorization. Cross-surface uncertainty alone does not authorize Astra.
Choose the profile once for the Workstream. Importance, file count, cross-module
scope, number of local closures, or ordinary alternatives alone do not determine
the choice.

Keep the working set focused. Directly read known, decision-critical sources.
Use Scanner work for discovery over a larger or unknown evidence surface and
for a clearly large, low-reasoning-density collection that can be compressed
independently. With the Sol Focused Implementer profile, consider offloading
broad or exhaustive peripheral call-site, rollout/log, and residual-reference
collections when that removes an independent working set. With an Astra
Focused Implementer profile, explore evidence needed for the current Workstream
directly and use Scanner work only for a clearly large, low-reasoning-density
collection that can be compressed independently. The collection choice does
not predetermine which evidence is relevant. Targeted reading of known sources
remains part of the implementation role's work; small local searches may be
direct. Delegate when doing so removes an independent working set. Use its output as evidence. Children work only within their assigned semantic Workstream,
preserve Controller decisions and invariants, and return a decision-changing
unknown instead of changing them. Local code decisions belong to Implementer or
Focused Implementer.
Once the Workstream goal, authority, and boundary are known, batch the relevant source,
test, generation, and documentation reads, plan, and make coherent edits.
Avoid per-patch, per-read, or per-grep reasoning rounds unless new information
could change direction. Match verification to the changed behavior and its
concrete regression surface. Start with focused checks for the changed
contract, generated output, and acceptance. If those pass without a failure,
anomaly, or new broader-risk evidence, continue any remaining assigned local
closures within the Workstream. Broaden checks only for a concrete
compatibility or integration risk. After fixing a test failure, rerun the
smallest acceptance-relevant range and continue the Workstream. A commit, push,
or final report alone does not call for another test run. Do not use counts,
time, file or token limits, or a stopping state machine.
Controller may spawn registered roles. Implementer, Focused Implementer, and
Reviewer may each spawn only a fresh Investigator doing Scanner work. Investigator,
Reasoning Specialist, Curator, and Verifier cannot delegate. Maximum managed
depth is two: one Controller-direct child and its one nested Investigator
session doing Scanner work, never siblings. Results belong to the requesting
Implementer, Focused Implementer, or Reviewer.

An implementation handoff states Goal, confirmed facts, hard invariants,
Controller-decided boundaries/contracts, decision-changing unknowns,
non-binding recommendations/advice, and acceptance. Decisions, invariants, and
acceptance are contract; recommendations/advice are not. An unknown that can
change direction cannot be silently dropped, guessed, or frozen: prove Host
protocol, serialization, identity, and native-schema contracts first.

Before another semantic correction Workstream, distinguish a local implementation
defect from a decision-basis failure. During an active Workstream, the executor
fixes an ordinary local defect within the assigned scope in the same session and
reruns the smallest acceptance-relevant check. If review overturns an accepted invariant,
depends on an unverified external capability, makes feasibility uncertain, or
changes a Controller boundary or contract, reopen the Controller decision. If
facts are missing, route to a fresh Investigator. When an independent challenge
could materially change direction, route the selected framing and evidence to a
fresh Reasoning Specialist, even if the current framing appears coherent or an
outcome was unexpected. The Specialist challenges hidden assumptions, causal
models, decomposition, boundaries, decision basis, premature convergence, and
direction-changing alternatives; it reports critical missing facts for the
Controller to route and does not decide the task. Do not use it for broad fact
gathering, implementation, routine review, or ordinary hard-problem solving.
Difficulty alone is not a trigger when the Controller can decide confidently
from established facts. If the accepted design is unchanged and the defect is
outside the active Workstream, Root may route a fresh Implementer Workstream.
Do not use counters, thresholds, risk scores, classifiers, or a state machine
for this routing.
Missing factual information routes to the Investigator role. Broad grep,
exhaustive residual references, and call-site discovery can use the Scanner
working pattern under Implementer, Focused Implementer, or Reviewer. The
Controller interprets findings,
decides whether to reopen the basis, selects any review, and decides when work
continues or ends.
Reviewer challenges a converged implementation Workstream; do not start it against
a still-mutating Implementer or Focused Implementer to obtain parallel progress. Findings return to the
Controller, which decides whether a fresh correction Workstream is needed.

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
transparent. With positive Host actor assurance, during an ACTIVE managed task
the persistent Controller uses only
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
An incompatible older task schema remains INVALID_STATE until the Controller
uses the supported explicit recovery operation. Read `task-status` for the
version, exact state SHA-256, recoverability, and recovery action. After the
project definition is ready, `task-recover-state --expected-sha256 <exact-hash>`
archives the original bytes before a separate, newly attested `task-start`.
An ACTIVE old task also requires `--abandon-active`; pending or nonterminal
child lifecycle authority blocks recovery. Never interpret an invalid state
as an absent state or delete it by hand. An unrecognized, user-owned managed
instruction block requires explicit review before project initialization may
replace it; the installed one-shot bootstrap reports that conflict.
If `task-start` was attempted but managed enforcement is unavailable or
rejected, label the run unmanaged/degraded. Diagnose only the bootstrap cause:
Codex version, host capability, task schema, git/worktree identity,
hook/profile presence, and the `task-start` error are allowed reads. Use the
installed pinned `thaliris-run.cmd` command named by the global startup block;
its runtime validation runs before Python starts. Runtime drift is evidence,
not a global work ban: detect it, diagnose concrete expected/actual differences,
then let the Controller decide to repair, restore, or explicitly accept a
legitimate upgrade within existing user authorization. Unknown runtime code
must not run as trusted. Ordinary source edits, tests, reads, and investigation
remain available through the assigned roles; report managed assurance UNKNOWN.
Changes to runtime/manifest/executable/package/hooks/profiles, Host upgrade or
topology, user configuration, control authority, and unexplained changes have
different consequences; a hash difference alone does not decide them. Deny
only unsafe managed control, child identity bypass, control-state writes,
fenced-session revival, or irreversible evidence replacement. If work continues,
apply the same minimum-role
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
The Controller may explicitly run `thaliris recover-pending-spawn <handoff-id>`
only after the Hook records exact, trusted native failure for that unbound
reservation: a name-bound `interrupted`, `errored`, or `shutdown` observation,
or an exact spawn failure callback. Missing events, `not_found`, completed,
timeouts, and Controller reports cannot release it. A pre-Start native failure
without a Hook callback or identity remains unresolved.
Decision-changing investigation belongs to the Investigator role. Bounded local reading
needed for implementation may stay inside Implementer or Focused Implementer. Execution, mutation,
and testing belong to fresh Implementer or Focused Implementer sessions. Existing native Codex child sessions are never resumed with follow-up/send tools.
An Investigator's, Implementer's, or Focused Implementer's obvious direct control-context retrieval is allowed and recorded.
Investigator, Implementer, and Focused Implementer reads remain telemetry-only; Curator, Reasoning
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
SubagentStart consumes the unique reservation and binds the nested
Investigator session's own identity. One live managed Codex CLI `0.155.0-alpha.9.2` probe on 2026-09-25
verified the exact reservation, SubagentStart, and bound Scanner PreToolUse
acceptance at depth two. The Scanner work result returned and the Focused
Implementer parent continued. See the [durable probe evidence](docs/codex-nested-scanner-live-20260925.md).
This is evidence for that one CLI build and probe only. Raw Host wire-byte
equality, other Host builds or Desktop scenarios, and native child
`Completed`/`task-close` completion were not observed and remain UNKNOWN.
The identity binding and fail-closed mechanics above are unchanged.
Spawn authorization, native identity binding,
SubagentStart/Stop, missing-stop reconciliation, and explicit blocking waits are
mechanical. SubagentStop alone is not success; only an explicitly observed
native Completed status can satisfy lifecycle completion. Call `wait_agent` only
for a known unfinished child whose result is necessary to proceed. When blocked
on that child, use one blocking `wait_agent` call with `timeout_ms`
equal to the maximum advertised in the current turn's `wait_agent` tool
definition. The current turn's tool definition is the authority; never infer a
maximum from release defaults, configuration, history, or capability tables.
After a child FINAL, use its result and do not wait on it again. Repeat a timed-out
wait only while that child remains unfinished and necessary. A child reporting a
decision-changing unknown must end its Workstream in FINAL for Controller decision,
not send MESSAGE and remain ACTIVE for another wait. Do not periodically wake
the Controller to poll. If no usable
current maximum is advertised, do not invent one.
After a child finishes, call `list_agents` once before `task-close` to obtain
its exact native name and Completed status. A `wait_agent` result that only
reports `timed_out: false` is a wake signal, not completion evidence. If the
name-bound status is unavailable, leave completion UNKNOWN and keep the task
open; do not infer it from SubagentStop, child prose, or elapsed time.
Task closure requires the last
Controller-direct handoff's completed lifecycle and no pending or active
descendants; a later Scanner does not replace that top-level completion.
The Controller interprets {_native_role_names_text()} results,
verification observations, review findings, and task surface deltas and decides
the next handoff and when work is complete.

Startup contract: Host integration is installed once. For substantive Git work,
the owning root Controller runs the installed pinned
`thaliris-run.cmd --root <repo> codex-bootstrap` named by the global startup
block. Bootstrap confirms repository identity, checks
existing task state, and establishes missing project definitions without
reinstalling Host hooks or profiles. On READY, use only its opaque
`task_start_receipt` in a direct `task-start --bootstrap-receipt` call in this
session; the current Host Hook must supply one-shot task-start attestation.
On DEFINITION_READY_ACTOR_UNKNOWN, definition configuration is ready but managed
Controller authority is unavailable. Do not retry task-start or manufacture a
Root receipt. Ordinary reads, source edits, focused tests, investigation, and
repair continue through the authorized roles with managed assurance UNKNOWN.
Codex 0.159.2 ThreadSpawn fields positively identify children; built-in Review
can share the owner session and omit them. Absence or a matching session alone
is not Controller proof. Known bound child and readonly rules still apply.
If operating as a managed child inside an ACTIVE task, follow the explicit
handoff and do not run project bootstrap, task-start, or task-abandon for the
parent's task; startup, admission, and continuation decisions belong to the
owning root Controller.
Do not choose `bootstrap-check` or `init` for normal startup, calculate an
executable hash in a shell wrapper, or select among internal SHA fields.
On CURRENT_CONTINUATION, the owner may continue or explicitly abort the
incomplete task using the exact `task-abandon` packet. An unbound pending spawn
needs trusted terminal recovery for ordinary task-abandon. The separate reviewed
repository source runner `tools/thaliris_offline_recovery.py` supports explicit
user-delegated offline administration while global integration is disconnected.
It archives exact state/lifecycle bytes, fences every extractable old session or
agent identity, and releases only the old task slot. Its authority is
OPERATOR_ASSERTED_USER_DELEGATED_ADMINISTRATION: flags are operator assertions,
not cryptographic consent, Host receipts, or Controller identity. All automated
actors, including ambiguous roots, are denied this operation while integration
is present. Unknown owner, unbound identity, incompatible fields, and Host
termination remain recorded UNKNOWN. Try native termination/observation for
known old children; missing death proof does not permanently lock this informed
recovery. The shared OS is not a privilege separation boundary. On FOREIGN_RECOVERY_DECISION or UNKNOWN, the Controller
explicitly decides whether to continue old work or use that exact recovery
packet before starting a fresh task. An abandoned task remains incomplete and its original
state and lifecycle evidence are preserved. On INVALID_STATE or a definition
conflict, diagnose the affected surface; never delete evidence or invent completion.
A configured CLI executable/version, shared daemon, process ancestry, environment,
or SessionSource does not prove a current Host session or Controller identity.
Use structured Hook event payloads; record CLI and daemon versions separately,
and retain UNKNOWN when the daemon version or current role catalog is unproved.
In user-facing status, describe the work and any concrete blocker in ordinary
task terms. Keep receipts, hashes, attestations, role/session binding details,
and lifecycle protocol out of that prose; report blocked work honestly.
Host maintenance uses a separate checkout and Codex session outside the ACTIVE
project task. That checkout can repair Thaliris source, tests, installed runtime,
hooks, profiles, and the global instruction without changing the original task
ledger. In an ACTIVE project, only exact installed, identity-checked direct
`codex-install` and `codex-uninstall` calls are Host maintenance exceptions;
ordinary source commands remain under the managed Controller boundary. A
self-invoked `codex-uninstall` may retain an inert runner until a later direct
cleanup or reinstall, and reports that state explicitly.
Project initialization never requires a Codex restart. A changed global Host
installation may require one Codex restart before its hooks, profiles, and
instructions become active. Saved Host registration alone does not prove
current-session activation. SessionStart's role filename snapshot is disk
presence evidence only; without a Host-native catalog signal, status remains
`HOST_ROLE_CATALOG_UNKNOWN`, and an unseen new role filename fails closed with
`NEW_ROLE_CATALOG_IDENTITY_NOT_ACTIVE`. Read `.agent-memory/INDEX.md` and
`.milestones/INDEX.md` explicitly when managed startup requires navigation.
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

Use terminology precisely: Investigator, Implementer, and Focused Implementer
are semantic roles. Scanner is a nested Investigator discovery working pattern,
not a separate role. Executor is a category covering Implementer and Focused
Implementer, not a selectable or spawnable role; route work by those actual
role names. A native execution profile selects model and effort for a semantic
role and does not create another role.

## Role Defaults

The persistent root Controller has no fixed model, effort, or native profile;
Host/user selection applies. {_native_profile_facts()}
Only Controller may select static Astra medium or xhigh profiles for Focused
Implementer or Reasoning Specialist before spawn, only with current-task user
authorization. Automatic routing stops at Sol, including cross-surface
uncertainty. These fixed profiles map to
the same stable roles; defaults remain on Luna or
Sol. Per-spawn model/effort overrides are denied. Role sessions never
override their own model or effort.
Before choosing an opportunistic discovered slice, the Controller confirms that
each explicit user goal has been addressed, explicitly deferred, or has a
decision-changing blocker. This is a semantic rule, not a mechanical checklist
or state machine.

When completed Investigator discovery is selected for a later semantic slice,
the Controller handoff carries confirmed facts, exact source locations and
affected surfaces, relevant unknowns or contradictions, and covered and
uncovered scope. The next implementation role starts from that selected map.

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
A decision-changing unknown requiring a Controller decision ends the Workstream in
FINAL. Do not send MESSAGE and remain ACTIVE for another wait. Follow-up and
input tools remain denied for managed children.

## Investigator

Investigator handles missing facts, broad scans, large working sets, and
factual compression, not architecture decisions. Scanner names its nested
discovery working pattern. Scanner
work batches related searches and reads, returns compact facts, and once
evidence is sufficient stops immediately; do not expand the scan for one more
confirmation. Return a distilled selection map with confirmed facts and exact
source locations and affected surfaces, relevant unknowns or contradictions,
and the scope covered and left uncovered, so the Controller can select later
work. For inventories grouped into areas such as A, B, and C, state covered
and uncovered scope by area. It cannot
delegate. Investigate the task in the handoff. Save detailed reusable evidence
as an optional repo-relative Artifact and return its pointer with a short result.

## Curator

Use only when the Controller's end-of-task judgment finds durable maintenance
useful. Task size alone never triggers Curator, and Curator is not a mandatory
stage. The fresh handoff supplies selected durable facts and exact relevant
prior knowledge/documents. Do not automatically summarize a task, select a
next role, or route a result. Curator output is an ordinary result or Artifact;
Core has no Curator state machine.

Maintain only Controller-selected durable knowledge files under
`.agent-memory/` and their relevant links in `.agent-memory/INDEX.md`. Preserve
provenance and scope for each retained claim. New evidence may update or
supersede an earlier conclusion; retain its original scope and historical
applicability where relevant. Keep the corpus small, current, non-conflicting,
and traceable by modifying, merging, splitting, superseding, or deleting only
selected entries as evidence warrants. Exclude task chronology, implementation
logs, ordinary commit histories, transient test outputs, and momentary failures
unless they establish stable knowledge that could affect a future decision.
If consistency depends on durable material the Controller did not select, stop
and report the missing knowledge area for the Controller to select; do not scan
the corpus. Product/protocol documentation and README changes aligned with
current behavior belong to Implementer or Focused Implementer. Curator does not
scan broadly, make architecture decisions, or delegate. Memory holds concise
future decision-changing conclusions; detailed evidence belongs in Artifacts,
Git, or rollout records.

## Durable knowledge loop

At task start, the Controller reads the root INDEX map and then makes an exact
`document-get` request for the selected linked entries. At task end, before
`task-close`, it makes one short semantic judgment: did the task add, change, or
overturn durable knowledge that could affect a future decision and would
otherwise require reinvestigation? If no, it silently skips Curator. If yes, it
selects a fresh Curator with selected durable facts and exact relevant prior
knowledge/documents. Curator is optional, never selected by task size, and not
a mandatory stage. `CHANGED` is an evidence change, not semantic invalidation;
the Controller may request revalidation when a decision depends on changed
evidence and has become unreliable. If the
Controller promotes a selected record that changes durable navigation, it
supplies the model-authored INDEX CAS update in that
same promotion. Otherwise it leaves INDEX bytes unchanged. A fresh later task
recovers only by reading INDEX and exact selected documents, not by broad
reinvention or recursive scanning.

## Reasoning Specialist

Act as an independent metacognitive challenger of the selected framing and
decision basis. Examine hidden assumptions, causal models, decomposition,
boundaries, premature convergence, and alternatives that could materially
change direction. Challenge framing that appears coherent and examine
unexpected outcomes when they may reveal a faulty assumption or causal model.
Stay grounded in selected information; distinguish evidence from inference and
explain what would change the conclusion. Do not gather broad facts, implement,
conduct routine review, solve an ordinary hard problem for its own sake, or
make the final decision. Report the strongest material challenge, any
direction-changing alternative, and critical missing facts for the Controller
to route. Missing factual information goes to Investigator; the Specialist
does not gather it. Do not delegate or reconstruct unselected task history.

## Implementer and Focused Implementer

Executor is a category for the two implementation roles, not a role to route
or spawn. Implementer is the general implementation role; Focused
Implementer handles focused judgment and complex implementation within a
focused working set. They make local code decisions within their accepted packets and
assigned Workstreams. Root routes workstreams. Executors close local loops
inside them. A semantic checkpoint is not necessarily a scheduling checkpoint.
The Workstream is a semantic routing unit held by Root and executed by one
authorized child; it is not a role or second semantic Controller.

Within a stable Workstream, the same Implementer session may complete multiple
local closures: batch reads, plan, implement, run focused verification, fix
ordinary in-scope failures, synchronize generated output and documentation, run
needed integration verification, inspect diff and status, and complete assigned
Git closure. A local verification PASS does not require returning to Root.
Ordinary test fixes, generated or documentation synchronization, integration
checks, and assigned Git closure do not create separate semantic routing
boundaries. Root regains control at the semantic Workstream boundary. If new
evidence changes task direction, ownership, observable semantics, a hard
invariant, compatibility contract, acceptance, or reveals an unverified
external dependency that can change the decision, the child stops and returns
the concrete unknown in FINAL. Execution authority remains limited to the
assigned goal, scope, invariants, and acceptance; it cannot expand Controller
scope. Do not use file, tool, token, time, or local-closure counts to end a
Workstream or choose the executor profile. No child acts as a second semantic
Controller.

Once the Workstream goal, authority, and boundary are known, batch
the relevant source, test, generation, and documentation reads, form a plan, and
make coherent edits. Avoid per-patch, per-read, or per-grep reasoning rounds
unless new information could change direction. For selected discovery from an
earlier slice, directly reopen decision-critical originals, call chains, diffs,
and tests as needed. Do not reconstruct the covered broad inventory or delegate
a Scanner over that same surface. A new Scanner may collect only a genuinely
uncovered decision-changing evidence gap needing independent broad discovery.
Keep the working set focused.
Read known, decision-critical sources directly. Use Scanner work to discover over
a larger or unknown evidence surface, or to compress a clearly large,
low-reasoning-density collection when delegation removes an independent
working set. Use Scanner output as evidence; retain responsibility for
implementation decisions. Work only within the assigned semantic Workstream and
preserve Controller decisions and invariants; return a decision-changing unknown
instead of changing them. Delegate Scanner work only to a fresh Investigator
role session with `fork_turns="none"`.
Synchronize formal project documentation, including product/protocol docs and
README, for behavior changed within the assigned Workstream; report any
documentation boundary that needs a Controller decision.
Match verification to the changed behavior and its concrete regression surface.
Start with focused checks for the changed contract, generated output, and
acceptance. If they pass without a failure, anomaly, or new broader-risk
evidence, continue any remaining assigned local closures within the Workstream.
Broaden only for a concrete compatibility or integration risk. After a test
fix, rerun the smallest acceptance-relevant range and continue the Workstream.
A commit, push, or final report alone does not call for another test run. Do not
use counts, time, file or token limits, or a stopping state machine.

Focused Implementer directly inspects known, decision-critical source code,
relevant call chains, the current diff, failed tests, and decision-critical raw
evidence. If the target is known, read it directly. Delegate one independent
discovery working set to a fresh Investigator for Scanner work when a larger or unknown
evidence surface needs discovery or a clearly large, low-reasoning-density
collection can be compressed independently. With the Sol Focused Implementer
profile, consider offloading broad or exhaustive peripheral call-site,
rollout/log, and residual-reference collections when that removes an
independent working set. With an Astra Focused Implementer profile, explore
evidence needed for the current Workstream directly and use Scanner work only for a
clearly large, low-reasoning-density collection that can be compressed
independently. The collection choice does not predetermine relevant evidence. Ask for key
conclusions, exceptions, UNKNOWNs, and accurate raw locations. The Scanner
narrows a collection; it does not replace reasoning-coupled reading. After the
result, targeted reopening of relevant originals to verify findings is useful.
There is no per-read delegation deliberation or file, token, or search-count
threshold; small local searches may be direct. Delegate when doing so removes
an independent discovery working set and leaves reasoning and implementation with
the Focused Implementer. Wait only while the Scanner is known unfinished and
its result is necessary. After its FINAL, use the distilled result and do not
wait on it again or repeat its discovery pass. Continue complex implementation
within the assigned Workstream across local checkpoints when it still benefits
from focused reasoning. A local verification PASS does not require returning to
Root. Close the Focused Workstream only at its semantic boundary or when its
assigned acceptance is complete; route a deterministic remainder only when it
is outside the Workstream or independently closable without the Focused model's
reasoning.

Choose one model/profile for the current Workstream from its work
shape, not as a ladder. The standard Implementer on Luna is the default for a
stable problem structure and direction, including remaining execution, local
code judgment, tests, synchronization, and mechanical consistency, regardless
of task size. Choose Focused Implementer on Sol when the smallest coherent
Workstream has a stable direction but inherently needs sustained reasoning
across coupled invariants, nonlocal effects, or constraints. Routine local
closures do not trigger a new role or profile choice. Astra medium and
xhigh remain exceptional profiles of
the same Focused Implementer role, available only with current-task user
authorization. Cross-surface uncertainty alone does not authorize Astra.
Choose the profile once for the Workstream. Importance, file count, cross-module
scope, number of local closures, or ordinary alternatives alone do not determine
the choice.
Use Reasoning Specialist on Sol when an independent challenge may materially
change direction, including when framing appears coherent or an outcome is
unexpected; difficulty alone is not a trigger. It does not make the final task
decision. At the Workstream boundary, close with
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
observations. Close the assigned Workstream with distilled state, its commit
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
checks, and large mechanical evidence collection as Scanner work to one fresh
Investigator role session with `fork_turns="none"` and no model or effort override. Use its evidence while
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
stage and never mandatory. It cannot delegate. After Implementer or Focused Implementer, check
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
return through a fresh Implementer or Focused Implementer handoff selected for
the correction-slice work shape. DECISION_REOPEN returns to the
Controller, then to Investigator or Reasoning Specialist as appropriate.

## Bounded delegation and Host evidence

Controller delegates registered roles. Only Implementer, Focused Implementer,
and Reviewer may delegate a fresh Investigator for Scanner work, at maximum
depth two. There is one active top-level child and at most one nested
Investigator session doing Scanner work. Results
return to the requesting parent; no automatic result or Artifact propagation
is introduced. Exact parent agent/session/turn/role identity authorizes the
unique reservation; the matching Start binds the Investigator's own identity.
Missing or conflicting fields deny execution. Direct-child hook wire shapes
have been observed on the CLI. One live managed Codex CLI
`0.155.0-alpha.9.2` probe verified the exact reservation, `Start`, and bound
Scanner `PreToolUse` acceptance for a depth-two Investigator doing Scanner work; the result
returned and the Focused parent continued. See the [durable probe evidence](codex-nested-scanner-live-20260925.md).
This scoped probe covers that one CLI build and probe only. Raw Host wire-byte
equality, other Host builds or Desktop scenarios, and native child
`Completed`/`task-close` completion were not observed and remain UNKNOWN.
A 2026-09-28 Desktop probe observed a `wait_agent` wake without child status;
an exact name-bound native `Completed` observation must come from
`list_agents` before `task-close`. End-to-end Desktop closure is unobserved.
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


def _managed_agents(current: str, accept_managed_instruction_sha256: str | None = None) -> str:
    span = _managed_span(current, "AGENTS.md")
    if span is not None:
        start, end = span
        expected = _normalize_line_endings(render_managed()).removesuffix("\n")
        if _normalize_line_endings(current[start:end]) == expected:
            # Preserve the complete document when only user-owned content
            # differs (including its line-ending convention).
            return current
        if _managed_agents_state(current) == "user":
            actual = hashlib.sha256(_normalize_line_endings(current[start:end]).encode("utf-8")).hexdigest()
            if accept_managed_instruction_sha256 != actual:
                return current
    newline = "\r\n" if "\r\n" in current else "\n"
    block = render_managed().replace("\n", newline)
    if span is None:
        return block + current
    start, end = span
    canonical_span = block.removesuffix(newline)
    prefix, suffix = current[:start], current[end:]
    if prefix and not prefix.endswith(("\n", "\r")):
        prefix += newline
    if not suffix:
        suffix = newline
    elif not suffix.startswith(("\n", "\r")):
        suffix = newline + suffix
    return prefix + canonical_span + suffix


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


def _install_plan(
    root: Path,
    *,
    accept_managed_instruction_sha256: str | None = None,
) -> tuple[dict[str, bytes], list[str]]:
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
    current_agents_state = _managed_agents_state(current_agents)
    current_span = _managed_span(current_agents, target_agents.name)
    current_span_sha256 = (
        hashlib.sha256(_normalize_line_endings(current_agents[current_span[0]:current_span[1]]).encode("utf-8")).hexdigest()
        if current_span is not None else None
    )
    accepted_current_block = (
        current_agents_state == "user"
        and isinstance(accept_managed_instruction_sha256, str)
        and re.fullmatch(r"[0-9a-f]{64}", accept_managed_instruction_sha256)
        and accept_managed_instruction_sha256 == current_span_sha256
    )
    if current_agents_state == "user" and not accepted_current_block:
        manual.append(target_agents.relative_to(root).as_posix())
    rendered_agents = _managed_agents(
        current_agents,
        accept_managed_instruction_sha256=(current_span_sha256 if accepted_current_block else None),
    )
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


def init(
    root: Path,
    *,
    accept_managed_instruction_sha256: str | None = None,
) -> dict[str, object]:
    resolved = core._repo_root(root)
    for instruction in _root_instruction_candidates(resolved):
        if instruction.is_file():
            _managed_span(_read_text(instruction), instruction.name)
    ignore = core._safe(resolved, ".gitignore")
    if ignore.is_file():
        _audit_ignore(_read_text(ignore))
    root = core._repo_root(root)
    generic_files, generic_manual = core._init_plan(root)
    adapter_files, adapter_manual = _install_plan(
        root,
        accept_managed_instruction_sha256=accept_managed_instruction_sha256,
    )
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
    facts = _project_definition_facts(root)
    definition_recovery_status = (
        "READY" if facts["project_definition_present"] == "YES"
        else "EXPLICIT_CONFIRMATION_REQUIRED" if any(item in manual for item in ("AGENTS.md", "AGENTS.override.md"))
        else "INIT_REQUIRED"
    )
    return {"ok": True, "changed": bool(files), "backup": backup, "files": sorted(files), "manual_action_required": manual, "definition_recovery_status": definition_recovery_status, "instruction_definition_changed": instruction_changed, "hook_definition_changed": False, "project_activation_marker_changed": ".codex/thaliris.json" in files, "agent_profile_changed": profile_changed, "new_role_profile_files": new_profile_names, "role_catalog_changed": bool(new_profile_names), "hook_re_attestation_required": False, "managed_hook_abi": lifecycle.MANAGED_HOOK_ABI, "executable_adapter_protocol_version": lifecycle.CODEX_ADAPTER_PROTOCOL_VERSION, "canonical_executable_available": hooks["canonical_executable_available"], "canonical_executable_identity": hooks["canonical_executable_identity"], "session_restart_required": False, "hook_trust_required": False, "host_wait_mode": host_wait_mode(), **facts, **_activation_fields(root), **_controller_bridge()}


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
    try:
        package_dir = Path(json.loads(runtime_identity.manifest_bytes(resolved))["package_dir"])
    except (OSError, RuntimeError, ValueError):
        return None, None, "host_installed_runtime_unavailable_or_unsafe"
    interpreter = resolved.parent / ("python.exe" if os.name == "nt" else "python")
    if not interpreter.is_file() or interpreter.is_symlink():
        return None, None, "host_runtime_interpreter_unavailable_or_unsafe"
    probe_env = os.environ.copy()
    probe_env.pop("PYTHONPATH", None)
    probe_env.pop("PYTHONHOME", None)
    probe_env["PYTHONNOUSERSITE"] = "1"
    probe_env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        origin = subprocess.run(
            [str(interpreter), "-I", "-B", "-c", "import thaliris; print(thaliris.__file__)"],
            capture_output=True, timeout=15, check=False, env=probe_env,
        )
        if origin.returncode != 0 or origin.stderr or Path(origin.stdout.decode("utf-8").strip()).resolve(strict=True) != (package_dir / "__init__.py").resolve(strict=True):
            return None, None, "host_runtime_import_origin_mismatch"
    except (OSError, UnicodeError, subprocess.SubprocessError, RuntimeError):
        return None, None, "host_runtime_import_origin_mismatch"
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
                env=probe_env,
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


def _write_runtime_audit(home: Path, previous: bytes, old_executable: Path) -> Path:
    """Keep exact prior pin and best-effort observed runtime identity off the active path."""
    try:
        observed = runtime_identity.manifest_identity(runtime_identity.manifest_bytes(old_executable))
    except (OSError, RuntimeError, ValueError):
        observed = "UNAVAILABLE"
    record = {
        "format": "thaliris-installed-runtime-audit-v1",
        "prior_manifest_base64": base64.b64encode(previous).decode("ascii"),
        "prior_manifest_sha256": runtime_identity.manifest_identity(previous),
        "observed_runtime_sha256": observed,
    }
    with tempfile.NamedTemporaryFile(mode="wb", prefix="thaliris-install-audit-", suffix=".json",
                                     dir=home, delete=False) as output:
        output.write((json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
        return Path(output.name)


def _global_agents_block(executable: Path | None = None, executable_sha256: str | None = None,
                         codex_home: Path | None = None) -> bytes:
    """Render the one-command user-layer startup contract."""
    if (executable is None) != (executable_sha256 is None):
        raise ValueError("global instruction executable and SHA-256 must be paired")
    script = _codex_home(codex_home) / HOST_RUN_SCRIPT_NAME
    quoted = str(script).replace("'", "''")
    trusted_route = f"`& '{quoted}' --root <repo> codex-bootstrap`" if os.name == "nt" else f"`'{quoted}' --root <repo> codex-bootstrap`"
    task_route = f"`& '{quoted}' --root <repo> task-start <goal> --bootstrap-receipt <receipt>`" if os.name == "nt" else f"`'{quoted}' --root <repo> task-start <goal> --bootstrap-receipt <receipt>`"
    return f"""<!-- thaliris:global:begin -->
## Thaliris project startup

For substantive work that creates or changes files in a Git repository,
including a README, unless the user opts out, the owning root Controller runs
{trusted_route} directly once.
Chatting, read-only work, and non-Git directories need no project bootstrap.
If you are a managed child inside an ACTIVE task, follow the explicit handoff;
do not run project bootstrap, task-start, or task-abandon for the parent's
task. The owning root Controller handles startup, admission, and continuation
decisions.
On READY, pass its `task_start_receipt` as `<receipt>` in {task_route}
in this session; the current Hook must attest
task start. On DEFINITION_READY_ACTOR_UNKNOWN, the definition is ready but
managed Controller authority is unavailable. Continue ordinary source work,
reads, investigation, focused tests, and repair through the authorized roles
with assurance UNKNOWN. Do not retry task-start or invent Root proof from
absent child fields, a matching owner session, inherited environment, PID,
process ancestry, or SessionSource. Known bound child/readonly rules remain.
Use this installed command for later Thaliris operations. On
CURRENT_CONTINUATION, continue or explicitly abort the owning task using the
exact `task-abandon` packet. Recover any unbound pending spawn with trusted
terminal Host evidence first for ordinary task-abandon. When the user authorizes
external repair or forced recovery, disconnect global integration and use the
separate reviewed source runner `tools/thaliris_offline_recovery.py` with exact
task/revision/state/lifecycle hashes and a reason. Its authority is
OPERATOR_ASSERTED_USER_DELEGATED_ADMINISTRATION. The flags assert operator
intent; they are not cryptographic human consent or a Host attestation. It
archives original bytes, fences extractable old identities, and releases the
slot; it grants no task-start, child binding, Controller identity, or readonly
exemption. Automated actors are denied this operation while integration is
present. Try native termination/observation of known old children; owner,
unbound identities, incompatible fields, and unavailable death proof remain
UNKNOWN. Disk disconnection does not prove the running Host configuration.
Shared OS shell access supplies governance, not privilege separation. On
FOREIGN_RECOVERY_DECISION or UNKNOWN, the Controller decides whether to continue
or recover. On INVALID_STATE or bootstrap failure, diagnose the affected
surface; ordinary source work remains available with assurance UNKNOWN.
In user-facing status, describe the work and any concrete blocker in ordinary
task terms. Keep receipts, hashes, attestations, role/session binding details,
and lifecycle protocol out of that prose; report blocked work honestly.
For Host maintenance while another project is ACTIVE, use a separate checkout
and Codex session. Only exact identity-checked installed `codex-install` and
`codex-uninstall` invocations cross the ACTIVE project boundary; ordinary
project work continues through its managed roles. A self-invoked uninstall
reports an inert retained runner for later direct cleanup or reinstall.
After task start, follow the effective project role router.
## Thaliris routing and goal coverage

Investigator, Implementer, and Focused Implementer are semantic roles. Scanner
is a nested Investigator discovery working pattern, not a separate role.
Executor is a category covering Implementer and Focused Implementer, not a
selectable or spawnable role. A native execution profile selects model and
effort for a semantic role and does not create another role.
Choose one model/profile for the current Workstream from its work
shape, not as a ladder. Standard Implementer on Luna is the default for a
stable problem structure and direction, including remaining execution, local
code judgment, tests, synchronization, and mechanical consistency, regardless
of task size. Choose Focused Implementer on Sol when the smallest coherent
Workstream has a stable direction but inherently needs sustained reasoning
across coupled invariants, nonlocal effects, or constraints. Routine local
closures do not trigger another role or profile choice. Astra medium and
xhigh remain exceptional profiles of
the same Focused Implementer role, available only with current-task user
authorization. Cross-surface uncertainty alone does not authorize Astra.
Choose the profile once for the Workstream. Importance, file count, cross-module
scope, number of local closures, or ordinary alternatives alone do not determine
the choice.

Root routes workstreams. Executors close local loops inside them. A semantic
checkpoint is not necessarily a scheduling checkpoint. A stable Workstream can
include several verification, ordinary in-scope fix, generated/documentation
sync, integration-check, and assigned Git-closure checkpoints in the same child
session. A local verification PASS does not require returning to Root. Root
regains control at the semantic Workstream boundary. A child stays within the
assigned goal, scope, invariants, and acceptance, and ends in FINAL with concrete
facts if evidence changes task direction, ownership, observable semantics, a
hard invariant, compatibility, acceptance, or reveals an unverified external
dependency that can change the decision. No child is a second semantic
Controller, and no file, tool, token, time, or local-closure count decides
Workstream end.

A Scanner batches related searches and reads, then stops as soon as evidence is
sufficient; do not expand a scan for one more confirmation. Implementer and
Focused Implementer directly read known, decision-critical sources. With the Sol Focused Implementer
profile, consider offloading broad or exhaustive peripheral call-site,
rollout/log, and residual-reference collections when this removes an
independent working set. With an Astra Focused Implementer profile, explore
evidence needed for the current Workstream directly and use Scanner work only for a
clearly large, low-reasoning-density collection that can be compressed
independently. The collection choice does not predetermine relevance. Targeted
reopening of relevant originals is useful; small local searches may be direct.
Focused Implementer continues accepted implementation across local checkpoints
within the assigned Workstream, and reports a deterministic remainder for
Controller routing only when it is outside the Workstream or independently
closable without focused reasoning.
Before choosing an opportunistic discovered slice, the Controller confirms
every explicit user goal is addressed, explicitly deferred, or has a
decision-changing blocker. This is a semantic instruction, not a mechanical
checklist or state machine.
When completed Investigator discovery is selected for a later semantic Workstream,
the Controller handoff carries confirmed facts, exact source locations and
affected surfaces, relevant unknowns or contradictions, and covered and
uncovered scope. Implementer and Focused Implementer start from this selected
map and directly reopen decision-critical originals, call chains, diffs, and
tests as needed. They do not reconstruct the covered broad inventory or
delegate a Scanner over that same surface. A new Scanner may collect only a
genuinely uncovered decision-changing evidence gap needing independent broad
discovery, limited to that gap. Use judgment about evidence coverage without
a cache, threshold, state machine, or new evidence system.
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
    codex_home: Path | None = None,
) -> bytes:
    span = _global_agents_span(current)
    # Project-owned markers in the user layer indicate a different ownership
    # claim. Never silently replace or combine it with the global block.
    outside = current if span is None else current[:span[0]] + current[span[1]:]
    if MANAGED_START.encode() in outside or MANAGED_END.encode() in outside:
        raise ValueError("AGENTS.md has conflicting project Thaliris markers")
    if span is None:
        return current if remove else _global_agents_block(executable, executable_sha256, codex_home) + current
    start, end = span
    return current[:start] + (b"" if remove else _global_agents_block(executable, executable_sha256, codex_home)) + current[end:]


def _install_host_hook_trust(home: Path, executable: Path, executable_sha256: str, runtime_sha256: str) -> dict[str, Any]:
    return codex_app_server.trust_installed_host_hooks(home, executable, executable_sha256, runtime_sha256)


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
    run_script_path = home / HOST_RUN_SCRIPT_NAME
    preflight_path = home / host_preflight.NAME
    manifest_path = home / runtime_identity.MANIFEST_NAME
    manual: list[str] = []
    files: list[str] = []
    changed = False

    # Host ownership cannot cross a symlink or Windows junction, including an
    # ancestor of a not-yet-created home. Match installed-runtime path safety.
    home_safe = not any(runtime_identity._is_link(path) for path in (home, *home.parents))
    if not home_safe:
        manual.append(str(home))
    if agents.is_symlink() or (agents.exists() and not agents.is_dir()):
        manual.append(str(agents))
    role_writes: list[tuple[Path, bytes]] = []
    if str(agents) not in manual and home_safe:
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

    # Diagnose an existing installation before probing/importing its code.
    # An unchanged launcher hash does not authorize changed package/bytecode.
    prior_problem = None
    try:
        if not home_safe or runtime_identity._is_link(manifest_path):
            raise ValueError("unsafe installed runtime manifest path")
        try:
            manifest_path.lstat()
        except FileNotFoundError:
            pass
        else:
            runtime_identity._safe_file(manifest_path)
    except (OSError, ValueError, RuntimeError) as exc:
        prior_problem = "installed_runtime_manifest_unavailable:" + str(exc)
    if prior_problem is None and manifest_path.is_file():
        try:
            old_record = runtime_identity.validate_manifest_record(manifest_path.read_bytes())
            selected = Path(executable).expanduser() if executable is not None else lifecycle._trusted_thaliris_executable()
            if selected is None:
                found = shutil.which("thaliris")
                selected = Path(found) if found else None
            if selected is not None and selected.resolve() == Path(old_record["executable"]).resolve():
                diagnosis = runtime_identity.diagnose_manifest(manifest_path.read_bytes())
                if diagnosis["status"] != "MATCH":
                    prior_problem = "installed_runtime_changed_in_place:" + json.dumps(diagnosis, sort_keys=True)
        except (OSError, ValueError, RuntimeError, TypeError) as exc:
            prior_problem = "installed_runtime_manifest_unavailable:" + str(exc)
    if prior_problem is None:
        executable_path, executable_hash, executable_problem = _host_install_executable(home, executable, executable_sha256)
    else:
        executable_path, executable_hash, executable_problem = None, None, prior_problem
    if executable_problem is not None:
        manual.append(executable_problem)
    runtime_bytes: bytes | None = None
    runtime_hash: str | None = None
    previous_runtime: tuple[bytes, Path] | None = None
    if executable_path is not None:
        try:
            runtime_bytes = runtime_identity.manifest_bytes(executable_path)
            runtime_hash = runtime_identity.manifest_identity(runtime_bytes)
            if json.loads(runtime_bytes)["executable_sha256"] != executable_hash:
                raise ValueError("Thaliris launcher changed while installing")
            if runtime_identity._is_link(manifest_path) or (manifest_path.exists() and not manifest_path.is_file()):
                raise ValueError("unsafe installed runtime manifest path")
            if manifest_path.exists():
                runtime_identity._safe_file(manifest_path)
                previous = manifest_path.read_bytes()
                old = runtime_identity.validate_manifest_record(previous)
                old_executable = Path(old["executable"])
                if old_executable == executable_path and previous != runtime_bytes:
                    raise ValueError("installed runtime changed in place; install a new runtime directory")
                if old_executable != executable_path:
                    previous_runtime = (previous, old_executable)
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            manual.append(f"installed_runtime_identity_unavailable:{exc}")
            runtime_bytes = None
            runtime_hash = None
    script_bytes = host_hook_script_bytes()
    run_script_bytes = host_run_script_bytes(executable_path, runtime_hash) if executable_path is not None and runtime_hash is not None else None
    unsafe_script_path = any(character in str(script_path) for character in ('"', "%", "!", "\r", "\n"))
    script_safe = home_safe and not script_path.is_symlink() and not unsafe_script_path
    if unsafe_script_path:
        manual.append("host_hook_script_path_not_safe_for_cmd_trampoline")
    if script_safe and script_path.exists():
        try:
            existing_script = script_path.read_bytes()
            if existing_script not in {script_bytes, lifecycle._v041_host_hook_script_bytes(), lifecycle._previous_host_hook_script_bytes(), lifecycle._legacy_host_hook_script_bytes()}:
                manual.append(str(script_path))
                script_safe = False
        except OSError:
            manual.append(str(script_path))
            script_safe = False
    elif script_path.is_symlink():
        manual.append(str(script_path))
        script_safe = False

    if preflight_path.is_symlink() or (preflight_path.exists() and
            (not preflight_path.is_file() or preflight_path.read_bytes() != host_preflight.script_bytes())):
        manual.append(str(preflight_path))
        script_safe = False

    if run_script_path.is_symlink() or (run_script_path.exists() and not run_script_path.is_file()):
        manual.append(str(run_script_path))
        script_safe = False
    elif run_script_path.exists() and run_script_bytes is not None:
        permitted = {run_script_bytes}
        if not manifest_path.exists() and lifecycle.installed_run_script_identity(run_script_path.read_bytes()) is not None:
            permitted.add(run_script_path.read_bytes())
        if manifest_path.is_file() and not manifest_path.is_symlink():
            try:
                prior = manifest_path.read_bytes()
                prior_record = runtime_identity.validate_manifest_record(prior)
                permitted.add(host_run_script_bytes(Path(prior_record["executable"]), runtime_identity.manifest_identity(prior)))
                permitted.add(lifecycle._v041_host_run_script_bytes(Path(prior_record["executable"]), runtime_identity.manifest_identity(prior)))
                permitted.add(lifecycle._previous_host_run_script_bytes(Path(prior_record["executable"]), runtime_identity.manifest_identity(prior)))
            except (OSError, ValueError, TypeError):
                pass
        if run_script_path.read_bytes() not in permitted:
            manual.append(str(run_script_path))
            script_safe = False

    hook_bytes: bytes | None = None
    if executable_path is not None and executable_hash is not None and runtime_hash is not None and script_safe and not hooks_path.is_symlink() and home_safe:
        try:
            if hooks_path.exists():
                original = json.loads(hooks_path.read_text(encoding="utf-8"))
                if not isinstance(original, dict):
                    raise ValueError("Host hooks.json must contain an object")
            else:
                original = {}
            merged, hooks_changed, hook_manual = merge_host_hooks(
                original, home, executable_path, executable_hash, runtime_hash
            )
            if hook_manual:
                manual.extend(str(hooks_path) + ":" + item for item in hook_manual)
            else:
                if previous_runtime is not None:
                    audit = _write_runtime_audit(home, *previous_runtime)
                    changed = True
                    files.append(audit.name)
                if runtime_bytes is not None and (not manifest_path.exists() or manifest_path.read_bytes() != runtime_bytes):
                    _atomic_host_write(manifest_path, runtime_bytes)
                    changed = True
                    files.append(runtime_identity.MANIFEST_NAME)
                if hooks_changed:
                    hook_bytes = (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                if not script_path.exists() or script_path.read_bytes() != script_bytes:
                    _atomic_host_write(script_path, script_bytes)
                    changed = True
                    if HOST_HOOK_SCRIPT_NAME not in files:
                        files.append(HOST_HOOK_SCRIPT_NAME)
                if not preflight_path.exists():
                    _atomic_host_write(preflight_path, host_preflight.script_bytes())
                    changed = True
                    files.append(host_preflight.NAME)
                if run_script_bytes is not None and (not run_script_path.exists() or run_script_path.read_bytes() != run_script_bytes):
                    _atomic_host_write(run_script_path, run_script_bytes)
                    changed = True
                    files.append(HOST_RUN_SCRIPT_NAME)
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
    if runtime_hash is not None and script_safe and run_script_path.is_file() and home_safe and not global_agents.is_symlink() and (not global_agents.exists() or global_agents.is_file()):
        try:
            current_agents = global_agents.read_bytes() if global_agents.exists() else b""
            updated_agents = _global_agents_update(
                current_agents, executable=executable_path, executable_sha256=executable_hash, codex_home=home
            )
            if updated_agents != current_agents:
                _atomic_host_write(global_agents, updated_agents)
                changed = True
                files.append("AGENTS.md")
            global_instruction_ready = True
        except (OSError, ValueError):
            manual.append(str(global_agents))
    elif runtime_hash is not None:
        manual.append(str(global_agents))

    health = lifecycle.host_hooks_health(home)
    trust_status = "NOT_REGISTERED"
    trusted_count = 0
    enabled_count = 0
    expected_count = len(lifecycle.HOOK_EVENTS)
    trust_error: str | None = None
    if health["hooks_configured"] == "YES" and executable_path is not None and executable_hash is not None and runtime_hash is not None:
        try:
            trust = _install_host_hook_trust(home, executable_path, executable_hash, runtime_hash)
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
    restart_needed = host_integration_ready and global_instruction_ready and changed
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
        "installed_runtime_identity": runtime_hash if health["hooks_configured"] == "YES" else "UNKNOWN",
        "install_status": "RESTART_CODEX_ONCE" if restart_needed else "HOST_INTEGRATION_UNCHANGED" if host_integration_ready and global_instruction_ready else "INSTALL_INCOMPLETE",
        "session_restart_required": restart_needed,
        "host_setup_requires_session_start": bool(files),
        "project_files_touched": [],
        **_controller_bridge(),
    }


def codex_uninstall(codex_home: Path | None = None) -> dict[str, object]:
    """Remove exact Thaliris-owned Host integration and global instruction."""
    home = _codex_home(codex_home)
    manual: list[str] = []
    removed: list[str] = []
    audit_records: list[str] = []
    hooks_path = home / "hooks.json"
    script_path = home / HOST_HOOK_SCRIPT_NAME
    run_script_path = home / HOST_RUN_SCRIPT_NAME
    manifest_path = home / runtime_identity.MANIFEST_NAME
    # cmd.exe resumes reading a running .cmd by pathname. Removing that file
    # inside its own child process makes the caller fail after a successful
    # uninstall, so leave an inert launcher for later direct cleanup.
    invoked_runner = os.environ.get("THALIRIS_RUN_SCRIPT")
    self_invoked = bool(invoked_runner and Path(invoked_runner) == run_script_path)
    retained_inert_runner = False
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
                    host_hook_script_bytes(), lifecycle._v041_host_hook_script_bytes(), lifecycle._previous_host_hook_script_bytes(), lifecycle._legacy_host_hook_script_bytes()
                }:
                    script_path.unlink()
                    removed.append(HOST_HOOK_SCRIPT_NAME)
                else:
                    manual.append(str(script_path))
            except OSError:
                manual.append(str(script_path))
    if not has_hook_manual and run_script_path.exists():
        if run_script_path.is_symlink() or manifest_path.is_symlink():
            manual.append(str(run_script_path))
        else:
            try:
                prior_runner = False
                if manifest_path.is_file():
                    prior = manifest_path.read_bytes()
                    record = runtime_identity.validate_manifest_record(prior)
                    expected = host_run_script_bytes(Path(record["executable"]), runtime_identity.manifest_identity(prior))
                    prior_bytes = lifecycle._previous_host_run_script_bytes(Path(record["executable"]), runtime_identity.manifest_identity(prior))
                    runner_bytes = run_script_path.read_bytes()
                    prior_runner = runner_bytes == prior_bytes
                    owned = runner_bytes in {
                        expected,
                        prior_bytes,
                        lifecycle._v041_host_run_script_bytes(Path(record["executable"]), runtime_identity.manifest_identity(prior)),
                    }
                else:
                    owned = lifecycle.installed_run_script_identity(run_script_path.read_bytes()) is not None
                if not owned:
                    manual.append(str(run_script_path))
                elif self_invoked or prior_runner:
                    # The previous exact runner did not set THALIRIS_RUN_SCRIPT.
                    # It may be executing this uninstall; preserve it until a
                    # later direct call after its manifest has been removed.
                    retained_inert_runner = True
                else:
                    run_script_path.unlink()
                    removed.append(HOST_RUN_SCRIPT_NAME)
            except (OSError, ValueError, TypeError):
                manual.append(str(run_script_path))
    preflight_path = home / host_preflight.NAME
    if not has_hook_manual and preflight_path.exists() and (not run_script_path.exists() or retained_inert_runner):
        if not preflight_path.is_symlink() and preflight_path.is_file() and preflight_path.read_bytes() == host_preflight.script_bytes():
            preflight_path.unlink()
            removed.append(host_preflight.NAME)
        else:
            manual.append(str(preflight_path))
    if not has_hook_manual and not script_path.exists() and (not run_script_path.exists() or retained_inert_runner) and manifest_path.exists():
        if manifest_path.is_symlink() or not manifest_path.is_file():
            manual.append(str(manifest_path))
        else:
            try:
                contents = manifest_path.read_bytes()
                installed = runtime_identity.validate_manifest_record(contents)
                old_executable = Path(installed["executable"])
                try:
                    runtime_identity.validate_manifest(contents, old_executable, runtime_identity.manifest_identity(contents))
                except (OSError, RuntimeError, ValueError):
                    try:
                        audit = _write_runtime_audit(home, contents, old_executable)
                        audit_records.append(audit.name)
                    except OSError:
                        pass
                manifest_path.unlink()
                removed.append(runtime_identity.MANIFEST_NAME)
            except (OSError, ValueError, TypeError):
                manual.append(str(manifest_path))
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
    inert_runner = retained_inert_runner and not manifest_path.exists() and health["hooks_configured"] == "NO"
    complete = trust_cleanup_status != "FAILED" and str(global_agents) not in manual and not manifest_path.exists() and health["hooks_configured"] == "NO"
    return {
        "ok": complete,
        "status": "UNINSTALLED_INERT_RUNNER_RETAINED" if complete and inert_runner else "UNINSTALLED" if complete else "UNINSTALL_INCOMPLETE",
        "changed": bool(removed),
        "target": str(home),
        "files": sorted(removed),
        "runtime_audit_records": audit_records,
        "manual_action_required": sorted(set(manual)),
        "host_hook_registration_present": health["hooks_configured"],
        "host_hook_trust_cleanup_status": trust_cleanup_status,
        "host_hook_trusted_state_removed": trust_removed,
        "host_hook_trust_cleanup_error": trust_cleanup_error,
        "host_profile_definition_present": _host_profile_definition_present(home),
        "host_role_catalog_status": lifecycle.HOST_ROLE_CATALOG_UNKNOWN,
        "retained_inert_runner": inert_runner,
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
    # Diagnose an existing incompatible ledger before consuming a one-shot
    # Host attestation. Core still validates it again under the task-start lock.
    try:
        core._load_state(root)
    except core.TaskStateSchemaIncompatible as exc:
        return task_state_schema_error(root, exc)
    except ValueError:
        pass
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
    if session_hash is not None:
        lifecycle.record_task_start_owner(root, str(result["task_id"]), session_hash)
    result["managed_readiness"] = {**readiness, **_activation_fields(root), "CONTROLLER_ACTIVATION_BRIDGE_ACTIVE": "YES" if hook_attestation is not None else "NOT_APPLICABLE", "HOST_INSTRUCTION_ACTIVE": "UNKNOWN", "controller_activation_bridge": "ACTIVE" if hook_attestation is not None else "NOT_APPLICABLE", "host_instruction_activation": "UNKNOWN", "role_catalog_session_status": catalog_status if hook_attestation is not None else "NOT_APPLICABLE"}
    return result


def task_abandon(
    root: Path, task_id: str, revision: int, state_sha256: str,
    lifecycle_sha256: str, reason: str, hook_attestation: str | None,
) -> dict[str, object]:
    """Use a current Hook PreToolUse proof for explicit ACTIVE takeover."""
    root = core._repo_root(root)
    session_hash, proof_hash = lifecycle.consume_task_abandon_attestation(root, hook_attestation)
    return lifecycle.task_abandon(
        root, task_id, revision, state_sha256, lifecycle_sha256,
        reason, session_hash, proof_hash,
    )


def task_state_schema_error(root: Path, error: core.TaskStateSchemaIncompatible) -> dict[str, object]:
    """Add lifecycle recoverability without exposing the archived task ID."""
    result = dict(error.diagnostic)
    if result.get("recoverable") is True:
        result["recovery_action"] = (
            f"{result['recovery_action']} --controller-bridge-sha256 <current-bridge-sha256>"
        )
    if result.get("recoverable") is True and error.task_id is not None:
        blocker = lifecycle.task_state_recovery_blocker(core._repo_root(root), error.task_id)
        if blocker is not None:
            result["recoverable"] = False
            result["recovery_action"] = "NONE"
            result["recovery_blocker"] = blocker
    return result


def task_recover_state(
    root: Path,
    expected_sha256: str,
    abandon_active: bool,
    hook_attestation: str | None,
    controller_bridge_sha256: str | None,
) -> dict[str, object]:
    """Archive one exact incompatible ledger before a separately attested task-start."""
    root = core._repo_root(root)
    definition = _project_definition_facts(root)
    if definition["project_definition_present"] != "YES":
        return {
            "ok": False,
            "status": "BOOTSTRAP_REQUIRED",
            "bootstrap": {
                **definition,
                "init_required": True,
                "session_restart_required": "UNKNOWN",
                "same_session_task_start": "UNKNOWN",
                "managed_runtime_after_restart": "UNVERIFIED",
            },
        }
    executable = lifecycle.managed_executable_health()
    if executable["canonical_executable_available"] != "YES":
        return {
            "ok": False,
            "status": "BOOTSTRAP_REQUIRED",
            "bootstrap": {
                **definition,
                **executable,
                "init_required": False,
                "session_restart_required": False,
                "manual_action_required": "canonical_executable_unavailable",
            },
        }
    bridge = _controller_bridge()
    if controller_bridge_sha256 != bridge["controller_bridge_sha256"]:
        return {
            "ok": False,
            "status": "CONTROLLER_BRIDGE_REQUIRED",
            "expected_controller_bridge_sha256": bridge["controller_bridge_sha256"],
            "host_instruction_activation": "UNKNOWN",
        }
    session_hash = lifecycle.consume_task_start_attestation(
        root,
        hook_attestation,
        controller_bridge_sha256,
    )
    catalog_status = lifecycle.role_catalog_session_status(root, session_hash)
    if catalog_status == lifecycle.NEW_ROLE_CATALOG_IDENTITY_NOT_ACTIVE:
        return {
            "ok": False,
            "status": catalog_status,
            "new_role_profile_files": lifecycle.new_role_profile_files(root, session_hash),
            "host_instruction_activation": "UNKNOWN",
        }
    if selected_continuation_mode(root) == "UNAVAILABLE":
        return {"ok": False, "status": "MANAGED_CONTINUATION_UNAVAILABLE"}

    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("expected task state SHA-256 must be 64 lowercase hexadecimal characters")
    state_name = ".context/state.json"
    core._safe_without_final_symlink(root, state_name)

    with core._lock(root):
        state_path = core._state_path(root)
        if not state_path.is_file():
            return {"ok": False, "status": "NO_INCOMPATIBLE_TASK_STATE", "recoverable": False}
        if state_path.stat().st_size > 512 * 1024:
            return {
                "ok": False,
                "status": "STATE_SCHEMA_INCOMPATIBLE",
                "from_version": "UNKNOWN",
                "to_version": core._STATE_SCHEMA_VERSION,
                "recoverable": False,
                "recovery_action": "NONE",
                "error": "task state exceeds 512 KiB",
            }
        raw_bytes = state_path.read_bytes()
        digest = hashlib.sha256(raw_bytes).hexdigest()
        if digest != expected_sha256:
            return {
                "ok": False,
                "status": "TASK_STATE_CHANGED",
                "expected_sha256": expected_sha256,
                "observed_sha256": digest,
                "recovered": False,
            }
        try:
            raw = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {
                "ok": False,
                "status": "STATE_SCHEMA_INCOMPATIBLE",
                "from_version": "UNKNOWN",
                "to_version": core._STATE_SCHEMA_VERSION,
                "state_sha256": digest,
                "recoverable": False,
                "recovery_action": "NONE",
                "error": "task state is not valid UTF-8 JSON",
            }
        diagnostic = core._task_state_schema_diagnostic(raw, raw_bytes)
        if diagnostic is None:
            return {
                "ok": False,
                "status": "STATE_SCHEMA_NOT_RECOVERABLE",
                "to_version": core._STATE_SCHEMA_VERSION,
                "state_sha256": digest,
                "recoverable": False,
                "recovery_action": "NONE",
            }
        if diagnostic["recoverable"] is not True:
            return diagnostic
        if raw.get("status") == "ACTIVE" and not abandon_active:
            return {
                **diagnostic,
                "ok": False,
                "status": "STATE_ABANDON_CONFIRMATION_REQUIRED",
                "recovery_action": f"thaliris task-recover-state --expected-sha256 {digest} --abandon-active --controller-bridge-sha256 <current-bridge-sha256>",
            }
        task_id = raw.get("task_id")
        blocker = lifecycle.task_state_recovery_blocker(root, task_id)
        if blocker is not None:
            return {
                **diagnostic,
                "ok": False,
                "status": "STATE_RECOVERY_BLOCKED",
                "recoverable": False,
                "recovery_action": "NONE",
                "recovery_blocker": blocker,
            }
        version = diagnostic["from_version"]
        archive_relative = f".context/recovery/task-state-v{version}-{digest}.json"
        archive_path = core._safe_without_final_symlink(root, archive_relative)
        if archive_path.exists():
            if not archive_path.is_file() or archive_path.read_bytes() != raw_bytes:
                return {
                    "ok": False,
                    "status": "STATE_ARCHIVE_COLLISION",
                    "state_sha256": digest,
                    "recoverable": False,
                    "recovery_action": "NONE",
                }
            writes: dict[str, bytes] = {}
        else:
            writes = {archive_relative: raw_bytes}
        backup = core._apply_with_backup(root, writes, [state_name], "task-state-recovery")
    return {
        "ok": True,
        "status": "STATE_ARCHIVED_FOR_RECOVERY",
        "from_version": version,
        "to_version": core._STATE_SCHEMA_VERSION,
        "state_sha256": digest,
        "preserved_state_location": archive_relative,
        "backup": backup,
        "recovered": True,
        "next_action": "bootstrap-check, then a fresh attested task-start",
    }
def bootstrap_check(root: Path) -> dict[str, object]:
    """Return the read-only facts needed by the external Codex bootstrap.

    This deliberately performs no initialization and creates no durable state;
    the host entrypoint uses it to decide whether one direct ``init`` call is
    necessary before handing control back to the Controller.
    """
    root = core._repo_root(root)
    facts = _project_definition_facts(root)
    definition_recovery_status = (
        "READY" if facts["project_definition_present"] == "YES"
        else "EXPLICIT_CONFIRMATION_REQUIRED" if facts.get("managed_instruction_state") == "USER"
        else "INIT_REQUIRED"
    )
    return {"ok": True, **facts, "definition_recovery_status": definition_recovery_status, **_controller_bridge(), "managed_hook_abi": lifecycle.MANAGED_HOOK_ABI, "executable_adapter_protocol_version": lifecycle.CODEX_ADAPTER_PROTOCOL_VERSION, "session_restart_required": False}


def task_close(root: Path, base_revision: int) -> dict[str, object]:
    state = core.task_show(root)["state"]
    task_id = str(state["task_id"])
    if not lifecycle.qualifying_child_completed(core._repo_root(root)):
        raise ValueError("task-close requires an authorized explicit handoff, a matching native SubagentStart/Stop identity, and no pending or active managed work; after child completion, use list_agents to observe an exact name-bound native Completed status")
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
    home = _codex_home()
    manifest = home / runtime_identity.MANIFEST_NAME
    runtime_drift = (runtime_identity.diagnose_manifest(manifest.read_bytes())
                     if manifest.is_file() and not manifest.is_symlink()
                     else {"status": "UNKNOWN", "execution_assurance": "UNKNOWN", "error": "installed manifest unavailable"})
    definitions = []
    for name, expected in ((HOST_HOOK_SCRIPT_NAME, host_hook_script_bytes()),
                           (host_preflight.NAME, host_preflight.script_bytes())):
        path = home / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else "UNKNOWN"
        wanted = hashlib.sha256(expected).hexdigest()
        definitions.append({"surface": "hook", "path": name, "expected": wanted, "actual": actual,
                            "status": "MATCH" if actual == wanted else "UNKNOWN" if actual == "UNKNOWN" else "CHANGED"})
    profiles = []
    for name, (model, effort, role) in _agent_profiles().items():
        path = home / "agents" / name
        actual = path.read_bytes() if path.is_file() and not path.is_symlink() else None
        expected = _agent_profile(name.removesuffix(".toml"), role, model, effort)
        profiles.append({"surface": "profile", "path": name,
                         "ownership": _agent_profile_state(actual, name) if actual is not None else "missing",
                         "expected": hashlib.sha256(expected).hexdigest(),
                         "actual": hashlib.sha256(actual).hexdigest() if actual is not None else "UNKNOWN"})
    result["drift_evidence"] = {"installed_runtime": runtime_drift, "hook_definitions": definitions,
                                "profile_definitions": profiles, "ordinary_workspace_work_allowed": True,
                                "user_configuration": "PRESERVE_UNLESS_EXPLICITLY_AUTHORIZED",
                                "cli_version": host_wait_mode().get("version", "UNKNOWN"),
                                "daemon_version": "UNKNOWN", "daemon_control_authority": "UNKNOWN",
                                "controller_actor_assurance": lifecycle._controller_actor_assurance({}),
                                "host_topology": "UNKNOWN",
                                "decision": "CONTROLLER_REPAIR_RESTORE_OR_ACCEPT_WITHIN_USER_AUTHORIZATION"}
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
