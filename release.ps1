#Requires -Version 5.1
<#
.SYNOPSIS
  发布 infowe_blog 新版本：校验版本一致性 → 重建压缩样式 → 打标签 → 推送 GitHub/Gitee → 创建 Releases。

.DESCRIPTION
  版本号以 config.py 的 VERSION 为准，发布说明自动取 README.md 里对应的「### vX.Y.Z」小节。
  执行前请先提交所有改动（脚本会先重建 theme.min.css，若产生变更会拒绝继续）。

  发布流程约定：
    1. 修改代码；
    2. 更新 README.md 顶部徽标、当前版本、更新日志（历史版本放进 <details>）；
    3. 提交；
    4. 运行本脚本。

.PARAMETER DryRun
  只做校验并打印将要执行的命令，不建标签、不推送、不创建 Release。

.PARAMETER SkipGitee
  跳过 Gitee 推送与 Release（只发 GitHub）。

.PARAMETER NoPush
  只创建本地标签，不推送、不建 Release。

.PARAMETER GithubRemote
  GitHub 远端名，默认 origin。

.PARAMETER GiteeRemote
  Gitee 远端名，默认 gitee。

.EXAMPLE
  .\release.ps1 -DryRun

.EXAMPLE
  .\release.ps1

.EXAMPLE
  .\release.ps1 -SkipGitee
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$SkipGitee,
    [switch]$NoPush,
    [string]$GithubRemote = "origin",
    [string]$GiteeRemote = "gitee"
)

$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $PSScriptRoot

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}
function Write-Ok([string]$Message) {
    Write-Host "    OK  $Message" -ForegroundColor Green
}
function Write-Warn([string]$Message) {
    Write-Host "    !!  $Message" -ForegroundColor Yellow
}
function Stop-Release([string]$Message) {
    Write-Host ""
    Write-Host "发布中止：$Message" -ForegroundColor Red
    exit 1
}
function Invoke-Git {
    param([string[]]$Arguments)
    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        Stop-Release ("git {0} 执行失败（退出码 {1}）" -f ($Arguments -join " "), $LASTEXITCODE)
    }
}
function Get-RemoteSlug([string]$Remote) {
    $url = (& git remote get-url $Remote 2>$null)
    if (-not $url) { return $null }
    if ($url -match "[/:](?<owner>[^/:]+)/(?<repo>[^/]+?)(?:\.git)?/?$") {
        return @{ Owner = $Matches["owner"]; Repo = $Matches["repo"] }
    }
    return $null
}
function Test-RemoteTag([string]$Remote, [string]$Tag) {
    # 走 cmd 拿纯文本结果：PowerShell 5.1 会把 git 的 stderr 当作 ErrorRecord，
    # 网络抖动时干扰流程判断
    $output = & cmd /c "git ls-remote --tags $Remote refs/tags/$Tag 2>nul"
    return [bool]($output -and ($output | Out-String).Trim())
}

# ── 1. 读取并校验版本号 ──
Write-Step "读取版本号"
$configPath = Join-Path $PSScriptRoot "config.py"
$readmePath = Join-Path $PSScriptRoot "README.md"
if (-not (Test-Path $configPath)) { Stop-Release "找不到 config.py" }
if (-not (Test-Path $readmePath)) { Stop-Release "找不到 README.md" }

$configText = [System.IO.File]::ReadAllText($configPath, [System.Text.Encoding]::UTF8)
$versionMatch = [regex]::Match($configText, '(?m)^VERSION\s*=\s*"([^"]+)"')
if (-not $versionMatch.Success) { Stop-Release "config.py 里没有找到 VERSION" }
$version = $versionMatch.Groups[1].Value
$tag = "v$version"
Write-Ok "当前版本 $tag"

$readmeText = [System.IO.File]::ReadAllText($readmePath, [System.Text.Encoding]::UTF8)
if ($readmeText -notmatch [regex]::Escape("version-$version-blue")) {
    Stop-Release "README.md 顶部徽标不是 version-$version-blue，请先更新徽标"
}
if ($readmeText -notmatch [regex]::Escape("releases/tag/$tag")) {
    Stop-Release "README.md 徽标链接没有指向 releases/tag/$tag"
}
if ($readmeText -notmatch [regex]::Escape("当前版本：**$tag**")) {
    Stop-Release "README.md 的「当前版本」不是 $tag"
}
if ($readmeText -notmatch ("(?m)^###\s+v" + [regex]::Escape($version) + "\s*$")) {
    Stop-Release "README.md 更新日志缺少「### v$version」小节"
}

