# checks/60-security.ps1 -- what application-control and protection policy is this machine under? (informational)

Register-Check -Id 'SEC-01' -Category 'Security posture' -Required $false -Title 'Code-integrity (WDAC) policies present (informational)' -Run {
    $ci = try { @(Get-ChildItem 'C:\Windows\System32\CodeIntegrity\CiPolicies\Active' -ErrorAction Stop).Count } catch { -1 }
    New-Result 'INFO' $(if ($ci -ge 0) { "$ci active code-integrity policy file(s); the Windows default set is non-zero, review if your organisation deploys WDAC" } else { 'could not enumerate (needs elevation)' })
}

Register-Check -Id 'SEC-02' -Category 'Security posture' -Required $false -Title 'AppLocker policy present (informational)' -Run {
    New-Result 'INFO' $(if (Test-Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\SrpV2') { 'AppLocker rule collections present; unsigned binaries may be blocked' } else { 'no AppLocker policy found' })
}

Register-Check -Id 'SEC-03' -Category 'Security posture' -Required $false -Title 'Microsoft Defender real-time protection (informational)' -Run {
    $mp = try { (Get-MpComputerStatus -ErrorAction Stop).RealTimeProtectionEnabled } catch { $null }
    New-Result 'INFO' $(if ($null -ne $mp) { "Defender real-time protection: $mp" } else { 'Defender status unavailable (third-party AV or insufficient rights)' })
}

Register-Check -Id 'SEC-04' -Category 'Security posture' -Required $false -Title 'PowerShell execution policy (informational)' -Run {
    New-Result 'INFO' "effective execution policy: $(Get-ExecutionPolicy)"
}
