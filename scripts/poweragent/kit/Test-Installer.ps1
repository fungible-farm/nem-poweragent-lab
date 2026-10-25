#Requires -Version 7.0
<#
.SYNOPSIS
  Test suite for Install-PowerAgent.ps1 (development; not shipped in the kit).
.DESCRIPTION
  Extracts the newest kit zip (or uses -KitZip), then drives the installer through a throwaway install/data
  prefix: preflight, strict config, tamper, WhatIf, install, status/drift, upgrade, rollback, injected
  failures, downgrade, process lock, uninstall. Real side effects are limited to the *user* PATH value and the
  user Uninstall registry key, both restored in `finally`; the original PATH is compared byte for byte.
  AllUsers install needs elevation and is not exercised here.
#>
[CmdletBinding()]
param([string]$KitZip)
$ErrorActionPreference = 'Stop'
if (-not $KitZip) {
    $KitZip = (Get-ChildItem (Join-Path $PSScriptRoot '..\..\..\dist\poweragent-pilot-*.zip') | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
}
$work = Join-Path $env:TEMP "pa-installer-tests-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
New-Item -ItemType Directory -Path $work | Out-Null
$pw = (Get-Process -Id $PID).Path
$originalUserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\PowerAgent'
$hadUninstallKey = Test-Path $uninstallKey
$fail = 0; $passed = 0

function Extract([string]$to) {
    Expand-Archive $KitZip -DestinationPath $to
    (Get-ChildItem $to -Directory | Select-Object -First 1).FullName
}
function Retag([string]$kitDir, [string]$version) {   # make a kit that claims another version, with consistent hashes
    $ki = Join-Path $kitDir 'data\kit-info.json'
    $j = Get-Content $ki -Raw | ConvertFrom-Json; $j.version = $version
    [IO.File]::WriteAllText($ki, ($j | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    $h = (Get-FileHash $ki -Algorithm SHA256).Hash.ToLower()
    $sums = Join-Path $kitDir 'SHA256SUMS'
    $lines = Get-Content $sums | ForEach-Object { if ($_ -match '  data/kit-info\.json$') { "$h  data/kit-info.json" } else { $_ } }
    [IO.File]::WriteAllText($sums, (($lines -join "`n") + "`n"), [Text.UTF8Encoding]::new($false))
}
function Inst([string]$kitDir, [string[]]$a, [hashtable]$env = @{}) {
    foreach ($k in $env.Keys) { Set-Item "env:$k" $env[$k] }
    try {
        $out = & $pw -NoProfile -File (Join-Path $kitDir 'Install-PowerAgent.ps1') @a 2>&1 | Out-String
        [pscustomobject]@{ Code = $LASTEXITCODE; Out = $out }
    } finally { foreach ($k in $env.Keys) { Remove-Item "env:$k" -ErrorAction SilentlyContinue } }
}
function Case([string]$name, [scriptblock]$body) {
    try { & $body; Write-Host "PASS: $name"; $script:passed++ }
    catch { Write-Host "FAIL: $name -- $($_.Exception.Message)"; $script:fail++ }
}
function Assert([bool]$cond, [string]$msg) { if (-not $cond) { throw $msg } }
function Eq($a, $b, [string]$msg) { if ($a -ne $b) { throw "$msg (got '$a', wanted '$b')" } }
function Prefix([string]$n) { $p = Join-Path $work $n; @{ Install = Join-Path $p 'app'; Data = Join-Path $p 'data'; Root = $p } }
function Common($p) { @('-InstallDir', $p.Install, '-DataDir', $p.Data) }
function ManifestVersion($p) { (Get-Content (Join-Path $p.Install 'install-manifest.json') -Raw | ConvertFrom-Json).version }

try {
    $kit = Extract (Join-Path $work 'k1')
    $kit2 = Extract (Join-Path $work 'k2'); Retag $kit2 '0.1.1'
    $kit0 = Extract (Join-Path $work 'k0'); Retag $kit0 '0.0.9'

    Case 'ListChecks prints the catalogue' {
        $r = Inst $kit @('-Action', 'ListChecks'); Eq $r.Code 0 'exit'
        foreach ($id in 'PLAT-03', 'DEP-01', 'KIT-02', 'OPT-03', 'INST-04') { Assert ($r.Out -match $id) "missing $id" }
    }

    Case 'Preflight is read-only, exits 0, emits exactly the catalogued checks' {
        $p = Prefix 'pre'; $rep = Join-Path $p.Root 'r.json'; New-Item -ItemType Directory $p.Root | Out-Null
        $r = Inst $kit (@('-Action', 'Preflight', '-ReportPath', $rep, '-Quiet') + (Common $p)); Eq $r.Code 0 "exit ($($r.Out))"
        Assert (-not (Test-Path $p.Install)) 'preflight created the install dir'
        Assert (-not (Test-Path $p.Data)) 'preflight created the data dir'
        $j = Get-Content $rep -Raw | ConvertFrom-Json
        Eq $j.schema 'poweragent.install-report/v1' 'schema'
        $ids = @($j.checks | ForEach-Object id)
        $cat = (Inst $kit @('-Action', 'ListChecks')).Out -split "`n" | ForEach-Object { if ($_ -match '^\s*([A-Z]+-\d\d)\s') { $Matches[1] } } | Where-Object { $_ }
        Eq (($ids | Sort-Object) -join ',') (($cat | Sort-Object) -join ',') 'check ids vs catalogue'
        Assert ($j.counts.fail -eq 0) 'unexpected FAIL'
        Assert (@($j.loadTimeDlls).Count -gt 30) 'load-time DLL list missing'
        Assert (@($j.loadTimeDlls | Where-Object { -not $_.resolved }).Count -eq 0) 'unresolved DLL'
    }

    Case 'Static C runtime: no Visual C++ redistributable dependency' {
        $imp = Get-Content (Join-Path $kit 'data\imports.json') -Raw | ConvertFrom-Json
        $all = $imp.PSObject.Properties.Value | ForEach-Object { $_ }
        Assert (-not ($all | Where-Object { $_ -match '(?i)vcruntime|msvcp|ucrtbase|api-ms-win-crt' })) 'binaries import the C runtime'
    }

    Case 'Strict config: unknown key, bad JSON and missing file are rejected (64)' {
        $c = Join-Path $work 'bad.json'
        '{"scope":"CurrentUser","bogus":1}' | Set-Content $c; Eq (Inst $kit @('-Action', 'Preflight', '-ConfigPath', $c, '-Quiet')).Code 64 'unknown key'
        '{"podman":{"requir":true}}' | Set-Content $c; Eq (Inst $kit @('-Action', 'Preflight', '-ConfigPath', $c, '-Quiet')).Code 64 'unknown nested key'
        '{not json' | Set-Content $c; Eq (Inst $kit @('-Action', 'Preflight', '-ConfigPath', $c, '-Quiet')).Code 64 'bad json'
        Eq (Inst $kit @('-Action', 'Preflight', '-ConfigPath', (Join-Path $work 'nope.json'), '-Quiet')).Code 64 'missing file'
    }

    Case 'Config file and parameters: parameters win' {
        $p = Prefix 'cfg'; $q = Prefix 'cfg2'; New-Item -ItemType Directory $p.Root | Out-Null
        $c = Join-Path $p.Root 'c.json'; @{ installDir = $p.Install; dataDir = $p.Data; addToPath = $false } | ConvertTo-Json | Set-Content $c
        $rep = Join-Path $p.Root 'r.json'
        Inst $kit @('-Action', 'Preflight', '-ConfigPath', $c, '-InstallDir', $q.Install, '-ReportPath', $rep, '-Quiet') | Out-Null
        $j = Get-Content $rep -Raw | ConvertFrom-Json
        Eq $j.installDir ([IO.Path]::GetFullPath($q.Install)) 'param overrides config installDir'
        Eq $j.dataDir ([IO.Path]::GetFullPath($p.Data)) 'config dataDir used'
        Eq $j.config.addToPath $false 'config addToPath used'
    }

    Case 'Tampered kit: preflight and install refuse (10), nothing created' {
        $t = Extract (Join-Path $work 'tamper'); Add-Content (Join-Path $t 'docs\README.md') 'x'
        $p = Prefix 'tamper'
        $r = Inst $t (@('-Action', 'Preflight', '-Quiet') + (Common $p)); Eq $r.Code 10 'preflight'
        $r = Inst $t (@('-Action', 'Install', '-NoPath', '-Quiet') + (Common $p)); Eq $r.Code 10 'install'
        Assert (-not (Test-Path $p.Install)) 'install dir created despite failed preflight'
    }

    Case 'Missing required binary fails KIT-03 (10)' {
        $t = Extract (Join-Path $work 'nobin'); Remove-Item (Join-Path $t 'bin\poweragent-worker.exe')
        Eq (Inst $t (@('-Action', 'Preflight', '-Quiet') + (Common (Prefix 'nobin')))).Code 10 'exit'
    }

    Case 'Unresolvable load-time DLL is a required failure (DEP)' {
        $t = Extract (Join-Path $work 'dll')
        $f = Join-Path $t 'data\imports.json'; $j = Get-Content $f -Raw | ConvertFrom-Json
        $j.'poweragent-worker.exe' += 'definitely-missing-library.dll'
        [IO.File]::WriteAllText($f, ($j | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
        $h = (Get-FileHash $f -Algorithm SHA256).Hash.ToLower()
        $lines = Get-Content (Join-Path $t 'SHA256SUMS') | ForEach-Object { if ($_ -match '  data/imports\.json$') { "$h  data/imports.json" } else { $_ } }
        [IO.File]::WriteAllText((Join-Path $t 'SHA256SUMS'), (($lines -join "`n") + "`n"), [Text.UTF8Encoding]::new($false))
        $rep = Join-Path $work 'dll.json'
        $r = Inst $t @('-Action', 'Preflight', '-Quiet', '-ReportPath', $rep); Eq $r.Code 10 'exit'
        $d = (Get-Content $rep -Raw | ConvertFrom-Json).checks | Where-Object id -eq 'DEP-02'
        Eq $d.status 'FAIL' 'DEP-02'; Assert ($d.detail -match 'definitely-missing-library') 'names the missing DLL'
    }

    Case 'requireSignedBinaries fails (10); failOnWarning turns the unsigned warning into 11' {
        $c = Join-Path $work 'sig.json'; '{"requireSignedBinaries":true}' | Set-Content $c
        Eq (Inst $kit @('-Action', 'Preflight', '-ConfigPath', $c, '-Quiet')).Code 10 'requireSigned'
        Eq (Inst $kit @('-Action', 'Preflight', '-FailOnWarning', '-Quiet')).Code 11 'failOnWarning'
    }

    Case 'AllUsers without elevation is refused (10)' {
        if (([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { Write-Host '  (skipped: running elevated)'; return }
        $r = Inst $kit @('-Action', 'Install', '-Scope', 'AllUsers', '-Quiet'); Eq $r.Code 10 'exit'
    }

    Case 'Sidecar image check: unpinned and missing images are reported' {
        $c = Join-Path $work 'reg.json'
        '[{"name":"a","runtime":"podman","image":"alpine:3.20"},{"name":"b","runtime":"podman","image":"example.invalid/x@sha256:' + ('a' * 64) + '"}]' | Set-Content $c
        $cfg = Join-Path $work 'regcfg.json'; (@{ registryFile = $c } | ConvertTo-Json) | Set-Content $cfg
        $rep = Join-Path $work 'reg-report.json'
        Inst $kit @('-Action', 'Preflight', '-ConfigPath', $cfg, '-Quiet', '-ReportPath', $rep) | Out-Null
        $o = (Get-Content $rep -Raw | ConvertFrom-Json).checks | Where-Object id -eq 'OPT-03'
        Assert ($o.status -in 'WARN', 'SKIP') "OPT-03 was $($o.status)"
        if ($o.status -eq 'WARN') { Assert ($o.detail -match 'not digest-pinned') 'names the unpinned image' }
    }

    $p = Prefix 'main'
    Case '-WhatIf install changes nothing but lists every step' {
        $rep = Join-Path $work 'whatif.json'
        $r = Inst $kit (@('-Action', 'Install', '-WhatIf', '-ReportPath', $rep, '-Quiet') + (Common $p)); Eq $r.Code 0 "exit $($r.Out)"
        Assert (-not (Test-Path $p.Install)) 'WhatIf created the install dir'
        Eq ([Environment]::GetEnvironmentVariable('Path', 'User')) $originalUserPath 'WhatIf changed PATH'
        $steps = (Get-Content $rep -Raw | ConvertFrom-Json).steps
        Assert (@($steps).Count -ge 5) 'steps not listed'
        Assert (-not ($steps | Where-Object { $_.result -ne 'skipped (WhatIf)' })) 'a step ran under WhatIf'
    }

    Case 'Install: files, manifest, data dirs, deny-all default policy, PATH, uninstall entry' {
        $rep = Join-Path $work 'install.json'
        $r = Inst $kit (@('-Action', 'Install', '-ReportPath', $rep, '-Quiet') + (Common $p)); Eq $r.Code 0 "exit $($r.Out)"
        Eq (ManifestVersion $p) '0.1.0' 'manifest version'
        foreach ($f in 'bin\poweragent.exe', 'bin\poweragent-worker.exe', 'bin\poweragent-probe.exe', 'Install-PowerAgent.ps1') { Assert (Test-Path (Join-Path $p.Install $f)) "missing $f" }
        foreach ($d in 'policy', 'audit', 'work', 'logs') { Assert (Test-Path (Join-Path $p.Data $d)) "missing data\$d" }
        $pol = Get-Content (Join-Path $p.Data 'policy\policy.json') -Raw | ConvertFrom-Json
        Eq @($pol.allowedCapabilities).Count 0 'default policy must allow nothing'
        $userPath = [Environment]::GetEnvironmentVariable('Path', 'User') -split ';'
        Assert ($userPath -contains (Join-Path $p.Install 'bin')) 'PATH entry missing'
        Assert (Test-Path $uninstallKey) 'uninstall entry missing'
        Eq (Get-ItemPropertyValue $uninstallKey DisplayVersion) '0.1.0' 'uninstall entry version'
        Assert ((Get-Content $rep -Raw | ConvertFrom-Json).result.exitCode -eq 0) 'report exit code'
    }

    Case 'Installed copy works and the default policy denies everything' {
        $d = Join-Path $p.Data 'work\t'; New-Item -ItemType Directory -Force "$d\in", "$d\out" | Out-Null
        [IO.File]::WriteAllBytes("$d\in\data.bin", [byte[]](1, 2, 3, 4, 250))
        $caps = @(@{ kind = 'fs_read'; path = ("$d\in".Replace('\', '/')) }, @{ kind = 'fs_write'; path = ("$d\out".Replace('\', '/')) })
        $prof = @{ apiVersion = 'poweragent.dev/v1alpha1'; kind = 'TaskProfile'; metadata = @{ name = 'inst-test' }; spec = @{ untrustedCode = $true; timeoutSeconds = 20; capabilities = $caps } }
        [IO.File]::WriteAllText("$d\profile.json", ($prof | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText("$d\allow.json", (@{ allowedCapabilities = $caps; allowedFallbacks = @() } | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
        $exe = Join-Path $p.Install 'bin\poweragent.exe'
        $common = @('run', '--profile', "$d\profile.json", '--registry', (Join-Path $p.Data 'policy\registry.json'), '--audit', "$d\audit.jsonl", '--in', "$d\in\data.bin")
        & $exe @common --policy (Join-Path $p.Data 'policy\policy.json') --out "$d\out\denied.txt" 2>$null
        Eq $LASTEXITCODE 3 'default policy must deny'
        Assert (-not (Test-Path "$d\out\denied.txt")) 'denied task produced output'
        & $exe @common --policy "$d\allow.json" --out "$d\out\sum.txt" 2>$null
        Eq $LASTEXITCODE 0 'authorised run'
        Eq (Get-Content "$d\out\sum.txt" -Raw).Trim() '260' 'result'
    }

    Case 'Status: healthy (0), drift detected (12), not installed (1)' {
        Eq (Inst $kit (@('-Action', 'Status', '-Quiet') + (Common $p))).Code 0 'healthy'
        $f = Join-Path $p.Install 'docs\01-security-model.md'; $orig = Get-Content $f -Raw
        Add-Content $f 'tamper'; Eq (Inst $kit (@('-Action', 'Status', '-Quiet') + (Common $p))).Code 12 'drift'
        [IO.File]::WriteAllText($f, $orig, [Text.UTF8Encoding]::new($false))
        Eq (Inst $kit (@('-Action', 'Status', '-Quiet') + (Common (Prefix 'never')))).Code 1 'not installed'
    }

    Case 'Re-install of the same version is idempotent' {
        Eq (Inst $kit (@('-Action', 'Install', '-Quiet') + (Common $p))).Code 0 'exit'
        Eq (ManifestVersion $p) '0.1.0' 'version'
        $n = @([Environment]::GetEnvironmentVariable('Path', 'User') -split ';' | Where-Object { $_ -eq (Join-Path $p.Install 'bin') }).Count
        Eq $n 1 'PATH entry duplicated'
    }

    Case 'Upgrade 0.1.0 -> 0.1.1 keeps the previous copy; user data and policy survive' {
        $pol = Join-Path $p.Data 'policy\policy.json'; '{"allowedCapabilities":[],"allowedFallbacks":[],"x":1}' | Set-Content $pol
        Eq (Inst $kit2 (@('-Action', 'Upgrade', '-Quiet') + (Common $p))).Code 0 'exit'
        Eq (ManifestVersion $p) '0.1.1' 'new version'
        Assert (Test-Path "$($p.Install).previous") 'previous copy kept'
        Assert ((Get-Content $pol -Raw) -match '"x":1') 'policy was overwritten'
    }

    Case 'Downgrade is refused (10) unless -Force' {
        Eq (Inst $kit0 (@('-Action', 'Install', '-Quiet') + (Common $p))).Code 10 'refused'
        Eq (ManifestVersion $p) '0.1.1' 'must be unchanged'
        Eq (Inst $kit0 (@('-Action', 'Install', '-Force', '-Quiet') + (Common $p))).Code 0 'forced'
        Eq (ManifestVersion $p) '0.0.9' 'forced version'
        Eq (Inst $kit2 (@('-Action', 'Install', '-Quiet') + (Common $p))).Code 0 'back to 0.1.1'
    }

    Case 'Rollback swaps with the previous version and back' {
        $before = ManifestVersion $p
        Eq (Inst $kit (@('-Action', 'Rollback', '-Quiet') + (Common $p))).Code 0 'rollback'
        $mid = ManifestVersion $p; Assert ($mid -ne $before) "version did not change ($mid)"
        Eq (Inst $kit (@('-Action', 'Rollback', '-Quiet') + (Common $p))).Code 0 'rollback again'
        Eq (ManifestVersion $p) $before 'swapped back'
        Eq (Inst $kit (@('-Action', 'Status', '-Quiet') + (Common $p))).Code 0 'healthy after rollbacks'
    }

    foreach ($fault in @(@('stage', 20), @('activate', 20), @('verify', 30))) {
        Case "Injected '$($fault[0])' failure during an upgrade rolls back (exit $($fault[1]))" {
            $cur = ManifestVersion $p; $pathBefore = [Environment]::GetEnvironmentVariable('Path', 'User')
            $retag = Extract (Join-Path $work "f-$($fault[0])"); Retag $retag '0.2.0'
            $r = Inst $retag (@('-Action', 'Upgrade', '-Quiet') + (Common $p)) @{ POWERAGENT_INSTALLER_FAULT = $fault[0] }
            Eq $r.Code $fault[1] "exit ($($r.Out))"
            Eq (ManifestVersion $p) $cur 'old version must be restored'
            Eq ([Environment]::GetEnvironmentVariable('Path', 'User')) $pathBefore 'PATH must be restored'
            Assert (-not (Test-Path "$($p.Install).new")) 'staging left behind'
            Eq (Inst $kit (@('-Action', 'Status', '-Quiet') + (Common $p))).Code 0 'restored copy is healthy'
        }
    }

    Case 'Injected failure on a FIRST install leaves nothing behind' {
        $q = Prefix 'firstfail'; $pathBefore = [Environment]::GetEnvironmentVariable('Path', 'User')
        $r = Inst $kit (@('-Action', 'Install', '-Quiet') + (Common $q)) @{ POWERAGENT_INSTALLER_FAULT = 'verify' }
        Eq $r.Code 30 'exit'
        Assert (-not (Test-Path $q.Install)) 'install dir remains'
        Eq ([Environment]::GetEnvironmentVariable('Path', 'User')) $pathBefore 'PATH not restored'
    }

    Case 'A running PowerAgent process blocks upgrade (10) and uninstall (40)' {
        $proc = Start-Process (Join-Path $p.Install 'bin\poweragent-worker.exe') -ArgumentList 'sleep', '60' -PassThru -WindowStyle Hidden
        try {
            Start-Sleep -Milliseconds 800
            Eq (Inst $kit2 (@('-Action', 'Install', '-Quiet') + (Common $p))).Code 10 'upgrade while running'
            Eq (Inst $kit (@('-Action', 'Uninstall', '-Quiet') + (Common $p))).Code 40 'uninstall while running'
            Assert (Test-Path $p.Install) 'install dir removed despite refusal'
        } finally { $proc | Stop-Process -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 500 }
    }

    Case 'Uninstall removes files, PATH entry and uninstall entry; data kept; -PurgeData removes it' {
        Eq (Inst $kit (@('-Action', 'Uninstall', '-WhatIf', '-Quiet') + (Common $p))).Code 0 'whatif'
        Assert (Test-Path $p.Install) 'WhatIf removed files'
        Eq (Inst $kit (@('-Action', 'Uninstall', '-Quiet') + (Common $p))).Code 0 'uninstall'
        Assert (-not (Test-Path $p.Install)) 'install dir remains'
        Assert (-not (Test-Path "$($p.Install).previous")) 'previous remains'
        Assert (Test-Path (Join-Path $p.Data 'policy\policy.json')) 'policy must be kept'
        Eq ([Environment]::GetEnvironmentVariable('Path', 'User')) $originalUserPath 'PATH not restored exactly'
        if (-not $hadUninstallKey) { Assert (-not (Test-Path $uninstallKey)) 'uninstall entry remains' }
        Eq (Inst $kit (@('-Action', 'Status', '-Quiet') + (Common $p))).Code 1 'status after uninstall'
        Eq (Inst $kit (@('-Action', 'Uninstall', '-Quiet') + (Common $p))).Code 0 'uninstall when absent is a no-op'
        Eq (Inst $kit (@('-Action', 'Install', '-NoPath', '-Quiet') + (Common $p))).Code 0 'reinstall'
        Eq (Inst $kit (@('-Action', 'Uninstall', '-PurgeData', '-Quiet') + (Common $p))).Code 0 'purge'
        Assert (-not (Test-Path $p.Data)) 'data remains after -PurgeData'
    }

    Case 'Rollback with no previous version is refused (40)' {
        $q = Prefix 'noprev'; Inst $kit (@('-Action', 'Install', '-NoPath', '-Quiet') + (Common $q)) | Out-Null
        Eq (Inst $kit (@('-Action', 'Rollback', '-Quiet') + (Common $q))).Code 40 'exit'
        Inst $kit (@('-Action', 'Uninstall', '-PurgeData', '-Quiet') + (Common $q)) | Out-Null
    }
}
finally {
    [Environment]::SetEnvironmentVariable('Path', $originalUserPath, 'User')
    if (-not $hadUninstallKey) { Remove-Item $uninstallKey -Recurse -Force -ErrorAction SilentlyContinue }
    Get-Process poweragent-worker -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$work*" } | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 300
    Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
    $restored = [Environment]::GetEnvironmentVariable('Path', 'User') -eq $originalUserPath
    Write-Host "user PATH restored exactly: $restored"
}
Write-Host ""
Write-Host "$passed passed, $fail failed"
exit ([int]($fail -gt 0))
