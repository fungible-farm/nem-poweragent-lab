# checks/40-dependencies.ps1 -- does every load-time dependency of every binary resolve on THIS machine?
# data\imports.json is extracted from the binaries when the kit is built (scripts/poweragent/pe_imports.py).

# One check per binary. The body is built from a template (not a closure) so it runs in the installer's own scope.
$depTemplate = @'
$impFile = Join-Path $kit 'data\imports.json'
if (-not (Test-Path $impFile)) { return New-Result 'SKIP' 'data\imports.json missing (see KIT-03)' }
$dlls = @((Read-Json $impFile).'__EXE__'); $unres = @()
foreach ($d in $dlls) {
    $h = [IntPtr]::Zero
    $ok = [Runtime.InteropServices.NativeLibrary]::TryLoad($d, [ref]$h)
    if ($ok) { [Runtime.InteropServices.NativeLibrary]::Free($h) } else { $unres += $d }
    $script:ImportsReport += [pscustomobject]@{ exe = '__EXE__'; dll = $d; resolved = $ok }
}
New-Result $(if ($unres) { 'FAIL' } else { 'PASS' }) $(if ($unres) { "unresolved: $($unres -join ', ')" } else { "$($dlls.Count) DLLs resolved" }) 'Install the missing Windows component or update Windows.'
'@
foreach ($pair in @(@('DEP-01', 'poweragent.exe'), @('DEP-02', 'poweragent-worker.exe'), @('DEP-03', 'poweragent-probe.exe'))) {
    Register-Check -Id $pair[0] -Category 'Dependencies' -Required $true -Title "Every load-time DLL of $($pair[1]) resolves on this machine" `
        -Run ([scriptblock]::Create($depTemplate.Replace('__EXE__', $pair[1])))
}

Register-Check -Id 'DEP-04' -Category 'Dependencies' -Required $false -Title 'No Visual C++ Redistributable needed (static C runtime)' -Run {
    $impFile = Join-Path $kit 'data\imports.json'
    if (-not (Test-Path $impFile)) { return New-Result 'SKIP' 'data\imports.json missing (see KIT-03)' }
    $imp = Read-Json $impFile
    $vc = @($imp.PSObject.Properties.Value | ForEach-Object { $_ } | Where-Object { $_ -match '(?i)^(vcruntime|msvcp|msvcr|api-ms-win-crt|ucrtbase)' })
    New-Result $(if ($vc) { 'WARN' } else { 'PASS' }) $(if ($vc) { "imports the C runtime: $(($vc | Select-Object -Unique) -join ', ')" } else { 'no Visual C++ / UCRT imports (statically linked)' }) 'Install the Microsoft Visual C++ Redistributable (x64).'
}
