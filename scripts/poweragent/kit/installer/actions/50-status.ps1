# actions/50-status.ps1 -- is the installed copy healthy? Files against the manifest; permissions against the security model.

function Invoke-StatusAction {
    $m = Installed-Manifest
    if (-not $m) { Say "Not installed at $installDir."; Finish 1 'not installed' }
    $bad = @($m.files | Where-Object { -not (Test-Path (Join-Path $installDir $_.path)) -or (Sha (Join-Path $installDir $_.path)) -ne $_.sha256 })
    $onPath = (Norm (Join-Path $installDir 'bin')) -in @([Environment]::GetEnvironmentVariable('Path', $pathTarget) -split ';' | ForEach-Object { Norm $_ })
    Say "PowerAgent $($m.version) ($($m.commit)) installed $($m.installedUtc) scope=$($m.scope)"
    Say "  installDir $installDir ; dataDir $($m.dataDir) ; on PATH: $onPath ; previous version kept: $(Test-Path $previousDir)"
    if ($m.components) { Say "  components: $((@($m.components) | ForEach-Object { "$($_.id)[$($_.type)]" }) -join ', ')" }
    if (@($m.skippedComponents).Count) { Say "  skipped: $((@($m.skippedComponents) | ForEach-Object component) -join ', ')" }
    if ($bad) { Say "  DRIFT in $($bad.Count) file(s): $(($bad | ForEach-Object path) -join ', ')"; Finish 12 'installed files differ from the manifest' }
    if ($allUsers) {
        $acl = @(Test-DataAcl)
        if ($acl.Count) { Say "  PERMISSION DRIFT: $($acl -join '; ')"; Finish 12 'data directory permissions differ from the security model' }
    }
    Finish 0 "healthy: $(@($m.files).Count) files match the manifest"
}
