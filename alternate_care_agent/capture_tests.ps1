Set-Location "c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent"
$outfile = "c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent\test_results.txt"

"=== STEP 2: focused tests ===" | Out-File -FilePath $outfile -Encoding utf8

$proc1 = Start-Process -FilePath "python" `
    -ArgumentList "-m", "pytest", "tests/test_location_maps.py", "-v", "--tb=short" `
    -WorkingDirectory "c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent" `
    -RedirectStandardOutput "c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent\step2_stdout.txt" `
    -RedirectStandardError  "c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent\step2_stderr.txt" `
    -Wait -PassThru -NoNewWindow

"Exit code: $($proc1.ExitCode)" | Out-File -FilePath $outfile -Encoding utf8 -Append
Get-Content "c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent\step2_stdout.txt" | Out-File -FilePath $outfile -Encoding utf8 -Append
Get-Content "c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent\step2_stderr.txt" | Out-File -FilePath $outfile -Encoding utf8 -Append

"`n=== STEP 3: full suite ===" | Out-File -FilePath $outfile -Encoding utf8 -Append

$proc2 = Start-Process -FilePath "python" `
    -ArgumentList "-m", "pytest", "tests/", "--tb=short", "-q" `
    -WorkingDirectory "c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent" `
    -RedirectStandardOutput "c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent\step3_stdout.txt" `
    -RedirectStandardError  "c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent\step3_stderr.txt" `
    -Wait -PassThru -NoNewWindow

"Exit code: $($proc2.ExitCode)" | Out-File -FilePath $outfile -Encoding utf8 -Append
Get-Content "c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent\step3_stdout.txt" | Out-File -FilePath $outfile -Encoding utf8 -Append
Get-Content "c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent\step3_stderr.txt" | Out-File -FilePath $outfile -Encoding utf8 -Append

Write-Host "All done. Results in $outfile"
Get-Content $outfile
