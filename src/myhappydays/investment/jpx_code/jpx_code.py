#!/usr/bin/env python
#coding: utf-8

import urllib3
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from platformdirs import user_cache_dir

class JPXDataDownloadError(RuntimeError):
    pass

class JPXDataAccessError(RuntimeError):
    pass

class JPXDataDownloader:
    """
    A class to download 'data_j.xls' from the JPX website.
    """

    APP_NAME = "jpx_data_retriever"
    DATA_FILENAME = "data_j.xls"

    def __init__(self):
        """
        Initialize the JPX data downloader.

        Sets the target URLs, creates an HTTP client, and configures cache paths.
        """
        self.base_url = "https://www.jpx.co.jp"
        self.target_page_url = urljoin(
            self.base_url, "/markets/statistics-equities/misc/01.html")
        self.http = urllib3.PoolManager()

        # Configure paths for caching downloaded files.
        self.cache_dir = Path(user_cache_dir(self.APP_NAME))
        self.cache_file = self.cache_dir / self.DATA_FILENAME

    def _find_file_url(self, page_content):
        """
        Parse HTML content to find the URL for 'data_j.xls'.

        Args:
            page_content (bytes): The HTML content of the page.

        Returns:
            str: The absolute URL to the xls file, or None if not found.
        """
        soup = BeautifulSoup(page_content, 'html.parser')
        # Find the anchor tag whose href contains 'data_j.xls'
        link_tag = soup.find(
            'a', href=lambda href: href and self.DATA_FILENAME in href)

        if link_tag and link_tag.get('href'):
            relative_url = link_tag.get('href')
            # Construct the absolute URL
            absolute_url = urljoin(self.base_url, relative_url)
            return absolute_url
        return None

    def _should_download(self):
        """
        Determine if data should be downloaded based on cache file existence and age.

        Returns:
            bool: True if a download is needed, False otherwise.
        """
        if not self.cache_file.exists():
            return True

        file_mod_time = datetime.fromtimestamp(self.cache_file.stat().st_mtime)
        one_month_ago = datetime.now() - timedelta(days=30)

        return file_mod_time <= one_month_ago

    def _get_file_response(self):
        # 1. Access the main statistics page
        print(f"Accessing page: {self.target_page_url}")
        response = self.http.request('GET', self.target_page_url)

        if response.status != 200:
            raise JPXDataAccessError(
                f"Error: Failed to access page. Status code: {response.status}"
            )

        # 2. Find the download link for the xls file
        print("Searching for download link...")
        file_url = self._find_file_url(response.data)

        if not file_url:
            raise JPXDataAccessError(
                f"Error: Could not find the download link for '{self.DATA_FILENAME}'"
            )

        print(f"Found file URL: {file_url}")

        # 3. Download the xls file
        file_response = None
        try:
            print(f"Downloading '{self.DATA_FILENAME}'...")
            file_response = self.http.request(
                'GET', file_url, preload_content=False
            )

            if file_response.status != 200:

                raise JPXDataAccessError(
                    f"Error: Failed to download file. Status code: {file_response.status}"
                )

            return file_response
        except Exception:
            if file_response:
                file_response.release_conn()
            raise

    def _download_xls(self):
        """Access the JPX statistics page and downloads the 'data_j.xls' file."""
        if not self._should_download():
            return

        file_response = None
        try:
            file_response = self._get_file_response()

            # 4. Save the file to disk
            with open(self.cache_file, 'wb') as f:
                for chunk in file_response.stream(1024):
                    f.write(chunk)
            print(f"Successfully downloaded and saved as '{self.cache_file}'.")

        except urllib3.exceptions.MaxRetryError as e:
            print(f"Error: Network connection failed. {e}", file=sys.stderr)
            raise
        except Exception as e:
            print(f"An unexpected error occurred: {e}", file=sys.stderr)
            raise
        finally:
            if file_response:
                file_response.release_conn()

    def df(self):
        """Retrieve the JPX stock list, caching it for one month.

        Returns:
        pandas.DataFrame: A DataFrame containing the processed stock list.
        """
        COLUMN_RENAME_MAP = {
            "コード": "code",
            "銘柄名": "name",
            "33業種コード": "kind",
            "33業種区分": "kind_name",
            "規模コード": "scale",
            "規模区分": "scale_name",
        }

        self._download_xls()

        try:
            raw_df = pd.read_excel(self.cache_file)
        except Exception as e:
            raise ValueError(
                f"Could not read or parse the Excel file at {self.cache_file}"
            ) from e

        # Filter for prime market stocks
        prime_market_filter = raw_df["市場・商品区分"] == "プライム（内国株式）"
        
        # Select the relevant columns from the filtered data
        target_columns = list(COLUMN_RENAME_MAP.keys())
        
        # Use .loc for safe selection and chain the rename operation
        processed_df = raw_df.loc[prime_market_filter, target_columns].rename(
            columns=COLUMN_RENAME_MAP
        )

        return processed_df


if __name__ == '__main__':
    jpx = JPXDataDownloader()
    df = jpx.df()
    print(df.head())
