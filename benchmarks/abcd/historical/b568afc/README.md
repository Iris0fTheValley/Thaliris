# Historical ABCD source

This directory is a safe index to the original ABCD files. The 103 source files, totaling 1,253,422 bytes, remain unchanged in Git history at commit `b568afc34ba4c344d513e13f377cd04aa32b70bf`. This archive lists their repository-relative original paths, Git blob IDs, SHA-256 checksums, and byte counts in [`provenance.json`](provenance.json). It contains no copied run evidence or machine-specific paths.

The source commit is historical evidence. Current benchmark behavior and protocol are described in [`../../../../docs/thaliris-benchmark-protocol.md`](../../../../docs/thaliris-benchmark-protocol.md); historical files are not part of the active benchmark protocol or runnable test suite.

Retrieve one original file from the repository root with:

```powershell
git show b568afc34ba4c344d513e13f377cd04aa32b70bf:<repository-relative-path> > <output-path>
```

For example:

```powershell
git show b568afc34ba4c344d513e13f377cd04aa32b70bf:benchmarks/abcd/README.md > abcd-original-readme.md
```

To retrieve the complete source snapshot at that commit:

```powershell
git archive --format=tar --output=b568afc-source.tar b568afc34ba4c344d513e13f377cd04aa32b70bf
```
