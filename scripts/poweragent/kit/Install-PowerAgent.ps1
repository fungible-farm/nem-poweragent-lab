#Requires -Version 7.0
<#
.SYNOPSIS
  Preflight, install, upgrade, roll back, uninstall and inspect the PowerAgent pilot kit.

.DESCRIPTION
  Every action starts with an exhaustive preflight (run `-Action ListChecks` for the catalogue). Required
  checks that fail stop the action before anything is changed. Behaviour comes from a strict JSON config
  (unknown keys are rejected) and parameters override it. Supports -WhatIf. Writes a JSON report.

  Exit codes
     0  success                                  1  Status: not installed
    10  preflight: a required check failed      11  preflight: warnings and failOnWarning is set
    12  Status: installed files differ from the manifest (drift)
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
$script:Checks = [System.Collections.Generic.List[object]]::new()
$script:Steps = [System.Collections.Generic.List[object]]::new()
$script:ImportsReport = @()

# ---------------------------------------------------------------- output helpers
function Say([string]$m) { if (-not $Quiet) { Write-Host $m } }
function Die([int]$code, [string]$m) { [Console]::Error.WriteLine("error: $m"); exit $code }

# Catalogue of checks: Id, Category, Required, Title. `-Action ListChecks` prints it; the test suite asserts that
# preflight emits exactly these ids (conditional ones are marked and may be SKIP).
$Catalogue = @(
    @('PLAT-01', 'Platform', $true, 'Operating system is Windows'),
    @('PLAT-02', 'Platform', $true, '64-bit process on x64 hardware (ARM64 is untested)'),
    @('PLAT-03', 'Platform', $true, 'Windows build meets the MXC processcontainer floor (data\mxc-os-floor.txt)'),
    @('PLAT-04', 'Platform', $false, 'Windows edition and virtual-machine status (informational)'),
    @('RIGHT-01', 'Rights', $true, 'Elevation matches the requested scope (AllUsers needs administrator)'),
    @('RIGHT-02', 'Rights', $true, 'Install directory location is writable'),
    @('RIGHT-03', 'Rights', $true, 'Data directory location is writable'),
    @('RIGHT-04', 'Rights', $true, 'Free disk space on the install drive'),
    @('KIT-01', 'Kit integrity', $true, 'SHA256SUMS present'),
    @('KIT-02', 'Kit integrity', $true, 'Every kit file matches SHA256SUMS'),
    @('KIT-03', 'Kit integrity', $true, 'Required kit files present (binaries, data)'),
    @('KIT-04', 'Kit integrity', $false, 'No Mark-of-the-Web (downloaded-file block) on kit files'),
    @('KIT-05', 'Kit integrity', $false, 'Authenticode signatures (required only if requireSignedBinaries)'),
    @('DEP-01', 'Dependencies', $true, 'Every load-time DLL of poweragent.exe resolves on this machine'),
    @('DEP-02', 'Dependencies', $true, 'Every load-time DLL of poweragent-worker.exe resolves on this machine'),
    @('DEP-03', 'Dependencies', $true, 'Every load-time DLL of poweragent-probe.exe resolves on this machine'),
    @('DEP-04', 'Dependencies', $false, 'No Visual C++ Redistributable needed (static C runtime)'),
    @('BACK-01', 'Sandbox backend', $true, 'The probe executes on this machine'),
    @('BACK-02', 'Sandbox backend', $true, 'The expected MXC backend is reported available'),
    @('BACK-03', 'Sandbox backend', $false, 'Backend tier (informational)'),
    @('BACK-04', 'Sandbox backend', $true, 'Fail-closed: a network request is denied (self-test)'),
    @('SEC-01', 'Security posture', $false, 'Code-integrity (WDAC) policies present (informational)'),
    @('SEC-02', 'Security posture', $false, 'AppLocker policy present (informational)'),
    @('SEC-03', 'Security posture', $false, 'Microsoft Defender real-time protection (informational)'),
    @('SEC-04', 'Security posture', $false, 'PowerShell execution policy (informational)'),
    @('MGMT-01', 'Management', $false, 'Entra / domain join state (informational)'),
    @('MGMT-02', 'Management', $false, 'MDM (Intune) enrollment (informational)'),
    @('OPT-01', 'Optional: Podman', $false, 'Podman installed (required only if podman.require)'),
    @('OPT-02', 'Optional: Podman', $false, 'Podman engine reachable (required only if podman.require)'),
    @('OPT-03', 'Optional: Podman', $false, 'Every digest-pinned image in registryFile is present locally'),
    @('INST-01', 'Existing install', $false, 'Existing installation and version (informational)'),
    @('INST-02', 'Existing install', $true, 'No downgrade without -Force'),
    @('INST-03', 'Existing install', $false, 'No other poweragent.exe earlier on PATH'),
    @('INST-04', 'Existing install', $true, 'No PowerAgent process running from the install directory')
)
if ($Action -eq 'ListChecks') {
    $Catalogue | ForEach-Object { [pscustomobject]@{ Id = $_[0]; Category = $_[1]; Required = $_[2]; Check = $_[3] } } | Format-Table -AutoSize
    exit 0
}

