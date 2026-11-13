"""Integration checks for the current-directory profile discovery endpoint."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from prophile.server import AppServer


class ServerTests(unittest.TestCase):
    def test_local_profiles_and_static_assets_from_other_directory(self):
        sample = next((Path(__file__).resolve().parents[1] / "sample_profiles").glob("*.alog"))
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / sample.name).write_bytes(sample.read_bytes())
            (directory / "bad.alog").write_text("not a roast")
            (directory / "other.txt").write_text("ignored")
            server = AppServer(("127.0.0.1", 0), directory.resolve())
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with urlopen(base + "/api/local-profiles") as response:
                    data = json.load(response)
                self.assertEqual(data["directory"], str(directory.resolve()))
                self.assertEqual(len(data["profiles"]), 1)
                self.assertEqual(data["profiles"][0]["bean"], "Baarbara Washed AA")
                self.assertEqual(len(data["errors"]), 1)
                with urlopen(base + "/") as response:
                    body = response.read()
                    self.assertIn(b"Beans &amp; batches", body)
                    self.assertIn(b'id="theme-toggle"', body)
                    self.assertIn(b'class="theme-toggle"', body)
                with urlopen(base + "/styles.css") as response:
                    css = response.read().decode("utf-8")
                    self.assertIn('data-theme="dark"', css)
                    self.assertIn("--ink", css)
                    self.assertIn("--paper", css)
                with urlopen(base + "/app.js") as response:
                    js = response.read().decode("utf-8")
                    self.assertIn("themeToggle", js)
                    self.assertIn("setTheme", js)
                with urlopen(base + "/chart.js") as response:
                    chart_js = response.read().decode("utf-8")
                    self.assertIn("isDarkMode", chart_js)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
