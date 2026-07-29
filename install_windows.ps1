# One-click installer for Windows (run install_windows.bat, which launches this).
#
# What it does:
#   1. Finds Python 3.10+ (installs Python 3.12 via winget if missing)
#   2. Creates the virtual environment and installs server dependencies
#   3. Optionally installs the ML (auto-annotation) dependencies
#   4. Generates backend\.env with a fresh secret key (SQLite by default)
#   5. Builds the frontend if needed (installs Node.js via winget if missing)
#   6. Opens TCP port 8000 in Windows Firewall (when run as Administrator)
#   7. Optionally registers a Scheduled Task so the server starts with Windows
#
# Parameters (all optional):
#   -WithML             install ML dependencies without asking
#   -NoML               skip ML dependencies without asking
#   -AutoStart          register the start-with-Windows scheduled task
#   -Port 8000          port for the firewall rule / shortcuts
#   -Offline            air-gapped install: never use winget or the internet
#   -NodeInstaller PATH local Node.js installer (.msi/.exe) to run if npm is missing
#   -WheelDir PATH      folder of pre-downloaded pip wheels (used with
#                       --no-index --find-links)
#
# OFFLINE / AIR-GAPPED INSTALL — prepare these on an online machine, copy them
# to the target, then run:   install_windows.bat -Offline [-WithML]
#   * Python 3.10+ already installed on the target (winget is NOT used offline;
#     install Python manually first if needed).
#   * Python packages: either already installed into backend\.venv, OR a folder
#     of wheels downloaded on the online machine with:
#         pip download -r backend\requirements.txt -r backend\requirements-ml.txt -d wheels
#     then pass  -WheelDir wheels
#   * Node.js: pass the downloaded installer with  -NodeInstaller node-vXX.msi
#     (not needed if npm is already on PATH, or if the frontend is pre-built).
#   * Frontend (surest offline path): pre-build it on the online machine
#         cd frontend; npm install; npm run build
#     and copy the generated backend\static folder to the target — then no
#     Node/npm is needed at all. Alternatively copy frontend\node_modules over
#     and this installer runs "npm run build" without touching the network.
param(
    [switch]$WithML,
    [switch]$NoML,
    [switch]$AutoStart,
    [switch]$Offline,
    [string]$NodeInstaller = "",
    [string]$WheelDir = "",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Ok($msg) { Write-Host $msg -ForegroundColor Green }
function Warn($msg) { Write-Host $msg -ForegroundColor Yellow }

# Run a command given as a string like "py -3.12" or "python" with extra args.
function Invoke-Python([string]$command, [string[]]$extraArgs) {
    $parts = $command.Split(" ")
    $exe = $parts[0]
    $baseArgs = @()
    if ($parts.Length -gt 1) { $baseArgs = $parts[1..($parts.Length - 1)] }
    & $exe @baseArgs @extraArgs
}

Write-Host "GraphMind (NER & RE annotation for knowledge graphs) - Windows installer" -ForegroundColor White
Write-Host "Install location: $Root"
if ($Offline) { Warn "Offline mode: winget and the internet will not be used." }

# pip network flags: in -Offline mode pip never reaches PyPI; if a local wheel
# folder is provided it installs from there, otherwise from what is already
# installed in the venv.
$pipNet = @()
if ($Offline) {
    $pipNet = @("--no-index")
    if ($WheelDir) {
        if (-not (Test-Path $WheelDir)) { Write-Error "-WheelDir '$WheelDir' does not exist." }
        $pipNet += @("--find-links", (Resolve-Path $WheelDir).Path)
    }
}

# ---------- 1. Python ----------
Step "Locating Python 3.10+"
$python = $null
foreach ($candidate in @("py -3.12", "py -3.11", "py -3.10", "py -3", "python")) {
    try {
        $ver = Invoke-Python $candidate @("-c", "import sys; print('%d.%d' % sys.version_info[:2])") 2>$null
        if ($ver -and [version]$ver -ge [version]"3.10") { $python = $candidate; break }
    } catch { }
}
if (-not $python) {
    Warn "Python 3.10+ not found."
    if ($Offline) {
        Write-Error "Offline mode: install Python 3.12 from your local installer (check 'Add python.exe to PATH'), then re-run."
    } elseif (Get-Command winget -ErrorAction SilentlyContinue) {
        Step "Installing Python 3.12 via winget"
        winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                    [Environment]::GetEnvironmentVariable("Path", "User")
        $python = "py -3.12"
    } else {
        Write-Error "Install Python 3.12 from https://python.org (check 'Add python.exe to PATH'), then re-run."
    }
}
Ok "Using: $python"

# ---------- 2. Backend dependencies ----------
Step "Creating virtual environment and installing server dependencies"
if (-not (Test-Path "backend\.venv")) {
    Invoke-Python $python @("-m", "venv", "backend\.venv")
}
# Use the venv's python for all pip work: upgrading pip via pip.exe directly
# fails on Windows ("Access is denied") because the running exe is locked.
$py = "backend\.venv\Scripts\python.exe"
if (-not $Offline) { & $py -m pip install --quiet --upgrade pip }
& $py -m pip install --quiet @pipNet -r backend\requirements.txt
Ok "Server dependencies installed."

# ---------- 3. ML dependencies ----------
$installML = $false
if ($WithML) { $installML = $true }
elseif (-not $NoML) {
    $answer = Read-Host "`nInstall auto-annotation + relation-rule ML deps (spaCy, PyTorch, transformers, sentence-transformers, ~2.5 GB)? [y/N]"
    if ($answer -match "^[yY]") { $installML = $true }
}
if ($installML) {
    Step "Installing ML dependencies (this can take several minutes)"
    if (-not $Offline) {
        # CUDA build of PyTorch is fetched from a special index (online only).
        # Offline installs must supply torch via -WheelDir or the existing venv.
        $gpu = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
               Where-Object { $_.Name -match "NVIDIA" }
        if ($gpu) {
            Ok "NVIDIA GPU detected ($($gpu[0].Name)) - installing CUDA build of PyTorch"
            & $py -m pip install torch --index-url https://download.pytorch.org/whl/cu121
        }
    }
    & $py -m pip install @pipNet -r backend\requirements-ml.txt
    Ok "ML dependencies installed."
} else {
    Warn "Skipping ML dependencies. Install later with:"
    Warn "  backend\.venv\Scripts\python -m pip install -r backend\requirements-ml.txt"
}

# ---------- 4. Configuration ----------
Step "Configuring"
if (-not (Test-Path "backend\.env")) {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $secret = ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
    # Absolute DB path (forward slashes) so the database is the same regardless
    # of which directory the server is launched from.
    $absDb = (Join-Path $Root "backend\annotation.db") -replace '\\', '/'
    @"
# Generated by install_windows.ps1 - see backend\.env.example for all options.
# For PostgreSQL (recommended for teams), change DATABASE_URL to:
#   postgresql+psycopg2://annotator:PASSWORD@localhost:5432/annotation
DATABASE_URL=sqlite:///$absDb
SECRET_KEY=$secret
"@ | Set-Content -Encoding ASCII backend\.env
    Ok "Created backend\.env (SQLite database, generated secret key)."
} else {
    Ok "backend\.env already exists - keeping it."
}

# ---------- 5. Frontend ----------
if (Test-Path "backend\static\index.html") {
    # Pre-built frontend present (e.g. copied from an online machine). This is
    # the simplest offline path: no Node/npm needed at all.
    Step "Frontend already built - skipping (delete backend\static to rebuild)"
} else {
    Step "Building frontend"

    # Ensure npm is available.
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        if ($NodeInstaller) {
            if (-not (Test-Path $NodeInstaller)) { Write-Error "-NodeInstaller '$NodeInstaller' not found." }
            $nodePath = (Resolve-Path $NodeInstaller).Path
            Step "Installing Node.js from $nodePath"
            if ([System.IO.Path]::GetExtension($nodePath).ToLower() -eq ".msi") {
                Start-Process msiexec.exe -ArgumentList "/i `"$nodePath`" /qn /norestart" -Wait
            } else {
                Start-Process -FilePath $nodePath -Wait
            }
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                        [Environment]::GetEnvironmentVariable("Path", "User")
        } elseif ($Offline) {
            Write-Error "npm not found. Pass the downloaded Node.js installer with -NodeInstaller <path>, OR pre-build the frontend on an online machine and copy its backend\static folder here."
        } elseif (Get-Command winget -ErrorAction SilentlyContinue) {
            Step "Installing Node.js LTS via winget"
            winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                        [Environment]::GetEnvironmentVariable("Path", "User")
        } else {
            Write-Error "Node.js is required to build the frontend. Install from https://nodejs.org and re-run."
        }
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Error "npm is still not on PATH after installing Node.js. Open a NEW terminal so PATH refreshes and re-run, or pre-build the frontend and copy backend\static here."
    }

    Push-Location frontend
    if (Test-Path "node_modules") {
        # Dependencies already vendored (copied from an online machine) — build
        # directly without touching the network.
        Ok "Using existing frontend\node_modules (skipping npm install)."
    } elseif ($Offline) {
        Step "npm install (offline — from the local npm cache)"
        npm install --offline --no-fund --no-audit
    } else {
        npm install --no-fund --no-audit
    }
    npm run build
    Pop-Location
    Ok "Frontend built into backend\static."
}

# ---------- 6. Firewall ----------
Step "Configuring Windows Firewall (port $Port)"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    if (-not (Get-NetFirewallRule -DisplayName "GraphMind Server" -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName "GraphMind Server" -Direction Inbound `
            -Protocol TCP -LocalPort $Port -Action Allow | Out-Null
        Ok "Inbound firewall rule added for TCP $Port."
    } else {
        Ok "Firewall rule already exists."
    }
} else {
    Warn "Not running as Administrator - skipped the firewall rule."
    Warn "Other machines won't reach the server until you allow TCP $Port"
    Warn "(re-run this installer as Administrator, or add the rule manually)."
}

# ---------- 7. Start with Windows (optional) ----------
$startBat = Join-Path $Root "start_server.bat"
if ($AutoStart -or ((Read-Host "`nStart the server automatically when Windows boots? [y/N]") -match "^[yY]")) {
    if ($isAdmin) {
        schtasks /Create /F /TN "GraphMind Server" /SC ONSTART /RU SYSTEM `
            /TR "`"$startBat`"" | Out-Null
        Ok "Scheduled task created - the server starts with Windows."
    } else {
        Warn "Administrator rights required for the scheduled task - skipped."
    }
}

# ---------- Done ----------
$hostname = $env:COMPUTERNAME
Write-Host ""
Ok "Installation complete."
Write-Host ""
Write-Host "Start the server now:   start_server.bat   (or reboot if auto-start was enabled)"
Write-Host "Open on this machine:   http://localhost:$Port"
Write-Host "Open from the network:  http://${hostname}:$Port"
Write-Host "First visit:            click 'First time setup: create admin account'"