function Add-Check([string]$Id, [ValidateSet('PASS', 'WARN', 'FAIL', 'SKIP', 'INFO')][string]$Status, [string]$Detail, [string]$Remedy = '') {
    $def = $Catalogue | Where-Object { $_[0] -eq $Id }
    if (-not $def) { throw "internal: check $Id is not in the catalogue" }
    $script:Checks.Add([pscustomobject]@{ id = $Id; category = $def[1]; required = $def[2]; title = $def[3]; status = $Status; detail = $Detail; remedy = $Remedy })
}

# ---------------------------------------------------------------- configuration (strict)
$defaults = [ordered]@{
    scope = 'CurrentUser'; installDir = $null; dataDir = $null; addToPath = $true; registerUninstallEntry = $true
    requireSignedBinaries = $false; failOnWarning = $false; minFreeDiskMB = 200
    podman = [ordered]@{ require = $false; bin = 'podman' }; registryFile = $null
    verify = [ordered]@{ expectBackend = 'processcontainer' }
}
function Merge-Config($base, $over, [string]$path = '') {
    foreach ($p in $over.PSObject.Properties) {
        if (-not $base.Contains($p.Name)) { Die 64 "unknown config key '$path$($p.Name)'. Valid: $(($base.Keys) -join ', ')" }
        if ($base[$p.Name] -is [System.Collections.Specialized.OrderedDictionary]) { Merge-Config $base[$p.Name] $p.Value "$path$($p.Name)." }
        else { $base[$p.Name] = $p.Value }
    }
}
$cfg = $defaults
$cfgFile = if ($ConfigPath) { $ConfigPath } else { $null }
if ($cfgFile) {
    if (-not (Test-Path $cfgFile)) { Die 64 "config file not found: $cfgFile" }
    try { $over = Get-Content $cfgFile -Raw | ConvertFrom-Json } catch { Die 64 "config is not valid JSON: $($_.Exception.Message)" }
    Merge-Config $cfg $over
}
if ($Scope) { $cfg.scope = $Scope }
if ($InstallDir) { $cfg.installDir = $InstallDir }
if ($DataDir) { $cfg.dataDir = $DataDir }
if ($NoPath) { $cfg.addToPath = $false }
if ($NoUninstallEntry) { $cfg.registerUninstallEntry = $false }
if ($FailOnWarning) { $cfg.failOnWarning = $true }
if ($cfg.scope -notin 'CurrentUser', 'AllUsers') { Die 64 "scope must be CurrentUser or AllUsers" }
if ($cfg.minFreeDiskMB -isnot [int] -and $cfg.minFreeDiskMB -isnot [long]) { Die 64 'minFreeDiskMB must be a number' }
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

