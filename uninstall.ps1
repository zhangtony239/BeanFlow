# 检查 uv 是否已安装
$uvInstalled = $false

if (Get-Command uv -ErrorAction SilentlyContinue) {
    $uvInstalled = $true
} else {
    # 检查默认安装路径下是否存在 uv.exe
    $defaultUvPath = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
    if (Test-Path $defaultUvPath) {
        $env:PATH += ";$env:USERPROFILE\.local\bin"
        $uvInstalled = $true
    }
}

if (-not $uvInstalled) {
    Write-Host "未检测到全局 uv 命令，beanflow 应该未通过 uv 安装。" -ForegroundColor Yellow
    Exit 0
}

# 执行 uv tool uninstall beanflow
Write-Host "正在通过 uv 卸载 beanflow..." -ForegroundColor Cyan
uv tool uninstall beanflow

if ($LASTEXITCODE -eq 0) {
    Write-Host "beanflow 卸载成功！" -ForegroundColor Green
} else {
    Write-Host "beanflow 卸载失败，请检查错误信息。" -ForegroundColor Red
    Exit $LASTEXITCODE
}
