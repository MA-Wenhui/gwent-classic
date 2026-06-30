#!/usr/bin/env python3
"""一键运行所有测试，输出同时写入控制台和日志文件"""

import subprocess
import sys
import os

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(TEST_DIR, "test_output.log")
TEST_FILES = [
    "test_card.py",
    "test_board.py",
    "test_engine.py",
]


def main():
    project_root = os.path.abspath(os.path.join(TEST_DIR, "..", ".."))

    with open(LOG_FILE, "w", encoding="utf-8") as log_f:
        header = "=" * 60 + "\n🏰 Gwent Classic Python Engine - Test Suite\n" + "=" * 60 + "\n\n"
        print(header, end="")
        log_f.write(header)

        passed = 0
        failed = 0

        for test_file in TEST_FILES:
            filepath = os.path.join(TEST_DIR, test_file)
            if not os.path.exists(filepath):
                msg = f"⚠️  {test_file} not found, skipping\n\n"
                print(msg, end="")
                log_f.write(msg)
                continue

            env = os.environ.copy()
            env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")
            env["GWENT_LOG_FILE"] = LOG_FILE
            result = subprocess.run(
                [sys.executable, filepath],
                cwd=project_root,
                env=env,
                capture_output=True,
                text=True,
            )

            output = result.stdout + result.stderr
            print(output, end="")
            log_f.write(output)

            if result.returncode == 0:
                passed += 1
            else:
                failed += 1
                msg = f"❌ {test_file} FAILED (exit code {result.returncode})\n\n"
                print(msg, end="")
                log_f.write(msg)

        footer = "\n" + "=" * 60 + "\n"
        total = passed + failed
        if failed == 0:
            summary = f"✅ All {total} test suites passed!\n"
        else:
            summary = f"❌ {failed}/{total} test suites failed\n"
        footer += summary + "=" * 60 + "\n"
        footer += f"\n📄 Full log saved to: {LOG_FILE}\n"

        print(footer, end="")
        log_f.write(footer)

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
