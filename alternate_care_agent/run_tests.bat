@echo off
cd /d "c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent"
python -m pytest tests/test_location_maps.py -v --tb=short > pytest_out1.txt 2>&1
python -m pytest tests/ --tb=short -q > pytest_out2.txt 2>&1
echo ALL DONE
