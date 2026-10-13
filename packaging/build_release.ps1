<#
  打包发布版（不含游戏素材）→ dist\SlugcatPet-v<版本>-win64.zip，中英文同一个 exe。

  用法:
    powershell -ExecutionPolicy Bypass -File packaging\build_release.ps1
    可选: -Version 0.1.0   -Console(保留控制台)   -Python E:\Python312\python.exe
          -Test(打包前跑行为检查 + 参数文档检查)
  解释器优先级：-Python > .venv > py -3.12 > PATH 上的 python
#>
param(
  [string]$Version,
  [switch]$Console,
  [string]$Python,
  [switch]$Test
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..").Path
$MinPy = [version]"3.12"
Set-Location $repo

# 结束残留进程，避免占用 dist 文件
Get-Process SlugcatPet, SlugcatPet-bundled -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

if (-not $Version) {
  $pp = "$repo\pyproject.toml"
  $Version = if ((Test-Path $pp) -and ((Get-Content $pp -Raw) -match 'version\s*=\s*"([^"]+)"')) { $Matches[1] } else { "0.0.0" }
}

# ── 选解释器 ──
# PS 5.1 + Stop 下原生程序写 stderr 会变成终止错误，故局部 Continue、只看退出码
function Get-PyVersion([string[]]$cmd) {
  $ErrorActionPreference = "Continue"
  try {
    $exe = $cmd[0]; $pre = @($cmd | Select-Object -Skip 1)
    $v = & $exe @pre -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null
    if ($LASTEXITCODE -eq 0 -and $v) { return [version]($v.Trim()) }
  } catch {}
  return $null
}
$candidates = @()
if ($Python) { $candidates += ,@($Python) }
if (Test-Path "$repo\.venv\Scripts\python.exe") { $candidates += ,@("$repo\.venv\Scripts\python.exe") }
if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += ,@("py", "-3.12") }
if (Get-Command python -ErrorAction SilentlyContinue) { $candidates += ,@("python") }
$py = $null
foreach ($c in $candidates) {
  $v = Get-PyVersion $c
  if ($v -and $v -ge $MinPy) { $py = $c; $pyVer = $v; break }
  elseif ($v) { Write-Host "  跳过 $($c -join ' ')：Python $v < $MinPy" -ForegroundColor DarkYellow }
}
if (-not $py) {
  throw "找不到 Python $MinPy+。可在仓库根执行 'uv venv --python 3.12 .venv' 并安装依赖，或用 -Python 指定解释器。"
}
$pyExe = $py[0]; $pyPre = @($py | Select-Object -Skip 1)
function Invoke-Py { $ErrorActionPreference = "Continue"; & $pyExe @pyPre @args }
function Invoke-Native { $ErrorActionPreference = "Continue"; $exe, $rest = $args; & $exe @rest }
Write-Host "==> 打包发布版 v$Version (无素材)，解释器: $($py -join ' ') (Python $pyVer)" -ForegroundColor Cyan

# ── 依赖检查 ──
Invoke-Py -c "import PySide6, UnityPy, numpy, PIL" 2>$null
if ($LASTEXITCODE -ne 0) {
  throw "所选解释器缺运行依赖（PySide6 / UnityPy / numpy / Pillow）。先安装: pip install -e . 或 uv pip install --python <解释器> -e ."
}
Invoke-Py -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "安装 PyInstaller ..."
  Invoke-Py -m pip --version 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { Invoke-Py -m pip install "pyinstaller>=6.10" }
  elseif (Get-Command uv -ErrorAction SilentlyContinue) {
    $target = (Invoke-Py -c "import sys; print(sys.executable)").Trim()
    Invoke-Native uv pip install --python $target "pyinstaller>=6.10"
  }
  else { throw "所选解释器没有 pip，也找不到 uv，无法安装 PyInstaller。" }
  if ($LASTEXITCODE -ne 0) { throw "PyInstaller 安装失败" }
}

# ── 可选：行为回归闸 ──
if ($Test) {
  Write-Host "==> 行为检查" -ForegroundColor Cyan
  Invoke-Py "$repo\tests\behavior_check.py" check
  if ($LASTEXITCODE -ne 0) { throw "行为检查与基线不一致，已中止打包（有意改动行为请先 record）。" }
  Invoke-Py "$repo\tools\params_doc.py" --check
  if ($LASTEXITCODE -ne 0) { throw "ai-docs/PARAMS.md 已过期，先运行 tools/params_doc.py 重新生成。" }
}

Remove-Item "$repo\dist\SlugcatPet", "$repo\build" -Recurse -Force -ErrorAction SilentlyContinue

$windowMode = if ($Console) { "--console" } else { "--windowed" }

