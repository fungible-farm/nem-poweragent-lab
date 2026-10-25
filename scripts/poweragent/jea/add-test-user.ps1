#Requires -RunAsAdministrator
# Gate 3 test identity: create a NON-admin local user 'pa-jea-test' and map it to the JEA endpoint.
# Why: an Entra-joined account cannot authenticate to a WinRM listener on localhost (0x8009030e).
# The password is typed by you into this window as a SecureString. It is never written to disk, a
# log or a parameter, and the calling session never sees it. teardown.ps1 deletes the account.
$ErrorActionPreference = 'Stop'
$name = 'pa-jea-test'

if (Get-LocalUser -Name $name -ErrorAction SilentlyContinue) { throw "Local user '$name' already exists; run teardown.ps1 first." }

$pw1 = Read-Host -AsSecureString "Choose a password for local user '$name' (a throwaway; it expires in 7 days)"
$pw2 = Read-Host -AsSecureString 'Repeat the password'
$a = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($pw1)
$b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($pw2)
try {
    $same = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($a) -ceq [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)
    $empty = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($a).Length -eq 0
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($a); [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b)
}
if (-not $same -or $empty) { throw 'Passwords differ or are empty; nothing was created.' }

# Standard (non-admin) user: member of 'Users' only, expires in 7 days, cannot change its password.
New-LocalUser -Name $name -Password $pw1 -AccountExpires (Get-Date).AddDays(7) -UserMayNotChangePassword `
    -Description 'PowerAgent Gate 3 JEA test (temporary; removed by teardown.ps1)' | Out-Null
Add-LocalGroupMember -Group 'Users' -Member $name -ErrorAction SilentlyContinue

# WinRM refuses non-administrators unless they are in 'Remote Management Users'. This grants only
# the right to reach WinRM; what they can do there is what the endpoint's role allows.
Add-LocalGroupMember -Group 'Remote Management Users' -Member $name

# Re-register the endpoint so both identities map to the same single role.
& (Join-Path $PSScriptRoot 'setup.ps1') -User @('AzureAD\BrianHorakh', "$env:COMPUTERNAME\$name")

Write-Host "OK: local user '$name' (non-admin) created and mapped. Now run verify.ps1 NON-elevated."