$sectionMatch = [regex]::Match(
    $readmeText,
    ("(?ms)^###\s+v" + [regex]::Escape($version) + "\s*\r?\n(?<body>.*?)(?=^###\s|^<details>|\z)")
)
$notes = if ($sectionMatch.Success) { $sectionMatch.Groups["body"].Value.Trim() } else { "" }
if (-not $notes) { Stop-Release "无法从 README.md 提取 $version 的发布说明" }

$detailsIndex = $readmeText.IndexOf("<details>")
$sectionIndex = $readmeText.IndexOf("### v$version")
if ($detailsIndex -ge 0 -and $sectionIndex -gt $detailsIndex) {
    Stop-Release "「### $version」必须放在 <details> 历史折叠区之前"
}
Write-Ok "README 徽标 / 当前版本 / 更新日志均已对齐"

# ── 2. 分支与标签检查 ──
Write-Step "检查分支与标签"
$branch = (& git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne "main") { Stop-Release "当前分支是 $branch，发版请在 main 上执行" }
Write-Ok "当前分支 main"

$existingTag = & git rev-parse -q --verify "refs/tags/$tag" 2>$null
if ($existingTag) { Stop-Release "本地已存在标签 $tag，请先删除或换版本号" }
if (Test-RemoteTag $GithubRemote $tag) { Stop-Release "$GithubRemote 已存在标签 $tag" }
if (-not $SkipGitee -and (Test-RemoteTag $GiteeRemote $tag)) {
    Stop-Release "$GiteeRemote 已存在标签 $tag"
}
Write-Ok "标签 $tag 未被占用"

# ── 3. 重建压缩样式 ──
if (-not $DryRun) {
    Write-Step "重建 theme.min.css"
    $python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) { $python = "python" }
    $buildCode = @'
import sys
sys.path.insert(0, ".")
from app import create_app
from services import theme
app = create_app()
with app.app_context():
    print(theme.css_name())
'@
    # 直接 python -c 传多行代码会被 PowerShell 吃掉内层引号，落到临时文件最稳
    $buildFile = Join-Path ([System.IO.Path]::GetTempPath()) "infowe-build-theme-$PID.py"
    [System.IO.File]::WriteAllText($buildFile, $buildCode, (New-Object System.Text.UTF8Encoding($false)))
    try {
        & $python $buildFile
        $buildExit = $LASTEXITCODE
    } finally {
        Remove-Item -LiteralPath $buildFile -ErrorAction SilentlyContinue
    }
    if ($buildExit -ne 0) { Stop-Release "重建 theme.min.css 失败" }
    Write-Ok "theme.min.css 已是最新"
}

# ── 4. 工作区必须干净 ──
Write-Step "检查工作区"
# 只看已跟踪文件：临时 demo、日志等未跟踪文件不应阻断发版
$dirty = @(& git status --porcelain --untracked-files=no)
if ($dirty.Count -gt 0) {
    Write-Host ($dirty -join [Environment]::NewLine)
    if ($DryRun) {
        Write-Warn "工作区有未提交改动（DryRun 仅提示，不阻断）"
    } else {
        Stop-Release "工作区有未提交改动，请先 git add / git commit 后再发版"
    }
} else {
    Write-Ok "工作区干净"
}

