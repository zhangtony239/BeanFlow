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
    Write-Host "未检测到全局 uv 命令。" -ForegroundColor Yellow
    $choice = Read-Host "是否自动安装 uv? (Y/N) [默认: Y]"
    if ($choice -eq 'Y' -or $choice -eq 'y' -or $choice -eq '') {
        Write-Host "正在安装 uv..." -ForegroundColor Cyan
        # 运行 uv 官方安装脚本
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        
        # 安装后，将 uv 路径加入当前会话的 PATH
        $uvPath = Join-Path $env:USERPROFILE ".local\bin"
        if (Test-Path (Join-Path $uvPath "uv.exe")) {
            $env:PATH += ";$uvPath"
            $uvInstalled = $true
            Write-Host "uv 安装成功并已加入当前会话 PATH。" -ForegroundColor Green
        } else {
            Write-Host "uv 安装可能失败，未在默认路径下找到 uv.exe。" -ForegroundColor Red
            Exit 1
        }
    } else {
        Write-Host "请手动安装 uv (https://github.com/astral-sh/uv) 后再运行此脚本。" -ForegroundColor Yellow
        Exit 1
    }
}

# 执行 uv tool install -e .
Write-Host "正在通过 uv 安装 beanflow..." -ForegroundColor Cyan
uv tool install -e .

if ($LASTEXITCODE -eq 0) {
    Write-Host "beanflow 安装成功！" -ForegroundColor Green
} else {
    Write-Host "beanflow 安装失败，请检查错误信息。" -ForegroundColor Red
    Exit $LASTEXITCODE
}
