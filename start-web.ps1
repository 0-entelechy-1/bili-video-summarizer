# B站视频分析器 Web 界面快速启动脚本
# 用法: .\start-web.ps1

$ErrorActionPreference = "Continue"

# 颜色输出
function Write-Color($Text, $Color = "White") {
    Write-Host $Text -ForegroundColor $Color
}

# 获取项目根目录
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ProjectRoot) {
    $ProjectRoot = $PSScriptRoot
}
Set-Location $ProjectRoot

Write-Color "========================================" "Cyan"
Write-Color "  B站视频分析器 Web 界面启动脚本" "Cyan"
Write-Color "========================================" "Cyan"
Write-Host ""

# 检查 conda 环境
Write-Color "[1/4] 检查 conda 环境..." "Yellow"
try {
    $CondaEnv = conda run -n pytorch3_9 python --version 2>&1 | Select-Object -First 1
    Write-Color "  [OK] conda 环境 pytorch3_9 可用: $CondaEnv" "Green"
} catch {
    Write-Color "  [FAIL] conda 环境 pytorch3_9 未找到" "Red"
    exit 1
}

# 检查后端依赖
Write-Color "[2/4] 检查后端依赖..." "Yellow"
try {
    $null = conda run -n pytorch3_9 python -c "import fastapi, sqlalchemy, aiosqlite" 2>&1 | Out-Null
    Write-Color "  [OK] 后端依赖已安装" "Green"
} catch {
    Write-Color "  [WARN] 后端依赖缺失，正在安装..." "Yellow"
    conda run -n pytorch3_9 pip install fastapi uvicorn sqlalchemy aiosqlite python-multipart pydantic
    Write-Color "  [OK] 后端依赖安装完成" "Green"
}

# 检查前端依赖
Write-Color "[3/4] 检查前端依赖..." "Yellow"
if (Test-Path "$ProjectRoot\web\frontend\node_modules") {
    Write-Color "  [OK] 前端依赖已安装" "Green"
} else {
    Write-Color "  [WARN] 前端依赖缺失，正在安装..." "Yellow"
    Set-Location "$ProjectRoot\web\frontend"
    npm install
    Set-Location $ProjectRoot
    Write-Color "  [OK] 前端依赖安装完成" "Green"
}

Write-Host ""
Write-Color "[4/4] 启动服务..." "Yellow"
Write-Host ""

# 查找可用端口
function Get-AvailablePort($StartPort) {
    $Port = $StartPort
    while ($Port -lt $StartPort + 100) {
        $Result = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if (-not $Result) {
            return $Port
        }
        $Port++
    }
    return $StartPort
}

$BackendPort = 8000
$FrontendPort = 5173

# 检查端口占用
$BackendInUse = Get-NetTCPConnection -LocalPort $BackendPort -ErrorAction SilentlyContinue
if ($BackendInUse) {
    Write-Color "  [WARN] 后端端口 $BackendPort 已被占用，使用下一个可用端口" "Yellow"
    $BackendPort = Get-AvailablePort ($BackendPort + 1)
}

$FrontendInUse = Get-NetTCPConnection -LocalPort $FrontendPort -ErrorAction SilentlyContinue
if ($FrontendInUse) {
    Write-Color "  [WARN] 前端端口 $FrontendPort 已被占用，使用下一个可用端口" "Yellow"
    $FrontendPort = Get-AvailablePort ($FrontendPort + 1)
}

Write-Host ""

# 启动后端
Write-Color "  -> 启动 FastAPI 后端 (http://localhost:$BackendPort)" "Blue"
$BackendJob = Start-Job -ScriptBlock {
    param($Root, $Port)
    Set-Location $Root
    conda run -n pytorch3_9 python -m uvicorn web.backend.main:app --host 0.0.0.0 --port $Port
} -ArgumentList $ProjectRoot, $BackendPort

# 等待后端启动
Write-Color "  -> 等待后端服务就绪..." "Gray"
$BackendReady = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    $Check = Get-NetTCPConnection -LocalPort $BackendPort -ErrorAction SilentlyContinue
    if ($Check) {
        $BackendReady = $true
        break
    }
}
if ($BackendReady) {
    Write-Color "  [OK] 后端已就绪 (端口 $BackendPort)" "Green"
} else {
    Write-Color "  [WARN] 后端启动超时" "Yellow"
}

