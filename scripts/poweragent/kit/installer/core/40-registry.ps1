# core/40-registry.ps1 -- the check registry. This is the extension point for preflight checks.
#
# A check is registered once, in a file under installer\checks\ (or extensions\), like this:
#
#   Register-Check -Id 'XYZ-01' -Category 'My category' -Required $true -Title 'What is verified' -Run {
#       New-Result 'PASS' 'detail shown to the operator' 'what to do if it fails'
#   }
#
# * The catalogue printed by `-Action ListChecks` is DERIVED from the registrations: there is no second list to keep
#   in sync. Checks run in registration order (files load sorted by name).
# * A check returns New-Result with Status PASS | WARN | FAIL | SKIP | INFO. A check that throws becomes a FAIL
#   (fail closed), never a crash and never a silent pass.
# * Checks are read-only. Use Get-Ctx to compute something expensive once and share it between checks.

$script:CheckDefs = [System.Collections.Generic.List[object]]::new()
$script:Checks = [System.Collections.Generic.List[object]]::new()   # results of the last run, in order
$script:Ctx = @{}
$script:ImportsReport = @()
$script:ComponentReport = @()

function Register-Check {
    param(
        [Parameter(Mandatory)][ValidatePattern('^[A-Z]+-\d{2}$')][string]$Id,
        [Parameter(Mandatory)][string]$Category,
        [Parameter(Mandatory)][bool]$Required,
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][scriptblock]$Run
    )
    if ($script:CheckDefs | Where-Object { $_.Id -eq $Id }) { throw "duplicate check id $Id" }
    $script:CheckDefs.Add([pscustomobject]@{ Id = $Id; Category = $Category; Required = $Required; Title = $Title; Run = $Run })
}

function New-Result([ValidateSet('PASS', 'WARN', 'FAIL', 'SKIP', 'INFO')][string]$Status, [string]$Detail = '', [string]$Remedy = '') {
    [pscustomobject]@{ Status = $Status; Detail = $Detail; Remedy = $Remedy }
}

# Compute once per preflight and share.
function Get-Ctx([string]$Key, [scriptblock]$Factory) {
    if (-not $script:Ctx.ContainsKey($Key)) { $script:Ctx[$Key] = & $Factory }
    $script:Ctx[$Key]
}

function Show-Catalogue {
    $script:CheckDefs | ForEach-Object { [pscustomobject]@{ Id = $_.Id; Category = $_.Category; Required = $_.Required; Check = $_.Title } } | Format-Table -AutoSize
}

function Invoke-Checks {
    $WhatIfPreference = $false   # -WhatIf governs mutations (Step); read-only probes must clean up after themselves
    $script:Ctx = @{}; $script:ImportsReport = @(); $script:Checks.Clear()
    foreach ($d in $script:CheckDefs) {
        try { $r = @(& $d.Run) | Select-Object -Last 1 }
        catch { $r = New-Result 'FAIL' "the check itself failed: $($_.Exception.Message)" 'This is a defect in the check, not in your machine; report it.' }
        if (-not $r -or $r.Status -notin 'PASS', 'WARN', 'FAIL', 'SKIP', 'INFO') { $r = New-Result 'FAIL' 'the check returned no valid result' 'This is a defect in the check; report it.' }
        $script:Checks.Add([pscustomobject]@{ id = $d.Id; category = $d.Category; required = $d.Required; title = $d.Title; status = $r.Status; detail = $r.Detail; remedy = $r.Remedy })
    }
}

# 0 = proceed; 10 = a required check failed; 11 = warnings and failOnWarning.
function Preflight-Verdict {
    if (@($script:Checks | Where-Object { $_.status -eq 'FAIL' })) { return 10 }
    if (@($script:Checks | Where-Object { $_.status -eq 'WARN' }) -and $cfg.failOnWarning) { return 11 }
    0
}
