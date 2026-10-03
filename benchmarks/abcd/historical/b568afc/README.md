# Historical ABCD source

This directory is a safe index to the original ABCD files. The 103 source files, totaling 1,253,422 bytes, remain unchanged in Git history at commit `b568afc34ba4c344d513e13f377cd04aa32b70bf`. This archive lists their repository-relative original paths, Git blob IDs, SHA-256 checksums, and byte counts in [`provenance.json`](provenance.json). It contains no copied run evidence or machine-specific paths.

The source commit is historical evidence. Current benchmark behavior and protocol are described in [`../../../../docs/thaliris-benchmark-protocol.md`](../../../../docs/thaliris-benchmark-protocol.md); historical files are not part of the active benchmark protocol or runnable test suite.

Retrieve one original file from the repository root with `git archive`. This
keeps the historical Git object bytes intact on Windows PowerShell as well as
on other platforms:

```powershell
New-Item -ItemType Directory -Force -Path .\historical-original | Out-Null
git archive --format=tar --output=historical-original.tar b568afc34ba4c344d513e13f377cd04aa32b70bf <repository-relative-path>
tar -xf .\historical-original.tar -C .\historical-original
```

For example:

```powershell
New-Item -ItemType Directory -Force -Path .\historical-original | Out-Null
git archive --format=tar --output=historical-original.tar b568afc34ba4c344d513e13f377cd04aa32b70bf benchmarks/abcd/README.md
tar -xf .\historical-original.tar -C .\historical-original
```

The example extracts to `historical-original/benchmarks/abcd/README.md`.

To retrieve the complete source snapshot at that commit:

```powershell
git archive --format=tar --output=b568afc-source.tar b568afc34ba4c344d513e13f377cd04aa32b70bf
```
