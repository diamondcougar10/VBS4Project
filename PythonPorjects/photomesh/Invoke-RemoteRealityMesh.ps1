param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$TargetIP,
    [Parameter(Mandatory=$true, Position=1)]
    [string]$SettingsFile
)

if (-not (Test-Path $SettingsFile)) {
    Write-Error "Settings file not found: $SettingsFile"
    exit 1
}

$session = New-PSSession -ComputerName $TargetIP
try {
    $scriptPath = Join-Path $PSScriptRoot 'RealityMeshProcess.ps1'
    Write-Host "Running RealityMeshProcess.ps1 on $TargetIP" -ForegroundColor Cyan
    $output = Invoke-Command -Session $session -FilePath $scriptPath -ArgumentList $SettingsFile
    Write-Output $output
}
finally {
    if ($session) {
        Remove-PSSession $session
    }
}
