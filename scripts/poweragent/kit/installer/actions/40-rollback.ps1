# actions/40-rollback.ps1 -- swap the installed version with the kept previous one (run again to swap back).

function Invoke-RollbackAction {
    if (-not (Test-Path $previousDir)) { Finish 40 "refused: no previous version at $previousDir" }
    if (Running-From $installDir) { Finish 40 'refused: PowerAgent is running from the install directory' }
    Say '== Rollback to the previous version'
    $swap = "$installDir.swap"
    Step "swap $installDir and $previousDir" {
        if (Test-Path $swap) { Remove-Item $swap -Recurse -Force }
        Move-Item $installDir $swap; Move-Item $previousDir $installDir; Move-Item $swap $previousDir
    }
    if (-not $WhatIfPreference) {
        $pm = Installed-Manifest
        if ($pm.uninstallEntry) { Set-UninstallEntry $pm }
        Say "  now running $($pm.version); the other version is kept at $previousDir (run Rollback again to swap back)"
    }
    Finish 0 $(if ($WhatIfPreference) { 'WhatIf: no changes made' } else { 'rolled back' })
}
