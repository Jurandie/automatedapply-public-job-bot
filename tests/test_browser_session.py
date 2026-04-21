import unittest

from app.browser.session import find_google_chrome


class BrowserSessionTest(unittest.TestCase):
    def test_find_google_chrome_returns_path_or_none(self):
        chrome = find_google_chrome()
        self.assertTrue(chrome is None or chrome.name.lower() == "chrome.exe")


if __name__ == "__main__":
    unittest.main()

