# Core and Host adapters

The `thaliris` distribution retains `thaliris.core`, `thaliris.authority`,
`thaliris.models` and `thaliris.markdown`. `thaliris-core` exposes neutral record
operations with opaque actor labels. These calls perform schema, identity, CAS,
freshness and provenance checks; authorization and semantic completion belong to
the invoking adapter and Controller. Core imports no Host adapter.

The separate `thaliris-codex` distribution exposes `thaliris_codex` and the
`thaliris` / `context` Codex command aliases. It depends on shared Core; it does
not bundle a Core copy. Native admission, lifecycle, doctor, Hook trust,
bootstrap, runtime identity and generated profiles belong to that package.

The shared Core baseline validated with the split Codex adapter is commit
[`da663e86ffea1fc8d09ea9bbec3ec8da21eeef34`](https://github.com/Iris0fTheValley/Thaliris/tree/da663e86ffea1fc8d09ea9bbec3ec8da21eeef34).
Pin this revision for reproducible installs of that validated Core/adapter
package boundary:

```sh
python -m pip install 'git+https://github.com/Iris0fTheValley/Thaliris.git@da663e86ffea1fc8d09ea9bbec3ec8da21eeef34'
```

Core installation does not install or configure a Host adapter. For local tests:

```sh
python -m venv .venv
# Activate the isolated environment using your platform's normal command.
python -m pip install -e '.[test]'
pytest tests/test_core_authority.py tests/test_mechanical_core.py tests/test_core_cli.py
# Explicit optional Codex dependency for benchmark source tests:
python -m pip install --no-deps -e ../Thaliris-Codex
pytest tests/test_benchmark_protocol.py tests/test_d11_collector.py
```

The current ABCD/D11 implementation remains in `benchmarks/abcd`; its Host
imports use the explicit optional Codex package. These source tests do not
perform a benchmark or evaluator run. Historical branch evidence is inert under
`benchmarks/abcd/historical`, with exact source commit, Git blob and SHA-256
identities. No historical supervisor or Core implementation is installed.

For actual Host setup follow [Codex](https://github.com/Iris0fTheValley/Thaliris-codex)
or [DSH](https://github.com/Iris0fTheValley/Thaliris-dsh). Do not infer a live or
trusted Host from package installation or a generated profile file.
