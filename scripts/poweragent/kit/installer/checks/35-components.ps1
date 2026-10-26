# checks/35-components.ps1 -- are the component descriptors sound, and can every component be installed here?

Register-Check -Id 'COMP-01' -Category 'Components' -Required $true -Title 'Component descriptors are valid, dependencies resolve, no cycles' -Run {
    $p = Get-ComponentPlan
    if ($p.Errors.Count) { return New-Result 'FAIL' ($p.Errors -join '; ') 'Fix or remove the invalid descriptor under components\ (and regenerate SHA256SUMS).' }
    if (-not $p.Components.Count) { return New-Result 'FAIL' 'no components found under components\' 'Re-extract the kit.' }
    New-Result 'PASS' "$($p.Components.Count) component(s): $(($p.Components | ForEach-Object id) -join ', ')"
}

Register-Check -Id 'COMP-02' -Category 'Components' -Required $true -Title 'Every kit component payload is present in the kit' -Run {
    $plan = Get-ComponentPlan
    if ($plan.Errors.Count) { return New-Result 'SKIP' 'descriptors invalid (see COMP-01)' }
    $missing = @()
    foreach ($c in (Get-ActiveComponents | Where-Object { $_.source.type -eq 'kit' })) {
        foreach ($p in @($c.source.paths)) { if (-not (Test-Path (Join-Path $kit $p))) { $missing += "$($c.id): $p" } }
    }
    New-Result $(if ($missing) { 'FAIL' } else { 'PASS' }) $(if ($missing) { "missing: $($missing -join ', ')" } else { 'all payloads present' }) 'Re-extract the kit.'
}

Register-Check -Id 'COMP-03' -Category 'Components' -Required $true -Title 'OCI components are digest-pinned, present locally and pass the signature gate' -Run {
    $plan = Get-ComponentPlan
    if ($plan.Errors.Count) { return New-Result 'SKIP' 'descriptors invalid (see COMP-01)' }
    $oci = @(Get-ActiveComponents | Where-Object { $_.source.type -eq 'oci' })
    if (-not $oci.Count) { return New-Result 'PASS' 'no OCI components' }
    $problems = @(); $warns = @(); $ok = @()
    foreach ($c in $oci) {
        $t = Test-OciComponent $c
        $why = @()
        if (-not $t.Pinned) { $why += 'not digest-pinned' }
        if (-not $t.Present) { $why += 'not present in the local Podman store (the installer never pulls)' }
        if ($t.SignatureRequired) { $why += $t.Note }
        elseif ($t.Installable) { $warns += "$($c.id): $($t.Note)" }
        if ($why.Count) { if ($c.required) { $problems += "$($c.id): $($why -join '; ')" } else { $warns += "$($c.id) will be SKIPPED: $($why -join '; ')" } }
        elseif ($t.Installable) { $ok += $c.id }
    }
    if ($problems.Count) { return New-Result 'FAIL' ($problems -join ' | ') 'Pin by digest, pre-load the image, and use a verification mechanism, or mark the component optional.' }
    if ($warns.Count) { return New-Result 'WARN' ($warns -join ' | ') 'Components that cannot be verified are not installed unless signature checking is explicitly waived.' }
    New-Result 'PASS' "$($ok.Count) OCI component(s) ready: $($ok -join ', ')"
}
