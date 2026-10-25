<#
Gate 0 probe (issue #54). Read-only. Reports whether this host meets the documented MXC
`processcontainer` OS-build floor and emits JSON shaped like poweragent-policy's `Probe`.
It does NOT detect the MXC SDK itself (not yet pinned), so mxcAvailable is always false
until that check exists; absence fails closed.
#>
$floors = @{ 26100 = 9278; 26200 = 9278; 26300 = 9550; 28000 = 2804 }  # Process Isolation, per MXC os-version-support.md
$cv = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
$build = [int]$cv.CurrentBuild
$ubr = [int]$cv.UBR
$floor = $floors[$build]
$meetsFloor = ($null -ne $floor) -and ($ubr -ge $floor)

$jea = $false
try { $jea = $null -ne (Get-PSSessionConfiguration -ErrorAction Stop | Where-Object { $_.RunAsVirtualAccount -or $_.SessionType -eq 'RestrictedRemoteServer' }) } catch { }

[ordered]@{
    os                 = "$($cv.ProductName) $($cv.DisplayVersion) build $build.$ubr"
    processIsolation   = [ordered]@{ requiredUbr = $floor; actualUbr = $ubr; meetsFloor = $meetsFloor }
    mxcAvailable       = $false
    mxcSupportsPolicy  = $false
    availableFallbacks = @(if ($jea) { 'jea' })
} | ConvertTo-Json -Depth 4
