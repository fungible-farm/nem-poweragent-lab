# actions/10-preflight.ps1 -- run every registered check; change nothing.

function Invoke-PreflightAction {
    Say '== Preflight'
    Invoke-Checks
    # The report lists the components this run would install (descriptors, in dependency order).
    $script:ComponentReport = @((Get-ComponentPlan).Components | ForEach-Object { [ordered]@{ id = $_.id; type = $_.source.type; required = $_.required } })
    Show-Checks
    $v = Preflight-Verdict
    $s = if ($v -eq 0) { 'preflight passed' } elseif ($v -eq 10) { 'preflight FAILED (required checks)' } else { 'preflight warnings (failOnWarning is set)' }
    Finish $v $s
}
