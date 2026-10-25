#Requires -RunAsAdministrator
# Undo setup.ps1 completely: endpoint, module, sample data, loopback listener, and stop WinRM.
$ErrorActionPreference = 'Continue'
Unregister-PSSessionConfiguration -Name 'PowerAgent.Gate3' -Force -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force 'C:\Program Files\WindowsPowerShell\Modules\PowerAgentJea' -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$env:ProgramData\PowerAgent" -ErrorAction SilentlyContinue
Remove-WSManInstance -ResourceURI winrm/config/Listener -SelectorSet @{ Address = 'IP:127.0.0.1'; Transport = 'HTTP' } -ErrorAction SilentlyContinue
Remove-LocalUser -Name 'pa-jea-test' -ErrorAction SilentlyContinue   # also drops its group memberships
Stop-Service WinRM -Force -ErrorAction SilentlyContinue
Write-Host 'OK: PowerAgent JEA endpoint removed, WinRM stopped (startup type left at Manual).'
