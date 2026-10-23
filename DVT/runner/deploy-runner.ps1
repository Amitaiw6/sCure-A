<#
.SYNOPSIS
  Copy the sCure DVT runner to a CureBox and install it (asks for the machine's sudo password once).

.EXAMPLE
  .\DVT\runner\deploy-runner.ps1 -Target 192.168.2.128 -Machine CureBox-1 -Unit UUT-01

  The portal URL and the DVT key are read from cloud/portal_secrets.local.txt (the "dvt key:" line) unless given.
  The firmware must be sCureBox 1.0.88 or later (it shows the Start / Decline dialog the runner waits for).
#>
param(
  [Parameter(Mandatory)] [string]$Target,
  [string]$Machine = "CureBox-1",
  [string]$Unit = "UUT-01",
  [string]$User = "scure",
  [string]$Key = "$env:USERPROFILE\.ssh\scure_pi",
  [string]$Portal = "https://script.google.com/macros/s/AKfycbyjbhA1FUVmhth0UPpM-UlbuLnh1wf2bpqM8vJn6RszPkfrWceJ6BrgrXLTEILMgNR7/exec",
  [string]$DvtKey = ""
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..\..").Path
if (-not $DvtKey) {
  $line = Select-String -Path "$repo\cloud\portal_secrets.local.txt" -Pattern '^dvt key:\s*(\S+)' | Select-Object -First 1
  if (-not $line) { throw "no -DvtKey and no 'dvt key:' line in cloud/portal_secrets.local.txt" }
  $DvtKey = $line.Matches[0].Groups[1].Value
}
$stage = Join-Path $env:TEMP "scure-dvt-runner"
Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$stage\runner", "$stage\web" | Out-Null
Copy-Item "$repo\DVT\runner\dvt-runner.cjs", "$repo\DVT\runner\install-runner.sh" "$stage\runner\"
Copy-Item "$repo\DVT\web\dvt-tool.html", "$repo\DVT\web\dvt-catalog.js", "$repo\DVT\web\dvt-criteria.js", "$repo\DVT\web\dvt-auto.js" "$stage\web\"
Copy-Item "$repo\VERSION" "$stage\"
Move-Item "$stage\runner\install-runner.sh" "$stage\install-runner.sh"
# Windows tools write CRLF; bash needs LF
(Get-Content "$stage\install-runner.sh" -Raw).Replace("`r`n", "`n") | Set-Content -NoNewline -Encoding ascii "$stage\install-runner.sh"
$tar = Join-Path $env:TEMP "scure-dvt-runner.tgz"
tar -czf $tar -C $stage .
Write-Host "== copy to $User@$Target"
scp -i $Key -o ConnectTimeout=10 $tar "${User}@${Target}:/tmp/scure-dvt-runner.tgz"
Write-Host "== install (the machine asks for its sudo password)"
ssh -t -i $Key "$User@$Target" "rm -rf /tmp/scure-dvt-runner && mkdir -p /tmp/scure-dvt-runner && tar -xzf /tmp/scure-dvt-runner.tgz -C /tmp/scure-dvt-runner && chmod +x /tmp/scure-dvt-runner/install-runner.sh && sudo /tmp/scure-dvt-runner/install-runner.sh --portal '$Portal' --key '$DvtKey' --machine '$Machine' --unit '$Unit' --user '$User'"
