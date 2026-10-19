"""Run pytest in a stripped environment and count results (no keys ever reach tests)."""
import os
import pathlib
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent
VENV_BIN = ROOT / ".venv-tests" / "bin"


def clean_env(extra=None):
    env = {
        "PATH": f"{VENV_BIN}:/usr/local/bin:/usr/bin:/bin",
        "HOME": os.environ.get("SCORING_HOME", "/tmp"),
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
    }
    env.update(extra or {})
    return env


def run_pytest(ws: pathlib.Path, tests_dir: pathlib.Path, timeout_per_test=60, copy_in=False, total_timeout=900):
    """Run tests_dir against ws. If copy_in, tests are copied to ws/tests_hidden first."""
    ws = pathlib.Path(ws)
    target = tests_dir
    if copy_in:
        target = ws / "tests_hidden"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(tests_dir, target)
    junit = ws / ".junit.xml"
    if junit.exists():
        junit.unlink()
    cmd = [str(VENV_BIN / "python"), "-m", "pytest", "-q", "-p", "no:cacheprovider",
           f"--timeout={timeout_per_test}", f"--junitxml={junit}", str(target)]
    t = time.time()
    try:
        p = subprocess.run(cmd, cwd=ws, env=clean_env(), capture_output=True, text=True, timeout=total_timeout)
        out, code = p.stdout + p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        out, code = f"TOTAL TIMEOUT after {total_timeout}s", -9
    secs = time.time() - t
    passed = total = 0
    if junit.exists():
        try:
            root = ET.parse(junit).getroot()
            suites = [root] if root.tag == "testsuite" else list(root)
            for s in suites:
                n = int(s.get("tests", 0))
                bad = int(s.get("failures", 0)) + int(s.get("errors", 0)) + int(s.get("skipped", 0))
                total += n
                passed += n - bad
        except ET.ParseError:
            pass
        junit.unlink()
    if copy_in and target.exists():
        shutil.rmtree(target)
    return {"passed": passed, "total": total, "exit": code, "seconds": secs, "tail": out[-1500:]}
