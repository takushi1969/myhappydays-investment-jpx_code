# JPX Data Retriever

The JPX Data Retriever is a Python module designed to obtain and process the Japanese stock list from the Japan Exchange Group (JPX) website. It efficiently downloads, caches, and parses the stock data into a pandas DataFrame, making it easy for analysts and developers to integrate JPX stock information into their applications.

## Features

- Downloads the latest JPX stock list directly from the JPX website.
- Caches the downloaded data locally and checks for updates every 30 days.
- Processes the downloaded Excel file into a pandas DataFrame.
- Filters the data to provide only stocks listed on the Prime Market.

## Installation

To use the JPX Data Retriever, ensure you have the following prerequisites:

- Python 3.x
- Required Python packages: `pandas`, `urllib3`, `beautifulsoup4`, `platformdirs`

Install the necessary packages using pip:

```bash
pip install pandas urllib3 beautifulsoup4 platformdirs
```

## Usage

To retrieve and display the JPX Prime Market stock list, run the following script:

```python
from myhappydays.investment.jpx_code import JPXDataRetriever

retriever = JPXDataRetriever()
try:
    stock_list_df = retriever.get_prime_market_list()
    print("Successfully retrieved data.")
    print(f"Cache file location: {retriever.cache_file}")
    print("\nFirst 5 entries:")
    print(stock_list_df.head())
except (JPXDataDownloadError, JPXDataAccessError, FileNotFoundError) as e:
    print(f"Error: {e}")
```

## Classes

### JPXDataRetriever

- **Purpose**: Handles the retrieval, caching, and processing of JPX stock data.
- **Key Methods**:
  - `get_prime_market_list()`: Returns the JPX Prime Market stock list as a pandas DataFrame.

### JPXDataDownloadError

- **Purpose**: Raised when a network-level error occurs during data download.

### JPXDataAccessError

- **Purpose**: Raised when the data cannot be accessed due to page structure changes, missing files, or unreadable content.

## License

This project is open-sourced and available for use under the MIT License. See the LICENSE file for details.
