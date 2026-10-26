<#
.SYNOPSIS
  Self-check for the PowerAgent pilot kit. Needs no admin rights and changes nothing outside this folder.
.DESCRIPTION
  1. Verifies every file against SHA256SUMS.
  2. Runs the backend probe and the fixture matrix (authorised / denied / unverified network).
  3. Runs one contained task and one denied task through `poweragent run`, then renders the HTML audit report.
  Writes verify-pilot.log next to this script. Exit code 0 only if every check passes.
  Podman sidecars are optional and are NOT exercised here; see docs\03-pilot-runbook.md.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$bin  = Join-Path $root 'bin'
$work = Join-Path $root 'work'
$log  = Join-Path $root 'verify-pilot.log'
$fails = 0
Start-Transcript -Path $log -Force | Out-Null

function Check([string]$name, [bool]$ok, [string]$detail = '') {
    if ($ok) { Write-Host "PASS: $name" } else { Write-Host "FAIL: $name  $detail"; $script:fails++ }
}
function Run-Exe([string]$exe, [string[]]$a) {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'   # a child's stderr is data, not an error
    try { $o = & $exe @a 2>&1 | Out-String; $code = $LASTEXITCODE } finally { $ErrorActionPreference = $old }
    [pscustomobject]@{ Code = $code; Out = $o }
}
function Write-Json([string]$path, $obj) {   # UTF-8 without BOM, on both Windows PowerShell 5.1 and 7
    [IO.File]::WriteAllText($path, ($obj | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding($false)))
}

Write-Host "== Environment"
$cv = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
Write-Host ("Windows build {0}.{1} ({2})" -f $cv.CurrentBuild, $cv.UBR, $cv.DisplayVersion)

Write-Host "== 1. File integrity (SHA256SUMS)"
$sums = Join-Path $root 'SHA256SUMS'
Check 'SHA256SUMS present' (Test-Path $sums)
foreach ($line in Get-Content $sums) {
    if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { continue }
    $f = Join-Path $root $Matches[2]
    $ok = (Test-Path $f) -and ((Get-FileHash $f -Algorithm SHA256).Hash.ToLower() -eq $Matches[1])
    Check "hash $($Matches[2])" $ok
}

Write-Host "== 2. Backend probe and fixture matrix"
$probe = Join-Path $bin 'poweragent-probe.exe'
$fx = Join-Path $root 'fixtures'
$r = Run-Exe $probe @('--profile', "$fx\profile-fs.json", '--policy', "$fx\policy-allow.json")
Check 'authorised fs-only profile -> run on MXC (exit 0)' ($r.Code -eq 0 -and $r.Out -match '"backend": "mxc"') $r.Out
Check 'MXC processcontainer backend reported' ($r.Out -match '"backend": "processcontainer"')
$r = Run-Exe $probe @('--profile', "$fx\profile-fs.json", '--policy', "$fx\policy-empty.json")
Check 'empty policy -> denied (exit 3)' ($r.Code -eq 3 -and $r.Out -match 'capability_not_authorized')
$r = Run-Exe $probe @('--profile', "$fx\profile-net.json", '--policy', "$fx\policy-allow.json")
Check 'network request -> fails closed (exit 3)' ($r.Code -eq 3 -and $r.Out -match 'containment_unavailable')

# Files saved by Notepad or Windows PowerShell 5.1 carry a UTF-8 BOM; they must be accepted.
$bom = Join-Path $root 'work-bom.json'
[IO.File]::WriteAllText($bom, (Get-Content "$fx\profile-fs.json" -Raw), (New-Object Text.UTF8Encoding($true)))
$r = Run-Exe $probe @('--profile', $bom, '--policy', "$fx\policy-allow.json")
Check 'profile saved with a UTF-8 BOM is accepted' ($r.Code -eq 0) $r.Out
Remove-Item $bom -Force -ErrorAction SilentlyContinue

Write-Host "== 3. Contained run, denied run, audit report"
if (Test-Path $work) { Remove-Item $work -Recurse -Force }
$in = Join-Path $work 'in'; $out = Join-Path $work 'out'
New-Item -ItemType Directory -Force -Path $in, $out | Out-Null
[IO.File]::WriteAllBytes((Join-Path $in 'data.bin'), [byte[]](1, 2, 3, 4, 250))
$fw = { param($p) $p.Replace('\', '/') }
$caps = @(
    @{ kind = 'fs_read';  path = (& $fw $in) },
    @{ kind = 'fs_write'; path = (& $fw $out) })
Write-Json (Join-Path $work 'profile.json') @{ apiVersion = 'poweragent.dev/v1alpha1'; kind = 'TaskProfile'; metadata = @{ name = 'pilot-check' }
    spec = @{ untrustedCode = $true; timeoutSeconds = 20; capabilities = $caps } }
Write-Json (Join-Path $work 'policy.json') @{ allowedCapabilities = $caps; allowedFallbacks = @() }
Write-Json (Join-Path $work 'policy-empty.json') @{ allowedCapabilities = @(); allowedFallbacks = @() }
[IO.File]::WriteAllText((Join-Path $work 'registry.json'), '[]', (New-Object Text.UTF8Encoding($false)))

$pa = Join-Path $bin 'poweragent.exe'
$audit = Join-Path $work 'audit.jsonl'
$common = @('--profile', "$work\profile.json", '--registry', "$work\registry.json", '--audit', $audit, '--in', "$in\data.bin")
$r = Run-Exe $pa (@('run') + $common + @('--policy', "$work\policy.json", '--out', "$out\sum.txt"))
Check 'authorised task ran contained (exit 0)' ($r.Code -eq 0) $r.Out
$sum = if (Test-Path "$out\sum.txt") { (Get-Content "$out\sum.txt" -Raw).Trim() } else { '' }
Check 'worker result is 260 (deterministic)' ($sum -eq '260') "got '$sum'"
$r = Run-Exe $pa (@('run') + $common + @('--policy', "$work\policy-empty.json", '--out', "$out\denied.txt"))
Check 'unauthorised task denied (exit 3)' ($r.Code -eq 3)
Check 'denied task produced no output' (-not (Test-Path "$out\denied.txt"))
$r = Run-Exe $pa @('report', '--audit', $audit, '--out', "$work\report.html")
Check 'audit chain verifies and report written (exit 0)' ($r.Code -eq 0 -and (Test-Path "$work\report.html"))
$html = Get-Content "$work\report.html" -Raw
Check 'report contains no script element' (-not ($html -match '<script'))

Write-Host ""
if ($fails -eq 0) { Write-Host "ALL CHECKS PASSED. Log: $log"; $code = 0 } else { Write-Host "$fails CHECK(S) FAILED. Log: $log"; $code = 1 }
Stop-Transcript | Out-Null
exit $code
