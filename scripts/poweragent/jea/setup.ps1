#Requires -RunAsAdministrator
# Gate 3 (issue #54): register ONE constrained JEA endpoint, "PowerAgent.Gate3", for the current user.
# Local-only: the WinRM HTTP listener is bound to 127.0.0.1 and NO firewall rule is created, so nothing
# off this machine can reach it. Undo everything with teardown.ps1.
[CmdletBinding()]
param([string[]]$User = @('AzureAD\BrianHorakh'))
$ErrorActionPreference = 'Stop'

$endpoint = 'PowerAgent.Gate3'
$dataRoot = 'C:\ProgramData\PowerAgent\jea-data'
$module   = 'C:\Program Files\WindowsPowerShell\Modules\PowerAgentJea'
$work     = Join-Path $env:ProgramData 'PowerAgent\jea-build'

# 1. Sample data the endpoint is allowed to list (the only granted root).
New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null
'sample' | Set-Content -Path (Join-Path $dataRoot 'a.txt')

# 2. Role capability module: one function, no cmdlets, no providers, no external commands.
New-Item -ItemType Directory -Force -Path "$module\RoleCapabilities" | Out-Null
@"
@{ RootModule = 'PowerAgentJea.psm1'; ModuleVersion = '0.1.0'; GUID = '5b0f3b0e-6a64-4f0e-9a3e-2d3a8c1e7a11'
   FunctionsToExport = @('Get-PowerAgentDirectory'); CmdletsToExport = @(); AliasesToExport = @(); VariablesToExport = @() }
"@ | Set-Content -Encoding UTF8 "$module\PowerAgentJea.psd1"
@"
function Get-PowerAgentDirectory {
    [CmdletBinding()] param([Parameter(Mandatory)][ValidateLength(1,260)][string]`$Path)
    `$root = [IO.Path]::GetFullPath('$dataRoot').TrimEnd('\')
    `$full = [IO.Path]::GetFullPath(`$Path)            # collapses '..' before the prefix check
    if (`$full -ne `$root -and -not `$full.StartsWith(`$root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "path is outside the granted root"
    }
    Get-ChildItem -LiteralPath `$full -Name
}
"@ | Set-Content -Encoding UTF8 "$module\PowerAgentJea.psm1"
@"
@{ GUID = '0c1f1d7e-3f5a-4a53-8f55-6a7d4b0c9e22'
   Description = 'PowerAgent Gate 3: list a directory under the granted root. Nothing else.'
   VisibleFunctions = @('Get-PowerAgentDirectory') }
"@ | Set-Content -Encoding UTF8 "$module\RoleCapabilities\PowerAgentGate3.psrc"

# 3. Session configuration: restricted language, runs as the CALLER (no virtual/admin account).
New-Item -ItemType Directory -Force -Path $work | Out-Null
$pssc = Join-Path $work "$endpoint.pssc"
$roles = @{}
foreach ($u in $User) { $roles[$u] = @{ RoleCapabilities = 'PowerAgentGate3' } }
New-PSSessionConfigurationFile -Path $pssc -SessionType RestrictedRemoteServer `
    -LanguageMode NoLanguage -ExecutionPolicy Restricted -TranscriptDirectory $work `
    -RoleDefinitions $roles
Test-PSSessionConfigurationFile -Path $pssc -Verbose | Out-Null

# 4. WinRM: start the service and bind a loopback-only listener. No firewall rule, no Enable-PSRemoting.
Set-Service WinRM -StartupType Manual
Start-Service WinRM
if (-not (Get-WSManInstance -ResourceURI winrm/config/Listener -Enumerate -ErrorAction SilentlyContinue |
          Where-Object { $_.Address -eq 'IP:127.0.0.1' })) {
    New-WSManInstance -ResourceURI winrm/config/Listener `
        -SelectorSet @{ Address = 'IP:127.0.0.1'; Transport = 'HTTP' } | Out-Null
}

# 5. Register the endpoint (access is limited to the principals in RoleDefinitions).
Unregister-PSSessionConfiguration -Name $endpoint -Force -ErrorAction SilentlyContinue
Register-PSSessionConfiguration -Name $endpoint -Path $pssc -Force | Out-Null
Get-PSSessionConfiguration -Name $endpoint | Format-List Name, Permission, SessionType
Write-Host "OK: endpoint $endpoint registered for $($User -join ', ') on 127.0.0.1 only."
