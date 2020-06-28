# twquant
Twquant is a framework which aims for quant investment. Within current version, the focus is stock selecting. The functions include but are not limited as follows.

1. Retrieve raw data by web scraping and turn raw data into formatted data.
1. Combine various source of data and get the whole picture.
1. Calculate yearly return after addressing price adjustment in given time period.
1. Backtesting - import specific criteria and calculate correspondent yearly return.

## Installing
Use the package manager [pip](https://pip.pypa.io/en/stable/) to install twquant.

```bash
pip install twquant
```

## Usage

```python

from twquant import stockindc as si

x = si.Price('20200619', '上市')
x.head(1) # returns price data of sii on 20200619

```

For more information, please check the files below.

[*api_metrics.ipynb*](https://github.com/gary136/twquant/blob/master/api_metrics.ipynb) illustrates how to retrieve clean financial data. 
[*api_test.ipynb*](https://github.com/gary136/twquant/blob/master/api_test.ipynb) illustrates how to download data to local and use the data to realize backtesting.

## Note
Some functions require 'tej.csv' to execute. This csv file is derived and simplified from open data of [tej companies basic information](https://api.tej.com.tw/columndoc.html?subId=14). The purpose of using tej data is to map the industry of each company and to generate average industry PE ratio. An example ready-to-use file can be found on the [github of twquant](https://github.com/gary136/twquant/blob/master/tej.csv). Although that file is compatible with package, the content is not updated and it's recommended to get your own tej api key and replace the content with the new one. 

## Disclaimer
Twquant retrieves data from publicly accessible source. We make no representations or warranties  about the completeness, reliability and accuracy of data. Any action you take on the data via this package is strictly on your own risk. We will not be liable for any losses and connections with the uses of package.

## License
[MIT](https://choosealicense.com/licenses/mit/)