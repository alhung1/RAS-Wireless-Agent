#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Configure network interfaces on 22.100 for safe router control.

    Router-facing NIC: static IP 192.168.1.50/24, NO default gateway.
    22-domain NIC:     keeps its current gateway (management traffic).

.DESCRIPTION
    Layer 2 safety: by removing the default gateway from the router NIC,
    a router reboot can never hijack 22.100's routing table. The 22-domain
    management path survives regardless of router state.

.PARAMETER RouterNicAlias
    Adapter name of the NIC connected to the router LAN (192.168.1.x).

.PARAMETER ControlNicAlias
    Adapter name of the NIC connected to the 22-domain switch.

.PARAMETER RouterStaticIP
    Static IP to assign on the router NIC. Default: 192.168.1.50.

.PARAMETER RouterSubnetPrefix
    Prefix length for the router subnet. Default: 24.

.EXAMPLE
    .\setup_22100_network.ps1 -RouterNicAlias "Ethernet 2" -ControlNicAlias "Ethernet"
#>
param(
    [Parameter(Mandatory = $false)]
    [string]$RouterNicAlias,

    [Parameter(Mandatory = $false)]
    [string]$ControlNicAlias,

    [string]$RouterStaticIP = "192.168.1.50",
    [int]$RouterSubnetPrefix = 24
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  22.100 Network Setup (Layer 2)        " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# --- Enumerate adapters ---
Write-Host "[INFO] Current network adapters:" -ForegroundColor Yellow
$adapters = Get-NetAdapter | Where-Object { $_.Status -eq "Up" }
$adapters | Format-Table Name, InterfaceIndex, MacAddress, LinkSpeed -AutoSize

$ipConfigs = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.InterfaceAlias -in $adapters.Name -and $_.IPAddress -ne "127.0.0.1" }
$ipConfigs | Format-Table InterfaceAlias, IPAddress, PrefixLength -AutoSize

# --- Identify NICs if not provided ---
if (-not $RouterNicAlias -or -not $ControlNicAlias) {
    Write-Host ""
    Write-Host "[WARN] NIC aliases not provided. Please identify them from the list above." -ForegroundColor Yellow
    Write-Host ""
    foreach ($a in $adapters) {
        $ips = ($ipConfigs | Where-Object { $_.InterfaceAlias -eq $a.Name }).IPAddress -join ", "
        Write-Host "  $($a.Name) -> $ips"
    }
    Write-Host ""

    if (-not $RouterNicAlias) {
        $RouterNicAlias = Read-Host "Enter the adapter name connected to the ROUTER (192.168.1.x)"
    }
    if (-not $ControlNicAlias) {
        $ControlNicAlias = Read-Host "Enter the adapter name connected to the 22-DOMAIN switch"
    }
}

# --- Validate adapters exist ---
$routerAdapter = Get-NetAdapter -Name $RouterNicAlias -ErrorAction SilentlyContinue
if (-not $routerAdapter) {
    Write-Host "[ERROR] Adapter '$RouterNicAlias' not found." -ForegroundColor Red
    exit 1
}
$controlAdapter = Get-NetAdapter -Name $ControlNicAlias -ErrorAction SilentlyContinue
if (-not $controlAdapter) {
    Write-Host "[ERROR] Adapter '$ControlNicAlias' not found." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[1/4] Configuring Router NIC: $RouterNicAlias" -ForegroundColor Cyan

# --- Remove existing IP config on the router NIC ---
$existingIP = Get-NetIPAddress -InterfaceAlias $RouterNicAlias -AddressFamily IPv4 -ErrorAction SilentlyContinue
if ($existingIP) {
    Write-Host "  Removing existing IP configuration..."
    Remove-NetIPAddress -InterfaceAlias $RouterNicAlias -AddressFamily IPv4 -Confirm:$false -ErrorAction SilentlyContinue
    Remove-NetRoute -InterfaceAlias $RouterNicAlias -AddressFamily IPv4 -Confirm:$false -ErrorAction SilentlyContinue
}

# --- Assign static IP with NO default gateway ---
Write-Host "  Setting static IP: $RouterStaticIP/$RouterSubnetPrefix (NO gateway)"
New-NetIPAddress -InterfaceAlias $RouterNicAlias `
    -IPAddress $RouterStaticIP `
    -PrefixLength $RouterSubnetPrefix `
    -ErrorAction Stop | Out-Null

# --- Disable DHCP on router NIC ---
Write-Host "  Disabling DHCP on router NIC..."
Set-NetIPInterface -InterfaceAlias $RouterNicAlias -Dhcp Disabled -ErrorAction SilentlyContinue

Write-Host "  [OK] Router NIC: $RouterStaticIP/$RouterSubnetPrefix, no gateway" -ForegroundColor Green

# --- Verify 22-domain NIC has a gateway ---
Write-Host ""
Write-Host "[2/4] Verifying Control NIC: $ControlNicAlias" -ForegroundColor Cyan

$controlRoutes = Get-NetRoute -InterfaceAlias $ControlNicAlias -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue
if ($controlRoutes) {
    $gw = $controlRoutes[0].NextHop
    Write-Host "  [OK] 22-domain NIC has default gateway: $gw" -ForegroundColor Green
} else {
    Write-Host "  [WARN] 22-domain NIC has NO default gateway!" -ForegroundColor Red
    Write-Host "  Management traffic may not route correctly." -ForegroundColor Red
    Write-Host "  Please configure a gateway on $ControlNicAlias." -ForegroundColor Red
}

# --- Verify no default gateway on router NIC ---
Write-Host ""
Write-Host "[3/4] Verifying router NIC has no default gateway..." -ForegroundColor Cyan

$routerRoutes = Get-NetRoute -InterfaceAlias $RouterNicAlias -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue
if ($routerRoutes) {
    Write-Host "  [FAIL] Router NIC still has a default gateway! Removing..." -ForegroundColor Red
    Remove-NetRoute -InterfaceAlias $RouterNicAlias -DestinationPrefix "0.0.0.0/0" -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "  [OK] Default gateway removed from router NIC" -ForegroundColor Green
} else {
    Write-Host "  [OK] Router NIC has no default gateway" -ForegroundColor Green
}

# --- Connectivity test ---
Write-Host ""
Write-Host "[4/4] Connectivity checks..." -ForegroundColor Cyan

$routerPing = Test-Connection -ComputerName 192.168.1.1 -Count 1 -Quiet -ErrorAction SilentlyContinue
if ($routerPing) {
    Write-Host "  [OK] Router 192.168.1.1 reachable via $RouterNicAlias" -ForegroundColor Green
} else {
    Write-Host "  [WARN] Router 192.168.1.1 NOT reachable (may be off or rebooting)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "--- Final routing table ---" -ForegroundColor Yellow
route print -4 | Select-String "0.0.0.0|192.168"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Layer 2 setup complete.               " -ForegroundColor Cyan
Write-Host "                                        " -ForegroundColor Cyan
Write-Host "  Router NIC: $RouterStaticIP/$RouterSubnetPrefix (no GW)" -ForegroundColor Cyan
Write-Host "  Control NIC: $ControlNicAlias (has GW)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
