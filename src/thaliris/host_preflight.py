"""Pinned platform preflight, independent of the installed Python runtime.

No changed runtime code is invoked for diagnosis or recovery admission. The
Host's structured hook payload, not process ancestry or environment, supplies
the actor. No ambiguous actor can gain dangerous control authority from this preflight.
Offline operator administration is a distinct disconnected source route.
"""
from __future__ import annotations

import base64
import hashlib
import gzip
import io
import zlib

NAME = "thaliris-preflight.ps1"


def degraded_source() -> str:
    """Small inline policy also survives a damaged preflight/trampoline."""
    source = r'''
function Present($path) {
  try { $null=[IO.File]::GetAttributes($path); return $true }
  catch [IO.FileNotFoundException] { return $false }
  catch [IO.DirectoryNotFoundException] { return $false }
}
function Unlinked($path) {
  while ($path) {
    if ((Present $path) -and (([IO.File]::GetAttributes($path) -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { throw 'linked observation path' }
    $path=[IO.Path]::GetDirectoryName($path)
  }
}
function FreshUnmanaged($h) {
  try {
    if ($null -ne $h.agent_id -or $null -ne $h.agent_type) { return $false }
    $i=$h.tool_input
    if ($i.fork_turns -cne 'none' -or $i.agent_type -cnotmatch '^thaliris-(investigator|curator|implementer|focused-implementer|reasoning-specialist|reviewer|verifier)$' -or $null -ne $i.model -or $null -ne $i.reasoning_effort) { return $false }
    $path=[Environment]::CurrentDirectory
    if ($h.cwd -and [IO.Path]::GetFullPath([string]$h.cwd) -ine $path) { return $false }
    while ($path -and -not (Present (Join-Path $path '.git'))) { $path=[IO.Path]::GetDirectoryName($path) }
    if (-not $path) { return $false }
    Unlinked (Join-Path $path '.git')
    # Only safely absent state is admitted without importing runtime schema.
    # Existing fences stay conservative; no actor gains a managed grant.
    foreach ($name in @('.context/state.json','.context/audit/abandoned/session-fence.json','.context/audit/abandoned-child-fence.json')) {
      $p=Join-Path $path $name; Unlinked $p; if (Present $p) { return $false }
    }
    return $true
  } catch { return $false }
}
function Degraded($detail) {
  if ($env:THALIRIS_HOOK_EVENT -cne 'PreToolUse') { return }
  try { $h=[Console]::In.ReadToEnd()|ConvertFrom-Json } catch { $h=$null }
  $tool=[string]$h.tool_name; if (-not $tool) { $tool=[string]$h.tool }
  $inputJson=$h.tool_input|ConvertTo-Json -Depth 32 -Compress
  $command=[string]$h.tool_input.command; if (-not $command) { $command=[string]$h.tool_input.cmd }
  $control=$command -match '(?i)(?:^|[;&|])\s*&?\s*["'']?(?:[^\s"'';|&]*[\\/])?(?:python[0-9.]*(\.exe)?|py(\.exe)?)["'']?\s+(-[IB]\s+)*(["'']?[^\r\n]*thaliris_offline_recovery\.py\b|-m\s+thaliris\.offline_recovery\b)'
  if ($tool -match '(?i)(spawn_agent|followup_task|send_input|send_message|Agent)$') {
    $control=$true
    if ($tool -match '(?i)(?:^|[._:/])spawn_agent$' -and (FreshUnmanaged $h)) { $control=$false }
  }
  $write=$tool -match '(?i)(apply_patch|file_change|write|edit|delete|move|rename)$'
  if ($tool -match '(?i)(Bash|exec_command|exec)$' -and $command -match '(?i)(Set-Content|Add-Content|Out-File|Remove-Item|Move-Item|Copy-Item|New-Item|apply_patch|git\s+(apply|reset|restore|checkout)|[>])') { $write=$true }
  if ($write -and $inputJson -match '(?i)\.context[\\/]+(state\.json|audit[\\/]+(lifecycle|abandoned|external-recovery))') { $control=$true }
  if ($command -match '(?i)^\s*&?\s*["'']?(thaliris(\.exe|\.cmd)?)["'']?\s' -and $command -match '(?i)\b(task-start|task-abandon|task-recover-state|task-recover-external|task-update|task-close|task-promote|task-artifact|recover-pending-spawn)\b') { $control=$true }
  if ($command -and $env:THALIRIS_EXECUTABLE -and $command -match ('^\s*&?\s*["'']?'+[regex]::Escape($env:THALIRIS_EXECUTABLE)+'["'']?\s')) { $control=$true }
  if ($write -and [string]$h.agent_type -match '^thaliris-(reviewer|verifier)$') { $control=$true }
  $o=@{hookEventName='PreToolUse';additionalContext=('THALIRIS_RUNTIME_DRIFT: '+$detail+'; assurance UNKNOWN. Diagnose and decide; ordinary workspace work remains available.')}
  if ($control) { $o.permissionDecision='deny';$o.permissionDecisionReason='THALIRIS_CONTROL_AUTHORITY_UNAVAILABLE: '+$detail }
  @{hookSpecificOutput=$o}|ConvertTo-Json -Depth 32 -Compress|Write-Output
}
'''
    for old, new in (("$inputJson", "$j"), ("$command", "$c"), ("$control", "$d"), ("$detail", "$e"), ("$path", "$x"), ("FreshUnmanaged", "Fresh"), ("Present", "Exists"), ("Unlinked", "Safe")):
        source = source.replace(old, new)
    return "\n".join(line.strip() for line in source.splitlines() if line.strip() and not line.lstrip().startswith("#"))


