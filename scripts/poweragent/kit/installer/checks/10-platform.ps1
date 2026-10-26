# checks/10-platform.ps1 -- is this machine a Windows 11 build that can run the MXC sandbox backend?

function Get-WinVer {
    Get-Ctx 'winver' {
        $cv = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
        [pscustomobject]@{ Build = [int]$cv.CurrentBuild; Ubr = [int]$cv.UBR; Edition = $cv.EditionID; Display = $cv.DisplayVersion }
    }
}

Register-Check -Id 'PLAT-01' -Category 'Platform' -Required $true -Title 'Operating system is Windows 11' -Run {
    $b = if ($IsWindows) { (Get-WinVer).Build } else { 0 }
    $n = if ($b -ge 22000) { 'Windows 11' } elseif ($b -gt 0) { 'Windows 10 or older' } else { [Runtime.InteropServices.RuntimeInformation]::OSDescription }
    New-Result $(if ($IsWindows -and $b -ge 22000) { 'PASS' } else { 'FAIL' }) "$n (build $b)" 'Run on Windows 11.'
}

Register-Check -Id 'PLAT-02' -Category 'Platform' -Required $true -Title '64-bit process on x64 hardware (ARM64 is untested)' -Run {
    $arch = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture
    $ok = [Environment]::Is64BitProcess -and $arch -eq 'X64'
    New-Result $(if ($ok) { 'PASS' } else { 'FAIL' }) "OS architecture $arch; 64-bit process: $([Environment]::Is64BitProcess)" 'The kit is x64 only; ARM64 has not been built or tested.'
}

Register-Check -Id 'PLAT-03' -Category 'Platform' -Required $true -Title 'Windows build meets the MXC processcontainer floor (data\mxc-os-floor.txt)' -Run {
    $floorFile = Join-Path $kit 'data\mxc-os-floor.txt'
    if (-not (Test-Path $floorFile)) { return New-Result 'FAIL' 'data\mxc-os-floor.txt is missing' 'Re-extract the kit.' }
    $v = Get-WinVer
    $row = Get-Content $floorFile | Where-Object { $_ -match '^\s*(\d+)\s+(\d+)\s*$' -and [int]$Matches[1] -eq $v.Build } | Select-Object -First 1
    if (-not $row) { return New-Result 'FAIL' "Windows build $($v.Build) is not in the floor table" 'Use a Windows 11 build listed in data\mxc-os-floor.txt (24H2, 25H2, 26H2, 26H1).' }
    $need = [int](($row -split '\s+' | Where-Object { $_ })[1])
    New-Result $(if ($v.Ubr -ge $need) { 'PASS' } else { 'FAIL' }) "build $($v.Build).$($v.Ubr); floor $($v.Build).$need" "Install Windows updates until the revision is at least $need."
}

Register-Check -Id 'PLAT-04' -Category 'Platform' -Required $false -Title 'Windows edition and virtual-machine status (informational)' -Run {
    $v = Get-WinVer
    $hv = try { (Get-CimInstance Win32_ComputerSystem).HypervisorPresent } catch { $null }
    New-Result 'INFO' "$($v.Edition), display version $($v.Display), hypervisor present: $hv"
}
