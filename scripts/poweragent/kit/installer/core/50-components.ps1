# core/50-components.ps1 -- what gets installed is described by components\*.json, one descriptor per component.
#
# Descriptor (schema poweragent.component/v1; unknown properties are rejected):
#   {
#     "schema": "poweragent.component/v1",
#     "id": "runtime",                      lower-case id: [a-z][a-z0-9-]*
#     "description": "...",
#     "required": true,                     a required component that cannot be installed fails the preflight
#     "dependsOn": [],                      other component ids; installed after them; cycles are rejected
#     "source": { "type": "kit", "paths": ["bin"], "optionalPaths": [] },
#     "install": { "to": "." }              relative to the install directory
#   }
#   or, for a container image (the path to signed OCI artifacts):
#     "source": { "type": "oci", "reference": "registry.example/name@sha256:<64 hex>", "pull": "never" },
#     "verify": { "signature": "required", "mechanism": "podman-policy" }
#
# Source providers
#   kit : files copied from the extracted kit. Their integrity is the kit's SHA256SUMS (checked first).
#   oci : an image referenced ONLY by digest. Never a tag. Checked for presence in the local Podman store.
#         Signature verification is a gate that FAILS CLOSED: `verify.signature: "required"` is refused until a
#         verification mechanism is implemented (none is in this release), and `"unverified-allowed"` is an explicit,
#         warned opt-out. The installer never pulls (`pull` must be "never") in this release.
#
# Extension: add a descriptor under components\ (or extensions\) and list it in SHA256SUMS. Nothing else to edit.

$script:ComponentSchema = 'poweragent.component/v1'
$script:OciMechanisms = 'podman-policy', 'cosign', 'notation'   # recognised names; none is implemented yet

function Test-ComponentDescriptor($c, [string]$file) {
    $e = @()
    $allowed = 'schema', 'id', 'description', 'required', 'dependsOn', 'source', 'install', 'verify'
    foreach ($p in $c.PSObject.Properties.Name) { if ($p -notin $allowed) { $e += "$file`: unknown property '$p'" } }
    if ($c.schema -ne $script:ComponentSchema) { $e += "$file`: schema must be $script:ComponentSchema" }
    if ($c.id -isnot [string] -or $c.id -notmatch '^[a-z][a-z0-9-]{0,40}$') { $e += "$file`: id must match [a-z][a-z0-9-]{0,40}" }
    if ($c.required -isnot [bool]) { $e += "$file`: required must be true or false" }
    if ($null -eq $c.source -or $c.source.type -notin 'kit', 'oci') { $e += "$file`: source.type must be 'kit' or 'oci'"; return $e }
    foreach ($d in @($c.dependsOn)) { if ($d -isnot [string] -or $d -notmatch '^[a-z][a-z0-9-]{0,40}$') { $e += "$file`: bad dependsOn entry '$d'" } }
    if ($c.source.type -eq 'kit') {
        foreach ($p in $c.source.PSObject.Properties.Name) { if ($p -notin 'type', 'paths', 'optionalPaths') { $e += "$file`: unknown source property '$p'" } }
        $paths = @($c.source.paths) + @($c.source.optionalPaths) | Where-Object { $_ }
        if (-not @($c.source.paths).Count) { $e += "$file`: kit source needs at least one path" }
        foreach ($p in $paths) { if ($p -isnot [string] -or [IO.Path]::IsPathRooted($p) -or $p -match '(^|[\\/])\.\.([\\/]|$)') { $e += "$file`: path '$p' must be relative and stay inside the kit" } }
        if ($null -eq $c.install -or $c.install.to -isnot [string] -or [IO.Path]::IsPathRooted($c.install.to) -or $c.install.to -match '(^|[\\/])\.\.([\\/]|$)') { $e += "$file`: install.to must be a relative path inside the install directory" }
        if ($null -ne $c.verify) { $e += "$file`: verify applies to oci sources only" }
    } else {
        foreach ($p in $c.source.PSObject.Properties.Name) { if ($p -notin 'type', 'reference', 'pull') { $e += "$file`: unknown source property '$p'" } }
        if ($c.source.reference -isnot [string] -or $c.source.reference -notmatch '^[^\s@]+@sha256:[0-9a-f]{64}$') { $e += "$file`: oci reference must be pinned by digest (name@sha256:<64 hex>); tags are refused" }
        if ($c.source.pull -and $c.source.pull -ne 'never') { $e += "$file`: pull must be 'never' in this release (the installer does not pull)" }
        if ($null -eq $c.verify -or $c.verify.signature -notin 'required', 'unverified-allowed') { $e += "$file`: oci components need verify.signature = 'required' or 'unverified-allowed'" }
        elseif ($c.verify.signature -eq 'required' -and $c.verify.mechanism -notin $script:OciMechanisms) { $e += "$file`: verify.mechanism must be one of $($script:OciMechanisms -join ', ')" }
        if ($null -ne $c.install) { $e += "$file`: install applies to kit sources only" }
    }
    $e
}

