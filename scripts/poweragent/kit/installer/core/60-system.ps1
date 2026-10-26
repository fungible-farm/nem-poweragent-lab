# core/60-system.ps1 -- the machine-state helpers actions use: PATH, the uninstall entry, and the data-directory ACLs.
# Each is small, idempotent, and independently testable.

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

# The security-critical invariants of the AllUsers data directory. Returns a list of violations (empty = holds).
#   policy\  : inheritance removed; Administrators and SYSTEM full control; nobody else may write, delete or change it
#              (in particular not Users, Everyone or Authenticated Users)
#   audit\ work\ logs\ : inheritance removed; Users may modify; Administrators and SYSTEM full control
function Test-DataAcl {
    $v = @()
    $write = [int][Security.AccessControl.FileSystemRights]'WriteData,AppendData,WriteExtendedAttributes,WriteAttributes,Delete,DeleteSubdirectoriesAndFiles,ChangePermissions,TakeOwnership'
    $full = [int][Security.AccessControl.FileSystemRights]::FullControl
    $trusted = 'S-1-5-18', 'S-1-5-32-544', 'S-1-3-0'          # SYSTEM, Administrators, CREATOR OWNER
    $sidOf = { param($r) try { $r.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } catch { "unresolvable:$($r.IdentityReference)" } }
    foreach ($d in 'policy', 'audit', 'work', 'logs') {
        $path = Join-Path $dataDir $d
        if (-not (Test-Path $path)) { $v += "$d is missing"; continue }
        $acl = Get-Acl $path
        if (-not $acl.AreAccessRulesProtected) { $v += "$d inherits permissions from its parent" }
        $allow = @($acl.Access | Where-Object { $_.AccessControlType -eq 'Allow' })
        foreach ($need in 'S-1-5-18', 'S-1-5-32-544') {
            $has = $allow | Where-Object { (& $sidOf $_) -eq $need -and (([int]$_.FileSystemRights -band $full) -eq $full) }
            if (-not $has) { $v += "${d}: $need lacks FullControl" }
        }
        if ($d -eq 'policy') {
            foreach ($r in $allow) {
                $sid = & $sidOf $r
                if ($sid -notin $trusted -and (([int]$r.FileSystemRights -band $write) -ne 0)) { $v += "policy: $sid can write ($($r.FileSystemRights))" }
            }
            if (-not ($allow | Where-Object { (& $sidOf $_) -eq 'S-1-5-32-545' })) { $v += 'policy: Users have no read access' }
        } else {
            $u = $allow | Where-Object { (& $sidOf $_) -eq 'S-1-5-32-545' }
            if (-not ($u | Where-Object { ([int]$_.FileSystemRights -band [int][Security.AccessControl.FileSystemRights]::Modify) -eq [int][Security.AccessControl.FileSystemRights]::Modify })) { $v += "${d}: Users cannot modify" }
        }
    }
    $v
}
function Set-DataAcl {
    if (-not $allUsers) { return }
    $grants = @(
        @('policy', @('*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F', '*S-1-5-32-545:(OI)(CI)RX')),   # administrators write, everyone reads
        @('audit',  @('*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F', '*S-1-5-32-545:(OI)(CI)M')),
        @('work',   @('*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F', '*S-1-5-32-545:(OI)(CI)M')),
        @('logs',   @('*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F', '*S-1-5-32-545:(OI)(CI)M')))
    foreach ($g in $grants) {
        $path = Join-Path $dataDir $g[0]
        # A native command's failure does not raise a PowerShell error: check every exit code.
        $o = & icacls $path /inheritance:r 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) { throw "icacls /inheritance:r failed on $path (exit $LASTEXITCODE): $($o.Trim())" }
        $o = & icacls $path /grant:r @($g[1]) 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) { throw "icacls /grant:r failed on $path (exit $LASTEXITCODE): $($o.Trim())" }
    }
    if ($env:POWERAGENT_INSTALLER_FAULT -eq 'acl') { throw 'injected fault: acl (after applying ACLs, before verification)' }
    # And verify the result actually is what the security model assumes; do not trust that the commands "worked".
    $bad = @(Test-DataAcl)
    if ($bad.Count) { throw "data directory permissions are not as required: $($bad -join '; ')" }
}
