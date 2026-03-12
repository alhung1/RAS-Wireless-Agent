#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Pin interface metrics on the Orchestrator PC to prevent auto-metric surprises.

.DESCRIPTION
    Layer 3 safety: disables automatic metric on all adapters and assigns
    fixed values so that Windows never re-prioritises routes when Wi-Fi
    connects or a NIC link-state changes.

    NIC-1 (Internet / 200-domain):  metric 10  (highest priority, default route)
    NIC-2 (22-domain control):      metric 20
    Wi-Fi:                          metric 50  (lowest priority)

    NICs can be selected by adapter alias (default), MAC address, or ifIndex.

.PARAMETER InternetNicAlias
    Adapter name of the NIC connected to the 200-domain / internet.
.PARAMETER InternetNicMAC
    MAC address to identify the internet-facing NIC.
.PARAMETER ControlNicAlias
    Adapter name of the NIC connected to the 22-domain switch.
.PARAMETER ControlNicMAC
    MAC address to identify the 22-domain NIC.

.EXAMPLE
    .\pin_metrics_orchestrator.ps1 -InternetNicAlias "Ethernet" -ControlNicAlias "Ethernet 2"
.EXAMPLE
    .\pin_metrics_orchestrator.ps1 -InternetNicMAC "AA-BB-CC-DD-EE-FF" -ControlNicMAC "11-22-33-44-55-66"
#>
param(
    [string]$InternetNicAlias,
    [string]$InternetNicMAC,
    [string]$ControlNicAlias,
    [string]$ControlNicMAC,
    [string]$WifiNicAlias = "Wi-Fi",
    [int]$InternetMetric = 10,
    [int]$ControlMetric = 20,
    [int]$WifiMetric = 50
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Orchestrator Metric Pinning (Layer 3) " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# --- Show current state ---
Write-Host "[INFO] Current adapter metrics:" -ForegroundColor Yellow
Get-NetIPInterface -AddressFamily IPv4 |
    Where-Object { $_.ConnectionState -eq "Connected" } |
    Sort-Object InterfaceMetric |
    Format-Table InterfaceAlias, InterfaceIndex, InterfaceMetric, AutomaticMetric -AutoSize

function Resolve-NicAlias {
    param([string]$Alias, [string]$MAC, [string]$Label)

    if ($Alias) { return $Alias }

    if ($MAC) {
        $adapter = Get-NetAdapter | Where-Object { $_.MacAddress -eq $MAC -and $_.Status -eq "Up" }
        if ($adapter) {
            Write-Host "  Resolved $Label by MAC $MAC -> $($adapter.Name)" -ForegroundColor Green
            return $adapter.Name
        }
        Write-Host "  [FAIL] No active adapter with MAC $MAC" -ForegroundColor Red
        exit 1
    }

    return $null
}

$InternetNicAlias = Resolve-NicAlias -Alias $InternetNicAlias -MAC $InternetNicMAC -Label "Internet"
$ControlNicAlias = Resolve-NicAlias -Alias $ControlNicAlias -MAC $ControlNicMAC -Label "22-domain"

# --- Identify NICs if still not resolved ---
if (-not $InternetNicAlias -or -not $ControlNicAlias) {
    $adapters = Get-NetAdapter | Where-Object { $_.Status -eq "Up" }
    $ipConfigs = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.InterfaceAlias -in $adapters.Name -and $_.IPAddress -ne "127.0.0.1" }

    Write-Host "[INFO] Connected adapters:" -ForegroundColor Yellow
    foreach ($a in $adapters) {
        $ips = ($ipConfigs | Where-Object { $_.InterfaceAlias -eq $a.Name }).IPAddress -join ", "
        Write-Host "  $($a.Name) [MAC=$($a.MacAddress), ifIndex=$($a.ifIndex)] -> $ips"
    }
    Write-Host ""

    if (-not $InternetNicAlias) {
        $InternetNicAlias = Read-Host "Enter the adapter name for INTERNET (200-domain)"
    }
    if (-not $ControlNicAlias) {
        $ControlNicAlias = Read-Host "Enter the adapter name for 22-DOMAIN control"
    }
}

function Set-FixedMetric {
    param([string]$Alias, [int]$Metric, [string]$Label)

    $iface = Get-NetIPInterface -InterfaceAlias $Alias -AddressFamily IPv4 -ErrorAction SilentlyContinue
    if (-not $iface) {
        Write-Host "  [SKIP] $Label ($Alias) not found or not connected" -ForegroundColor Yellow
        return
    }
    Set-NetIPInterface -InterfaceAlias $Alias -AddressFamily IPv4 `
        -AutomaticMetric Disabled `
        -InterfaceMetric $Metric
    Write-Host "  [OK] $Label ($Alias) -> metric $Metric (AutomaticMetric=Disabled)" -ForegroundColor Green
}

Write-Host ""
Write-Host "[1/3] Pinning NIC-1 (Internet): $InternetNicAlias -> metric $InternetMetric" -ForegroundColor Cyan
Set-FixedMetric -Alias $InternetNicAlias -Metric $InternetMetric -Label "NIC-1 Internet"

Write-Host "[2/3] Pinning NIC-2 (Control): $ControlNicAlias -> metric $ControlMetric" -ForegroundColor Cyan
Set-FixedMetric -Alias $ControlNicAlias -Metric $ControlMetric -Label "NIC-2 Control"

Write-Host "[3/3] Pinning Wi-Fi: $WifiNicAlias -> metric $WifiMetric" -ForegroundColor Cyan
Set-FixedMetric -Alias $WifiNicAlias -Metric $WifiMetric -Label "Wi-Fi"

# --- Verify ---
Write-Host ""
Write-Host "[VERIFY] Final metrics:" -ForegroundColor Yellow
$final = Get-NetIPInterface -AddressFamily IPv4 |
    Where-Object { $_.ConnectionState -eq "Connected" } |
    Sort-Object InterfaceMetric
$final | Format-Table InterfaceAlias, InterfaceIndex, InterfaceMetric, AutomaticMetric -AutoSize

$allDisabled = ($final | Where-Object { $_.AutomaticMetric -eq $true }).Count -eq 0
if ($allDisabled) {
    Write-Host "[OK] All connected adapters have AutomaticMetric=Disabled" -ForegroundColor Green
} else {
    Write-Host "[WARN] Some adapters still have AutomaticMetric=Enabled" -ForegroundColor Yellow
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Layer 3 complete (Orchestrator).      " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
