# JPX Code Retriever

`myhappydays.jpx_code` is a Python utility to download, cache, and parse the list of companies listed on the Japan Exchange Group (JPX) Prime Market.

It automates the process of fetching the official stock list Excel file (`data_j.xls`), processes it, and provides the data as a clean, ready-to-use pandas DataFrame.

## Features

- **Automated Download:** Automatically finds and downloads the latest stock list from the official JPX statistics page.
- **Smart Caching:** Caches the downloaded file in a local user directory to avoid redundant network requests. The cache is considered fresh for 30 days.
- **Data Processing:** Parses the Excel file, filters for stocks in the "Prime Market" category, and selects relevant columns.
- **Clean DataFrame Output:** Returns data in a pandas DataFrame with convenient English column names (e.g., `code`, `name`, `kind_name`).

## Usage

Instantiate the `JPXDataDownloader` and call the `.df()` method to get the stock list. The first call will download and cache the data; subsequent calls within 30 days will load directly from the cache.

```python
from myhappydays.jpx_code import JPXDataDownloader

# Initialize the downloader
jpx = JPXDataDownloader()

# Get the stock list as a pandas DataFrame
# This will handle downloading and caching automatically
prime_market_stocks_df = jpx.df()

# Display the first 5 rows
print(prime_market_stocks_df.head())

# Expected Output:
#
#    code    name          kind kind_name     scale scale_name
# 0  1301    極洋          0050   水産・農林業    1     TOPIX Core30
# 1  1332  ニッスイ        0050   水産・農林業    1     TOPIX Core30
# 2  1333  マルハニチロ    0050   水産・農林業    1     TOPIX Core30
# 3  1375  雪国まいたけ    0050   水産・農林業    -     -
# 4  1376  カネコ種苗      0050   水産・農林業    -     -
```
