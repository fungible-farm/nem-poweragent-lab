# Gate 3 JEA checks. Run NON-elevated, after add-test-user.ps1. You are prompted for the
# 'pa-jea-test' password; it is held only as a PSCredential in this process. Every "must fail"
# case is a real attempt against the endpoint.
param([string]$LogPath)
$ErrorActionPreference = 'Stop'
if ($LogPath) { Start-Transcript -Path $LogPath -Force | Out-Null }
$cfg  = 'PowerAgent.Gate3'
$root = 'C:\ProgramData\PowerAgent\jea-data'
$fail = 0
function Check($name, [scriptblock]$body, [bool]$expectOk) {
    try { $r = & $body; $ok = $true } catch { $r = $_.Exception.Message; $ok = $false }
    $pass = ($ok -eq $expectOk)
    if (-not $pass) { $script:fail++ }
    '{0}: {1}  [{2}]' -f ($(if ($pass) { 'PASS' } else { 'FAIL' }), $name, (($r | Out-String).Trim() -split "`n")[0])
}
$cred = Get-Credential -UserName "$env:COMPUTERNAME\pa-jea-test" -Message 'Password for the local test user pa-jea-test'
$s = New-PSSession -ComputerName localhost -ConfigurationName $cfg -Credential $cred -Authentication Negotiate
Check 'authorized: list granted root'            { Invoke-Command $s { Get-PowerAgentDirectory -Path $using:root } } $true
Check 'rejected: path outside the root'          { Invoke-Command $s { Get-PowerAgentDirectory -Path 'C:\Windows' } } $false
Check 'rejected: ..\ traversal out of the root'  { Invoke-Command $s { Get-PowerAgentDirectory -Path "$using:root\..\.." } } $false
Check 'rejected: arbitrary PowerShell'           { Invoke-Command $s { Get-Process } } $false
Check 'rejected: script block / expression'      { Invoke-Command $s { 1 + 1 } } $false
Check 'rejected: starting a process'             { Invoke-Command $s { & cmd.exe /c whoami } } $false
Check 'rejected: Get-ChildItem directly'         { Invoke-Command $s { Get-ChildItem C:\ } } $false
Remove-PSSession $s
if ($fail) { Write-Host "FAIL: $fail check(s)" } else { Write-Host 'PASS: JEA endpoint allows exactly the one typed operation.' }
if ($LogPath) { Stop-Transcript | Out-Null }
exit ([int][bool]$fail)
