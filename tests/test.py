import unittest
from unittest.mock import patch, MagicMock, mock_open
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import urllib3

from myhappydays.jpx_code.jpx_code import (
    JPXDataDownloader,
    JPXDataDownloadError,
    JPXDataAccessError,
)

# Dummy HTML content for testing _find_file_url
DUMMY_HTML_WITH_LINK = """
<html>
<body>
    <h1>Some Title</h1>
    <p>Some text.</p>
    <a href="/some/other/link.pdf">PDF</a>
    <a href="/markets/statistics-equities/misc/tvdivq000000x29e-att/data_j.xls">Download XLS</a>
    <p>More text.</p>
</body>
</html>
"""

DUMMY_HTML_WITHOUT_LINK = """
<html>
<body>
    <h1>Some Title</h1>
    <p>Some text.</p>
    <a href="/some/other/link.pdf">PDF</a>
</body>
</html>
"""

class TestJPXDataDownloader(unittest.TestCase):

    @patch('myhappydays.jpx_code.jpx_code.user_cache_dir')
    def setUp(self, mock_user_cache_dir):
        # Use a temporary directory for cache during tests
        self.temp_cache_dir = Path("/tmp/test_jpx_cache")
        mock_user_cache_dir.return_value = str(self.temp_cache_dir)
        
        # We patch PoolManager to avoid actual HTTP requests
        with patch('myhappydays.jpx_code.jpx_code.urllib3.PoolManager'):
            self.downloader = JPXDataDownloader()
        
        # Ensure the cache dir is consistent for all tests
        self.assertEqual(self.downloader.cache_dir, self.temp_cache_dir)

    def test_initialization(self):
        """Test that the downloader is initialized with correct attributes."""
        self.assertEqual(self.downloader.base_url, "https://www.jpx.co.jp")
        self.assertEqual(self.downloader.target_page_url, "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html")
        self.assertIsInstance(self.downloader.http, MagicMock) # Patched in setUp
        self.assertEqual(self.downloader.cache_file, self.temp_cache_dir / "data_j.xls")

    def test_find_file_url_success(self):
        """Test finding the xls file URL from HTML content."""
        url = self.downloader._find_file_url(DUMMY_HTML_WITH_LINK.encode('utf-8'))
        expected_url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq000000x29e-att/data_j.xls"
        self.assertEqual(url, expected_url)

    def test_find_file_url_failure(self):
        """Test that None is returned when the link is not found."""
        url = self.downloader._find_file_url(DUMMY_HTML_WITHOUT_LINK.encode('utf-8'))
        self.assertIsNone(url)

    @patch('myhappydays.jpx_code.jpx_code.datetime')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.stat')
    def test_should_download(self, mock_stat, mock_exists, mock_datetime):
        """Test the logic for deciding whether to download the file."""
        # Case 1: File does not exist
        mock_exists.return_value = False
        self.assertTrue(self.downloader._should_download())

        # Case 2: File exists and is recent
        mock_exists.return_value = True
        now = datetime(2023, 10, 27, 12, 0, 0)
        file_time = datetime(2023, 10, 27, 10, 0, 0)  # 2 hours ago
        
        mock_datetime.now.return_value = now
        mock_datetime.fromtimestamp.return_value = file_time
        mock_stat.return_value.st_mtime = file_time.timestamp()

        self.assertFalse(self.downloader._should_download())

        # Case 3: File exists and is old
        old_file_time = datetime(2023, 9, 26, 10, 0, 0)  # More than 30 days ago
        mock_datetime.fromtimestamp.return_value = old_file_time
        mock_stat.return_value.st_mtime = old_file_time.timestamp()

        self.assertTrue(self.downloader._should_download())

    def test_get_file_response_success(self):
        """Test successfully getting the file response object."""
        # Mock the page response
        mock_page_response = MagicMock()
        mock_page_response.status = 200
        mock_page_response.data = DUMMY_HTML_WITH_LINK.encode('utf-8')

        # Mock the file response
        mock_file_response = MagicMock()
        mock_file_response.status = 200

        self.downloader.http.request.side_effect = [mock_page_response, mock_file_response]

        response = self.downloader._get_file_response()

        self.assertEqual(response, mock_file_response)
        self.downloader.http.request.assert_any_call('GET', self.downloader.target_page_url)
        expected_file_url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq000000x29e-att/data_j.xls"
        self.downloader.http.request.assert_any_call('GET', expected_file_url, preload_content=False)

    def test_get_file_response_page_access_error(self):
        """Test handling of page access failure."""
        mock_page_response = MagicMock()
        mock_page_response.status = 404
        self.downloader.http.request.return_value = mock_page_response

        with self.assertRaises(JPXDataAccessError) as cm:
            self.downloader._get_file_response()
        self.assertIn("Failed to access page", str(cm.exception))

    def test_get_file_response_link_not_found_error(self):
        """Test handling of missing download link."""
        mock_page_response = MagicMock()
        mock_page_response.status = 200
        mock_page_response.data = DUMMY_HTML_WITHOUT_LINK.encode('utf-8')
        self.downloader.http.request.return_value = mock_page_response

        with self.assertRaises(JPXDataAccessError) as cm:
            self.downloader._get_file_response()
        self.assertIn("Could not find the download link", str(cm.exception))

    def test_get_file_response_download_error(self):
        """Test handling of file download failure."""
        mock_page_response = MagicMock()
        mock_page_response.status = 200
        mock_page_response.data = DUMMY_HTML_WITH_LINK.encode('utf-8')

        mock_file_response = MagicMock()
        mock_file_response.status = 500
        mock_file_response.release_conn = MagicMock()

        self.downloader.http.request.side_effect = [mock_page_response, mock_file_response]
        
        with self.assertRaises(JPXDataAccessError) as cm:
            self.downloader._get_file_response()
        self.assertIn("Failed to download file", str(cm.exception))
        mock_file_response.release_conn.assert_called_once()
        
    @patch('myhappydays.jpx_code.jpx_code.JPXDataDownloader._should_download')
    @patch('myhappydays.jpx_code.jpx_code.JPXDataDownloader._get_file_response')
    def test_download_xls_should_not_download(self, mock_get_response, mock_should_download):
        """Test that download is skipped if not needed."""
        mock_should_download.return_value = False
        
        self.downloader._download_xls()
        
        mock_get_response.assert_not_called()

    @patch('myhappydays.jpx_code.jpx_code.JPXDataDownloader._should_download')
    @patch('myhappydays.jpx_code.jpx_code.JPXDataDownloader._get_file_response')
    @patch('builtins.open', new_callable=mock_open)
    def test_download_xls_success(self, mock_file_open, mock_get_response, mock_should_download):
        """Test successful download and saving of the xls file."""
        mock_should_download.return_value = True
        
        mock_response = MagicMock()
        mock_response.stream.return_value = [b'chunk1', b'chunk2']
        mock_response.release_conn = MagicMock()
        mock_get_response.return_value = mock_response
        
        self.downloader._download_xls()
        
        mock_get_response.assert_called_once()
        mock_file_open.assert_called_once_with(self.downloader.cache_file, 'wb')
        handle = mock_file_open()
        handle.write.assert_any_call(b'chunk1')
        handle.write.assert_any_call(b'chunk2')
        mock_response.release_conn.assert_called_once()

    @patch('myhappydays.jpx_code.jpx_code.JPXDataDownloader._should_download')
    @patch('myhappydays.jpx_code.jpx_code.JPXDataDownloader._get_file_response')
    def test_download_xls_unexpected_error(self, mock_get_response, mock_should_download):
        """Test that unexpected errors are wrapped in JPXDataDownloadError."""
        mock_should_download.return_value = True
        mock_get_response.side_effect = ValueError("Some unexpected error")

        with self.assertRaises(JPXDataDownloadError) as cm:
            self.downloader._download_xls()
        
        self.assertIsInstance(cm.exception.__cause__, ValueError)
        self.assertIn("Unexpected download error", str(cm.exception))

    @patch('myhappydays.jpx_code.jpx_code.JPXDataDownloader._download_xls')
    @patch('pandas.read_excel')
    def test_df_success(self, mock_read_excel, mock_download_xls):
        """Test successful processing of the xls file into a DataFrame."""
        dummy_data = {
            "コード": [1301, 9984, 7203],
            "銘柄名": ["極洋", "ソフトバンクグループ", "トヨタ自動車"],
            "市場・商品区分": ["プライム（内国株式）", "プライム（内国株式）", "スタンダード（内国株式）"],
            "33業種コード": ["0050", "9050", "3700"],
            "33業種区分": ["水産・農林業", "情報・通信業", "輸送用機器"],
            "規模コード": ["7", "7", "7"],
            "規模区分": ["TOPIX Core30", "TOPIX Core30", "TOPIX Core30"],
        }
        mock_raw_df = pd.DataFrame(dummy_data)
        mock_read_excel.return_value = mock_raw_df

        df = self.downloader.df()

        mock_download_xls.assert_called_once()
        mock_read_excel.assert_called_once_with(self.downloader.cache_file)
        
        self.assertEqual(len(df), 2)
        self.assertTrue(all(df['code'].isin([1301, 9984])))
        
        expected_columns = ["code", "name", "kind", "kind_name", "scale", "scale_name"]
        self.assertListEqual(list(df.columns), expected_columns)
        self.assertEqual(df[df['code'] == 1301]['name'].iloc[0], "極洋")
        
    @patch('myhappydays.jpx_code.jpx_code.JPXDataDownloader._download_xls')
    @patch('pandas.read_excel')
    def test_df_read_excel_error(self, mock_read_excel, mock_download_xls):
        """Test that an error during Excel reading is handled."""
        mock_read_excel.side_effect = Exception("Cannot parse file")
        
        with self.assertRaises(ValueError) as cm:
            self.downloader.df()
            
        self.assertIn("Could not read or parse the Excel file", str(cm.exception))
        self.assertIsInstance(cm.exception.__cause__, Exception)
        
    @patch('myhappydays.jpx_code.jpx_code.JPXDataDownloader._download_xls')
    def test_df_download_error_propagation(self, mock_download_xls):
        """Test that an error during download propagates up."""
        mock_download_xls.side_effect = JPXDataDownloadError("Network failed")
        
        with self.assertRaises(JPXDataDownloadError):
            self.downloader.df()

if __name__ == '__main__':
    unittest.main()
