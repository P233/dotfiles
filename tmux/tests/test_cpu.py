from pathlib import Path
import re
import subprocess
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/cpu.sh"
AWK = re.search(r'/usr/bin/awk -v cores="\$cores" \'(.*?)\'\n', SCRIPT.read_text(), re.S).group(1)


def render(cores, *shares):
    result = subprocess.run(["/usr/bin/awk", "-v", f"cores={cores}", AWK],
                            input="".join(f" {share}\n" for share in shares),
                            capture_output=True, text=True, check=True)
    return result.stdout.strip()


class CpuDisplayTests(unittest.TestCase):
    def test_fractional_process_shares_are_averaged_across_cores(self):
        self.assertEqual(render(4, "50.0", "30.5", "19.5"), "CPU 25%")
        self.assertEqual(render(1, *["0.6"] * 5), "CPU 3%")

    def test_live_output_is_one_percentage(self):
        result = subprocess.run(["sh", str(SCRIPT)], capture_output=True, text=True, check=True)
        self.assertRegex(result.stdout, r"\ACPU \d+%\n\Z")


if __name__ == "__main__":
    unittest.main()
