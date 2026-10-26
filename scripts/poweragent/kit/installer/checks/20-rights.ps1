# checks/20-rights.ps1 -- may this run write where it needs to, with the rights the chosen scope requires?

Register-Check -Id 'RIGHT-01' -Category 'Rights' -Required $true -Title 'Elevation matches the requested scope (AllUsers needs administrator)' -Run {
    New-Result $(if ($allUsers -and -not $isAdmin) { 'FAIL' } else { 'PASS' }) "scope $($cfg.scope); elevated: $isAdmin" 'For AllUsers run PowerShell as administrator, or use -Scope CurrentUser.'
}

Register-Check -Id 'RIGHT-02' -Category 'Rights' -Required $true -Title 'Install directory location is writable' -Run {
    New-Result $(if (Can-Write $installDir) { 'PASS' } else { 'FAIL' }) $installDir 'Choose a writable -InstallDir or elevate.'
}

Register-Check -Id 'RIGHT-03' -Category 'Rights' -Required $true -Title 'Data directory location is writable' -Run {
    New-Result $(if (Can-Write $dataDir) { 'PASS' } else { 'FAIL' }) $dataDir 'Choose a writable -DataDir or elevate.'
}

Register-Check -Id 'RIGHT-04' -Category 'Rights' -Required $true -Title 'Free disk space on the install drive' -Run {
    $root = [IO.Path]::GetPathRoot($installDir)
    $free = try { [math]::Floor((New-Object IO.DriveInfo($root)).AvailableFreeSpace / 1MB) } catch { -1 }
    New-Result $(if ($free -ge $cfg.minFreeDiskMB) { 'PASS' } else { 'FAIL' }) "$free MB free on $root; need $($cfg.minFreeDiskMB)" 'Free disk space or lower minFreeDiskMB.'
}