# Load every descriptor, validate, resolve dependencies and order them. Returns Components, Errors.
function Get-ComponentPlan {
    Get-Ctx 'components' {
        $errors = @(); $list = @()
        $dir = Join-Path $kit 'components'
        foreach ($f in @(Get-ChildItem $dir -Filter *.json -File -ErrorAction SilentlyContinue | Sort-Object Name)) {
            try { $c = Read-Json $f.FullName } catch { $errors += "$($f.Name): not valid JSON"; continue }
            $errors += @(Test-ComponentDescriptor $c $f.Name)
            $list += $c
        }
        $ids = @($list | ForEach-Object { $_.id })
        $dups = @($ids | Group-Object | Where-Object Count -gt 1 | ForEach-Object Name)
        foreach ($d in $dups) { $errors += "duplicate component id '$d'" }
        foreach ($c in $list) { foreach ($d in @($c.dependsOn)) { if ($d -and $d -notin $ids) { $errors += "component '$($c.id)' depends on unknown component '$d'" } } }
        # topological order, rejecting cycles
        $ordered = @(); $state = @{}
        $visit = $null
        $visit = {
            param($id)
            if ($state[$id] -eq 2) { return }
            if ($state[$id] -eq 1) { $script:cycle = $id; return }
            $state[$id] = 1
            $c = $list | Where-Object { $_.id -eq $id } | Select-Object -First 1
            if ($c) { foreach ($d in @($c.dependsOn)) { if ($d -in $ids) { & $visit $d } } }
            $state[$id] = 2
            if ($c) { $script:orderedTmp += $c }
        }
        $script:cycle = $null; $script:orderedTmp = @()
        foreach ($id in ($ids | Select-Object -Unique)) { & $visit $id }
        if ($script:cycle) { $errors += "dependency cycle involving '$($script:cycle)'" }
        $ordered = @($script:orderedTmp)
        [pscustomobject]@{ Components = $ordered; Errors = $errors }
    }
}

# The components that will be installed: descriptors minus the operator's exclusions. A required component cannot be excluded.
function Get-ActiveComponents {
    $plan = Get-ComponentPlan
    foreach ($x in $cfg.components.exclude) {
        $c = $plan.Components | Where-Object { $_.id -eq $x }
        if (-not $c) { Die 64 "components.exclude names unknown component '$x'" }
        if ($c.required) { Die 64 "component '$x' is required and cannot be excluded" }
    }
    @($plan.Components | Where-Object { $_.id -notin $cfg.components.exclude })
}

# Is this OCI component installable here? Pinned, present, and passing the signature gate.
function Test-OciComponent($c) {
    $ref = $c.source.reference
    $pinned = $ref -match '^[^\s@]+@sha256:[0-9a-f]{64}$'
    $present = $false
    $pcmd = Get-Command $cfg.podman.bin -ErrorAction SilentlyContinue
    if ($pinned -and $pcmd) { $present = (Run-Exe $pcmd.Source @('image', 'exists', $ref)).Code -eq 0 }
    $sig = $c.verify.signature
    $verified = $false
    $note = ''
    if ($sig -eq 'required') {
        # Fail closed: no verification mechanism is implemented in this release, so a signature requirement cannot be met.
        $note = "signature verification via '$($c.verify.mechanism)' is not implemented in this release, so a required signature cannot be established"
    } else {
        $note = 'UNVERIFIED: signature checking is explicitly waived for this component'
    }
    $ok = $pinned -and $present -and ($sig -eq 'unverified-allowed')
    [pscustomobject]@{ Pinned = $pinned; Present = $present; SignatureRequired = ($sig -eq 'required'); Verified = $verified; Installable = $ok; Note = $note; Reference = $ref }
}
