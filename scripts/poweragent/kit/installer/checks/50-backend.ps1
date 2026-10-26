# checks/50-backend.ps1 -- does the sandbox backend actually work here, and does it fail closed?

function Get-Probe {
    Get-Ctx 'probe' {
        $exe = Join-Path $kit 'bin\poweragent-probe.exe'
        if (-not (Test-Path $exe)) { return $null }
        $r = Run-Exe $exe @()
        $json = try { $r.Out | ConvertFrom-Json } catch { $null }
        [pscustomobject]@{ Result = $r; Json = $json }
    }
}

Register-Check -Id 'BACK-01' -Category 'Sandbox backend' -Required $true -Title 'The probe executes on this machine' -Run {
    $p = Get-Probe
    if (-not $p) { return New-Result 'SKIP' 'probe binary missing (see KIT-03)' }
    $ok = $p.Result.Code -eq 0 -and $p.Json
    New-Result $(if ($ok) { 'PASS' } else { 'FAIL' }) $(if ($p.Json) { "exit $($p.Result.Code)" } else { "exit $($p.Result.Code): $($p.Result.Out.Trim().Split("`n")[0])" }) 'If the exe is blocked (WDAC/AppLocker/antivirus), see SEC-01..03.'
}

Register-Check -Id 'BACK-02' -Category 'Sandbox backend' -Required $true -Title 'The expected MXC backend is reported available' -Run {
    $p = Get-Probe
    if (-not $p) { return New-Result 'SKIP' 'probe binary missing (see KIT-03)' }
    $be = @($p.Json.backends) | Where-Object { $_.backend -eq $cfg.verify.expectBackend }
    New-Result $(if ($be) { 'PASS' } else { 'FAIL' }) $(if ($be) { "$($cfg.verify.expectBackend) available" } else { "backend '$($cfg.verify.expectBackend)' not reported; reported: $((@($p.Json.backends) | ForEach-Object backend) -join ', ')" }) 'Update Windows to the build floor; the sandbox backend is unavailable on this machine.'
}

Register-Check -Id 'BACK-03' -Category 'Sandbox backend' -Required $false -Title 'Backend tier (informational)' -Run {
    $p = Get-Probe
    if (-not $p) { return New-Result 'SKIP' 'probe binary missing (see KIT-03)' }
    $be = @($p.Json.backends) | Where-Object { $_.backend -eq $cfg.verify.expectBackend }
    New-Result 'INFO' $(if ($be) { "tier $($be.tier); capabilities: $(@($be.capabilities) -join ', ')" } else { 'n/a' })
}

Register-Check -Id 'BACK-04' -Category 'Sandbox backend' -Required $true -Title 'Fail-closed: a network request is denied (self-test)' -Run {
    $exe = Join-Path $kit 'bin\poweragent-probe.exe'
    if (-not (Test-Path $exe)) { return New-Result 'SKIP' 'probe binary missing (see KIT-03)' }
    $net = Run-Exe $exe @('--profile', (Join-Path $kit 'fixtures\profile-net.json'), '--policy', (Join-Path $kit 'fixtures\policy-allow.json'))
    New-Result $(if ($net.Code -eq 3 -and $net.Out -match 'containment_unavailable') { 'PASS' } else { 'FAIL' }) "exit $($net.Code)" 'The fail-closed self-test did not behave as designed; do not install.'
}
