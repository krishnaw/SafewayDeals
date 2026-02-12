# Safeway Deals Server - Start/Stop script
# Usage: powershell -File web/server.ps1 start
#        powershell -File web/server.ps1 stop

param(
    [Parameter(Position=0)]
    [ValidateSet("start", "stop")]
    [string]$Action
)

$Port = 8001
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ScriptDir ".server.pid"
$LogFile = Join-Path $ScriptDir "server.log"
$ProjectRoot = Split-Path -Parent $ScriptDir

function Get-ServerPids {
    # Try Get-NetTCPConnection first, fall back to netstat
    $pids = @()
    try {
        $pids = Get-NetTCPConnection -LocalPort $Port -ErrorAction Stop |
            Where-Object State -eq "Listen" |
            Select-Object -ExpandProperty OwningProcess -Unique
    } catch {
        # Fallback: parse netstat output
        $lines = netstat -aon 2>$null | Select-String ":$Port\s" | Select-String "LISTENING"
        foreach ($line in $lines) {
            if ($line -match '\s(\d+)\s*$') {
                $pids += [int]$Matches[1]
            }
        }
        $pids = $pids | Select-Object -Unique
    }
    return $pids
}

function Start-Server {
    $existing = Get-ServerPids
    if ($existing) {
        # Verify the server is actually responding (not a ghost PID)
        $alive = $false
        try {
            $null = Invoke-WebRequest -Uri "http://localhost:$Port/api/categories" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            $alive = $true
        } catch {}

        if ($alive) {
            Write-Host "Server already running on port $Port (PID: $($existing -join ', '))"
            Write-Host "  URL: http://localhost:$Port"
            return
        }
        # Ghost PID — kill and proceed
        Write-Host "Stale process on port $Port, cleaning up..."
        foreach ($p in $existing) {
            & taskkill /F /T /PID $p 2>$null | Out-Null
        }
        Start-Sleep -Seconds 1
    }

    Write-Host "Starting Safeway Deals server on http://localhost:$Port (hot reload enabled)..."

    $proc = Start-Process -FilePath python -ArgumentList @(
        "-m", "uvicorn", "web.server:app",
        "--host", "0.0.0.0",
        "--port", $Port,
        "--reload",
        "--reload-dir", "web",
        "--reload-dir", "search"
    ) -WorkingDirectory $ProjectRoot -RedirectStandardOutput $LogFile -RedirectStandardError "$LogFile.err" -PassThru -WindowStyle Hidden

    # Wait for server to be ready (up to 20 seconds)
    $ready = $false
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        try {
            $null = Invoke-WebRequest -Uri "http://localhost:$Port/api/categories" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            $ready = $true
            break
        } catch {}
    }

    # Find the actual listening PID (uvicorn reload spawns child processes)
    $serverPids = Get-ServerPids
    if ($serverPids) {
        $serverPids -join "`n" | Set-Content $PidFile
        Write-Host ""
        Write-Host "Server started successfully"
        Write-Host "  PID:    $($serverPids -join ', ')"
        Write-Host "  Port:   $Port"
        Write-Host "  URL:    http://localhost:$Port"
        Write-Host "  Log:    $LogFile"
        Write-Host "  Reload: Watching web/ and search/ for changes"
    } else {
        Write-Host "WARNING: Server may have started but PID could not be determined."
        Write-Host "  Check: http://localhost:$Port"
        Write-Host "  Log:   $LogFile"
    }
}

function Stop-Server {
    $found = $false

    # Try PID file first
    if (Test-Path $PidFile) {
        $savedPids = Get-Content $PidFile
        foreach ($p in $savedPids) {
            $p = $p.Trim()
            if ($p) {
                Write-Host "Stopping server (PID: $p, Port: $Port)..."
                & taskkill /F /T /PID $p 2>$null | Out-Null
                $found = $true
            }
        }
        Remove-Item $PidFile -ErrorAction SilentlyContinue
    }

    # Also kill anything still on the port (reload spawns child processes)
    $serverPids = Get-ServerPids
    foreach ($p in $serverPids) {
        & taskkill /F /T /PID $p 2>$null | Out-Null
        $found = $true
    }

    if ($found) {
        Write-Host "Server stopped."
    } else {
        Write-Host "No server found running on port $Port."
    }
}

if (-not $Action) {
    Write-Host "Usage: powershell -File web/server.ps1 [start|stop]"
    Write-Host "  start  - Start the Safeway Deals server (port $Port, hot reload)"
    Write-Host "  stop   - Stop the running server"
    exit 1
}

switch ($Action) {
    "start" { Start-Server }
    "stop"  { Stop-Server }
}
