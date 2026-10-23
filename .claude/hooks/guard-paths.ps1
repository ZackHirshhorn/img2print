# PreToolUse hook: blocks tool calls that reference paths outside the allowed roots.
# Allowed: the workspace, the session scratchpad root, and the project memory folder.
# Best-effort for shell commands (it scans the command text); exact for file tools.

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8

$AllowedRoots = @(
    'C:\Users\Hezi\img2print',
    'C:\Users\Hezi\AppData\Local\Temp\claude\c--Users-Hezi-img2print',
    'C:\Users\Hezi\.claude\projects\c--Users-Hezi-img2print\memory'
)

function Deny([string]$reason) {
    $out = @{
        hookSpecificOutput = @{
            hookEventName            = 'PreToolUse'
            permissionDecision       = 'deny'
            permissionDecisionReason = "Blocked by workspace guard: $reason. Rule #1 in CLAUDE.md: never leave the workspace - ask the user to fetch it instead."
        }
    }
    $out | ConvertTo-Json -Compress -Depth 5
    exit 0
}

function Test-Allowed([string]$fullPath) {
    $p = $fullPath.TrimEnd('\')
    foreach ($root in $AllowedRoots) {
        if ($p -ieq $root -or $p.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    return $false
}

function Resolve-Candidate([string]$path, [string]$baseDir) {
    $p = $path.Trim().Trim('"', "'")
    # Git Bash drive mounts: /c/Users/... -> C:\Users\...
    if ($p -match '^/([A-Za-z])(/.*)?$') { $p = $Matches[1] + ':' + $(if ($Matches[2]) { $Matches[2] } else { '\' }) }
    $p = $p -replace '/', '\'
    if ($p -match '^[A-Za-z]:$') { $p += '\' }
    if (-not [System.IO.Path]::IsPathRooted($p)) { $p = Join-Path $baseDir $p }
    return [System.IO.Path]::GetFullPath($p)
}

function Assert-Path([string]$path, [string]$baseDir) {
    if ([string]::IsNullOrWhiteSpace($path)) { return }
    if ($path -match '^\\\\|^//') { Deny "network/UNC path '$path'" }
    $full = Resolve-Candidate $path $baseDir
    if (-not (Test-Allowed $full)) { Deny "path '$path' resolves outside the workspace ($full)" }
}

$payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
$tool = $payload.tool_name
$inputObj = $payload.tool_input
$cwd = if ($payload.cwd) { $payload.cwd } else { $AllowedRoots[0] }

if ($tool -in @('Bash', 'PowerShell')) {
    $cmd = [string]$inputObj.command
    if (-not (Test-Allowed (Resolve-Candidate $cwd $AllowedRoots[0]))) { Deny "shell working directory '$cwd' is outside the workspace" }

    # Expand home/temp/appdata references so they can be checked as real paths.
    $vars = @{
        'USERPROFILE' = $env:USERPROFILE; 'HOME' = $env:USERPROFILE; 'HOMEPATH' = $env:USERPROFILE
        'TEMP' = $env:TEMP; 'TMP' = $env:TEMP; 'TMPDIR' = $env:TEMP
        'APPDATA' = $env:APPDATA; 'LOCALAPPDATA' = $env:LOCALAPPDATA
        'PROGRAMFILES' = $env:ProgramFiles; 'PROGRAMDATA' = $env:ProgramData
        'SYSTEMROOT' = $env:SystemRoot; 'WINDIR' = $env:windir; 'PUBLIC' = $env:PUBLIC
    }
    foreach ($name in $vars.Keys) {
        $val = $vars[$name]
        if (-not $val) { continue }
        $cmd = [regex]::Replace($cmd, "(?i)\`$env:$name\b|\`$\{$name\}|\`$$name\b|%$name%", [System.Text.RegularExpressions.MatchEvaluator] { param($m) $val })
    }
    $cmd = [regex]::Replace($cmd, '(?<![\w~])~(?=[\\/\s''"]|$)', [System.Text.RegularExpressions.MatchEvaluator] { param($m) $env:USERPROFILE })

    if ($cmd -match '(?i)\b(HKLM|HKCU|HKCR|HKU|HKCC):|Registry::') { Deny 'registry access' }
    if ($cmd -match '(?<![\w\\])\\\\[A-Za-z0-9]') { Deny 'network/UNC path' }
    if ($cmd -match '(?<![\w.~/-])/(tmp|etc|usr|home|mnt|proc|root|var|opt|bin|sbin|lib)(?=/|\s|$|[''"])') { Deny "system path '/$($Matches[1])'" }

    $stop = '[^\s''"`;|&<>(),=]'
    # Absolute Windows paths (C:\..., C:/...) and Git Bash mounts (/c/...).
    $absolute = [regex]::Matches($cmd, "(?<![\w])[A-Za-z]:(?:[\\/]$stop*)?")
    $mounts = [regex]::Matches($cmd, "(?<![\w.~/-])/[A-Za-z](?=/|\s|$|['""])$stop*")
    foreach ($m in @($absolute) + @($mounts)) { Assert-Path $m.Value $cwd }

    # Relative paths that climb with '..'.
    foreach ($token in [regex]::Split($cmd, '[\s''"`;|&<>(),=]+')) {
        if ($token -match '(^|[\\/])\.\.([\\/]|$)') { Assert-Path $token $cwd }
    }
}
else {
    foreach ($field in @('file_path', 'notebook_path', 'path')) {
        $val = $inputObj.$field
        if ($val) { Assert-Path ([string]$val) $cwd }
    }
    if ($tool -eq 'Glob' -and $inputObj.pattern) {
        $pattern = [string]$inputObj.pattern
        $prefix = ($pattern -split '[*?\[{]', 2)[0]
        if ($prefix -and ([System.IO.Path]::IsPathRooted(($prefix -replace '/', '\')) -or $prefix -match '(^|[\\/])\.\.([\\/]|$)')) {
            Assert-Path $prefix $cwd
        }
    }
}

exit 0
