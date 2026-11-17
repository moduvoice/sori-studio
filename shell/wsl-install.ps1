# WSL2 켜기(관리자 권한으로 돌아요). 1) wsl --install --no-distribution  2) 안 되면 기능 켜기 + 공식 MSI(해시 확인)
# 끝나면 PC 를 다시 시작해야 해요. 종료 코드 0 = 됨.
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
$msiUrl = "https://github.com/microsoft/WSL/releases/download/3.0.5/wsl.3.0.5.0.x64.msi"
$msiSha = "2313EFC5873E3F8552F42E77F950FABD913C0289078FA89D2100F3421A525EAA"
$out = & wsl.exe --install --no-distribution 2>&1 | Out-String
if ($LASTEXITCODE -eq 0 -and $out -notmatch "not installed") { exit 0 }
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart | Out-Null
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart | Out-Null
$msi = Join-Path $env:TEMP "sori-studio-wsl.msi"
Invoke-WebRequest $msiUrl -OutFile $msi
if ((Get-FileHash $msi -Algorithm SHA256).Hash -ne $msiSha) { Remove-Item $msi; exit 3 }
$p = Start-Process msiexec.exe -ArgumentList "/i", "`"$msi`"", "/qn", "/norestart" -Wait -PassThru
Remove-Item $msi -ErrorAction SilentlyContinue
if ($p.ExitCode -eq 0 -or $p.ExitCode -eq 3010) { exit 0 }
exit $p.ExitCode