def script_bytes() -> bytes:
    return (r'''$ErrorActionPreference='Stop'
function HashBytes($bytes) {
  $sha=[Security.Cryptography.SHA256]::Create()
  try { return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant() }
  finally { $sha.Dispose() }
}
function FileHash($path) { return HashBytes ([IO.File]::ReadAllBytes($path)) }
function SafePath($path) {
  $item=Get-Item -LiteralPath $path -Force
  while ($null -ne $item) {
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw ('linked path: '+$path) }
    if ($item -is [IO.FileInfo]) { $item=$item.Directory } else { $item=$item.Parent }
  }
}
''' + degraded_source() + r'''
try {
  $manifest=$env:THALIRIS_INSTALL_MANIFEST; $identity=$env:THALIRIS_RUNTIME_SHA256; $exe=$env:THALIRIS_EXECUTABLE
  SafePath $manifest
  if ($identity -cnotmatch '^[0-9a-f]{64}$' -or (FileHash $manifest) -cne $identity) { throw ('manifest expected='+$identity+' actual='+(FileHash $manifest)) }
  $m=Get-Content -LiteralPath $manifest -Raw -Encoding UTF8|ConvertFrom-Json
  if ($m.format -cne 'thaliris-installed-runtime-v1' -or $m.executable -cne $exe) { throw 'manifest topology mismatch' }
  SafePath $exe; SafePath $m.venv_dir; SafePath $m.package_dir
  $venv=(Get-Item -LiteralPath $m.venv_dir).FullName
  if (-not $exe.StartsWith($venv+'\',[StringComparison]::OrdinalIgnoreCase) -or -not $m.package_dir.StartsWith($venv+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'runtime topology outside pinned venv' }
  $expected=@{}; foreach ($e in $m.files.PSObject.Properties) {
    if ($e.Name -match '(^|/)\.\.?(/|$)|\\|^/|:' -or $e.Value -cnotmatch '^[0-9a-f]{64}$') { throw 'invalid manifest entry' }
    $expected[$e.Name]=$e.Value
  }
  if (-not $expected.ContainsKey('pyvenv.cfg')) { throw 'missing venv configuration pin' }
  $seen=@{}; $diff=[Collections.Generic.List[object]]::new()
  foreach ($item in (Get-ChildItem -LiteralPath $venv -Recurse -Force)) {
    SafePath $item.FullName
    if ($item.PSIsContainer) { continue }
    $relative=$item.FullName.Substring($venv.Length).TrimStart('\').Replace('\','/')
    $actual=FileHash $item.FullName; $wanted=$expected[$relative]
    if (-not $wanted) { $wanted='ABSENT' }
    if ($actual -cne $wanted) { $diff.Add(@{path=$relative;expected=$wanted;actual=$actual;surface=$(if($relative.EndsWith('.pyc')){'python_bytecode'}else{'runtime'})}) }
    $seen[$relative]=$true
  }
  foreach ($name in $expected.Keys) { if (-not $seen.ContainsKey($name)) { $diff.Add(@{path=$name;expected=$expected[$name];actual='ABSENT';surface='runtime'}) } }
  if ($diff.Count) { throw ($diff|ConvertTo-Json -Depth 8 -Compress) }
  if ((FileHash $exe) -cne $m.executable_sha256) { throw 'launcher manifest hash mismatch' }
  $config=Get-Content -LiteralPath (Join-Path $venv 'pyvenv.cfg') -Raw
  if ($config -notmatch '(?im)^\s*include-system-site-packages\s*=\s*false\s*$') { throw 'system site packages enabled' }
  foreach ($pth in (Get-ChildItem -LiteralPath $venv -Recurse -Force -Filter '*.pth' -File)) {
    foreach ($line in (Get-Content -LiteralPath $pth.FullName)) { if ($line.Trim() -and -not $line.TrimStart().StartsWith('#')) { throw 'external .pth execution or import path' } }
  }
  exit 0
} catch {
  $detail=$_.Exception.Message
  if ($env:THALIRIS_HOOK_EVENT -ceq 'PreToolUse') {
    $raw=[Console]::In.ReadToEnd()
    # Degraded reads Console.In; supply the already consumed payload directly.
    $reader=[IO.StringReader]::new($raw); [Console]::SetIn($reader)
    Degraded $detail
  } elseif (-not $env:THALIRIS_HOOK_EVENT) {
    @{ok=$false;status='THALIRIS_RUNTIME_IDENTITY_MISMATCH';execution_assurance='UNKNOWN';diagnostic=$detail;decision_required=$true}|ConvertTo-Json -Depth 32 -Compress|Write-Output
  }
  exit 1
}
''').encode("utf-8")


