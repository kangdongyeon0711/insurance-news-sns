<#
.SYNOPSIS
    로그온 시 insurance-news-sns 웹 조회 페이지를 자동으로 실행하는
    Windows 작업 스케줄러(Task Scheduler) 작업을 등록한다.

.DESCRIPTION
    - 트리거: 로그온 시(AtLogOn) — 컴퓨터를 켜고 로그인하면 자동 시작된다.
    - 실행 내용: scripts\serve_web_waitress.py를 waitress(프로덕션 WSGI 서버)로 실행한다.
    - 기본적으로 pythonw(콘솔 창 없음)를 사용한다. 문제를 디버깅하려면
      -PythonExe python 옵션으로 콘솔 창이 보이게 등록할 수 있다.
    - 로그는 콘솔이 없어도 data\web_server.log 파일에 남는다.
    - 작업이 죽으면 1분 간격으로 최대 3회 자동 재시작한다.

.사용법
    이 저장소 루트에서 PowerShell을 열고:

        powershell -ExecutionPolicy Bypass -File scripts\windows\register_web_task.ps1

    관리자 권한은 보통 필요 없다(현재 로그인한 사용자 계정으로 등록됨).
    권한 오류가 나면 "관리자 권한으로 PowerShell 실행" 후 다시 시도한다.

    디버깅용으로 콘솔 창을 보이게 등록하려면:

        powershell -ExecutionPolicy Bypass -File scripts\windows\register_web_task.ps1 -PythonExe python
#>

param(
    [string]$TaskName = "InsuranceNewsWebViewer",
    [string]$PythonExe = "pythonw"
)

$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
$ScriptPath = Join-Path $RepoRoot "scripts\serve_web_waitress.py"

if (-not (Test-Path $ScriptPath)) {
    Write-Error "스크립트를 찾을 수 없습니다: $ScriptPath`n이 저장소 루트에서 실행했는지 확인하세요."
    exit 1
}

$PythonCmd = Get-Command $PythonExe -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    Write-Error "'$PythonExe' 실행 파일을 찾을 수 없습니다. Python이 설치되어 있고 PATH에 등록되어 있는지 확인하세요."
    exit 1
}

$Action = New-ScheduledTaskAction `
    -Execute $PythonCmd.Source `
    -Argument "`"$ScriptPath`"" `
    -WorkingDirectory $RepoRoot

$Trigger = New-ScheduledTaskTrigger -AtLogOn

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "insurance-news-sns 웹 조회 페이지를 로그온 시 자동 실행" `
    -Force | Out-Null

Write-Host "작업 스케줄러에 '$TaskName' 작업이 등록되었습니다."
Write-Host "다음 로그온부터 자동 실행됩니다."
Write-Host ""
Write-Host "지금 바로 실행해서 확인:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "상태 확인:               Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
Write-Host "로그 확인:               Get-Content '$RepoRoot\data\web_server.log' -Tail 20"
Write-Host "제거:                    scripts\windows\unregister_web_task.ps1"
