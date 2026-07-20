import unittest
from unittest.mock import Mock, patch

import main


class FetchUrlJsonTests(unittest.TestCase):
    def test_fetch_url_json_returns_parsed_payload(self):
        mock_response = Mock()
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_response.read.return_value = b'{"hello": "world"}'

        with patch("main.urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            result = main.fetch_url_json("https://example.com/data", timeout=5)

        self.assertEqual(result, {"hello": "world"})
        mock_urlopen.assert_called_once_with("https://example.com/data", timeout=5)

    def test_fetch_url_json_uses_default_timeout(self):
        mock_response = Mock()
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_response.read.return_value = b'[]'

        with patch("main.urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            result = main.fetch_url_json("https://example.com/data")

        self.assertEqual(result, [])
        mock_urlopen.assert_called_once_with("https://example.com/data", timeout=10)


if __name__ == "__main__":
    unittest.main()
