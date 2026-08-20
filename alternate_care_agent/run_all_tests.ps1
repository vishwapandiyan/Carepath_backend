Set-Location "c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent"

Write-Host "=== STEP 2: focused tests ==="
python -m pytest tests/test_location_maps.py -v --tb=short

Write-Host ""
Write-Host "=== STEP 3: full suite ==="
python -m pytest tests/ --tb=short -q
