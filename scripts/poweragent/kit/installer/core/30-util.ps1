# core/30-util.ps1 -- small, side-effect-free helpers shared by checks and actions.

function Read-Json([string]$p) { Get-Content $p -Raw | ConvertFrom-Json }
function Write-Json([string]$p, $o) { [IO.File]::WriteAllText($p, ($o | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false)) }
function Sha([string]$p) { (Get-FileHash $p -Algorithm SHA256).Hash.ToLower() }
function Norm([string]$p) { $p.TrimEnd('\').ToLowerInvariant() }
function Nearest-Existing([string]$p) { while ($p -and -not (Test-Path $p)) { $p = Split-Path $p -Parent }; $p }

# Can this location be written? Probes the nearest existing parent with a temp file that it always removes
# (even under -WhatIf), so a read-only check never leaves anything behind.
function Can-Write([string]$dir) {
    $d = Nearest-Existing $dir
    if (-not $d) { return $false }
    $t = Join-Path $d ".pa-write-test-$([guid]::NewGuid().ToString('N'))"
    try { [IO.File]::WriteAllText($t, 'x'); Remove-Item $t -Force -WhatIf:$false; $true } catch { $false }
}

# Run a native program; its stderr is data, not a PowerShell error. Returns Code and Out.
function Run-Exe([string]$exe, [string[]]$a) {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { $o = & $exe @a 2>&1 | Out-String; $c = $LASTEXITCODE } finally { $ErrorActionPreference = $old }
    [pscustomobject]@{ Code = $c; Out = $o }
}

function Installed-Manifest { if (Test-Path $manifestPath) { Read-Json $manifestPath } }
function Running-From([string]$dir) {
    @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($dir + '\', [StringComparison]::OrdinalIgnoreCase) -and $_.Id -ne $PID })
}