# 启动前端
Write-Color "  -> 启动 React 前端..." "Blue"
$FrontendJob = Start-Job -ScriptBlock {
    param($Root, $Port)
    Set-Location "$Root\web\frontend"
    $env:PORT = $Port
    npm run dev
} -ArgumentList $ProjectRoot, $FrontendPort

# 等待前端启动并检测实际端口
Write-Color "  -> 等待前端服务就绪..." "Gray"
$FrontendReady = $false
$ActualFrontendPort = $FrontendPort

for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500

    # 获取前端Job输出，看实际使用的端口
    $Output = Receive-Job -Job $FrontendJob
    if ($Output -match "Local:\s+http://localhost:(\d+)") {
        $ActualFrontendPort = [int]$Matches[1]
        $FrontendReady = $true
        break
    }

    # 检查端口是否已监听
    $Check = Get-NetTCPConnection -LocalPort $FrontendPort -ErrorAction SilentlyContinue
    if ($Check) {
        $FrontendReady = $true
        break
    }
}

if ($FrontendReady) {
    Write-Color "  [OK] 前端已就绪 (端口 $ActualFrontendPort)" "Green"
} else {
    Write-Color "  [WARN] 前端启动超时" "Yellow"
}

Write-Host ""
Write-Color "========================================" "Cyan"
Write-Color "  服务已启动!" "Green"
Write-Color "========================================" "Cyan"
Write-Color "  前端界面: http://localhost:$ActualFrontendPort" "Green"
Write-Color "  后端 API: http://localhost:$BackendPort" "Green"
Write-Color "  API 文档:  http://localhost:$BackendPort/docs" "Green"
Write-Color "========================================" "Cyan"
Write-Host ""

# 自动打开浏览器
$BrowserUrl = "http://localhost:$ActualFrontendPort"
Write-Color "  -> 正在打开浏览器..." "Blue"
try {
    Start-Process $BrowserUrl
    Write-Color "  [OK] 浏览器已打开: $BrowserUrl" "Green"
} catch {
    Write-Color "  [WARN] 自动打开浏览器失败，请手动访问 $BrowserUrl" "Yellow"
}

Write-Host ""
Write-Color "按 Ctrl+C 停止所有服务..." "Yellow"
Write-Host ""

# 实时输出日志
$Running = $true

try {
    while ($Running) {
        # 检查是否收到Ctrl+C
        if ($Host.UI.RawUI.KeyAvailable) {
            $key = $Host.UI.RawUI.ReadKey("IncludeKeyUp,NoEcho")
            if ($key.VirtualKeyCode -eq 0x03) {  # Ctrl+C
                $Running = $false
                break
            }
        }

        # 获取日志输出
        $BackendOutput = Receive-Job -Job $BackendJob
        $FrontendOutput = Receive-Job -Job $FrontendJob

        if ($BackendOutput) {
            $BackendOutput | ForEach-Object { Write-Host "[后端] $_" -ForegroundColor Gray }
        }

        if ($FrontendOutput) {
            $FrontendOutput | ForEach-Object { Write-Host "[前端] $_" -ForegroundColor DarkGray }
        }

        # 检查任务状态
        if ($BackendJob.State -eq "Failed") {
            Write-Color "后端服务异常退出!" "Red"
            break
        }
        if ($FrontendJob.State -eq "Failed") {
            Write-Color "前端服务异常退出!" "Red"
            break
        }

        Start-Sleep -Milliseconds 200
    }
} finally {
    Write-Host ""
    Write-Color "正在停止服务..." "Yellow"
    Stop-Job -Job $BackendJob -ErrorAction SilentlyContinue
    Stop-Job -Job $FrontendJob -ErrorAction SilentlyContinue
    Remove-Job -Job $BackendJob -ErrorAction SilentlyContinue
    Remove-Job -Job $FrontendJob -ErrorAction SilentlyContinue
    Write-Color "服务已停止" "Green"
}
