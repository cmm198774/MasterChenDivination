# Redis Server Startup Script
# Check if Redis is running, start it if not

# Redis server path (relative to project directory)
$redisPath = Join-Path $PSScriptRoot "redis-server\redis-server.exe"

# Check if Redis is already running
$redisRunning = Get-Process -Name "redis-server" -ErrorAction SilentlyContinue

if (-not $redisRunning) {
    # Check if redis-server.exe exists
    if (-not (Test-Path $redisPath)) {
        Write-Host "[ERROR] Redis server not found: $redisPath"
        exit 1
    }

    # Try to start Redis server
    try {
        Start-Process -FilePath $redisPath -WindowStyle Hidden
        Write-Host "[OK] Redis server started"
        Start-Sleep -Seconds 2

        # Verify if started successfully
        $redisRunning = Get-Process -Name "redis-server" -ErrorAction SilentlyContinue
        if ($redisRunning) {
            Write-Host "[OK] Redis server is running"
        } else {
            Write-Host "[ERROR] Redis server failed to start"
            exit 1
        }
    } catch {
        Write-Host "[ERROR] Cannot start Redis server: $_"
        exit 1
    }
} else {
    Write-Host "[OK] Redis server is already running"
}
