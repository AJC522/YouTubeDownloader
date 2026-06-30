<#
    Video Download Manager - setup / startup script (Windows / PowerShell)
    ----------------------------------------------------------------------
    Installs and updates everything the app needs in one step:
      1. A Python virtual environment (.venv)
      2. The Python dependencies from requirements.txt (upgraded to the latest
         allowed versions)
      3. ffmpeg (external system dependency) via winget or Chocolatey,
         installing it if missing or updating it if already present

    Re-running this script is safe: it brings an existing setup up to date.

    Usage (from a PowerShell prompt in the project folder):
      ./setup.ps1            # set up / update, then exit
      ./setup.ps1 -Run       # set up / update, then launch the app

    If you get an execution-policy error, run PowerShell once as:
      powershell -ExecutionPolicy Bypass -File .\setup.ps1
#>

[CmdletBinding()]
param(
    [switch]$Run
)

$ErrorActionPreference = 'Stop'

function Write-Info  { param($m) Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Warn  { param($m) Write-Host "[!] $m" -ForegroundColor Yellow }
function Write-Err   { param($m) Write-Host "[x] $m" -ForegroundColor Red }
function Test-Command { param($n) [bool](Get-Command $n -ErrorAction SilentlyContinue) }

# Work from the directory containing this script.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$VenvDir = '.venv'

# ---------------------------------------------------------------------------
# 1. Locate a usable Python interpreter (3.9+)
# ---------------------------------------------------------------------------
$Python = $null
foreach ($candidate in @('python', 'python3', 'py')) {
    if (Test-Command $candidate) {
        try {
            & $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { $Python = $candidate; break }
        } catch { }
    }
}

if (-not $Python) {
    Write-Err 'Python 3.9+ is required but was not found on your PATH.'
    Write-Err 'Install Python from https://www.python.org/downloads/ and re-run this script.'
    exit 1
}
Write-Info "Using Python: $(& $Python --version 2>&1)"

# ---------------------------------------------------------------------------
# 2. Create / reuse the virtual environment and upgrade Python dependencies
# ---------------------------------------------------------------------------
if (-not (Test-Path $VenvDir)) {
    Write-Info "Creating virtual environment in $VenvDir"
    & $Python -m venv $VenvDir
} else {
    Write-Info "Reusing existing virtual environment in $VenvDir"
}

# Use the venv's interpreter directly (avoids needing to 'activate').
$VenvPy = Join-Path $VenvDir 'Scripts\python.exe'

Write-Info 'Upgrading pip, setuptools and wheel'
& $VenvPy -m pip install --quiet --upgrade pip setuptools wheel

Write-Info 'Installing / upgrading Python dependencies from requirements.txt'
# --upgrade pulls the newest versions permitted by requirements.txt so the
# install stays current on every run.
& $VenvPy -m pip install --upgrade -r requirements.txt

# ---------------------------------------------------------------------------
# 3. Install / update ffmpeg via winget or Chocolatey
# ---------------------------------------------------------------------------
function Install-Or-Update-FFmpeg {
    if (Test-Command 'winget') {
        $installed = (winget list --id Gyan.FFmpeg -e 2>$null | Select-String 'Gyan.FFmpeg')
        if ($installed) {
            Write-Info 'Updating ffmpeg via winget'
            winget upgrade --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
        } else {
            Write-Info 'Installing ffmpeg via winget'
            winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
        }
    } elseif (Test-Command 'choco') {
        Write-Info 'Installing / updating ffmpeg via Chocolatey'
        choco upgrade ffmpeg -y
    } else {
        Write-Warn 'Neither winget nor Chocolatey was found.'
        Write-Warn 'Install one of them, or download ffmpeg from https://www.gyan.dev/ffmpeg/builds/'
        Write-Warn 'and add its bin folder to your PATH.'
    }
}

Install-Or-Update-FFmpeg

# winget/choco may update PATH for new sessions only; refresh it for this one.
$env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
            [System.Environment]::GetEnvironmentVariable('Path', 'User')

# Verify ffmpeg ended up on the PATH (mirrors the app's shutil.which check).
if (Test-Command 'ffmpeg') {
    $ver = (ffmpeg -version 2>$null | Select-Object -First 1)
    Write-Info "ffmpeg is available: $ver"
} else {
    Write-Warn 'ffmpeg is installed but not yet visible on this PATH.'
    Write-Warn 'Close and reopen your terminal, then run "ffmpeg -version" to confirm.'
}

Write-Info 'Setup complete.'

# ---------------------------------------------------------------------------
# 4. Optionally launch the application
# ---------------------------------------------------------------------------
if ($Run) {
    Write-Info 'Launching Video Download Manager'
    & $VenvPy -m app.main
} else {
    Write-Host ''
    Write-Info 'To run the app:'
    Write-Host "    $VenvPy -m app.main"
    Write-Info 'Or re-run this script with -Run to launch it now:'
    Write-Host '    ./setup.ps1 -Run'
}
