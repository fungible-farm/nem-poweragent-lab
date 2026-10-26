# checks/70-management.ps1 -- is this device joined to a directory or enrolled in device management? (informational)

function Get-DsReg {
    Get-Ctx 'dsreg' {
        $text = dsregcmd /status 2>$null | Out-String
        $get = { param($k) if ($text -match "(?m)^[ \t]*$k[ \t]*:[ \t]*(\S.*)?$") { "$($Matches[1])".Trim() } else { '' } }
        [pscustomobject]@{ AzureAdJoined = (& $get 'AzureAdJoined'); DomainJoined = (& $get 'DomainJoined'); Tenant = (& $get 'TenantName'); MdmUrl = (& $get 'MdmUrl') }
    }
}

Register-Check -Id 'MGMT-01' -Category 'Management' -Required $false -Title 'Entra / domain join state (informational)' -Run {
    $d = Get-DsReg
    New-Result 'INFO' "AzureAdJoined=$($d.AzureAdJoined) DomainJoined=$($d.DomainJoined) Tenant=$($d.Tenant)"
}

Register-Check -Id 'MGMT-02' -Category 'Management' -Required $false -Title 'MDM (Intune) enrollment (informational)' -Run {
    $d = Get-DsReg
    New-Result 'INFO' $(if ($d.MdmUrl) { "MDM enrolled ($($d.MdmUrl))" } else { 'no MDM enrollment detected (MdmUrl is empty)' })
}
