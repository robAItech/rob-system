import os
import sys
import time
import re
import subprocess
from pathlib import Path
import argparse
from dotenv import load_dotenv

load_dotenv()
from bridges.llm_bridge import LLMBridge

def run_cmd(cmd, cwd=None, timeout=30):
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd, env=env, timeout=timeout)
        return res.returncode, res.stdout, res.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"TIMEOUT: Command exceeded {timeout} seconds"

def extract_code_blocks(text):
    files = {}
    pattern = r"### FILE:\s*([^\n]+)\n" + chr(96)*3 + r"(?:python)?\n(.*?)" + chr(96)*3
    matches = re.findall(pattern, text, re.DOTALL)
    for filepath, content in matches:
        files[filepath.strip()] = content.strip()
    return files

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--directive", required=True)
    args = parser.parse_args()

    target = args.target.strip()
    directive = args.directive.strip()
    target_dir = Path("actions") / target

    print("=" * 80)
    print("ROB AI STUDIO | AUTONOMOUS SWARM EXECUTION ENGINE".center(80))
    print("=" * 80)
    print(f"TARGET MODULE : {target}")
    print("AGENT         : GSTACK-Architect")
    print(f"DIRECTIVE     : {directive}")
    print("=" * 80)

    start_time = time.time()
    llm = LLMBridge()

    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "__init__.py").touch()

    system_prompt = f"You are GSTACK-Architect. Generate module {target} inside actions/{target}.\n"
    system_prompt += "You MUST generate ALL these files:\n"
    system_prompt += f"1. ### FILE: actions/{target}/__init__.py\n"
    system_prompt += f"2. ### FILE: actions/{target}/schemas.py\n"
    system_prompt += f"3. ### FILE: actions/{target}/{target}.py\n"
    system_prompt += f"4. ### FILE: actions/{target}/main.py\n"
    system_prompt += f"5. ### FILE: actions/{target}/test_{target}.py\n\n"
    system_prompt += "Rules:\n"
    system_prompt += f"- All imports must use full path: from actions.{target}.schemas import ...\n"
    system_prompt += "- main.py must define app = FastAPI().\n"
    system_prompt += f"- test_{target}.py must contain working pytest tests and import from actions.{target}.main import app.\n"
    system_prompt += "- Output format for ALL files:\n"
    system_prompt += f"### FILE: actions/{target}/filename.py\n" + chr(96)*3 + "python\ncode\n" + chr(96)*3 + "\n"

    prompt = f"Directive for module {target}: {directive}"
    max_retries = 3
    success = False

    for attempt in range(1, max_retries + 1):
        print(f"\n[Attempt {attempt}/{max_retries}] Calling DeepSeek LLM (timeout 45s)...")
        try:
            response = llm.complete(prompt, system_prompt=system_prompt)
            files = extract_code_blocks(response)

            if not files:
                print("Invalid file format from LLM response. Retrying...")
                prompt += "\n\nERROR: You MUST use the format ### FILE: actions/..."
                continue

            for filepath, content in files.items():
                p = Path(filepath)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
                print(f"  Saved: {filepath}")

            print(f"Running Pytest verification for actions/{target} (timeout 30s)...")
            code, out, err = run_cmd(f"pytest -v actions/{target}", timeout=30)

            if code == 0:
                print(f"\nPASSED: Module actions/{target} passed all tests!")
                success = True
                break
            else:
                print(f"PYTEST FAILURE (Exit Code {code}):")
                if out: print(f"--- STDOUT ---\n{out[:1000]}")
                if err: print(f"--- STDERR ---\n{err[:1000]}")
                prompt += f"\n\nFix these Pytest errors and return the complete code again:\n{out}\n{err}"

        except Exception as e:
            print(f"EXECUTION ERROR: {e}")
            prompt += f"\n\nSystem error: {e}"

    elapsed = round(time.time() - start_time, 2)
    print("=" * 80)
    if success:
        print(f"100% VERIFIED GREEN & SHIPPED ({elapsed}s)".center(80))
        print("=" * 80)
        sys.exit(0)
    else:
        print(f"EXECUTION FAILED ({elapsed}s)".center(80))
        print("=" * 80)
        sys.exit(1)

if __name__ == "__main__":
    main()