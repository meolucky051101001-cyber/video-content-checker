@echo off
title Dung Tool AI Video Reviewer
echo Dang dung tien trinh Streamlit dang chay ngam...
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if (-not $c) { Write-Host 'Server hien tai khong chay.' -ForegroundColor Yellow; exit }; $owner = $c.OwningProcess; $proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $owner); $cmd = [string]$proc.CommandLine; if ($cmd -match 'streamlit' -and $cmd -match 'app\.py') { Stop-Process -Id $owner -Force; Write-Host 'Da dung AI Video Reviewer thanh cong!' -ForegroundColor Green } else { Write-Host ('Cong 8501 do process khac (PID ' + $owner + ') chiem, khong kill de tranh nham.') -ForegroundColor Yellow }"
ping 127.0.0.1 -n 2 >nul