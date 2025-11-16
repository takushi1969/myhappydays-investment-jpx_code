# JPX Code Retriever

`myhappydays.jpx_code` is a Python tool designed to streamline the process of downloading, caching, and parsing the stock listings from the Japan Exchange Group (JPX) Prime Market.

This utility automates the retrieval of the official stock list Excel file (`data_j.xls`), processes it effectively, and provides the data as a neatly formatted pandas DataFrame, ready for analysis.

## Features

- **Automated Download:** Seamlessly identifies and retrieves the latest stock list from the JPX's official statistics page.
- **Efficient Caching:** Stores the downloaded file locally, reducing redundant network requests. Cached data is valid for 30 days, ensuring up-to-date information while minimizing downloads.
- **Advanced Processing:** Extracts and processes data focusing on the "Prime Market" stocks, selecting only the pertinent columns.
- **User-Friendly DataFrame:** Outputs data in a pandas DataFrame with English column names for easy manipulation and understanding (e.g., `code`, `name`, `kind_name`).

## Usage

Create an instance of `JPXDataDownloader` and use the `.df()` method to obtain the stock list. The first invocation handles the downloading and caching, while subsequent calls within a 30-day period will use the cached file.

```python
from myhappydays.jpx_code import JPXDataDownloader

# Initialize the downloader
jpx = JPXDataDownloader()

# Retrieve the stock list as a pandas DataFrame
# This process manages downloading and caching seamlessly
prime_market_stocks_df = jpx.df()

# Display the first 5 rows of the data
print(prime_market_stocks_df.head())

# Expected Output:
#
#    code    name        kind      kind_name    scale    scale_name
# 0  1301    極洋        0050      水産・農林業  1        TOPIX Core30
# 1  1332  ニッスイ      0050      水産・農林業  1        TOPIX Core30
# 2  1333  マルハニチロ  0050      水産・農林業  1        TOPIX Core30
# 3  1375  雪国まいたけ  0050      水産・農林業  -        -
# 4  1376  カネコ種苗    0050      水産・農林業  -        -
```