function Read-Json([string]$p) { Get-Content $p -Raw | ConvertFrom-Json }
function Write-Json([string]$p, $o) { [IO.File]::WriteAllText($p, ($o | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false)) }
function Sha([string]$p) { (Get-FileHash $p -Algorithm SHA256).Hash.ToLower() }
function Nearest-Existing([string]$p) { while ($p -and -not (Test-Path $p)) { $p = Split-Path $p -Parent }; $p }
function Can-Write([string]$dir) {
    $d = Nearest-Existing $dir
    if (-not $d) { return $false }
    $t = Join-Path $d ".pa-write-test-$([guid]::NewGuid().ToString('N'))"
    try { [IO.File]::WriteAllText($t, 'x'); Remove-Item $t -Force; $true } catch { $false }
}
function Norm([string]$p) { $p.TrimEnd('\').ToLowerInvariant() }
function Installed-Manifest { if (Test-Path $manifestPath) { Read-Json $manifestPath } }
function Run-Exe([string]$exe, [string[]]$a) {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { $o = & $exe @a 2>&1 | Out-String; $c = $LASTEXITCODE } finally { $ErrorActionPreference = $old }
    [pscustomobject]@{ Code = $c; Out = $o }
}

# ---------------------------------------------------------------- preflight
function Invoke-Preflight {
    $kitInfo = $null
    # PLAT
    $osb = if ($IsWindows) { [int](Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').CurrentBuild } else { 0 }
    $osn = if ($osb -ge 22000) { 'Windows 11' } elseif ($osb -gt 0) { 'Windows 10 or older' } else { [Runtime.InteropServices.RuntimeInformation]::OSDescription }
    Add-Check 'PLAT-01' $(if ($IsWindows -and $osb -ge 22000) { 'PASS' } else { 'FAIL' }) "$osn (build $osb)" 'Run on Windows 11.'
    $arch = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture
    $ok64 = [Environment]::Is64BitProcess -and $arch -eq 'X64'
    Add-Check 'PLAT-02' $(if ($ok64) { 'PASS' } elseif ($arch -eq 'Arm64') { 'FAIL' } else { 'FAIL' }) "OS architecture $arch; 64-bit process: $([Environment]::Is64BitProcess)" 'The kit is x64 only; ARM64 has not been built or tested.'
    $cv = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
    $build = [int]$cv.CurrentBuild; $ubr = [int]$cv.UBR
    $floorFile = Join-Path $kit 'data\mxc-os-floor.txt'
    if (Test-Path $floorFile) {
        $row = Get-Content $floorFile | Where-Object { $_ -match '^\s*(\d+)\s+(\d+)\s*$' -and [int]$Matches[1] -eq $build } | Select-Object -First 1
        if (-not $row) { Add-Check 'PLAT-03' 'FAIL' "Windows build $build is not in the floor table" 'Use a Windows 11 build listed in data\mxc-os-floor.txt (24H2, 25H2, 26H2, 26H1).' }
        else { $need = [int](($row -split '\s+' | Where-Object { $_ })[1])
            Add-Check 'PLAT-03' $(if ($ubr -ge $need) { 'PASS' } else { 'FAIL' }) "build $build.$ubr; floor $build.$need" "Install Windows updates until the revision is at least $need." }
    } else { Add-Check 'PLAT-03' 'FAIL' 'data\mxc-os-floor.txt is missing' 'Re-extract the kit.' }
    $vm = try { (Get-CimInstance Win32_ComputerSystem).HypervisorPresent } catch { $null }
    Add-Check 'PLAT-04' 'INFO' "$($cv.EditionID), display version $($cv.DisplayVersion), hypervisor present: $vm"
    # RIGHT
    $needAdmin = $allUsers
    Add-Check 'RIGHT-01' $(if ($needAdmin -and -not $isAdmin) { 'FAIL' } else { 'PASS' }) "scope $($cfg.scope); elevated: $isAdmin" 'For AllUsers run PowerShell as administrator, or use -Scope CurrentUser.'
    Add-Check 'RIGHT-02' $(if (Can-Write $installDir) { 'PASS' } else { 'FAIL' }) $installDir 'Choose a writable -InstallDir or elevate.'
    Add-Check 'RIGHT-03' $(if (Can-Write $dataDir) { 'PASS' } else { 'FAIL' }) $dataDir 'Choose a writable -DataDir or elevate.'
    $root = [IO.Path]::GetPathRoot($installDir)
    $free = try { [math]::Floor((New-Object IO.DriveInfo($root)).AvailableFreeSpace / 1MB) } catch { -1 }
    Add-Check 'RIGHT-04' $(if ($free -ge $cfg.minFreeDiskMB) { 'PASS' } else { 'FAIL' }) "$free MB free on $root; need $($cfg.minFreeDiskMB)" 'Free disk space or lower minFreeDiskMB.'
    # KIT
    $sums = Join-Path $kit 'SHA256SUMS'
    if (-not (Test-Path $sums)) { Add-Check 'KIT-01' 'FAIL' 'SHA256SUMS missing' 'Re-extract the kit from the original zip.'; Add-Check 'KIT-02' 'SKIP' 'no SHA256SUMS' }
    else {
        Add-Check 'KIT-01' 'PASS' $sums
        $bad = @(); $n = 0
        foreach ($l in Get-Content $sums) {
            if ($l -notmatch '^([0-9a-f]{64})  (.+)$') { continue }
            $n++; $f = Join-Path $kit $Matches[2]
            if (-not (Test-Path $f) -or (Sha $f) -ne $Matches[1]) { $bad += $Matches[2] }
        }
        Add-Check 'KIT-02' $(if ($bad.Count -eq 0) { 'PASS' } else { 'FAIL' }) $(if ($bad.Count) { "changed or missing: $($bad -join ', ')" } else { "$n files verified" }) 'Re-extract the kit; compare the zip with its .sha256 file.'
    }
    $req = 'bin\poweragent.exe', 'bin\poweragent-worker.exe', 'bin\poweragent-probe.exe', 'data\kit-info.json', 'data\imports.json', 'data\mxc-os-floor.txt', 'fixtures\profile-net.json', 'fixtures\policy-allow.json'
    $miss = $req | Where-Object { -not (Test-Path (Join-Path $kit $_)) }
    Add-Check 'KIT-03' $(if ($miss) { 'FAIL' } else { 'PASS' }) $(if ($miss) { "missing: $($miss -join ', ')" } else { "$($req.Count) required files present" }) 'Re-extract the kit.'
    $motw = Get-ChildItem $kit -Recurse -File | Where-Object { Get-Item $_.FullName -Stream Zone.Identifier -ErrorAction SilentlyContinue } | Select-Object -First 5
    Add-Check 'KIT-04' $(if ($motw) { 'WARN' } else { 'PASS' }) $(if ($motw) { "downloaded-file marker on $(($motw | % Name) -join ', ') ..." } else { 'no Zone.Identifier streams' }) 'Run: Get-ChildItem <kit> -Recurse | Unblock-File  (after verifying the zip hash).'
    $sig = @{}; foreach ($e in 'poweragent.exe', 'poweragent-worker.exe', 'poweragent-probe.exe') { $f = Join-Path $kit "bin\$e"; if (Test-Path $f) { $sig[$e] = (Get-AuthenticodeSignature $f).Status.ToString() } }
    $unsigned = $sig.Keys | Where-Object { $sig[$_] -ne 'Valid' }
    $sigStatus = if (-not $unsigned) { 'PASS' } elseif ($cfg.requireSignedBinaries) { 'FAIL' } else { 'WARN' }
    Add-Check 'KIT-05' $sigStatus (($sig.GetEnumerator() | % { "$($_.Key)=$($_.Value)" }) -join '; ') 'Use a signed release, or set requireSignedBinaries=false for a lab pilot.'
    # DEP
    $impFile = Join-Path $kit 'data\imports.json'
    if (Test-Path $impFile) {
        $imp = Read-Json $impFile
        $ids = @{ 'poweragent.exe' = 'DEP-01'; 'poweragent-worker.exe' = 'DEP-02'; 'poweragent-probe.exe' = 'DEP-03' }
        foreach ($e in $ids.Keys) {
            $dlls = @($imp.$e); $unres = @()
            foreach ($d in $dlls) {
                $h = [IntPtr]::Zero
                $ok = [Runtime.InteropServices.NativeLibrary]::TryLoad($d, [ref]$h)
                if ($ok) { [Runtime.InteropServices.NativeLibrary]::Free($h) } else { $unres += $d }
                $script:ImportsReport += [pscustomobject]@{ exe = $e; dll = $d; resolved = $ok }
            }
            Add-Check $ids[$e] $(if ($unres) { 'FAIL' } else { 'PASS' }) $(if ($unres) { "unresolved: $($unres -join ', ')" } else { "$($dlls.Count) DLLs resolved" }) 'Install the missing Windows component or update Windows.'
        }
        $vc = @($imp.PSObject.Properties.Value | ForEach-Object { $_ } | Where-Object { $_ -match '(?i)^(vcruntime|msvcp|msvcr|api-ms-win-crt|ucrtbase)' })
        Add-Check 'DEP-04' $(if ($vc) { 'WARN' } else { 'PASS' }) $(if ($vc) { "imports the C runtime: $(($vc | Select -Unique) -join ', ')" } else { 'no Visual C++ / UCRT imports (statically linked)' }) 'Install the Microsoft Visual C++ Redistributable (x64).'
    } else { foreach ($i in 'DEP-01', 'DEP-02', 'DEP-03', 'DEP-04') { Add-Check $i 'SKIP' 'data\imports.json missing (see KIT-03)' } }
    # BACK
    $probe = Join-Path $kit 'bin\poweragent-probe.exe'
    if (Test-Path $probe) {
        $r = Run-Exe $probe @()
        $json = try { $r.Out | ConvertFrom-Json } catch { $null }
        Add-Check 'BACK-01' $(if ($r.Code -eq 0 -and $json) { 'PASS' } else { 'FAIL' }) $(if ($json) { "exit $($r.Code)" } else { "exit $($r.Code): $($r.Out.Trim().Split("`n")[0])" }) 'If the exe is blocked (WDAC/AppLocker/antivirus), see SEC-01..03.'
        $be = @($json.backends) | Where-Object { $_.backend -eq $cfg.verify.expectBackend }
        Add-Check 'BACK-02' $(if ($be) { 'PASS' } else { 'FAIL' }) $(if ($be) { "$($cfg.verify.expectBackend) available" } else { "backend '$($cfg.verify.expectBackend)' not reported; reported: $((@($json.backends) | % backend) -join ', ')" }) 'Update Windows to the build floor; the sandbox backend is unavailable on this machine.'
        Add-Check 'BACK-03' 'INFO' $(if ($be) { "tier $($be.tier); capabilities: $(@($be.capabilities) -join ', ')" } else { 'n/a' })
        $net = Run-Exe $probe @('--profile', (Join-Path $kit 'fixtures\profile-net.json'), '--policy', (Join-Path $kit 'fixtures\policy-allow.json'))
        Add-Check 'BACK-04' $(if ($net.Code -eq 3 -and $net.Out -match 'containment_unavailable') { 'PASS' } else { 'FAIL' }) "exit $($net.Code)" 'The fail-closed self-test did not behave as designed; do not install.'
    } else { foreach ($i in 'BACK-01', 'BACK-02', 'BACK-03', 'BACK-04') { Add-Check $i 'SKIP' 'probe binary missing (see KIT-03)' } }
    # SEC
    $ci = try { @(Get-ChildItem 'C:\Windows\System32\CodeIntegrity\CiPolicies\Active' -ErrorAction Stop).Count } catch { -1 }
    Add-Check 'SEC-01' 'INFO' $(if ($ci -ge 0) { "$ci active code-integrity policy file(s); the Windows default set is non-zero, review if your organisation deploys WDAC" } else { 'could not enumerate (needs elevation)' })
    $al = Test-Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\SrpV2'
    Add-Check 'SEC-02' 'INFO' $(if ($al) { 'AppLocker rule collections present; unsigned binaries may be blocked' } else { 'no AppLocker policy found' })
    $mp = try { (Get-MpComputerStatus -ErrorAction Stop).RealTimeProtectionEnabled } catch { $null }
    Add-Check 'SEC-03' 'INFO' $(if ($null -ne $mp) { "Defender real-time protection: $mp" } else { 'Defender status unavailable (third-party AV or insufficient rights)' })
    Add-Check 'SEC-04' 'INFO' "effective execution policy: $(Get-ExecutionPolicy)"
    # MGMT
    $ds = dsregcmd /status 2>$null | Out-String
    $g = { param($k) if ($ds -match "(?m)^[ \t]*$k[ \t]*:[ \t]*(\S.*)?$") { "$($Matches[1])".Trim() } else { '' } }
    Add-Check 'MGMT-01' 'INFO' "AzureAdJoined=$(& $g 'AzureAdJoined') DomainJoined=$(& $g 'DomainJoined') Tenant=$(& $g 'TenantName')"
    $mdm = & $g 'MdmUrl'
    Add-Check 'MGMT-02' 'INFO' $(if ($mdm) { "MDM enrolled ($mdm)" } else { 'no MDM enrollment detected (MdmUrl is empty)' })
    # OPT
    $pb = $cfg.podman.bin; $pcmd = Get-Command $pb -ErrorAction SilentlyContinue
    $preq = [bool]$cfg.podman.require
    if (-not $pcmd) {
        Add-Check 'OPT-01' $(if ($preq) { 'FAIL' } else { 'INFO' }) "'$pb' not found; helper services will be unavailable" 'Install Podman (needs WSL2 or Hyper-V) if helper services are wanted.'
        Add-Check 'OPT-02' 'SKIP' 'no podman'; Add-Check 'OPT-03' 'SKIP' 'no podman'
    } else {
        $pv = Run-Exe $pcmd.Source @('--version')
        Add-Check 'OPT-01' 'PASS' $pv.Out.Trim()
        $pi = Run-Exe $pcmd.Source @('info', '--format', '{{.Host.Arch}}')
        Add-Check 'OPT-02' $(if ($pi.Code -eq 0) { 'PASS' } elseif ($preq) { 'FAIL' } else { 'WARN' }) $(if ($pi.Code -eq 0) { "engine reachable ($($pi.Out.Trim()))" } else { "podman info failed: $($pi.Out.Trim().Split("`n")[0])" }) 'Start the Podman machine (podman machine start).'
        if ($cfg.registryFile) {
            $rf = Expand $cfg.registryFile
            if (-not (Test-Path $rf)) { Add-Check 'OPT-03' $(if ($preq) { 'FAIL' } else { 'WARN' }) "registryFile not found: $rf" }
            else {
                $imgs = @((Get-Content $rf -Raw | ConvertFrom-Json) | Where-Object { $_.image } | ForEach-Object { $_.image })
                $missing = @($imgs | Where-Object { (Run-Exe $pcmd.Source @('image', 'exists', $_)).Code -ne 0 })
                $notPinned = @($imgs | Where-Object { $_ -notmatch '@sha256:[0-9a-fA-F]{64}$' })
                $st = if ($missing -or $notPinned) { if ($preq) { 'FAIL' } else { 'WARN' } } else { 'PASS' }
                Add-Check 'OPT-03' $st $(if ($notPinned) { "not digest-pinned: $($notPinned -join ', ')" } elseif ($missing) { "not present locally: $($missing -join ', ')" } else { "$($imgs.Count) image(s) present and pinned" }) 'Pre-load the images by digest; PowerAgent never pulls.'
            }
        } else { Add-Check 'OPT-03' 'SKIP' 'registryFile not configured' }
    }
    # INST
    $m = Installed-Manifest
    $new = if (Test-Path (Join-Path $kit 'data\kit-info.json')) { Read-Json (Join-Path $kit 'data\kit-info.json') } else { $null }
    Add-Check 'INST-01' 'INFO' $(if ($m) { "installed version $($m.version) ($($m.commit)) at $installDir" } else { 'not installed' })
    $down = $m -and $new -and ([version]$new.version -lt [version]$m.version)
    Add-Check 'INST-02' $(if ($down -and -not $Force) { 'FAIL' } else { 'PASS' }) $(if ($down) { "kit $($new.version) is older than installed $($m.version)" } else { 'not a downgrade' }) 'Pass -Force to downgrade deliberately.'
    $binDir = Join-Path $installDir 'bin'
    $other = @(Get-Command poweragent.exe -All -ErrorAction SilentlyContinue | Where-Object { (Norm (Split-Path $_.Source -Parent)) -ne (Norm $binDir) })
    Add-Check 'INST-03' $(if ($other) { 'WARN' } else { 'PASS' }) $(if ($other) { "another poweragent.exe on PATH: $($other[0].Source)" } else { 'no conflicting poweragent.exe on PATH' }) 'Remove the other copy from PATH or invoke by full path.'
    $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($installDir + '\', [StringComparison]::OrdinalIgnoreCase) })
    Add-Check 'INST-04' $(if ($running) { 'FAIL' } else { 'PASS' }) $(if ($running) { "running from install dir: $(($running | % ProcessName) -join ', ')" } else { 'none' }) 'Stop those processes first.'
}

function Ordered-Checks { $idx = @{}; for ($i = 0; $i -lt $Catalogue.Count; $i++) { $idx[$Catalogue[$i][0]] = $i }; $script:Checks | Sort-Object { $idx[$_.id] } }
function Show-Checks {
    if ($Quiet) { return }
    Ordered-Checks | ForEach-Object {
        $col = switch ($_.status) { 'PASS' { 'Green' } 'FAIL' { 'Red' } 'WARN' { 'Yellow' } default { 'DarkGray' } }
        Write-Host ('{0,-4} ' -f $_.status) -ForegroundColor $col -NoNewline
        Write-Host ('{0,-8} {1}' -f $_.id, $_.title)
        if ($_.detail) { Write-Host "          $($_.detail)" -ForegroundColor DarkGray }
        if ($_.status -in 'FAIL', 'WARN' -and $_.remedy) { Write-Host "          fix: $($_.remedy)" -ForegroundColor $col }
    }
}
function Preflight-Verdict {
    $failed = @($script:Checks | Where-Object { $_.status -eq 'FAIL' })
    $warned = @($script:Checks | Where-Object { $_.status -eq 'WARN' })
    if ($failed) { return 10 }
    if ($warned -and $cfg.failOnWarning) { return 11 }
    0
}
function Save-Report([int]$code, [string]$outcome) {
    $path = $ReportPath
    if (-not $path) { return }
    $o = [ordered]@{
        schema = 'poweragent.install-report/v1'; action = $Action; timestampUtc = (Get-Date).ToUniversalTime().ToString('o')
        host = [ordered]@{ computer = $env:COMPUTERNAME; user = "$env:USERDOMAIN\$env:USERNAME"; elevated = $isAdmin; os = [Runtime.InteropServices.RuntimeInformation]::OSDescription; powershell = $PSVersionTable.PSVersion.ToString() }
        config = $cfg; installDir = $installDir; dataDir = $dataDir
        result = [ordered]@{ outcome = $outcome; exitCode = $code }
        counts = [ordered]@{ pass = @($script:Checks | ? status -eq PASS).Count; warn = @($script:Checks | ? status -eq WARN).Count; fail = @($script:Checks | ? status -eq FAIL).Count; info = @($script:Checks | ? status -eq INFO).Count; skip = @($script:Checks | ? status -eq SKIP).Count }
        checks = @(Ordered-Checks); loadTimeDlls = $script:ImportsReport; steps = $script:Steps
    }
    Write-Json $path $o
    Say "report: $path"
}
function Finish([int]$code, [string]$outcome) { Save-Report $code $outcome; Say "RESULT: $outcome (exit $code)"; exit $code }

# ---------------------------------------------------------------- mutation helpers (each honours -WhatIf)
function Step([string]$what, [scriptblock]$body) {
    if ($PSCmdlet.ShouldProcess($what, $Action)) {
        try { & $body; $script:Steps.Add([pscustomobject]@{ step = $what; result = 'done' }); Say "  done: $what" }
        catch { $script:Steps.Add([pscustomobject]@{ step = $what; result = "FAILED: $($_.Exception.Message)" }); throw }
    } else { $script:Steps.Add([pscustomobject]@{ step = $what; result = 'skipped (WhatIf)' }); Say "  would: $what" }
}
function Path-Add([string]$dir) {
    $cur = [Environment]::GetEnvironmentVariable('Path', $pathTarget); $parts = @($cur -split ';' | Where-Object { $_ })
    if (-not ($parts | Where-Object { (Norm $_) -eq (Norm $dir) })) { [Environment]::SetEnvironmentVariable('Path', (($parts + $dir) -join ';'), $pathTarget) }
}
function Path-Remove([string]$dir) {
    $cur = [Environment]::GetEnvironmentVariable('Path', $pathTarget); $parts = @($cur -split ';' | Where-Object { $_ })
    $keep = @($parts | Where-Object { (Norm $_) -ne (Norm $dir) })
    if ($keep.Count -ne $parts.Count) { [Environment]::SetEnvironmentVariable('Path', ($keep -join ';'), $pathTarget) }
}
function Set-UninstallEntry($manifest) {
    New-Item -Path $uninstallKey -Force | Out-Null
    $pw = (Get-Process -Id $PID).Path
    $vals = @{ DisplayName = 'PowerAgent (pilot)'; DisplayVersion = $manifest.version; Publisher = 'PowerAgent project'; InstallLocation = $installDir
        UninstallString = "`"$pw`" -NoProfile -File `"$installDir\Install-PowerAgent.ps1`" -Action Uninstall -Scope $($cfg.scope) -InstallDir `"$installDir`" -DataDir `"$dataDir`" -Quiet"
        NoModify = 1; NoRepair = 1 }
    foreach ($k in $vals.Keys) { New-ItemProperty -Path $uninstallKey -Name $k -Value $vals[$k] -Force | Out-Null }
}
function Set-DataAcl {
    if (-not $allUsers) { return }
    # Policy is readable by everyone, writable only by administrators: the start of an independent policy authority.
    & icacls (Join-Path $dataDir 'policy') /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' | Out-Null
    foreach ($d in 'audit', 'work', 'logs') { & icacls (Join-Path $dataDir $d) /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)M' | Out-Null }
}

# ---------------------------------------------------------------- actions
function Do-Install {
    Say "== Preflight"
    Invoke-Preflight; Show-Checks
    $v = Preflight-Verdict
    if ($v -ne 0) { Finish $v $(if ($v -eq 10) { 'preflight failed (required checks); nothing was changed' } else { 'preflight warnings; failOnWarning is set; nothing was changed' }) }
    $new = Read-Json (Join-Path $kit 'data\kit-info.json')
    $old = Installed-Manifest
    Say "== $(if ($old) { "Upgrade $($old.version) -> $($new.version)" } else { "Install $($new.version)" }) ($($cfg.scope))"
    # What this run has actually done, so a failure undoes exactly that and nothing else.
    $script:movedCurrent = $false; $script:activated = $false; $script:pathTouched = $false; $script:entryTouched = $false; $script:verifyFailed = $false
    try {
        if ($env:POWERAGENT_INSTALLER_FAULT -eq 'stage') { throw 'injected fault: stage' }
        Step "stage payload in $stagingDir" {
            if (Test-Path $stagingDir) { Remove-Item $stagingDir -Recurse -Force }
            New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null
            foreach ($d in 'bin', 'data', 'docs', 'fixtures') { Copy-Item (Join-Path $kit $d) (Join-Path $stagingDir $d) -Recurse }
            foreach ($f in 'Install-PowerAgent.ps1', 'install.config.json', 'LICENSE', 'README.md', 'SHA256SUMS') { if (Test-Path (Join-Path $kit $f)) { Copy-Item (Join-Path $kit $f) $stagingDir } }
            $files = Get-ChildItem $stagingDir -Recurse -File | ForEach-Object { [ordered]@{ path = $_.FullName.Substring($stagingDir.Length + 1).Replace('\', '/'); sha256 = Sha $_.FullName } }
            Write-Json (Join-Path $stagingDir 'install-manifest.json') ([ordered]@{
                product = 'PowerAgent'; version = $new.version; commit = $new.commit; installedUtc = (Get-Date).ToUniversalTime().ToString('o')
                scope = $cfg.scope; installDir = $installDir; dataDir = $dataDir; pathAdded = [bool]$cfg.addToPath; uninstallEntry = [bool]$cfg.registerUninstallEntry
                uninstallKey = $uninstallKey; files = $files })
        }
        if ($old) { Step "keep the current version as $previousDir" {
            if (Test-Path $previousDir) { Remove-Item $previousDir -Recurse -Force }
            Move-Item $installDir $previousDir
            $script:movedCurrent = $true } }
        Step "activate $installDir" { Move-Item $stagingDir $installDir; $script:activated = $true }
        if ($env:POWERAGENT_INSTALLER_FAULT -eq 'activate') { throw 'injected fault: after activation' }
        Step "create data directories under $dataDir" {
            foreach ($d in 'policy', 'audit', 'work', 'logs') { New-Item -ItemType Directory -Force -Path (Join-Path $dataDir $d) | Out-Null }
            $pol = Join-Path $dataDir 'policy\policy.json'
            if (-not (Test-Path $pol)) { [IO.File]::WriteAllText($pol, '{"allowedCapabilities":[],"allowedFallbacks":[]}', [Text.UTF8Encoding]::new($false)) }   # deny-all until an administrator edits it
            $reg = Join-Path $dataDir 'policy\registry.json'
            if (-not (Test-Path $reg)) { [IO.File]::WriteAllText($reg, '[]', [Text.UTF8Encoding]::new($false)) }
            Set-DataAcl
        }
        if ($cfg.addToPath) { Step "add $installDir\bin to the $pathTarget PATH" { $script:pathTouched = $true; Path-Add (Join-Path $installDir 'bin') } }
        if ($cfg.registerUninstallEntry) { Step "register the uninstall entry $uninstallKey" { $script:entryTouched = $true; Set-UninstallEntry (Read-Json $manifestPath) } }
        Step "verify the installed copy (hashes, backend)" {
            if ($env:POWERAGENT_INSTALLER_FAULT -eq 'verify') { $script:verifyFailed = $true; throw 'injected fault: verification' }
            $m = Read-Json $manifestPath
            $bad = @($m.files | Where-Object { (Sha (Join-Path $installDir $_.path)) -ne $_.sha256 })
            if ($bad) { throw "installed files differ from the manifest: $(($bad | % path) -join ', ')" }
            $r = Run-Exe (Join-Path $installDir 'bin\poweragent-probe.exe') @()
            $j = try { $r.Out | ConvertFrom-Json } catch { $null }
            if (-not (@($j.backends) | Where-Object { $_.backend -eq $cfg.verify.expectBackend })) { $script:verifyFailed = $true; throw "post-install probe did not report backend '$($cfg.verify.expectBackend)'" }
        }
    } catch {
        $msg = $_.Exception.Message; $vf = [bool]$script:verifyFailed
        Say "  FAILED: $msg -- rolling back"
        if (-not $WhatIfPreference) {
            if (Test-Path $stagingDir) { Remove-Item $stagingDir -Recurse -Force -ErrorAction SilentlyContinue }
            if ($script:movedCurrent) {            # the old version was moved aside: put it back over the new one
                if (Test-Path $installDir) { Remove-Item $installDir -Recurse -Force -ErrorAction SilentlyContinue }
                Move-Item $previousDir $installDir
            } elseif ($script:activated -and -not $old) {   # first install: remove what we created
                Remove-Item $installDir -Recurse -Force -ErrorAction SilentlyContinue
            }
            if ($script:pathTouched) { try { if ($old -and $old.pathAdded) { Path-Add (Join-Path $installDir 'bin') } else { Path-Remove (Join-Path $installDir 'bin') } } catch {} }
            if ($script:entryTouched) { try { if ($old -and $old.uninstallEntry) { Set-UninstallEntry $old } else { Remove-Item $uninstallKey -Recurse -Force -ErrorAction SilentlyContinue } } catch {} }
        }
        Finish $(if ($vf) { 30 } else { 20 }) "install failed and was rolled back: $msg"
    }
    Finish 0 $(if ($WhatIfPreference) { 'WhatIf: no changes made' } else { "installed $($new.version) at $installDir" })
}

function Do-Uninstall {
    $m = Installed-Manifest
    if (-not $m) { Say 'Not installed.'; Finish 0 'nothing to uninstall' }
    $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($installDir + '\', [StringComparison]::OrdinalIgnoreCase) -and $_.Id -ne $PID })
    if ($running) { Finish 40 "refused: running from the install directory: $(($running | % ProcessName) -join ', ')" }
    if ($allUsers -and -not $isAdmin) { Finish 10 'AllUsers uninstall needs an elevated shell' }
    Say "== Uninstall $($m.version)"
    if ($m.pathAdded) { Step "remove $installDir\bin from the $pathTarget PATH" { Path-Remove (Join-Path $installDir 'bin') } }
    if ($m.uninstallEntry) { Step "remove the uninstall entry" { Remove-Item $m.uninstallKey -Recurse -Force -ErrorAction SilentlyContinue } }
    Step "delete $installDir" {
        # The running script may live in $installDir; copy it out is unnecessary on Windows for a closed file, but delete after we finish reading it.
        Remove-Item $installDir -Recurse -Force
    }
    if (Test-Path $previousDir) { Step "delete $previousDir" { Remove-Item $previousDir -Recurse -Force } }
    if ($PurgeData) { if (Test-Path $dataDir) { Step "delete data directory $dataDir (policy, audit logs)" { Remove-Item $dataDir -Recurse -Force } } }
    else { Say "  kept data directory $dataDir (policy and audit logs); use -PurgeData to delete it" }
    Finish 0 $(if ($WhatIfPreference) { 'WhatIf: no changes made' } else { 'uninstalled' })
}

function Do-Rollback {
    $m = Installed-Manifest
    if (-not (Test-Path $previousDir)) { Finish 40 "refused: no previous version at $previousDir" }
    $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($installDir + '\', [StringComparison]::OrdinalIgnoreCase) })
    if ($running) { Finish 40 'refused: PowerAgent is running from the install directory' }
    Say "== Rollback to the previous version"
    $swap = "$installDir.swap"
    Step "swap $installDir and $previousDir" {
        if (Test-Path $swap) { Remove-Item $swap -Recurse -Force }
        Move-Item $installDir $swap; Move-Item $previousDir $installDir; Move-Item $swap $previousDir
    }
    if (-not $WhatIfPreference) { $pm = Installed-Manifest; if ($pm.uninstallEntry) { Set-UninstallEntry $pm }; Say "  now running $($pm.version); the other version is kept at $previousDir (run Rollback again to swap back)" }
    Finish 0 $(if ($WhatIfPreference) { 'WhatIf: no changes made' } else { 'rolled back' })
}

function Do-Status {
    $m = Installed-Manifest
    if (-not $m) { Say "Not installed at $installDir."; Finish 1 'not installed' }
    $bad = @($m.files | Where-Object { -not (Test-Path (Join-Path $installDir $_.path)) -or (Sha (Join-Path $installDir $_.path)) -ne $_.sha256 })
    $onPath = (Norm (Join-Path $installDir 'bin')) -in @([Environment]::GetEnvironmentVariable('Path', $pathTarget) -split ';' | ForEach-Object { Norm $_ })
    Say "PowerAgent $($m.version) ($($m.commit)) installed $($m.installedUtc) scope=$($m.scope)"
    Say "  installDir $installDir ; dataDir $($m.dataDir) ; on PATH: $onPath ; previous version kept: $(Test-Path $previousDir)"
    if ($bad) { Say "  DRIFT in $($bad.Count) file(s): $(($bad | % path) -join ', ')"; Finish 12 'installed files differ from the manifest' }
    Finish 0 "healthy: $($m.files.Count) files match the manifest"
}

switch ($Action) {
    'Preflight' { Say '== Preflight'; Invoke-Preflight; Show-Checks; $v = Preflight-Verdict
        $s = if ($v -eq 0) { 'preflight passed' } elseif ($v -eq 10) { 'preflight FAILED (required checks)' } else { 'preflight warnings (failOnWarning is set)' }
        Finish $v $s }
    { $_ -in 'Install', 'Upgrade' } { Do-Install }
    'Uninstall' { Do-Uninstall }
    'Rollback' { Do-Rollback }
    'Status' { Do-Status }
}
