from pathlib import Path
import re
import subprocess
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ram.sh"
AWK = re.search(r'/usr/bin/awk -v total="\$total" \'(.*?)\'\n', SCRIPT.read_text(), re.S).group(1)


def render(page_size, total_pages, free=0, speculative=0, cached=0, purgeable=0):
    stats = (f"Mach Virtual Memory Statistics: (page size of {page_size} bytes)\n"
             f"Pages free: {free}.\nPages speculative: {speculative}.\n"
             f"File-backed pages: {cached}.\nPages purgeable: {purgeable}.\n")
    result = subprocess.run(["/usr/bin/awk", "-v", f"total={total_pages * page_size}", AWK],
                            input=stats, capture_output=True, text=True, check=True)
    return result.stdout.strip()


class RamDisplayTests(unittest.TestCase):
    def test_file_cache_is_available_for_other_apps(self):
        self.assertEqual(render(16384, 1000, free=100, cached=200, purgeable=50), "RAM 65%")

    def test_speculative_pages_are_already_counted_as_file_backed(self):
        self.assertEqual(render(16384, 1000, free=100, speculative=50,
                                cached=200, purgeable=50), "RAM 65%")

    def test_kernel_and_app_memory_remain_used(self):
        self.assertEqual(render(16384, 1000, free=100), "RAM 90%")

    def test_page_size_does_not_change_the_percentage(self):
        self.assertEqual(render(4096, 1000, cached=300), "RAM 70%")
        self.assertEqual(render(16384, 1000, cached=300), "RAM 70%")


if __name__ == "__main__":
    unittest.main()