# exe 版本信息：名称与版本号，音量合成器、任务管理器据此显示
New-Item -ItemType Directory -Force "$repo\build" | Out-Null
$nums = @(($Version -split '[^0-9]+') | Where-Object { $_ -ne "" } | Select-Object -First 4)
while ($nums.Count -lt 4) { $nums += "0" }
$verTuple = ($nums | ForEach-Object { [int]$_ }) -join ", "
$verFile = "$repo\build\version_info.txt"
$verText = @"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($verTuple), prodvers=($verTuple), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'SlugcatPet'),
      StringStruct('FileDescription', 'SlugcatPet'),
      StringStruct('FileVersion', '$Version'),
      StringStruct('InternalName', 'SlugcatPet'),
      StringStruct('OriginalFilename', 'SlugcatPet.exe'),
      StringStruct('ProductName', 'SlugcatPet'),
      StringStruct('ProductVersion', '$Version')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@
[IO.File]::WriteAllText($verFile, $verText, (New-Object System.Text.UTF8Encoding $false))
$pyi = @(
  "--noconfirm", "--clean", $windowMode,
  "--name", "SlugcatPet",
  "--version-file", $verFile,
  "--paths", $repo,
  "--distpath", "$repo\dist",
  "--workpath", "$repo\build",
  "--specpath", "$repo\build",
  "--collect-all", "UnityPy",
  "--collect-all", "archspec",                                  # astc 贴图解码器需其 json 数据
  "--runtime-hook", "$repo\packaging\pyi_rth_stub_fmod.py",     # stub 掉 fmod 音频链（场景曲不解码，见 audio/fsbogg.py）
  # 运行时按 _MEIPASS\slugcatpet\resources 找；只带 characters + layouts + icons，assets 永不入包
  "--add-data", "$repo\slugcatpet\resources\characters;slugcatpet/resources/characters",
  "--add-data", "$repo\slugcatpet\resources\layouts;slugcatpet/resources/layouts",
  "--add-data", "$repo\slugcatpet\resources\icons;slugcatpet/resources/icons",
  "--add-data", "$repo\slugcatpet\audio\LICENSE.python-fsb5;slugcatpet/audio",   # 第三方许可随包
  "--add-data", "$repo\slugcatpet\audio\LICENSE.libvorbis;slugcatpet/audio"
)
# 排除 fmod 音频链（由 stub 顶替）与无关重包
foreach ($m in @("fmod_toolkit","pyfmodex",
                 "pandas","scipy","matplotlib","pyarrow","lxml","sqlalchemy","IPython",
                 "jedi","parso","pygame","tkinter","_tkinter","notebook","zmq",
                 "openpyxl","numba","sympy","bokeh","PyQt5","PyQt6","wx")) {
  $pyi += @("--exclude-module", $m)
}
Invoke-Py -m PyInstaller @pyi "$repo\run_slugcatpet.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败" }

# 安全闸：产物里绝不能出现任何游戏素材
$leak = Get-ChildItem "$repo\dist\SlugcatPet" -Recurse -File |
        Where-Object { $_.Name -in @("rainWorld", "rainWorld.png", "rainworldmsc", "rainworldmsc.png") -or
                       $_.Extension -in @(".ogg", ".mp3", ".wav", ".fsb") }
if ($leak) {
  $leak | ForEach-Object { Write-Host "  泄漏: $($_.FullName)" -ForegroundColor Red }
  throw "产物包含游戏素材，已中止！发布版绝不能携带素材。"
}
Write-Host "==> 安全闸通过：零游戏素材" -ForegroundColor Green

# 安全闸 2：发布版绝不能夹带仓库外的彩蛋包 surprises
$egg = Get-ChildItem "$repo\dist\SlugcatPet" -Recurse -File |
       Where-Object { $_.FullName -match '[\\/]surprises[\\/]' -or $_.Name -eq 'surprises' }
if ($egg) {
  $egg | ForEach-Object { Write-Host "  彩蛋泄漏: $($_.FullName)" -ForegroundColor Red }
  throw "产物包含彩蛋包 surprises，已中止！发布版绝不能携带彩蛋。"
}
Write-Host "==> 安全闸通过：零彩蛋" -ForegroundColor Green

# 一个 zip；UTF8 条目名避免中文文件名乱码
Add-Type -AssemblyName System.IO.Compression.FileSystem
function Compress-WithRetry($src, $dst) {
  Remove-Item $dst -Force -ErrorAction SilentlyContinue
  for ($t = 1; $t -le 5; $t++) {
    try {
      [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $src, $dst, [System.IO.Compression.CompressionLevel]::Optimal, $true,
        [System.Text.Encoding]::UTF8)
      return
    }
    catch { if ($t -eq 5) { throw }; Write-Host "  zip 被占用(多为杀软扫描)，3s 后重试 $t/5 ..."; Start-Sleep -Seconds 3 }
  }
}

$out = "$repo\dist\SlugcatPet"
Copy-Item "$repo\packaging\使用说明.txt" "$out\使用说明.txt" -Force
Copy-Item "$repo\packaging\README.txt" "$out\README.txt" -Force
$zip = "$repo\dist\SlugcatPet-v$Version-win64.zip"
Compress-WithRetry $out $zip

Write-Host "==> 完成: $zip" -ForegroundColor Green
