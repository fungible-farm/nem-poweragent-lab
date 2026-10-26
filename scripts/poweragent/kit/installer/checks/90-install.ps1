# checks/90-install.ps1 -- what is already installed, and would this run conflict with it?

Register-Check -Id 'INST-01' -Category 'Existing install' -Required $false -Title 'Existing installation and version (informational)' -Run {
    $m = Installed-Manifest
    New-Result 'INFO' $(if ($m) { "installed version $($m.version) ($($m.commit)) at $installDir" } else { 'not installed' })
}

Register-Check -Id 'INST-02' -Category 'Existing install' -Required $true -Title 'No downgrade without -Force' -Run {
    $m = Installed-Manifest
    $infoFile = Join-Path $kit 'data\kit-info.json'
    $new = if (Test-Path $infoFile) { Read-Json $infoFile } else { $null }
    $down = $m -and $new -and ([version]$new.version -lt [version]$m.version)
    New-Result $(if ($down -and -not $Force) { 'FAIL' } else { 'PASS' }) $(if ($down) { "kit $($new.version) is older than installed $($m.version)" } else { 'not a downgrade' }) 'Pass -Force to downgrade deliberately.'
}

Register-Check -Id 'INST-03' -Category 'Existing install' -Required $false -Title 'No other poweragent.exe earlier on PATH' -Run {
    $binDir = Join-Path $installDir 'bin'
    $other = @(Get-Command poweragent.exe -All -ErrorAction SilentlyContinue | Where-Object { (Norm (Split-Path $_.Source -Parent)) -ne (Norm $binDir) })
    New-Result $(if ($other) { 'WARN' } else { 'PASS' }) $(if ($other) { "another poweragent.exe on PATH: $($other[0].Source)" } else { 'no conflicting poweragent.exe on PATH' }) 'Remove the other copy from PATH or invoke by full path.'
}

Register-Check -Id 'INST-04' -Category 'Existing install' -Required $true -Title 'No PowerAgent process running from the install directory' -Run {
    $running = Running-From $installDir
    New-Result $(if ($running) { 'FAIL' } else { 'PASS' }) $(if ($running) { "running from install dir: $(($running | ForEach-Object ProcessName) -join ', ')" } else { 'none' }) 'Stop those processes first.'
}
