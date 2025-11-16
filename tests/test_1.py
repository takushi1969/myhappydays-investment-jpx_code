#!/usr/bin/env python
# coding: utf-8

import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
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


@pytest.fixture
def setup_retriever():
    """Set up a temporary directory and a JPXDataRetriever instance for each test."""
    tmpdir_obj = tempfile.TemporaryDirectory()
    tmpdir_path = Path(tmpdir_obj.name)

    try:
        retriever = JPXDataRetriever()
        retriever.cache_dir = tmpdir_path
        retriever.cache_file = tmpdir_path / retriever.DATA_FILENAME
        yield retriever
    finally:
        tmpdir_obj.cleanup()


def _create_dummy_xls_file(tmpdir_path):
    """Helper to create a dummy Excel file in the temp directory."""
    xls_path = tmpdir_path / "dummy_data.xls"
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


def test_find_file_url(setup_retriever):
    """Tests that the correct file URL is extracted from HTML."""
    url = setup_retriever._find_file_url(DUMMY_HTML_WITH_LINK.encode('utf-8'))
    assert url == EXPECTED_FILE_URL


def test_find_file_url_not_found(setup_retriever):
    """Tests that None is returned when the link is not in the HTML."""
    url = setup_retriever._find_file_url(DUMMY_HTML_WITHOUT_LINK.encode('utf-8'))
    assert url is None


def test_is_cache_stale_no_file(setup_retriever):
    """Tests that cache is stale if the file doesn't exist."""
    assert not setup_retriever.cache_file.exists()
    assert setup_retriever._is_cache_stale()


def test_is_cache_stale_old_file(setup_retriever):
    """Tests that cache is stale if the file is older than 30 days."""
    setup_retriever.cache_file.touch()
    thirty_one_days_ago = time.time() - (31 * 24 * 60 * 60)
    os.utime(setup_retriever.cache_file, (thirty_one_days_ago, thirty_one_days_ago))
    assert setup_retriever._is_cache_stale()


def test_is_cache_stale_fresh_file(setup_retriever):
    """Tests that cache is not stale if the file is recent."""
    setup_retriever.cache_file.touch()
    assert not setup_retriever._is_cache_stale()


def test_load_and_process_dataframe_success(setup_retriever):
    """Tests successful loading and processing of the cached Excel file."""
    dummy_xls_path = _create_dummy_xls_file(setup_retriever.cache_dir)
    shutil.copy(dummy_xls_path, setup_retriever.cache_file)
    df = setup_retriever._load_and_process_dataframe()

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    expected_cols = ["code", "name", "kind", "kind_name", "scale", "scale_name"]
    assert all(col in df.columns for col in expected_cols)
    assert "UnrelatedColumn" not in df.columns
    assert 1301 in df["code"].values
    assert 9984 in df["code"].values
    assert 1332 not in df["code"].values


def test_load_and_process_dataframe_file_not_found(setup_retriever):
    """Tests that FileNotFoundError is raised if cache file is missing."""
    with pytest.raises(FileNotFoundError):
        setup_retriever._load_and_process_dataframe()


def test_load_and_process_dataframe_corrupt_file(setup_retriever):
    """Tests that JPXDataAccessError is raised for unreadable files."""
    setup_retriever.cache_file.write_text("This is not valid Excel content.")
    with pytest.raises(JPXDataAccessError):
        setup_retriever._load_and_process_dataframe()


@patch('myhappydays.investment.jpx_code.jpx_code.urllib3.PoolManager')
def test_get_list_stale_cache_full_download(mock_pool_manager, setup_retriever):
    """Tests the end-to-end flow when the cache is stale."""
    dummy_xls_path = _create_dummy_xls_file(setup_retriever.cache_dir)
    mock_http = mock_pool_manager.return_value

    # Manually assign the mock to the instance
    setup_retriever.http = mock_http

    mock_page_response = MagicMock(status=200, data=DUMMY_HTML_WITH_LINK.encode('utf-8'))
    with open(dummy_xls_path, 'rb') as f:
        xls_content = f.read()
    mock_file_response = MagicMock(status=200)
    mock_file_response.stream.return_value = [xls_content]

    def request_side_effect(method, url, **kwargs):
        if url == setup_retriever.target_page_url:
            return mock_page_response
        if url == EXPECTED_FILE_URL:
            return mock_file_response
        return MagicMock(status=404)

    mock_http.request.side_effect = request_side_effect

    assert not setup_retriever.cache_file.exists()
    df = setup_retriever.get_prime_market_list()

    assert mock_http.request.call_count == 2
    assert setup_retriever.cache_file.exists()
    assert len(df) == 2

    mock_http.request.reset_mock()
    setup_retriever.get_prime_market_list()
    mock_http.request.assert_not_called()


@patch('myhappydays.investment.jpx_code.jpx_code.urllib3.PoolManager')
def test_get_list_fresh_cache_no_download(mock_pool_manager, setup_retriever):
    """Tests that no network call is made when the cache is fresh."""
    dummy_xls_path = _create_dummy_xls_file(setup_retriever.cache_dir)
    shutil.copy(dummy_xls_path, setup_retriever.cache_file)
    mock_http = mock_pool_manager.return_value
    setup_retriever.http = mock_http

    df = setup_retriever.get_prime_market_list()

    mock_http.request.assert_not_called()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2


@patch('myhappydays.investment.jpx_code.jpx_code.urllib3.PoolManager')
def test_raises_download_error_on_network_failure(mock_pool_manager, setup_retriever):
    """Tests that JPXDataDownloadError is raised on network issues."""
    mock_http = mock_pool_manager.return_value
    setup_retriever.http = mock_http
    mock_http.request.side_effect = urllib3.exceptions.MaxRetryError(None, "", "Network is down")

    with pytest.raises(JPXDataDownloadError):
        setup_retriever.get_prime_market_list()


@patch('myhappydays.investment.jpx_code.jpx_code.urllib3.PoolManager')
def test_raises_access_error_on_404(mock_pool_manager, setup_retriever):
    """Tests that JPXDataAccessError is raised on HTTP 404 Not Found."""
    mock_http = mock_pool_manager.return_value
    setup_retriever.http = mock_http
    mock_http.request.return_value = MagicMock(status=404)

    with pytest.raises(JPXDataAccessError):
        setup_retriever.get_prime_market_list()


@patch('myhappydays.investment.jpx_code.jpx_code.urllib3.PoolManager')
def test_raises_access_error_if_link_not_found(mock_pool_manager, setup_retriever):
    """Tests that JPXDataAccessError is raised if the download link is missing."""
    mock_http = mock_pool_manager.return_value
    setup_retriever.http = mock_http
    mock_http.request.return_value = MagicMock(
        status=200, data=DUMMY_HTML_WITHOUT_LINK.encode('utf-8')
    )

    with pytest.raises(JPXDataAccessError, match="Could not find link"):
        setup_retriever.get_prime_market_list()
