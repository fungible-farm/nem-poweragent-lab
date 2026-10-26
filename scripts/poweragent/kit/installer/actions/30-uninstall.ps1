# actions/30-uninstall.ps1 -- remove exactly what the manifest says was installed. Policy and audit data are kept unless -PurgeData.

function Invoke-UninstallAction {
    $m = Installed-Manifest
    if (-not $m) { Say 'Not installed.'; Finish 0 'nothing to uninstall' }
    $running = Running-From $installDir
    if ($running) { Finish 40 "refused: running from the install directory: $(($running | ForEach-Object ProcessName) -join ', ')" }
    if ($allUsers -and -not $isAdmin) { Finish 10 'AllUsers uninstall needs an elevated shell' }
    Say "== Uninstall $($m.version)"
    if ($m.pathAdded) { Step "remove $installDir\bin from the $pathTarget PATH" { Path-Remove (Join-Path $installDir 'bin') } }
    if ($m.uninstallEntry) { Step 'remove the uninstall entry' { Remove-Item $m.uninstallKey -Recurse -Force -ErrorAction SilentlyContinue } }
    Step "delete $installDir" { Remove-Item $installDir -Recurse -Force }
    if (Test-Path $previousDir) { Step "delete $previousDir" { Remove-Item $previousDir -Recurse -Force } }
    if ($PurgeData) { if (Test-Path $dataDir) { Step "delete data directory $dataDir (policy, audit logs)" { Remove-Item $dataDir -Recurse -Force } } }
    else { Say "  kept data directory $dataDir (policy and audit logs); use -PurgeData to delete it" }
    Finish 0 $(if ($WhatIfPreference) { 'WhatIf: no changes made' } else { 'uninstalled' })
}
