# checks/80-podman.ps1 -- optional helper-container runtime. Required only if podman.require is set in the config.

function Get-PodmanCmd { Get-Ctx 'podman' { Get-Command $cfg.podman.bin -ErrorAction SilentlyContinue } }

Register-Check -Id 'OPT-01' -Category 'Optional: Podman' -Required $false -Title 'Podman installed (required only if podman.require)' -Run {
    $pcmd = Get-PodmanCmd
    if (-not $pcmd) { return New-Result $(if ($cfg.podman.require) { 'FAIL' } else { 'INFO' }) "'$($cfg.podman.bin)' not found; helper services will be unavailable" 'Install Podman (needs WSL2 or Hyper-V) if helper services are wanted.' }
    New-Result 'PASS' (Run-Exe $pcmd.Source @('--version')).Out.Trim()
}

Register-Check -Id 'OPT-02' -Category 'Optional: Podman' -Required $false -Title 'Podman engine reachable (required only if podman.require)' -Run {
    $pcmd = Get-PodmanCmd
    if (-not $pcmd) { return New-Result 'SKIP' 'no podman' }
    $pi = Run-Exe $pcmd.Source @('info', '--format', '{{.Host.Arch}}')
    $bad = if ($cfg.podman.require) { 'FAIL' } else { 'WARN' }
    New-Result $(if ($pi.Code -eq 0) { 'PASS' } else { $bad }) $(if ($pi.Code -eq 0) { "engine reachable ($($pi.Out.Trim()))" } else { "podman info failed: $($pi.Out.Trim().Split("`n")[0])" }) 'Start the Podman machine (podman machine start).'
}

Register-Check -Id 'OPT-03' -Category 'Optional: Podman' -Required $false -Title 'Every digest-pinned image in registryFile is present locally' -Run {
    $pcmd = Get-PodmanCmd
    if (-not $pcmd) { return New-Result 'SKIP' 'no podman' }
    if (-not $cfg.registryFile) { return New-Result 'SKIP' 'registryFile not configured' }
    $bad = if ($cfg.podman.require) { 'FAIL' } else { 'WARN' }
    $rf = Expand $cfg.registryFile
    if (-not (Test-Path $rf)) { return New-Result $bad "registryFile not found: $rf" }
    $imgs = @((Get-Content $rf -Raw | ConvertFrom-Json) | Where-Object { $_.image } | ForEach-Object { $_.image })
    $missing = @($imgs | Where-Object { (Run-Exe $pcmd.Source @('image', 'exists', $_)).Code -ne 0 })
    $notPinned = @($imgs | Where-Object { $_ -notmatch '@sha256:[0-9a-fA-F]{64}$' })
    $st = if ($missing -or $notPinned) { $bad } else { 'PASS' }
    New-Result $st $(if ($notPinned) { "not digest-pinned: $($notPinned -join ', ')" } elseif ($missing) { "not present locally: $($missing -join ', ')" } else { "$($imgs.Count) image(s) present and pinned" }) 'Pre-load the images by digest; PowerAgent never pulls.'
}
