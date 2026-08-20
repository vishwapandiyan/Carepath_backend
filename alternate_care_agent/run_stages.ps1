Set-Location "c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent"

python -m pytest tests/test_provider_discovery.py -v --tb=short 2>&1 | Out-File stage2.txt -Encoding utf8
Write-Host "=== STAGE2 DONE ==="
python -m pytest tests/test_appointment_schemas.py -v --tb=short 2>&1 | Out-File stage3.txt -Encoding utf8
Write-Host "=== STAGE3 DONE ==="
python -m pytest tests/test_appointment_flow.py::test_10e_dental_pain_routes_to_dentistry tests/test_appointment_flow.py::test_10f_breathing_copd_routes_to_specialist_pulmonology tests/test_appointment_flow.py::test_availability_specialist_specialty_derived_from_decision -v --tb=short 2>&1 | Out-File stage4.txt -Encoding utf8
Write-Host "=== STAGE4 DONE ==="
python -m pytest tests/test_appointment_flow.py -v --tb=short 2>&1 | Out-File stage5.txt -Encoding utf8
Write-Host "=== STAGE5 DONE ==="
python -m pytest tests/test_appointment_agent.py -v --tb=short 2>&1 | Out-File stage6.txt -Encoding utf8
Write-Host "=== STAGE6 DONE ==="
python -m pytest tests/test_shared_appointment_contract.py -v --tb=short 2>&1 | Out-File stage7.txt -Encoding utf8
Write-Host "=== STAGE7 DONE ==="
python -m pytest tests/ --tb=short 2>&1 | Out-File stage8.txt -Encoding utf8
Write-Host "=== STAGE8 DONE ==="
python -m pytest tests/ --tb=no -p no:warnings -q 2>&1 | Select-String -Pattern "(overpass-api|api.anthropic|generativelanguage\.googleapis|HTTPError|real network|ConnectionError)" | Out-File stage9.txt -Encoding utf8
Write-Host "=== STAGE9 DONE ==="
Write-Host "=== ALL DONE ==="
