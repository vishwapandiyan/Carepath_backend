import subprocess, sys, os

work_dir = r"c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent"
out_file = os.path.join(work_dir, "test_results.txt")

with open(out_file, "w", encoding="utf-8") as f:
    f.write("=== STEP 2: focused tests ===\n")
    r1 = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_location_maps.py", "-v", "--tb=short"],
        cwd=work_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    f.write(r1.stdout)
    f.write(f"\nExit code: {r1.returncode}\n\n")

    f.write("=== STEP 3: full suite ===\n")
    r2 = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--tb=short", "-q"],
        cwd=work_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    f.write(r2.stdout)
    f.write(f"\nExit code: {r2.returncode}\n")

print("Done. Results written to", out_file)
