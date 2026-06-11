$session = Join-Path $PSScriptRoot "brainstorm\dashboard-design"
$content = Join-Path $session "content"
$state = Join-Path $session "state"

New-Item -ItemType Directory -Force -Path $content, $state | Out-Null

$env:BRAINSTORM_DIR = $session
$env:BRAINSTORM_HOST = "127.0.0.1"
$env:BRAINSTORM_URL_HOST = "localhost"
Remove-Item Env:BRAINSTORM_OWNER_PID -ErrorAction SilentlyContinue

$server = "C:\Users\anant\.codex\plugins\cache\openai-curated\superpowers\c6ea566d\skills\brainstorming\scripts\server.cjs"
$stdout = Join-Path $state "server.log"
$stderr = Join-Path $state "server.err"
$info = Join-Path $state "server-info"
$stopped = Join-Path $state "server-stopped"

Remove-Item $info, $stopped, $stdout, $stderr -Force -ErrorAction SilentlyContinue

$process = Start-Process `
    -FilePath "C:\Program Files\nodejs\node.exe" `
    -ArgumentList $server `
    -WorkingDirectory (Split-Path $server) `
    -WindowStyle Hidden `
    -PassThru `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr

for ($attempt = 0; $attempt -lt 50; $attempt++) {
    if (Test-Path $info) {
        Write-Output "PID=$($process.Id)"
        Get-Content $info
        exit 0
    }
    Start-Sleep -Milliseconds 100
}

Write-Error "Visual companion server failed to start."
if (Test-Path $stderr) {
    Get-Content $stderr
}
exit 1
