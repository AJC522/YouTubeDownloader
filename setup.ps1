<#
    Video Download Manager - one-step setup & launch (Windows / PowerShell)
    ----------------------------------------------------------------------
    Easiest way to run: double-click setup.bat (it runs this script).

    Or from a PowerShell prompt in the project folder:
      ./setup.ps1              # set up / update, then launch the app
      ./setup.ps1 -SetupOnly   # set up / update, but don't launch

    The script creates a private Python environment (.venv) and installs or
    updates all dependencies - including a bundled ffmpeg, so there is nothing
    else to install.

    Re-running it is always safe: it updates an existing install (useful when
    downloads stop working because a site changed and yt-dlp needs updating).

    If you get an execution-policy error, run PowerShell once as:
      powershell -ExecutionPolicy Bypass -File .\setup.ps1
#>

[CmdletBinding()]
param(
    [switch]$Run,       # Kept for backwards compatibility; launching is now the default.
    [switch]$SetupOnly
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
    Write-Err 'Install Python from https://www.python.org/downloads/ (tick "Add Python to PATH"), then re-run this script.'
    exit 1
}
Write-Info "Using Python: $(& $Python --version 2>&1)"

# ---------------------------------------------------------------------------
# 2. Create / reuse the virtual environment and install dependencies
# ---------------------------------------------------------------------------
if (-not (Test-Path $VenvDir)) {
    Write-Info "Creating virtual environment in $VenvDir"
    & $Python -m venv $VenvDir
} else {
    Write-Info "Reusing existing virtual environment in $VenvDir"
}

# Use the venv's interpreter directly (avoids needing to 'activate').
$VenvPy = Join-Path $VenvDir 'Scripts\python.exe'

Write-Info 'Upgrading pip'
& $VenvPy -m pip install --quiet --upgrade pip

Write-Info 'Installing / updating dependencies (GUI, yt-dlp and bundled ffmpeg)'
# --upgrade pulls the newest versions permitted by requirements.txt so the
# install stays current on every run.
& $VenvPy -m pip install --upgrade -r requirements.txt

# ---------------------------------------------------------------------------
# 3. Verify everything the app needs is in place
# ---------------------------------------------------------------------------
Write-Info 'Checking the installation'
$check = @'
import sys
sys.path.insert(0, ".")
from app.downloader import ffmpeg_source, ytdlp_version

version = ytdlp_version()
source, path = ffmpeg_source()
print(f"    yt-dlp {version}")
print(f"    ffmpeg: {source}" + (f" ({path})" if path else ""))
sys.exit(0 if version and source != "missing" else 1)
'@
& $VenvPy -c $check
if ($LASTEXITCODE -eq 0) {
    Write-Info 'Everything is ready.'
} else {
    Write-Warn 'Something is missing - see the lines above. Try re-running this script.'
}

# ---------------------------------------------------------------------------
# 4. Launch the application
# ---------------------------------------------------------------------------
if (-not $SetupOnly) {
    Write-Info 'Launching Video Download Manager'
    & $VenvPy -m app.main
} else {
    Write-Host ''
    Write-Info 'Setup complete. To run the app later:'
    Write-Host '    ./setup.ps1     (or double-click setup.bat)'
}
