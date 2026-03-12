#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Pin interface metrics on 22.100 to prevent auto-metric surprises.

.DESCRIPTION
    Layer 3 safety: disables automatic metric on all adapters and assigns
    fixed values so the 22-domain management path always wins over the
    router-facing NIC and Wi-Fi.

    22-domain NIC:  metric 10   (highest priority, management traffic)
    Router NIC:     metric 100  (only for local 192.168.1.x traffic)
    Wi-Fi:          metric 50+  (test traffic only)

    NICs can be selected by adapter alias (default), MAC address, or
    ifIndex for reliability across renames.

.PARAMETER ControlNicAlias
    Adapter name of the NIC connected to the 22-domain switch.
.PARAMETER ControlNicMAC
    MAC address to identify the 22-domain NIC (e.g. "AA-BB-CC-DD-EE-FF").
.PARAMETER RouterNicAlias
    Adapter name of the NIC connected to the router LAN (192.168.1.x).
.PARAMETER RouterNicMAC
    MAC address to identify the router-facing NIC.
.PARAMETER RouterNicIndex
    ifIndex to identify the router-facing NIC.

.EXAMPLE
    .\pin_metrics_22100.ps1 -ControlNicAlias "Ethernet" -RouterNicAlias "Ethernet 2"
.EXAMPLE
    .\pin_metrics_22100.ps1 -ControlNicMAC "AA-BB-CC-DD-EE-FF" -RouterNicMAC "11-22-33-44-55-66"
#>
param(
    [string]$ControlNicAlias,
    [string]$ControlNicMAC,
    [string]$RouterNicAlias,
    [string]$RouterNicMAC,
    [int]$RouterNicIndex = 0,
    [string]$WifiNicAlias = "Wi-Fi",
    [int]$ControlMetric = 10,
    [int]$RouterMetric = 100,
    [int]$WifiMetric = 50
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  22.100 Metric Pinning (Layer 3)       " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# --- Show current state ---
Write-Host "[INFO] Current adapter metrics:" -ForegroundColor Yellow
Get-NetIPInterface -AddressFamily IPv4 |
    Where-Object { $_.ConnectionState -eq "Connected" } |
    Sort-Object InterfaceMetric |
    Format-Table InterfaceAlias, InterfaceIndex, InterfaceMetric, AutomaticMetric -AutoSize

function Resolve-NicAlias {
    param([string]$Alias, [string]$MAC, [int]$IfIndex, [string]$Label)

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

    if ($IfIndex -gt 0) {
        $iface = Get-NetIPInterface -InterfaceIndex $IfIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
        if ($iface) {
            Write-Host "  Resolved $Label by ifIndex $IfIndex -> $($iface.InterfaceAlias)" -ForegroundColor Green
            return $iface.InterfaceAlias
        }
        Write-Host "  [FAIL] No adapter with ifIndex $IfIndex" -ForegroundColor Red
        exit 1
    }

    return $null
}

$ControlNicAlias = Resolve-NicAlias -Alias $ControlNicAlias -MAC $ControlNicMAC -IfIndex 0 -Label "22-domain"
$RouterNicAlias = Resolve-NicAlias -Alias $RouterNicAlias -MAC $RouterNicMAC -IfIndex $RouterNicIndex -Label "Router"

# --- Identify NICs if still not resolved ---
if (-not $ControlNicAlias -or -not $RouterNicAlias) {
    $adapters = Get-NetAdapter | Where-Object { $_.Status -eq "Up" }
    $ipConfigs = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.InterfaceAlias -in $adapters.Name -and $_.IPAddress -ne "127.0.0.1" }

    Write-Host "[INFO] Connected adapters:" -ForegroundColor Yellow
    foreach ($a in $adapters) {
        $ips = ($ipConfigs | Where-Object { $_.InterfaceAlias -eq $a.Name }).IPAddress -join ", "
        Write-Host "  $($a.Name) [MAC=$($a.MacAddress), ifIndex=$($a.ifIndex)] -> $ips"
    }
    Write-Host ""

    if (-not $ControlNicAlias) {
        $ControlNicAlias = Read-Host "Enter the adapter name for 22-DOMAIN (management)"
    }
    if (-not $RouterNicAlias) {
        $RouterNicAlias = Read-Host "Enter the adapter name for ROUTER (192.168.1.x)"
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
Write-Host "[1/3] Pinning 22-domain NIC: $ControlNicAlias -> metric $ControlMetric" -ForegroundColor Cyan
Set-FixedMetric -Alias $ControlNicAlias -Metric $ControlMetric -Label "22-domain"

Write-Host "[2/3] Pinning Router NIC: $RouterNicAlias -> metric $RouterMetric" -ForegroundColor Cyan
Set-FixedMetric -Alias $RouterNicAlias -Metric $RouterMetric -Label "Router"

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
Write-Host "  Layer 3 complete (22.100).            " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
