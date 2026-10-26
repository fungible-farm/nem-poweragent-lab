# core/20-config.ps1 -- strict configuration: defaults, install.config.json, parameter overrides, derived paths.
# Contract: after this file loads, $cfg, $installDir, $dataDir, $previousDir, $stagingDir, $manifestPath, $pathTarget,
# $uninstallKey, $allUsers and $isAdmin are set. Unknown config keys are rejected (exit 64).

$defaults = [ordered]@{
    scope = 'CurrentUser'; installDir = $null; dataDir = $null; addToPath = $true; registerUninstallEntry = $true
    requireSignedBinaries = $false; failOnWarning = $false; minFreeDiskMB = 200
    podman = [ordered]@{ require = $false; bin = 'podman' }; registryFile = $null
    verify = [ordered]@{ expectBackend = 'processcontainer' }
    components = [ordered]@{ exclude = @() }
}
function Merge-Config($base, $over, [string]$path = '') {
    foreach ($p in $over.PSObject.Properties) {
        if (-not $base.Contains($p.Name)) { Die 64 "unknown config key '$path$($p.Name)'. Valid: $(($base.Keys) -join ', ')" }
        if ($base[$p.Name] -is [System.Collections.Specialized.OrderedDictionary]) { Merge-Config $base[$p.Name] $p.Value "$path$($p.Name)." }
        else { $base[$p.Name] = $p.Value }
    }
}
$cfg = $defaults
if ($ConfigPath) {
    if (-not (Test-Path $ConfigPath)) { Die 64 "config file not found: $ConfigPath" }
    try { $over = Get-Content $ConfigPath -Raw | ConvertFrom-Json } catch { Die 64 "config is not valid JSON: $($_.Exception.Message)" }
    Merge-Config $cfg $over
}
if ($Scope) { $cfg.scope = $Scope }
if ($InstallDir) { $cfg.installDir = $InstallDir }
if ($DataDir) { $cfg.dataDir = $DataDir }
if ($NoPath) { $cfg.addToPath = $false }
if ($NoUninstallEntry) { $cfg.registerUninstallEntry = $false }
if ($FailOnWarning) { $cfg.failOnWarning = $true }
if ($cfg.scope -notin 'CurrentUser', 'AllUsers') { Die 64 'scope must be CurrentUser or AllUsers' }
if ($cfg.minFreeDiskMB -isnot [int] -and $cfg.minFreeDiskMB -isnot [long]) { Die 64 'minFreeDiskMB must be a number' }
$cfg.components.exclude = @($cfg.components.exclude | Where-Object { $_ })

function Expand([string]$p) { if ($p) { [Environment]::ExpandEnvironmentVariables($p) } }
$allUsers = $cfg.scope -eq 'AllUsers'
if (-not $cfg.installDir) { $cfg.installDir = if ($allUsers) { Join-Path $env:ProgramFiles 'PowerAgent' } else { Join-Path $env:LOCALAPPDATA 'Programs\PowerAgent' } }
if (-not $cfg.dataDir) { $cfg.dataDir = if ($allUsers) { Join-Path $env:ProgramData 'PowerAgent' } else { Join-Path $env:LOCALAPPDATA 'PowerAgent' } }
$installDir = [IO.Path]::GetFullPath((Expand $cfg.installDir))
$dataDir = [IO.Path]::GetFullPath((Expand $cfg.dataDir))
$previousDir = "$installDir.previous"
$stagingDir = "$installDir.new"
$manifestPath = Join-Path $installDir 'install-manifest.json'
$pathTarget = if ($allUsers) { 'Machine' } else { 'User' }
$uninstallKey = $(if ($allUsers) { 'HKLM:' } else { 'HKCU:' }) + '\Software\Microsoft\Windows\CurrentVersion\Uninstall\PowerAgent'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