# ── 5. DryRun 预览 ──
if ($DryRun) {
    Write-Step "DryRun 预览"
    Write-Host "  git tag -a $tag -m `"$tag`""
    if (-not $NoPush) {
        Write-Host "  git push $GithubRemote $branch"
        Write-Host "  git push $GithubRemote $tag"
        if (-not $SkipGitee) {
            Write-Host "  git push $GiteeRemote $branch"
            Write-Host "  git push $GiteeRemote $tag"
        }
        Write-Host "  gh release create $tag --title $tag --notes-file <README 提取的发布说明>"
        if (-not $SkipGitee) {
            Write-Host "  POST https://gitee.com/api/v5/repos/<owner>/<repo>/releases"
        }
    }
    Write-Ok "预览结束，未做任何改动"
    exit 0
}

# ── 6. 打标签 ──
Write-Step "创建标签 $tag"
Invoke-Git -Arguments @("tag", "-a", $tag, "-m", $tag)
Write-Ok "已创建本地标签 $tag"

if ($NoPush) {
    Write-Warn "已指定 -NoPush：标签只留在本地"
    Write-Host "  推送：git push $GithubRemote $tag"
    exit 0
}

# ── 7. 推送代码与标签 ──
Write-Step "推送到 $GithubRemote"
Invoke-Git -Arguments @("push", $GithubRemote, $branch)
Invoke-Git -Arguments @("push", $GithubRemote, $tag)
Write-Ok "GitHub 代码与标签已推送"

if (-not $SkipGitee) {
    Write-Step "推送到 $GiteeRemote"
    Invoke-Git -Arguments @("push", $GiteeRemote, $branch)
    Invoke-Git -Arguments @("push", $GiteeRemote, $tag)
    Write-Ok "Gitee 代码与标签已推送"
}

# ── 8. GitHub Release ──
Write-Step "创建 GitHub Release"
$notesFile = Join-Path ([System.IO.Path]::GetTempPath()) "infowe-release-$version.md"
[System.IO.File]::WriteAllText($notesFile, "$notes`n", (New-Object System.Text.UTF8Encoding($false)))

& gh release view $tag *> $null
if ($LASTEXITCODE -eq 0) {
    & gh release edit $tag --title $tag --notes-file $notesFile
    if ($LASTEXITCODE -ne 0) { Stop-Release "更新 GitHub Release 失败" }
    Write-Ok "GitHub Release 已更新"
} else {
    & gh release create $tag --title $tag --notes-file $notesFile --verify-tag
    if ($LASTEXITCODE -ne 0) { Stop-Release "创建 GitHub Release 失败" }
    Write-Ok "GitHub Release 已创建"
}

$githubSlug = Get-RemoteSlug $GithubRemote
$githubUrl = if ($githubSlug) { "https://github.com/$($githubSlug.Owner)/$($githubSlug.Repo)/releases/tag/$tag" } else { "" }

# ── 9. Gitee Release ──
$giteeUrl = ""
if (-not $SkipGitee) {
    Write-Step "创建 Gitee Release"
    $giteeSlug = Get-RemoteSlug $GiteeRemote
    if (-not $giteeSlug) {
        Write-Warn "无法从远端 $GiteeRemote 解析 owner/repo，跳过 Gitee Release"
    } elseif (-not $env:GITEE_TOKEN) {
        Write-Warn "未设置环境变量 GITEE_TOKEN，跳过 Gitee Release"
        Write-Host "  设置后可手动补建，或删除本地标签后重跑：`$env:GITEE_TOKEN='<token>'; .\release.ps1"
    } else {
        $api = "https://gitee.com/api/v5/repos/$($giteeSlug.Owner)/$($giteeSlug.Repo)/releases"
        $token = $env:GITEE_TOKEN
        $headers = @{ "Content-Type" = "application/json; charset=utf-8" }
        $payload = @{
            access_token     = $token
            tag_name         = $tag
            target_commitish = $branch
            name             = $tag
            body             = $notes
            prerelease       = $false
        }
        $json = $payload | ConvertTo-Json -Depth 5
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)

        try {
            $existing = Invoke-RestMethod -Method Get -Uri "$api/tags/$tag`?access_token=$token" -ErrorAction Stop
        } catch {
            $existing = $null
        }

        try {
            if ($existing -and $existing.id) {
                $null = Invoke-RestMethod -Method Patch -Uri "$api/$($existing.id)" -Headers $headers -Body $bytes -ErrorAction Stop
                Write-Ok "Gitee Release 已更新"
            } else {
                $null = Invoke-RestMethod -Method Post -Uri $api -Headers $headers -Body $bytes -ErrorAction Stop
                Write-Ok "Gitee Release 已创建"
            }
            $giteeUrl = "https://gitee.com/$($giteeSlug.Owner)/$($giteeSlug.Repo)/releases/tag/$tag"
        } catch {
            Write-Warn "Gitee Release 创建失败：$($_.Exception.Message)"
            Write-Host "  标签已推送，可到 https://gitee.com/$($giteeSlug.Owner)/$($giteeSlug.Repo)/releases 手动创建"
        }
    }
}

# ── 10. 汇总 ──
Write-Step "发版完成 $tag"
if ($githubUrl) { Write-Host "  GitHub: $githubUrl" }
if ($giteeUrl)  { Write-Host "  Gitee : $giteeUrl" }
Write-Host ""
