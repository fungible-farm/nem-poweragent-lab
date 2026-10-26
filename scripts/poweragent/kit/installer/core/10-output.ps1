# core/10-output.ps1 -- console output, exit handling, steps (honouring -WhatIf) and the JSON report.
# Contract: Say, Die, Step, Show-Checks, Save-Report, Finish. Nothing here knows about specific checks or components.

$script:Steps = [System.Collections.Generic.List[object]]::new()

function Say([string]$m) { if (-not $Quiet) { Write-Host $m } }
# `exit` inside a dot-sourced module ends only that module, so Die also records its code; the entry script checks
# $script:DieCode after loading each module and exits the process (Install-PowerAgent.ps1).
$script:DieCode = $null
function Die([int]$code, [string]$m) { [Console]::Error.WriteLine("error: $m"); $script:DieCode = $code; exit $code }

# One mutation. Under -WhatIf it is listed and skipped; otherwise it runs and is recorded in the report.
function Step([string]$what, [scriptblock]$body) {
    if ($PSCmdlet.ShouldProcess($what, $Action)) {
        try { & $body; $script:Steps.Add([pscustomobject]@{ step = $what; result = 'done' }); Say "  done: $what" }
        catch { $script:Steps.Add([pscustomobject]@{ step = $what; result = "FAILED: $($_.Exception.Message)" }); throw }
    } else { $script:Steps.Add([pscustomobject]@{ step = $what; result = 'skipped (WhatIf)' }); Say "  would: $what" }
}

function Show-Checks {
    if ($Quiet) { return }
    foreach ($c in $script:Checks) {
        $col = switch ($c.status) { 'PASS' { 'Green' } 'FAIL' { 'Red' } 'WARN' { 'Yellow' } default { 'DarkGray' } }
        Write-Host ('{0,-4} ' -f $c.status) -ForegroundColor $col -NoNewline
        Write-Host ('{0,-8} {1}' -f $c.id, $c.title)
        if ($c.detail) { Write-Host "          $($c.detail)" -ForegroundColor DarkGray }
        if ($c.status -in 'FAIL', 'WARN' -and $c.remedy) { Write-Host "          fix: $($c.remedy)" -ForegroundColor $col }
    }
}

function Save-Report([int]$code, [string]$outcome) {
    if (-not $ReportPath) { return }
    $count = { param($s) @($script:Checks | Where-Object status -eq $s).Count }
    $o = [ordered]@{
        schema = 'poweragent.install-report/v1'; action = $Action; timestampUtc = (Get-Date).ToUniversalTime().ToString('o')
        host = [ordered]@{ computer = $env:COMPUTERNAME; user = "$env:USERDOMAIN\$env:USERNAME"; elevated = $isAdmin; os = [Runtime.InteropServices.RuntimeInformation]::OSDescription; powershell = $PSVersionTable.PSVersion.ToString() }
        config = $cfg; installDir = $installDir; dataDir = $dataDir
        result = [ordered]@{ outcome = $outcome; exitCode = $code }
        counts = [ordered]@{ pass = & $count 'PASS'; warn = & $count 'WARN'; fail = & $count 'FAIL'; info = & $count 'INFO'; skip = & $count 'SKIP' }
        checks = @($script:Checks); components = @($script:ComponentReport); loadTimeDlls = $script:ImportsReport; steps = $script:Steps
    }
    Write-Json $ReportPath $o
    Say "report: $ReportPath"
}

function Finish([int]$code, [string]$outcome) { Save-Report $code $outcome; Say "RESULT: $outcome (exit $code)"; exit $code }
