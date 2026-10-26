#Requires -Version 7.0
#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Elevated test of the AllUsers install scope (development; not shipped). Run only after reading it.
.DESCRIPTION
  Installs to *test* locations (not the real ones):
      %ProgramFiles%\PowerAgent-test      and      %ProgramData%\PowerAgent-test
  Machine-wide changes it makes, all undone in `finally` and verified:
      - appends <ProgramFiles>\PowerAgent-test\bin to the MACHINE Path (restored byte for byte)
      - creates HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\PowerAgent (removed)
      - changes ACLs only on folders it creates (deleted at the end)
  It touches no services, firewall rules, scheduled tasks, drivers or WinRM.
#>
[CmdletBinding()]
param([string]$KitZip)
$ErrorActionPreference = 'Stop'
if (-not $KitZip) { $KitZip = (Get-ChildItem (Join-Path $PSScriptRoot '..\..\..\dist\poweragent-pilot-*.zip') | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName }
$work = Join-Path $env:TEMP "pa-allusers-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
$inst = Join-Path $env:ProgramFiles 'PowerAgent-test'
$data = Join-Path $env:ProgramData 'PowerAgent-test'
$key = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\PowerAgent'
$pw = (Get-Process -Id $PID).Path
$origMachinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
$hadKey = Test-Path $key
$pass = 0; $fail = 0
foreach ($d in $inst, $data, "$inst.previous", "$inst.new") { if (Test-Path $d) { throw "refusing to run: $d already exists (remove it first)" } }

function Case([string]$n, [scriptblock]$b) { try { & $b; Write-Host "PASS: $n"; $script:pass++ } catch { Write-Host "FAIL: $n -- $($_.Exception.Message)"; $script:fail++ } }
function Assert($c, [string]$m) { if (-not $c) { throw $m } }   # untyped: callers pass strings, arrays and booleans
function Inst([string]$kitDir, [string[]]$a, [hashtable]$env = @{}) {
    foreach ($k in $env.Keys) { Set-Item "env:$k" $env[$k] }
    try { $o = & $pw -NoProfile -File (Join-Path $kitDir 'Install-PowerAgent.ps1') @a 2>&1 | Out-String; [pscustomobject]@{ Code = $LASTEXITCODE; Out = $o } }
    finally { foreach ($k in $env.Keys) { Remove-Item "env:$k" -ErrorAction SilentlyContinue } }
}
$common = @('-Scope', 'AllUsers', '-InstallDir', $inst, '-DataDir', $data, '-Quiet')
function Rights($path, $sid) {
    (Get-Acl $path).Access | Where-Object { $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -eq $sid -and $_.AccessControlType -eq 'Allow' } |
        ForEach-Object { $_.FileSystemRights.ToString() }
}

try {
    New-Item -ItemType Directory $work | Out-Null
    Expand-Archive $KitZip -DestinationPath $work
    $kit = (Get-ChildItem $work -Directory | Select-Object -First 1).FullName

    Case 'Preflight as AllUsers passes when elevated (RIGHT-01)' {
        $r = Inst $kit (@('-Action', 'Preflight') + $common); Assert ($r.Code -eq 0) "exit $($r.Code): $($r.Out)"
    }
    Case 'AllUsers install succeeds' {
        $r = Inst $kit (@('-Action', 'Install') + $common); Assert ($r.Code -eq 0) "exit $($r.Code): $($r.Out)"
        Assert ((Get-Content "$inst\install-manifest.json" -Raw | ConvertFrom-Json).scope -eq 'AllUsers') 'manifest scope'
    }
    Case 'Machine PATH and HKLM uninstall entry were created' {
        Assert (([Environment]::GetEnvironmentVariable('Path', 'Machine') -split ';') -contains "$inst\bin") 'machine PATH entry missing'
        Assert (Test-Path $key) 'HKLM uninstall entry missing'
        Assert ((Get-ItemPropertyValue $key DisplayVersion) -eq '0.1.0') 'DisplayVersion'
    }
    Case 'Policy folder: Users read-only, Administrators and SYSTEM full control, inheritance removed' {
        $pol = Join-Path $data 'policy'
        $users = Rights $pol 'S-1-5-32-545'
        Assert ($users) 'Users have no rule on policy'
        foreach ($bad in 'Write', 'Modify', 'FullControl', 'CreateFiles', 'AppendData', 'Delete') { Assert (-not ($users -match $bad)) "Users hold '$bad' on policy: $users" }
        Assert (Rights $pol 'S-1-5-32-544' | Where-Object { $_ -match 'FullControl' }) 'Administrators lack FullControl'
        Assert (Rights $pol 'S-1-5-18' | Where-Object { $_ -match 'FullControl' }) 'SYSTEM lacks FullControl'
        Assert ((Get-Acl $pol).AreAccessRulesProtected) 'policy ACL still inherits from the parent'
        foreach ($sid in 'S-1-1-0', 'S-1-5-11') { Assert (-not (Rights $pol $sid | Where-Object { $_ -match 'Write|Modify|FullControl' })) "SID $sid can write policy" }
    }
    Case 'Audit/work/logs folders: Users may modify, inheritance removed' {
        foreach ($d in 'audit', 'work', 'logs') {
            $u = Rights (Join-Path $data $d) 'S-1-5-32-545'
            Assert ($u -match 'Modify') "Users cannot modify $d : $u"
            Assert ((Get-Acl (Join-Path $data $d)).AreAccessRulesProtected) "$d inherits"
        }
    }
    Case 'Default policy is deny-all and the installed probe runs from Program Files' {
        $pol = Get-Content "$data\policy\policy.json" -Raw | ConvertFrom-Json
        Assert (@($pol.allowedCapabilities).Count -eq 0) 'default policy allows something'
        $j = & "$inst\bin\poweragent-probe.exe" | ConvertFrom-Json
        Assert (@($j.backends | Where-Object backend -eq 'processcontainer').Count -eq 1) 'processcontainer not reported'
    }
    Case 'Status healthy; drift is detected' {
        Assert ((Inst $kit (@('-Action', 'Status') + $common)).Code -eq 0) 'healthy'
        $f = "$inst\docs\01-security-model.md"; $orig = Get-Content $f -Raw; Add-Content $f 'x'
        $c = (Inst $kit (@('-Action', 'Status') + $common)).Code
        [IO.File]::WriteAllText($f, $orig, [Text.UTF8Encoding]::new($false))
        Assert ($c -eq 12) "drift exit $c"
    }
    Case 'Status detects a weakened policy ACL (Users granted write) and reports drift (12)' {
        & icacls "$data\policy" /grant '*S-1-5-32-545:(OI)(CI)M' | Out-Null
        try { $c = (Inst $kit (@('-Action', 'Status') + $common)).Code } finally { & icacls "$data\policy" /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' | Out-Null }
        Assert ($c -eq 12) "weakened ACL not detected (exit $c)"
        Assert ((Inst $kit (@('-Action', 'Status') + $common)).Code -eq 0) 'status should be healthy again after restoring the ACL'
    }
    Case 'Injected verify failure during an AllUsers upgrade restores machine PATH, HKLM entry and files' {
        $before = [Environment]::GetEnvironmentVariable('Path', 'Machine')
        $r = Inst $kit (@('-Action', 'Upgrade') + $common) @{ POWERAGENT_INSTALLER_FAULT = 'verify' }
        Assert ($r.Code -eq 30) "exit $($r.Code)"
        Assert ([Environment]::GetEnvironmentVariable('Path', 'Machine') -eq $before) 'machine PATH not restored'
        Assert (Test-Path $key) 'HKLM entry lost'
        Assert ((Inst $kit (@('-Action', 'Status') + $common)).Code -eq 0) 'installed copy unhealthy after rollback'
    }
    Case 'A failure while applying/verifying permissions fails the install and leaves nothing behind (first install)' {
        Assert ((Inst $kit (@('-Action', 'Uninstall', '-PurgeData') + $common)).Code -eq 0) 'setup: uninstall'
        $before = [Environment]::GetEnvironmentVariable('Path', 'Machine')
        $r = Inst $kit (@('-Action', 'Install') + $common) @{ POWERAGENT_INSTALLER_FAULT = 'acl' }
        Assert ($r.Code -eq 20) "exit $($r.Code): $($r.Out)"
        Assert (-not (Test-Path $inst)) 'install dir left behind'
        Assert (-not (Test-Path $data)) 'data directory with unverified permissions left behind'
        Assert ([Environment]::GetEnvironmentVariable('Path', 'Machine') -eq $before) 'machine PATH not restored'
        Assert ((Inst $kit (@('-Action', 'Install') + $common)).Code -eq 0) 're-install after the failure'
    }
    Case 'Uninstall -PurgeData removes everything and restores the machine PATH exactly' {
        Assert ((Inst $kit (@('-Action', 'Uninstall', '-PurgeData') + $common)).Code -eq 0) 'uninstall'
        Assert (-not (Test-Path $inst)) 'install dir remains'
        Assert (-not (Test-Path $data)) 'data dir remains'
        Assert ([Environment]::GetEnvironmentVariable('Path', 'Machine') -eq $origMachinePath) 'machine PATH differs from the original'
        if (-not $hadKey) { Assert (-not (Test-Path $key)) 'HKLM entry remains' }
    }
}
finally {
    [Environment]::SetEnvironmentVariable('Path', $origMachinePath, 'Machine')
    if (-not $hadKey) { Remove-Item $key -Recurse -Force -ErrorAction SilentlyContinue }
    foreach ($d in $inst, "$inst.previous", "$inst.new", $data) { if (Test-Path $d) { Remove-Item $d -Recurse -Force -ErrorAction SilentlyContinue } }
    Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host ("machine PATH restored exactly: {0}; test folders removed: {1}" -f ([Environment]::GetEnvironmentVariable('Path', 'Machine') -eq $origMachinePath), (-not (Test-Path $inst)) -and (-not (Test-Path $data)))
}
Write-Host "`n$pass passed, $fail failed"
exit ([int]($fail -gt 0))
