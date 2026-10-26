# checks/30-kit.ps1 -- is the extracted kit intact and trustworthy? (Installer code itself was verified at bootstrap.)

Register-Check -Id 'KIT-01' -Category 'Kit integrity' -Required $true -Title 'SHA256SUMS present' -Run {
    $s = Join-Path $kit 'SHA256SUMS'
    if (Test-Path $s) { New-Result 'PASS' $s } else { New-Result 'FAIL' 'SHA256SUMS missing' 'Re-extract the kit from the original zip.' }
}

Register-Check -Id 'KIT-02' -Category 'Kit integrity' -Required $true -Title 'Every kit file matches SHA256SUMS' -Run {
    $sums = Join-Path $kit 'SHA256SUMS'
    if (-not (Test-Path $sums)) { return New-Result 'SKIP' 'no SHA256SUMS' }
    $bad = @(); $n = 0
    foreach ($l in Get-Content $sums) {
        if ($l -notmatch '^([0-9a-f]{64})  (.+)$') { continue }
        $n++; $f = Join-Path $kit $Matches[2]
        if (-not (Test-Path $f) -or (Sha $f) -ne $Matches[1]) { $bad += $Matches[2] }
    }
    New-Result $(if ($bad.Count -eq 0) { 'PASS' } else { 'FAIL' }) $(if ($bad.Count) { "changed or missing: $($bad -join ', ')" } else { "$n files verified" }) 'Re-extract the kit; compare the zip with its .sha256 file.'
}

Register-Check -Id 'KIT-03' -Category 'Kit integrity' -Required $true -Title 'Required kit files present (binaries, data)' -Run {
    $req = 'bin\poweragent.exe', 'bin\poweragent-worker.exe', 'bin\poweragent-probe.exe', 'data\kit-info.json', 'data\imports.json', 'data\mxc-os-floor.txt', 'fixtures\profile-net.json', 'fixtures\policy-allow.json'
    $miss = $req | Where-Object { -not (Test-Path (Join-Path $kit $_)) }
    New-Result $(if ($miss) { 'FAIL' } else { 'PASS' }) $(if ($miss) { "missing: $($miss -join ', ')" } else { "$($req.Count) required files present" }) 'Re-extract the kit.'
}

Register-Check -Id 'KIT-04' -Category 'Kit integrity' -Required $false -Title 'No Mark-of-the-Web (downloaded-file block) on kit files' -Run {
    $motw = Get-ChildItem $kit -Recurse -File | Where-Object { Get-Item $_.FullName -Stream Zone.Identifier -ErrorAction SilentlyContinue } | Select-Object -First 5
    New-Result $(if ($motw) { 'WARN' } else { 'PASS' }) $(if ($motw) { "downloaded-file marker on $(($motw | ForEach-Object Name) -join ', ') ..." } else { 'no Zone.Identifier streams' }) 'Run: Get-ChildItem <kit> -Recurse | Unblock-File  (after verifying the zip hash).'
}

Register-Check -Id 'KIT-05' -Category 'Kit integrity' -Required $false -Title 'Authenticode signatures (required only if requireSignedBinaries)' -Run {
    $sig = @{}
    foreach ($e in 'poweragent.exe', 'poweragent-worker.exe', 'poweragent-probe.exe') {
        $f = Join-Path $kit "bin\$e"
        if (Test-Path $f) { $sig[$e] = (Get-AuthenticodeSignature $f).Status.ToString() }
    }
    $unsigned = $sig.Keys | Where-Object { $sig[$_] -ne 'Valid' }
    $st = if (-not $unsigned) { 'PASS' } elseif ($cfg.requireSignedBinaries) { 'FAIL' } else { 'WARN' }
    New-Result $st (($sig.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join '; ') 'Use a signed release, or set requireSignedBinaries=false for a lab pilot.'
}
