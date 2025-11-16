#!/usr/bin/env python
# coding: utf-8

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import urllib3

from myhappydays.investment.jpx_code.jpx_code import (
    JPXDataAccessError,
    JPXDataDownloadError,
    JPXDataRetriever,
)

# --- Test Constants ---
DUMMY_HTML_WITH_LINK = """
<html><body>
<a href="/somewhere/else/data_j.xls">Download Excel</a>
</body></html>
"""
DUMMY_HTML_WITHOUT_LINK = "<html><body>No link here.</body></html>"
EXPECTED_FILE_URL = "https://www.jpx.co.jp/somewhere/else/data_j.xls"


class TestJPXDataRetriever(unittest.TestCase):

    def setUp(self):
        """Set up a temporary directory and a JPXDataRetriever instance for each test."""
        self.tmpdir_obj = tempfile.TemporaryDirectory()
        self.tmpdir_path = Path(self.tmpdir_obj.name)

        # Create the retriever and override its cache path
        self.retriever = JPXDataRetriever()
        self.retriever.cache_dir = self.tmpdir_path
        self.retriever.cache_file = self.tmpdir_path / self.retriever.DATA_FILENAME

    def tearDown(self):
        """Clean up the temporary directory after each test."""
        self.tmpdir_obj.cleanup()

    def _create_dummy_xls_file(self):
        """Helper to create a dummy Excel file in the temp directory."""
        xls_path = self.tmpdir_path / "dummy_data.xls"
        df_data = {
            "コード": [1301, 1332, 9984],
            "銘柄名": ["Kyokuyo", "Nissui", "Softbank Group"],
            "市場・商品区分": ["プライム（内国株式）", "スタンダード（内国株式）", "プライム（内国株式）"],
            "33業種コード": [1050, 1050, 5250],
            "33業種区分": ["水産・農林業", "水産・農林業", "情報・通信業"],
            "規模コード": [7, 7, 7],
            "規模区分": ["TOPIX Mid400", "TOPIX Mid400", "TOPIX Core30"],
            "UnrelatedColumn": ["A", "B", "C"],
        }
        df = pd.DataFrame(df_data)
        df.to_excel(xls_path, index=False)
        return xls_path

    def test_find_file_url(self):
        """Tests that the correct file URL is extracted from HTML."""
        url = self.retriever._find_file_url(DUMMY_HTML_WITH_LINK.encode('utf-8'))
        self.assertEqual(url, EXPECTED_FILE_URL)

    def test_find_file_url_not_found(self):
        """Tests that None is returned when the link is not in the HTML."""
        url = self.retriever._find_file_url(DUMMY_HTML_WITHOUT_LINK.encode('utf-8'))
        self.assertIsNone(url)

    def test_is_cache_stale_no_file(self):
        """Tests that cache is stale if the file doesn't exist."""
        self.assertFalse(self.retriever.cache_file.exists())
        self.assertTrue(self.retriever._is_cache_stale())

    def test_is_cache_stale_old_file(self):
        """Tests that cache is stale if the file is older than 30 days."""
        self.retriever.cache_file.touch()
        thirty_one_days_ago = time.time() - (31 * 24 * 60 * 60)
        os.utime(self.retriever.cache_file, (thirty_one_days_ago, thirty_one_days_ago))
        self.assertTrue(self.retriever._is_cache_stale())

    def test_is_cache_stale_fresh_file(self):
        """Tests that cache is not stale if the file is recent."""
        self.retriever.cache_file.touch()
        self.assertFalse(self.retriever._is_cache_stale())

    def test_load_and_process_dataframe_success(self):
        """Tests successful loading and processing of the cached Excel file."""
        dummy_xls_path = self._create_dummy_xls_file()
        shutil.copy(dummy_xls_path, self.retriever.cache_file)
        df = self.retriever._load_and_process_dataframe()

        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 2)
        expected_cols = ["code", "name", "kind", "kind_name", "scale", "scale_name"]
        self.assertTrue(all(col in df.columns for col in expected_cols))
        self.assertNotIn("UnrelatedColumn", df.columns)
        self.assertIn(1301, df["code"].values)
        self.assertIn(9984, df["code"].values)
        self.assertNotIn(1332, df["code"].values)

    def test_load_and_process_dataframe_file_not_found(self):
        """Tests that FileNotFoundError is raised if cache file is missing."""
        with self.assertRaises(FileNotFoundError):
            self.retriever._load_and_process_dataframe()

    def test_load_and_process_dataframe_corrupt_file(self):
        """Tests that JPXDataAccessError is raised for unreadable files."""
        self.retriever.cache_file.write_text("This is not valid Excel content.")
        with self.assertRaises(JPXDataAccessError):
            self.retriever._load_and_process_dataframe()

    @patch('myhappydays.investment.jpx_code.jpx_code.urllib3.PoolManager')
    def test_get_list_stale_cache_full_download(self, mock_pool_manager):
        """Tests the end-to-end flow when the cache is stale."""
        dummy_xls_path = self._create_dummy_xls_file()
        mock_http = mock_pool_manager.return_value
        
        # --- FIX: Manually assign the mock to the instance ---
        self.retriever.http = mock_http
        # -----------------------------------------------------

        mock_page_response = MagicMock(status=200, data=DUMMY_HTML_WITH_LINK.encode('utf-8'))
        with open(dummy_xls_path, 'rb') as f:
            xls_content = f.read()
        mock_file_response = MagicMock(status=200)
        mock_file_response.stream.return_value = [xls_content]

        def request_side_effect(method, url, **kwargs):
            if url == self.retriever.target_page_url:
                return mock_page_response
            if url == EXPECTED_FILE_URL:
                return mock_file_response
            return MagicMock(status=404)

        mock_http.request.side_effect = request_side_effect

        self.assertFalse(self.retriever.cache_file.exists())
        df = self.retriever.get_prime_market_list()

        self.assertEqual(mock_http.request.call_count, 2)
        self.assertTrue(self.retriever.cache_file.exists())
        self.assertEqual(len(df), 2)

        mock_http.request.reset_mock()
        self.retriever.get_prime_market_list()
        mock_http.request.assert_not_called()

    @patch('myhappydays.investment.jpx_code.jpx_code.urllib3.PoolManager')
    def test_get_list_fresh_cache_no_download(self, mock_pool_manager):
        """Tests that no network call is made when the cache is fresh."""
        dummy_xls_path = self._create_dummy_xls_file()
        shutil.copy(dummy_xls_path, self.retriever.cache_file)
        mock_http = mock_pool_manager.return_value
        self.retriever.http = mock_http # Also add here for consistency

        df = self.retriever.get_prime_market_list()

        mock_http.request.assert_not_called()
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 2)

    @patch('myhappydays.investment.jpx_code.jpx_code.urllib3.PoolManager')
    def test_raises_download_error_on_network_failure(self, mock_pool_manager):
        """Tests that JPXDataDownloadError is raised on network issues."""
        mock_http = mock_pool_manager.return_value
        self.retriever.http = mock_http # Apply fix
        mock_http.request.side_effect = urllib3.exceptions.MaxRetryError(None, "", "Network is down")

        with self.assertRaises(JPXDataDownloadError):
            self.retriever.get_prime_market_list()

    @patch('myhappydays.investment.jpx_code.jpx_code.urllib3.PoolManager')
    def test_raises_access_error_on_404(self, mock_pool_manager):
        """Tests that JPXDataAccessError is raised on HTTP 404 Not Found."""
        mock_http = mock_pool_manager.return_value
        self.retriever.http = mock_http # Apply fix
        mock_http.request.return_value = MagicMock(status=404)

        with self.assertRaises(JPXDataAccessError):
            self.retriever.get_prime_market_list()

    @patch('myhappydays.investment.jpx_code.jpx_code.urllib3.PoolManager')
    def test_raises_access_error_if_link_not_found(self, mock_pool_manager):
        """Tests that JPXDataAccessError is raised if the download link is missing."""
        mock_http = mock_pool_manager.return_value
        self.retriever.http = mock_http # Apply fix
        mock_http.request.return_value = MagicMock(
            status=200, data=DUMMY_HTML_WITHOUT_LINK.encode('utf-8')
        )

        with self.assertRaisesRegex(JPXDataAccessError, "Could not find link"):
            self.retriever.get_prime_market_list()


if __name__ == '__main__':
    unittest.main()