def encoded_entry() -> str:
    """Keep cmd's physical command line comfortably below its 8191 limit."""
    digest = hashlib.sha256(script_bytes()).hexdigest()
    source = (
        "$ErrorActionPreference='Stop';try{"
        "$p=$env:THALIRIS_PREFLIGHT;"
        "$s=[Security.Cryptography.SHA256]::Create();"
        "try{$a=([BitConverter]::ToString($s.ComputeHash([IO.File]::ReadAllBytes($p)))).Replace('-','').ToLowerInvariant()}finally{$s.Dispose()};"
        f"if($a -cne '{digest}'){{throw 'preflight hash mismatch'}};"
        "& $p;exit $LASTEXITCODE}catch{"
        + inline_degraded()
        + "if($env:THALIRIS_HOOK_EVENT){Degraded ('platform preflight unavailable: '+$_.Exception.Message)}else{"
        + "@{ok=$false;status='THALIRIS_RUNTIME_IDENTITY_MISMATCH';execution_assurance='UNKNOWN';diagnostic=$_.Exception.Message}|ConvertTo-Json -Compress|Write-Output};exit 1}"
    )
    return base64.b64encode(source.encode("utf-16le")).decode("ascii")


def inline_degraded() -> str:
    """Pinned literal policy compressed to fit cmd's physical line limit.

    Only this generated literal is evaluated, never hook input or disk code.
    """
    return packed_literal(degraded_source())


_PACKED_PREFIX = "$r=[IO.StreamReader]::new([IO.Compression.GZipStream]::new([IO.MemoryStream]::new([Convert]::FromBase64String('"
_PACKED_SUFFIX = "')),[IO.Compression.CompressionMode]::Decompress));try{iex $r.ReadToEnd()}finally{$r.Dispose()};"
_VARIABLE_FREE_PACKED_PREFIX = "iex ([IO.StreamReader]::new([IO.Compression.GZipStream]::new([IO.MemoryStream]::new([Convert]::FromBase64String('"
_VARIABLE_FREE_PACKED_SUFFIX = "')),[IO.Compression.CompressionMode]::Decompress)).ReadToEnd())"


def packed_literal(source: str) -> str:
    """Encode only generated literal code, including the outer Host command."""
    data = base64.b64encode(gzip.compress(source.encode(), mtime=0)).decode()
    return _PACKED_PREFIX + data + _PACKED_SUFFIX


def packed_literal_without_variables(source: str) -> str:
    """Pack generated code behind a loader safe inside nested PowerShell quotes."""
    data = base64.b64encode(gzip.compress(source.encode(), mtime=0)).decode()
    return _VARIABLE_FREE_PACKED_PREFIX + data + _VARIABLE_FREE_PACKED_SUFFIX


def unpack_literal(source: str) -> str:
    """Decode for exact ownership comparison, never evaluation or authority."""
    if source.startswith(_PACKED_PREFIX):
        prefix, suffix = _PACKED_PREFIX, _PACKED_SUFFIX
    elif source.startswith(_VARIABLE_FREE_PACKED_PREFIX):
        prefix, suffix = _VARIABLE_FREE_PACKED_PREFIX, _VARIABLE_FREE_PACKED_SUFFIX
    else:
        return source
    if not source.endswith(suffix):
        raise ValueError("invalid packed Host literal")
    data = base64.b64decode(source[len(prefix):-len(suffix)], validate=True)
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            raw = stream.read(65537)
    except (OSError, EOFError, zlib.error) as exc:
        raise ValueError("invalid packed Host literal") from exc
    if len(raw) > 65536:
        raise ValueError("oversized packed Host literal")
    return raw.decode("utf-8")
