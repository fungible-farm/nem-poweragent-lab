#Requires -Version 7.0
<#
.SYNOPSIS
  Preflight, install, upgrade, roll back, uninstall and inspect the PowerAgent pilot kit.

.DESCRIPTION
  This file is only the entry point. It (1) verifies that every piece of installer code in the kit is covered by
  SHA256SUMS, (2) loads the modules under installer\ and extensions\, and (3) dispatches the requested action.
  Nothing is loaded that SHA256SUMS does not list, so a tampered or planted module is refused before it can run.

  Layout (see docs\07-install.md):
    installer\core\     output, configuration, utilities, the check registry, components, system helpers
    installer\checks\   one file per check category; each check registers itself (Register-Check)
    installer\actions\  install, uninstall, rollback, status
    components\         one JSON descriptor per installable component (kit files, or an OCI image by digest)
    extensions\         optional additions with the same contracts; must also be listed in SHA256SUMS

  Every action starts with an exhaustive preflight (`-Action ListChecks` prints the catalogue). Required checks that
  fail stop the action before anything is changed. Behaviour comes from a strict JSON config (unknown keys are
  rejected) and parameters override it. Supports -WhatIf. Writes a JSON report.

  Exit codes
     0  success                                  1  Status: not installed
    10  preflight: a required check failed;     11  preflight: warnings and failOnWarning is set
        or installer code is not covered by SHA256SUMS
    12  Status: installed files or permissions differ from the manifest (drift)
    20  install failed and was rolled back       30  post-install verification failed; rolled back
    40  refused (e.g. a PowerAgent process is running from the install directory, or nothing to roll back)
    64  bad arguments or config

.EXAMPLE
  .\Install-PowerAgent.ps1 -Action Preflight -ReportPath preflight.json
.EXAMPLE
  .\Install-PowerAgent.ps1 -Action Install -ConfigPath .\install.config.json -Quiet
.EXAMPLE
  .\Install-PowerAgent.ps1 -Action Install -Scope AllUsers -WhatIf     # elevated; shows every step, changes nothing
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'None')]
param(
    [ValidateSet('Preflight', 'Install', 'Upgrade', 'Rollback', 'Uninstall', 'Status', 'ListChecks')]
    [string]$Action = 'Preflight',
    [string]$ConfigPath,
    [ValidateSet('CurrentUser', 'AllUsers')][string]$Scope,
    [string]$InstallDir,
    [string]$DataDir,
    [switch]$NoPath,
    [switch]$NoUninstallEntry,
    [switch]$FailOnWarning,
    [switch]$Force,
    [switch]$PurgeData,
    [string]$ReportPath,
    [switch]$Quiet
)
$ErrorActionPreference = 'Stop'
$kit = Split-Path -Parent $MyInvocation.MyCommand.Path

# ---------------------------------------------------------------- bootstrap integrity
# Runs before any module is loaded. Every file under installer\, components\ and extensions\ must be listed in
# SHA256SUMS with a matching hash. The checksum file itself is protected by the zip's published hash.
$sumsFile = Join-Path $kit 'SHA256SUMS'
if (-not (Test-Path $sumsFile)) {
    [Console]::Error.WriteLine('error: SHA256SUMS is missing; refusing to load installer code. Run the installer from an extracted kit.')
    exit 10
}
$listed = @{}
foreach ($l in Get-Content $sumsFile) { if ($l -match '^([0-9a-f]{64})  (.+)$') { $listed[$Matches[2]] = $Matches[1] } }
$refused = @()
foreach ($d in 'installer', 'components', 'extensions') {
    $root = Join-Path $kit $d
    if (-not (Test-Path $root)) { continue }
    foreach ($f in Get-ChildItem $root -Recurse -File -Force) {
        $rel = $f.FullName.Substring($kit.Length + 1).Replace('\', '/')
        if (-not $listed.ContainsKey($rel)) { $refused += "$rel (not listed in SHA256SUMS)" }
        elseif ((Get-FileHash $f.FullName -Algorithm SHA256).Hash.ToLower() -ne $listed[$rel]) { $refused += "$rel (hash differs from SHA256SUMS)" }
    }
}
if (-not (Test-Path (Join-Path $kit 'installer\core'))) { $refused += 'installer/core (missing)' }
if ($refused) {
    [Console]::Error.WriteLine("error: refusing to load installer code that SHA256SUMS does not cover: $($refused -join '; ')")
    exit 10
}

# ---------------------------------------------------------------- load modules (sorted; core, checks, actions, extensions)
$modules = @()
foreach ($d in 'installer\core', 'installer\checks', 'installer\actions', 'extensions') {
    $root = Join-Path $kit $d
    if (Test-Path $root) { $modules += Get-ChildItem $root -File -Filter *.ps1 | Sort-Object Name }
}
foreach ($m in $modules) {
    . $m.FullName
    if ($null -ne $script:DieCode) { exit $script:DieCode }   # a module called Die while loading (e.g. an invalid config)
}

# ---------------------------------------------------------------- dispatch
switch ($Action) {
    'ListChecks' { Show-Catalogue; exit 0 }
    'Preflight' { Invoke-PreflightAction }
    { $_ -in 'Install', 'Upgrade' } { Invoke-InstallAction }
    'Uninstall' { Invoke-UninstallAction }
    'Rollback' { Invoke-RollbackAction }
    'Status' { Invoke-StatusAction }
}
