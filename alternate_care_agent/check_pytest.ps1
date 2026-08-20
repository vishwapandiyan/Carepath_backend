Set-Location "c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent"
Write-Host "Python version:"
python --version
Write-Host "Pytest version:"
python -m pytest --version
Write-Host "Pytest collect only:"
python -m pytest tests/test_location_maps.py --collect-only 2>&1
Write-Host "Done"
