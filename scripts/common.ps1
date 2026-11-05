Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw '此启动器仅支持 Windows。其他系统请使用手动启动文档。' }
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { } # Hidden owner has no console.
$script:Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$script:Runtime = Join-Path $script:Root '.runtime\launcher'
$script:StateFile = Join-Path $script:Runtime 'state.json'
foreach ($relative in @('.runtime', '.runtime\launcher', '.cache', '.cache\launcher')) {
  $folder = Join-Path $script:Root $relative
  if ((Test-Path -LiteralPath $folder) -and ((Get-Item -LiteralPath $folder).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw '运行/缓存目录不能是链接，请人工核对。' }
  [IO.Directory]::CreateDirectory($folder) | Out-Null
}
[IO.Directory]::CreateDirectory($script:Runtime) | Out-Null
$env:TEMP = Join-Path $script:Root '.cache\launcher'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $script:Root '.cache\pip'
$env:npm_config_cache = Join-Path $script:Root '.cache\npm'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
if (-not ('RiichiLauncher.ProcessJob' -as [type])) { Add-Type -Path (Join-Path $PSScriptRoot 'LauncherProcess.cs') }

function Enter-LauncherLock {
  $hash = [Security.Cryptography.SHA256]::Create()
  try { $key = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($script:Root.ToLowerInvariant()))).Replace('-', '') } finally { $hash.Dispose() }
  $mutex = New-Object Threading.Mutex($false, "Local\Riichi-$key")
  try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
  if (-not $locked) { $mutex.Dispose(); throw '已有启动或停止操作进行中，请稍后重试；不会创建重复服务。' }
  return $mutex
}
function Get-FileFingerprint([string]$Path) {
  $stream = [IO.File]::OpenRead($Path)
  $algorithm = [Security.Cryptography.SHA256]::Create()
  try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '') }
  finally { $stream.Dispose(); $algorithm.Dispose() }
}
function Write-State($State) {
  $temporary = Join-Path $script:Runtime ("state-$([guid]::NewGuid().ToString('N')).tmp")
  [IO.File]::WriteAllText($temporary, ($State | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding($false)))
  if (Test-Path -LiteralPath $script:StateFile) { [IO.File]::Replace($temporary, $script:StateFile, [NullString]::Value) }
  else { [IO.File]::Move($temporary, $script:StateFile) }
}
function Read-State {
  if (-not (Test-Path -LiteralPath $script:StateFile)) { return $null }
  # Readers allow atomic replacement; Get-Content's sharing mode can otherwise
  # race the worker's phase updates on Windows PowerShell 5.1.
  $stream = [IO.File]::Open($script:StateFile, [IO.FileMode]::Open, [IO.FileAccess]::Read, ([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
  $reader = New-Object IO.StreamReader($stream, [Text.Encoding]::UTF8, $true)
  try { $state = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
  if ($state.root -ne $script:Root -or $state.runId -notmatch '^[a-f0-9]{32}$') { throw '启动状态不属于当前目录或格式损坏，已拒绝管理进程，请人工核对 .runtime/launcher。' }
  return $state
}
function Test-Owner($State) {
  $identity = [RiichiLauncher.ProcessJob]::Snapshot([int]$State.owner.ProcessId)
  if ($null -eq $identity) { return $false }
  if ($identity.CreationTime -ne $State.owner.CreationTime -or $identity.ImagePath -ne $State.owner.ImagePath) { throw 'PID 已复用或进程身份不符，拒绝终止无关进程；请人工核对状态文件。' }
  $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($identity.ProcessId)"
  if ($null -eq $process -or [string]::IsNullOrEmpty($process.CommandLine)) {
    # A normal exit can occur between the kernel snapshot and CIM query. Only
    # accept that case after another kernel check, never on missing CIM alone.
    if ($null -eq [RiichiLauncher.ProcessJob]::Snapshot([int]$State.owner.ProcessId)) { return $false }
    throw '无法确认进程命令行，拒绝终止；请人工核对状态。'
  }
  $worker = Join-Path $script:Root 'scripts\run.ps1'
  if ($process.CommandLine.IndexOf($worker, [StringComparison]::OrdinalIgnoreCase) -lt 0 -or $process.CommandLine.IndexOf($State.runId, [StringComparison]::Ordinal) -lt 0) { throw '进程命令行不属于本次 Riichi 启动，拒绝终止。' }
  return $true
}
function Stop-Owned($State) {
  if (Test-Owner $State) { [RiichiLauncher.ProcessJob]::StopVerified([int]$State.owner.ProcessId, $State.owner.CreationTime, $State.owner.ImagePath) }
}
function Test-PortFree([int]$Port) {
  $listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $Port)
  try { $listener.Start() } catch { throw "端口 $Port 已被占用，未终止占用者。请先核对服务或端口。" } finally { $listener.Stop() }
}
function Test-Http([string]$Url, [switch]$Health) {
  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
    if ($response.StatusCode -ne 200) { return $false }
    if ($Health) { $body = $response.Content | ConvertFrom-Json; return ($body.status -eq 'ok' -and $body.service -eq 'riichi-api') }
    return $response.Content.Contains('<div id="root">')
  } catch { return $false }
}
function Open-RiichiBrowser {
  try { Start-Process 'http://127.0.0.1:5173' -WindowStyle Normal }
  catch { Write-Host '服务已就绪，但无法调用默认浏览器。请手动打开 http://127.0.0.1:5173。' -ForegroundColor Yellow }
}
