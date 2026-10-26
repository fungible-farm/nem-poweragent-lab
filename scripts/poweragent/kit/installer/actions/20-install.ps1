# actions/20-install.ps1 -- install or upgrade. Preflight first; stage; keep the previous version; activate; configure; verify.
# Every failure after the first mutation undoes exactly what this run did (see the $script:* flags) and nothing else.

# Stage every active component under $stagingDir and return the manifest fragments (files, components, images, skipped).
function Stage-Components {
    $files = @(); $components = @(); $images = @(); $skipped = @()
    foreach ($c in (Get-ActiveComponents)) {
        if ($c.source.type -eq 'kit') {
            $to = if ($c.install.to -eq '.') { $stagingDir } else { Join-Path $stagingDir $c.install.to }
            $paths = @($c.source.paths) + @(@($c.source.optionalPaths) | Where-Object { $_ }) | Where-Object { $_ }
            foreach ($p in $paths) {
                $src = Join-Path $kit $p
                if (-not (Test-Path $src)) {
                    if ($p -in @($c.source.optionalPaths)) { continue }
                    throw "component '$($c.id)': payload '$p' is missing from the kit"
                }
                $dst = Join-Path $to $p
                New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent) | Out-Null
                Copy-Item $src $dst -Recurse -Force
                foreach ($f in @(Get-Item $dst) + @(if ((Get-Item $dst).PSIsContainer) { Get-ChildItem $dst -Recurse -File })) {
                    if ($f.PSIsContainer) { continue }
                    $files += [ordered]@{ path = $f.FullName.Substring($stagingDir.Length + 1).Replace('\', '/'); sha256 = Sha $f.FullName; component = $c.id }
                }
            }
            $components += [ordered]@{ id = $c.id; type = 'kit' }
        } else {
            $t = Test-OciComponent $c
            if ($t.Installable) {
                $images += [ordered]@{ component = $c.id; reference = $t.Reference; signature = 'unverified-allowed'; verified = $false }
                $components += [ordered]@{ id = $c.id; type = 'oci' }
            } elseif ($c.required) {
                throw "component '$($c.id)' cannot be installed: pinned=$($t.Pinned) present=$($t.Present); $($t.Note)"
            } else {
                $skipped += [ordered]@{ component = $c.id; reason = "pinned=$($t.Pinned) present=$($t.Present); $($t.Note)" }
            }
        }
    }
    [pscustomobject]@{ Files = $files; Components = $components; Images = $images; Skipped = $skipped }
}

function Invoke-InstallAction {
    Say '== Preflight'
    Invoke-Checks; Show-Checks
    $v = Preflight-Verdict
    if ($v -ne 0) { Finish $v $(if ($v -eq 10) { 'preflight failed (required checks); nothing was changed' } else { 'preflight warnings; failOnWarning is set; nothing was changed' }) }
    $new = Read-Json (Join-Path $kit 'data\kit-info.json')
    $old = Installed-Manifest
    Say "== $(if ($old) { "Upgrade $($old.version) -> $($new.version)" } else { "Install $($new.version)" }) ($($cfg.scope))"
    # What this run has actually done, so a failure undoes exactly that and nothing else.
    $script:dataExisted = Test-Path $dataDir
    $script:movedCurrent = $false; $script:activated = $false; $script:pathTouched = $false; $script:entryTouched = $false; $script:verifyFailed = $false
    try {
        if ($env:POWERAGENT_INSTALLER_FAULT -eq 'stage') { throw 'injected fault: stage' }
        Step "stage the components in $stagingDir" {
            if (Test-Path $stagingDir) { Remove-Item $stagingDir -Recurse -Force }
            New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null
            $staged = Stage-Components
            foreach ($s in $staged.Skipped) { Say "  skipped optional component $($s.component): $($s.reason)" }
            $script:ComponentReport = @($staged.Components) + @($staged.Skipped | ForEach-Object { [ordered]@{ id = $_.component; type = 'oci'; skipped = $_.reason } })
            Write-Json (Join-Path $stagingDir 'install-manifest.json') ([ordered]@{
                product = 'PowerAgent'; version = $new.version; commit = $new.commit; installedUtc = (Get-Date).ToUniversalTime().ToString('o')
                scope = $cfg.scope; installDir = $installDir; dataDir = $dataDir; pathAdded = [bool]$cfg.addToPath; uninstallEntry = [bool]$cfg.registerUninstallEntry
                uninstallKey = $uninstallKey; components = $staged.Components; images = $staged.Images; skippedComponents = $staged.Skipped; files = $staged.Files })
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
        Step 'verify the installed copy (hashes, permissions, backend)' {
            if ($env:POWERAGENT_INSTALLER_FAULT -eq 'verify') { $script:verifyFailed = $true; throw 'injected fault: verification' }
            $m = Read-Json $manifestPath
            $bad = @($m.files | Where-Object { (Sha (Join-Path $installDir $_.path)) -ne $_.sha256 })
            if ($bad) { throw "installed files differ from the manifest: $(($bad | ForEach-Object path) -join ', ')" }
            if ($allUsers) { $acl = @(Test-DataAcl); if ($acl.Count) { throw "data directory permissions are not as required: $($acl -join '; ')" } }
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
            if (-not $script:dataExisted -and (Test-Path $dataDir)) { Remove-Item $dataDir -Recurse -Force -ErrorAction SilentlyContinue }   # created by this run; its permissions are unverified
            if ($script:pathTouched) { try { if ($old -and $old.pathAdded) { Path-Add (Join-Path $installDir 'bin') } else { Path-Remove (Join-Path $installDir 'bin') } } catch {} }
            if ($script:entryTouched) { try { if ($old -and $old.uninstallEntry) { Set-UninstallEntry $old } else { Remove-Item $uninstallKey -Recurse -Force -ErrorAction SilentlyContinue } } catch {} }
        }
        Finish $(if ($vf) { 30 } else { 20 }) "install failed and was rolled back: $msg"
    }
    Finish 0 $(if ($WhatIfPreference) { 'WhatIf: no changes made' } else { "installed $($new.version) at $installDir" })
}
