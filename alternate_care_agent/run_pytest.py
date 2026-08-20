import subprocess
import sys
import os

work_dir = r"c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent"

print("=== STEP 2: focused tests ===")
result1 = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_location_maps.py", "-v", "--tb=short"],
    cwd=work_dir,
    capture_output=True,
    text=True
)
print(result1.stdout)
if result1.stderr:
    print("STDERR:", result1.stderr)
print("Exit code:", result1.returncode)

print("\n=== STEP 3: full suite ===")
result2 = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "--tb=short", "-q"],
    cwd=work_dir,
    capture_output=True,
    text=True
)
print(result2.stdout)
if result2.stderr:
    print("STDERR:", result2.stderr)
print("Exit code:", result2.returncode)
