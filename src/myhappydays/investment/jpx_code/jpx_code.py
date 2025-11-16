#!/usr/bin/env python
# coding: utf-8

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urljoin

import pandas as pd
import urllib3
from bs4 import BeautifulSoup
from platformdirs import user_cache_dir


class JPXDataDownloadError(RuntimeError):
    """Raised when a network-level error occurs during download."""
    pass


class JPXDataAccessError(RuntimeError):
    """
    Raised when the data cannot be accessed, e.g., page structure changes,
    file
    not found on the server, or file is unreadable.
    """
    pass


class JPXDataRetriever:
    """
    Retrieves and processes the Japanese stock list from the JPX website.

    This class handles downloading the 'data_j.xls' file, caching it locally,
    and parsing it into a pandas DataFrame.
    """

    APP_NAME: str = "jpx_data_retriever"
    DATA_FILENAME: str = "data_j.xls"
    BASE_URL: str = "https://www.jpx.co.jp"
    TARGET_PAGE_PATH: str = "/markets/statistics-equities/misc/01.html"

    _COLUMN_RENAME_MAP: Dict[str, str] = {
        "コード": "code",
        "銘柄名": "name",
        "33業種コード": "kind",
        "33業種区分": "kind_name",
        "規模コード": "scale",
        "規模区分": "scale_name",
    }
    _MARKET_COLUMN_NAME: str = "市場・商品区分"
    _PRIME_MARKET_NAME: str = "プライム（内国株式）"

    def __init__(self) -> None:
        """Initializes the JPX data retriever."""
        self.target_page_url: str = urljoin(self.BASE_URL, self.TARGET_PAGE_PATH)
        self.http: urllib3.PoolManager = urllib3.PoolManager()
        self.cache_dir: Path = Path(user_cache_dir(self.APP_NAME))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file: Path = self.cache_dir / self.DATA_FILENAME

    def _find_file_url(self, page_content: bytes) -> Optional[str]:
        """Parses HTML content to find the URL for the data file."""
        soup = BeautifulSoup(page_content, 'html.parser')
        link_tag = soup.find(
            'a', href=lambda href: href and self.DATA_FILENAME in href
        )
        if link_tag and (href := link_tag.get('href')):
            return urljoin(self.BASE_URL, href)
        return None

    def _is_cache_stale(self) -> bool:
        """Checks if the cached file is missing or older than 30 days."""
        if not self.cache_file.exists():
            return True
        file_mod_time = datetime.fromtimestamp(self.cache_file.stat().st_mtime)
        thirty_days_ago = datetime.now() - timedelta(days=30)
        return file_mod_time < thirty_days_ago

    def _update_cache_if_needed(self) -> None:
        """
        Downloads the data file from JPX if the local cache is stale.
        """
        if not self._is_cache_stale():
            return

        # 1. Access the main statistics page to find the download link
        try:
            page_response = self.http.request('GET', self.target_page_url)
            if page_response.status != 200:
                raise JPXDataAccessError(
                    f"Failed to access page {self.target_page_url}. "
                    f"Status: {page_response.status}"
                )
        except urllib3.exceptions.HTTPError as e:
            raise JPXDataDownloadError(
                f"Network error accessing {self.target_page_url}"
            ) from e

        file_url = self._find_file_url(page_response.data)
        if not file_url:
            raise JPXDataAccessError(
                f"Could not find link for '{self.DATA_FILENAME}' on {self.target_page_url}"
            )

        # 2. Download and save the file
        file_response = None
        try:
            file_response = self.http.request(
                'GET', file_url, preload_content=False
            )
            if file_response.status != 200:
                raise JPXDataAccessError(
                    f"Failed to download file from {file_url}. "
                    f"Status: {file_response.status}"
                )

            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'wb') as f:
                for chunk in file_response.stream(1024):
                    f.write(chunk)
        except urllib3.exceptions.HTTPError as e:
            raise JPXDataDownloadError(
                f"Network error downloading from {file_url}"
            ) from e
        finally:
            if file_response:
                file_response.release_conn()

    def _load_and_process_dataframe(self) -> pd.DataFrame:
        """Loads the cached Excel file and processes it into a DataFrame."""
        if not self.cache_file.exists():
            raise FileNotFoundError(
                f"Cache file not found at {self.cache_file}. "
                "Download may have failed or been skipped."
            )
        try:
            raw_df = pd.read_excel(self.cache_file)
        except Exception as e:
            raise JPXDataAccessError(
                f"Could not read or parse Excel file at {self.cache_file}. "
                "It may be corrupt or in an unexpected format."
            ) from e

        if self._MARKET_COLUMN_NAME not in raw_df.columns:
            raise JPXDataAccessError(
                f"Required column '{self._MARKET_COLUMN_NAME}' not found in Excel file."
            )

        prime_market_filter = raw_df[self._MARKET_COLUMN_NAME] == self._PRIME_MARKET_NAME
        target_columns = list(self._COLUMN_RENAME_MAP.keys())

        processed_df = (
            raw_df.loc[prime_market_filter, target_columns]
            .rename(columns=self._COLUMN_RENAME_MAP)
        )
        return processed_df

    def get_prime_market_list(self) -> pd.DataFrame:
        """
        Retrieves the JPX Prime Market stock list as a pandas DataFrame.

        This method ensures the data file is cached and up-to-date before
        loading and processing it.

        Returns:
            pd.DataFrame: A DataFrame containing the processed stock list.

        Raises:
            JPXDataDownloadError: If a network error occurs.
            JPXDataAccessError: If the site structure has changed or the file is invalid.
            FileNotFoundError: If the cache file is missing after an update check.
        """
        self._update_cache_if_needed()
        return self._load_and_process_dataframe()


if __name__ == '__main__':
    print("Attempting to retrieve JPX Prime Market stock list...")
    retriever = JPXDataRetriever()
    try:
        stock_list_df = retriever.get_prime_market_list()
        print("Successfully retrieved data.")
        print(f"Cache file location: {retriever.cache_file}")
        print("\nFirst 5 entries:")
        print(stock_list_df.head())
    except (JPXDataDownloadError, JPXDataAccessError, FileNotFoundError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)
