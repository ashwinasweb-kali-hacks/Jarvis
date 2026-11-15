param(
    [string]$Ssid = "JARVIS-HUD",
    [string]$Key = "jarvis2026"
)

# Creates a private Wi-Fi network on this PC so the Quest can reach the
# JARVIS daemon without the USB debugging prompt, then republishes the
# certificate for the new address and restarts the HTTPS daemon.

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

Write-Host ""
Write-Host "  Setting up the JARVIS-HUD hotspot..." -ForegroundColor Cyan
Write-Host ""

netsh wlan set hostednetwork mode=allow ssid=$Ssid key=$Key | Out-Host
netsh wlan start hostednetwork | Out-Host
Start-Sleep -Seconds 6

# The hosted network shows up as "Local Area Connection* N".
$adapter = Get-NetAdapter |
    Where-Object { $_.InterfaceDescription -match "Hosted Network|Virtual Adapter|Microsoft Wi-Fi Direct" -or $_.Name -like "Local Area Connection*" } |
    Select-Object -First 1
if (-not $adapter) {
    $adapter = Get-NetAdapter | Where-Object { $_.Status -eq "Up" -and $_.Name -notlike "Wi-Fi" } | Select-Object -First 1
}

$ip = $null
if ($adapter) {
    $ip = (Get-NetIPAddress -InterfaceAlias $adapter.Name -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "169.254*" } | Select-Object -First 1).IPAddress
}

if (-not $ip) {
    Write-Host "  Could not find the hotspot address." -ForegroundColor Yellow
    Write-Host "  Run 'netsh wlan show hostednetwork' to check the state." -ForegroundColor Yellow
} else {
    Write-Host ("  Hotspot address: {0}" -f $ip) -ForegroundColor Green

    # Publish the new address on the certificate.
    & $python -c "from jarvis import tls; tls.ensure_certificate(force=True); print('  certificate refreshed')"
    if ($LASTEXITCODE -ne 0) { Write-Host "  certificate refresh failed (is the venv present?)" -ForegroundColor Yellow }

    # Restart the HTTPS daemon so it picks up the new certificate.
    Get-CimInstance Win32_Process |
        Where-Object { $_.Name -match "^python" -and $_.CommandLine -match "jarvis\.daemon" } |
        ForEach-Object {
            if ($_.CommandLine -match "8766" -or $env:JARVIS_DAEMON_PORT -eq "8766") {
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            }
        }
    Start-Sleep -Seconds 2
    $env:JARVIS_TLS = "1"
    $env:JARVIS_DAEMON_PORT = "8766"
    $env:JARVIS_DAEMON_HOST = "0.0.0.0"
    Start-Process -FilePath $python -ArgumentList "-m", "jarvis.daemon" -WorkingDirectory $root -WindowStyle Hidden
    Start-Sleep -Seconds 8

    Write-Host ""
    Write-Host "  ========================================================" -ForegroundColor Cyan
    Write-Host "   In the Quest:" -ForegroundColor Cyan
    Write-Host "     1. Settings -> Wi-Fi -> join '$Ssid'  (password: $Key)" -ForegroundColor White
    Write-Host "     2. Meta Quest Browser -> https://$ip:8766/" -ForegroundColor White
    Write-Host "     3. First visit: Advanced -> Proceed to $ip" -ForegroundColor White
    Write-Host "     4. Press the AR MODE button in the HUD" -ForegroundColor White
    Write-Host "  ========================================================" -ForegroundColor Cyan
    Write-Host ""
}

Write-Host "  Press a key to close." -ForegroundColor DarkGray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
