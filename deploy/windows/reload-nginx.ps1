param([string]$NginxRoot = 'D:/OKR/nginx')
$ErrorActionPreference = 'Stop'
$resolvedRoot = (Resolve-Path -LiteralPath $NginxRoot).Path.Replace('\','/') + '/'
$nginxExe = Join-Path $resolvedRoot 'nginx.exe'
& $nginxExe -p $resolvedRoot -c conf/nginx.conf -t
if ($LASTEXITCODE -ne 0) { throw 'Nginx validation failed. Reload cancelled.' }
& $nginxExe -p $resolvedRoot -c conf/nginx.conf -s reload
if ($LASTEXITCODE -ne 0) { throw 'Nginx reload failed.' }
