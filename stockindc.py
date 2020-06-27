import pandas as pd
import requests
import numpy as np
from io import StringIO
import time
import html5lib
from datetime import datetime, timedelta, date
import calendar
import datetime as dt
from functools import reduce
import json
import os
from collections import Counter

# functions for processing convenience
def revr(data, nmbr):
    cols = data.columns.tolist()
    cols = cols[nmbr:] + cols[:nmbr]
    data = data[cols]
    return data

def add_months(sourcedate, months):
    sourcedate = datetime.strptime(sourcedate, "%Y%m%d").date() if type(sourcedate)==str else sourcedate
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year,month)[1])
    return dt.date(year, month, day)

def fullpathname(outdir, outname):
    if not os.path.exists(outdir):
        os.mkdir(outdir)
    return os.path.join(outdir, outname)

def clean(d):
    d = d.fillna(1e-4)
    def flt(x):
        try:
            return float(x)
        except ValueError:
            # return 0
            return 1e-4
    not_nmbr = ['日','月','季','年','代號','名稱']
    numeric_cols = list(filter(lambda x:not any(i in x for i in not_nmbr), list(d.columns)))
    for i in numeric_cols:
        d[i] = d[i].apply(flt)                           
    return d

#############################

# 價格
def siiPrice(str_date, corporation_only=True):
    url = f'https://www.twse.com.tw/exchangeReport/MI_INDEX?response=csv&date={str_date}&type=ALL'
    r = requests.get(url)
    if r.text=='':
        return None    
    
    df = pd.read_csv(StringIO(r.text.replace("=", "")), 
                header=["證券代號" in l for l in r.text.split("\n")].index(True)-1)
    df.drop(['Unnamed: 16','最後揭示買價', '最後揭示買量', '最後揭示賣價', '最後揭示賣量','漲跌(+/-)'], axis=1, inplace=True)
    for i in ['成交股數', '成交筆數', '成交金額', '開盤價', '最高價', '最低價', '收盤價', '漲跌價差', '本益比']:
        df[i] = df[i].apply(lambda x: pd.to_numeric(x.replace(",", ""), errors='coerce') if type(x)!=float else x)
    df['股價日期'] = datetime(int(str_date[:4]),int(str_date[4:6]),int(str_date[6:]),0,0,0)
    df = revr(df,-1)
    if corporation_only==True: 
        df = df[~df.證券代號.str.startswith('0')] 
        df = df[df.證券代號.apply(lambda x:len(x)==4)]
    df = clean(df)
    return df

def otcPrice(str_date, corporation_only=True):
    url = f'https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php?l=zh-tw&o=htm&d={str_date}&se=AL&s=0,asc,0'
    r = requests.get(url)
    if r.text=='':
        return None

    df = pd.read_html(StringIO(r.text))[0]
    df.columns = df.columns.get_level_values(1)
    df = df.drop(['次日漲停價', '次日跌停價'], axis=1)
    not_need = ['最後買價', '最後買量(千股)', '最後賣價', '最後賣量(千股)']
    for i in not_need:
        if i in df.columns: 
            df = df.drop(i, axis=1)
    spl = str_date.split('/')
    df['股價日期'] = datetime(int(spl[0])+1911,int(spl[1]),int(spl[2]),0,0,0)
    df = revr(df,-1)
    df = df[~df.代號.str.contains('筆')]
    if corporation_only==True: 
        df = df[~df.代號.str.startswith('0')] 
        df = df[df.代號.apply(lambda x:len(x)==4)]
    df = clean(df)
    return df

def Price(dt, mkt):
    # 對照表
    mkt_mapping = {'上市':'sii','上櫃':'otc'}
    dt_mapping = {}
    if '/' not in dt:
        dt_mapping['sii_date']=dt
        dt_mapping['otc_date']=f'{int(dt[:-4])-1911}/{dt[-4:-2]}/{dt[-2:]}'
    else:
        dt_mapping['sii_date']=f'{int(dt[:-6])+1911}{dt[-5:-3]}{dt[-2:]}'
        dt_mapping['otc_date']=dt
    
    mkt = mkt_mapping[mkt]
    dt = dt_mapping[f'{mkt}_date']
    price = siiPrice(dt) if mkt=='sii' else otcPrice(dt)
    return price

# 合併上市上櫃並簡化欄位
def allPrice(dt):
    sii_p = Price(dt, '上市')
    sii_p = sii_p[['股價日期', '證券代號', '證券名稱', '收盤價']]
    sii_p = sii_p.rename(columns = {'證券代號':'公司代號', '證券名稱':'公司名稱'})
    otc_p = Price(dt, '上櫃')
    otc_p = otc_p[['股價日期', '代號', '名稱', '收盤']]
    otc_p = otc_p.rename(columns = {'代號':'公司代號', '名稱':'公司名稱', '收盤':'收盤價'})
    price = pd.concat([sii_p,otc_p])
    return price   
        
#############################

# 營益分析 / 財務結構分析
class FinanceRatio:
    m_mapping = {'上市':'sii','上櫃':'otc'}
    base_url = 'https://mops.twse.com.tw/mops/web/'
    p_mapping = { # 損益表':base_url+'t163sb04','資產負債表':base_url+'t163sb05',
                 '營益分析':base_url+'t163sb06'
                ,'財務結構分析':base_url+'t51sb02'}
    old_p_mapping = { # '損益表':base_url+'t51sb08','資產負債表':base_url+'t51sb07',
                 '營益分析':base_url+'t51sb06'
                ,'財務結構分析':base_url+'ajax_t51sb02'}

    def __init__(self, mkt_type, year, season, purpose, \
                 m_mapping=m_mapping, p_mapping=p_mapping, old_p_mapping=old_p_mapping, smp=True):
        year = year if year < 1000 else year-1911
        self.year = year #yyy
        self.season = '0'+str(season) if type(season)==int else season
        self.mkt_type = m_mapping[mkt_type] if mkt_type in m_mapping else None
        self.purpose = purpose
        p_mapping = p_mapping if year>=102 else old_p_mapping
        self.url = p_mapping[self.purpose] if self.purpose in p_mapping else None
        self.smp = smp
    
    def add_raw(self):
        form = {'encodeURIComponent':1,
            'step':1,
            'firstin':1,
            'off':1,
            'TYPEK':self.mkt_type,
            'year':str(self.year),
            'season':self.season
            }
        form['ifrs']='Y' if self.year>=102 else 'N'            
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) \
                    AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}    
        r = requests.post(self.url, form, headers=headers)
        r.encoding = 'utf8'
        dfs = pd.read_html(StringIO(r.text))
        self.raw_data = dfs
        
    def unify(self):
        if self.purpose=='營益分析':
            dfs = [i for i in self.raw_data if i.shape[0]>5]
            dfs = [i for i in dfs if i.shape[1]>5]
            data = dfs[0]
            data.columns = ['公司代號','公司名稱','營業收入(百萬元)','毛利率(%)','營業利益率(%)','稅前純益率(%)','稅後純益率(%)']
            data = data[data['公司代號']!='公司代號']
            data = data.reset_index().drop('index', axis=1)
            data['財報年度'] = self.year+1911 #yyyy
            data['季'] = self.season
            data = revr(data,-2)
            data = clean(data)
            self.data = data

        elif self.purpose=='財務結構分析':
            dfs = [i for i in self.raw_data if i.shape[0]>5]
            dfs = [i for i in dfs if i.shape[1]>5]
            data = dfs[0]
            data.columns = data.columns.get_level_values(1)
            data = data[data['公司代號']!='公司代號']
            data = data.reset_index().drop('index', axis=1)
            data.rename(columns={'股東權益報酬率(%)':'權益報酬率(%)'
                                 ,'不動產、廠房及設備週轉率(次)':'固定資產週轉率(次)'
                                 ,'負債佔資產比率(%)':'負債比率(%)'
                                 ,'公司簡稱':'公司名稱'}, inplace=True)
            data['財報年度'] = self.year+1911 #yyyy
            # data['季'] = self.season
            data = revr(data,-1)
            if self.smp==True :
                clms = list(data.columns)
                clms = [i for i in clms if i not in \
                       ['平均收現日數','平均售貨日數','平均銷貨日數'
                        ,'長期資金佔不動產、廠房及設備比率(%)','純益率(%)','長期資金佔固定資產比率(%)'
                        ,'應收款項收現日數','稅前純益佔實收資本比率(%)','營業利益佔實收資本比率(%)']]
                data = data[clms]
            data = clean(data)
            self.data = data
            
#############################

# 營收
class Revenue:
    m_mapping = {'上市':'sii','上櫃':'otc'}
    base_url = 'https://mops.twse.com.tw/nas/t21/{}/t21sc03_{}_{}_0.html' 
    def __init__(self, mkt_type, year, month, url=base_url, m_mapping=m_mapping):
        self.mkt_type = m_mapping[mkt_type] if mkt_type in m_mapping else None
        year = year if year < 1000 else year-1911
        self.year = year #yyy
        self.month = month
        self.url = url.format(self.mkt_type, self.year, self.month)
        
    def add_raw(self):
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36'}    
        r = requests.get(self.url, headers=headers)
        r.encoding = 'big5'
        dfs = pd.read_html(StringIO(r.text))
        self.raw_data = dfs
        
    def unify(self, smp=True):
        data = pd.concat([data for data in self.raw_data if data.shape[1] <= 11 and data.shape[1] > 5]\
                       ,axis=0,ignore_index=True)
        if 'levels' in dir(data.columns):
            data.columns = data.columns.get_level_values(1)
        else:
            data = data[list(range(0,10))]
            column_index = data.index[(data[0] == '公司代號')][0]
            data.columns = data.iloc[column_index]
        data['當月營收'] = pd.to_numeric(data['當月營收'], 'coerce')
        data = data[~data['當月營收'].isnull()]
        data = data[~data['公司代號'].str.contains('合計')]
        if '備註' not in data.columns:
            data['備註'] = '-'
        data.drop_duplicates(subset='公司代號', keep='first', inplace=True)
        # 置換例外資料
        if (self.year,self.month)==(102,1):
            data.replace(to_replace='不適用', value=np.NaN, inplace=True)            
        data = data.drop('備註', axis=1)
        data['年'] = self.year
        data['月'] = self.month
        if smp==True:
            clms = ['年','月','公司代號','公司名稱','當月營收','去年當月營收','去年同月增減(%)']
        else:
            clms = ['年','月','公司代號','公司名稱','當月營收','去年當月營收','去年同月增減(%)'\
                    ,'上月營收','上月比較增減(%)','前期比較增減(%)','去年累計營收','當月累計營收']
        data = data[clms]
        data = data.rename(columns={'當月營收':f'{self.month}月營收'
                            ,'去年當月營收':f'去年{self.month}月營收'
                            ,'去年同月增減(%)':f'{self.month}月營收年成長(%)'})
        data = clean(data)        
        self.data = data
        
# 近3月營收 YOY(%)
def last3MthRvnuGrw(y,last_m=3):
    str_last_m = '0'+str(last_m) if last_m<=9 else str(last_m)
    last_ymd = f'{y}{str_last_m}01'
    YmList = [add_months(last_ymd, i).strftime("%Y%m") for i in range(0,-3,-1)]
    print(f'last 3 month rvnu period = {YmList[0]} - {YmList[2]}')
    r_container = {}
    for seq,ym in enumerate(YmList):
        y = int(ym[:4])
        m = ym[4:]
        m = int(m[1]) if m[0]=='0' else int(m)
        x = Revenue('上市', y, m)
        x.add_raw()
        x.unify()
        sii_r = x.data 
        x = Revenue('上櫃', y, m)
        x.add_raw()
        x.unify()
        otc_r = x.data
        # 合併資料
        r = pd.concat([sii_r,otc_r], axis=0, ignore_index=True)
        r = r.drop(['年','月'], axis=1)
        r_container[(y,m)]=r
    m_list = [i[1] for i in r_container.keys()]
    rvnu = reduce(lambda x,y:pd.merge(x,y,on=['公司代號','公司名稱'],how='inner'), list(r_container.values()))
    rvnu = reduce(lambda x,y:pd.merge(x,y,on=['公司代號','公司名稱'],how='inner'), list(r_container.values()))
    rvnu['近3月營收 平均YOY(%)'] = round((rvnu[f'{m_list[0]}月營收年成長(%)']\
                                    +rvnu[f'{m_list[1]}月營收年成長(%)']+rvnu[f'{m_list[2]}月營收年成長(%)'])/3,2)
    rvnu['近3月累計營收'] = rvnu[f'{m_list[0]}月營收']+rvnu[f'{m_list[1]}月營收']+rvnu[f'{m_list[2]}月營收']
    rvnu['去年近3月累計營收'] = rvnu[f'去年{m_list[0]}月營收'] + rvnu[f'去年{m_list[1]}月營收']+rvnu[f'去年{m_list[2]}月營收']
    rvnu['近3月累計營收 YOY(%)'] = round((rvnu['近3月累計營收']/rvnu['去年近3月累計營收']-1)*100,2) 
    rvnu['近3月累計營收 YOY(%)'] = rvnu['近3月累計營收 YOY(%)'].apply(lambda x:x if x!=np.inf else 1e-4)
    rvnu = rvnu[['公司代號','公司名稱','近3月營收 平均YOY(%)','近3月累計營收 YOY(%)']]
    return rvnu

#############################

# etf 股利
class EtfDiv:
    def __init__(self, year, start='0101', end='1231'):
        year = year if year > 1000 else year+1911
        self.year = year #yyyy
        self.start = start
        self.end = end
        self.url = f"https://www.twse.com.tw/exchangeReport/TWT49U?response=json&strDate={year}{start}&endDate={year}{end}"
        self.headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36'}
        
    def add_raw(self):
        r = requests.get(self.url, headers=self.headers)  
        d = json.loads(r.text)
        data = pd.DataFrame(data=d['data'], columns=d['fields'])
        data = data[data.股票代號.str.startswith('0')]
        self.raw_data = data

    def unify(self):
        self.raw_data['詳細資料'] = self.raw_data['詳細資料'].apply(lambda x:x.split("'")[1][9:])
        self.raw_data.drop(['漲停價格','跌停價格','開盤競價基準','最近一次申報資料 季別/日期',\
                   '最近一次申報每股 (單位)淨值','最近一次申報每股 (單位)盈餘'], axis=1, inplace=True)
        self.raw_data['資料日期'] = self.raw_data['詳細資料'].apply(lambda x:x[-8:])
        self.raw_data = self.raw_data[self.raw_data['除權息前收盤價']!=self.raw_data['減除股利參考價']]
        
        def stockDividend(dtl):
            headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36'}
            basic_url = 'https://www.twse.com.tw/zh/'
            url = basic_url+dtl
            r = requests.get(url, headers=headers)
            d = pd.read_html(StringIO(r.text))[0]
            tgt = d.iloc[4][1].split(' ')[0]
            time.sleep(3)
            return tgt

        def cashDividend(dtl):
            headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36'}
            basic_url = 'https://www.twse.com.tw/zh/'
            url = basic_url+dtl
            r = requests.get(url, headers=headers)
            d = pd.read_html(StringIO(r.text))[0]
            tgt = d.iloc[2][1].split(' ')[0]
            time.sleep(3)
            return tgt
        
        x1 = self.raw_data[self.raw_data['權/息']=='息']
        x1['現金股利'] = x1['權值+息值']
        x1['股票股利'] = 0
        x2 = self.raw_data[self.raw_data['權/息']=='權']
        x2['現金股利'] = 0
        x2['股票股利'] = x2['詳細資料'].apply(stockDividend)
        x12 = self.raw_data[self.raw_data['權/息']=='權息']
        x12['現金股利']=x12['詳細資料'].apply(cashDividend)
        x12['股票股利']=x12['詳細資料'].apply(stockDividend)

        d_all = pd.concat([x1,x2,x12],ignore_index=True)
        d_all = d_all[['資料日期', '股票代號', '股票名稱', '現金股利', '股票股利', '詳細資料']]
        self.data = d_all
        
# 公司股利
class Dividend:
    m_mapping = {'上市':'sii','上櫃':'otc'}
    def __init__(self, mkt_type, year, m_mapping=m_mapping):
        year = year if year <= 1000 else year-1911
        self.mkt_type = m_mapping[mkt_type]
        self.year = str(year) #yyy
        self.url = f"https://mops.twse.com.tw/mops/web/ajax_t108sb27"
        self.headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36'}
        
    def add_raw(self):
        form = {
            "step": "1",
            "firstin": "1",
            "TYPEK": self.mkt_type,
            "year": self.year,
            "type": "2"
        }
        r = requests.post(self.url, data=form, headers=self.headers)  
        self.raw_data = pd.read_html(StringIO(r.text))[0]

    def unify(self):
        d = self.raw_data
        d.columns = d.columns.get_level_values(-1)
        d = d[d['公司代號']!='公司代號']
        d['資料日期'] = d[['除權交易日' , '除息交易日']].apply(lambda x:x[0] if x[0] is not np.nan else x[1], axis=1)
        for i in ['盈餘分配之股東現金股利(元/股)' , '法定盈餘公積、資本公積發放之現金(元/股)', \
                 '盈餘轉增資配股(元/股)' , '法定盈餘公積、資本公積轉增資配股(元/股)']:
            d[i] = d[i].replace(to_replace='-', value=np.nan)
        d['現金股利'] = d[['盈餘分配之股東現金股利(元/股)' , '法定盈餘公積、資本公積發放之現金(元/股)']].apply\
            (lambda x:float(x[0])+float(x[1]) if x[0] is not np.nan and x[1] is not np.nan else np.nan, axis=1)
        d['股票股利'] = d[['盈餘轉增資配股(元/股)' , '法定盈餘公積、資本公積轉增資配股(元/股)']].apply\
            (lambda x:(float(x[0])+float(x[1]))*100 if x[0] is not np.nan and x[1] is not np.nan else np.nan, axis=1)
        d = d[['資料日期', '公司代號', '公司名稱', '現金股利', '股票股利']]
        d = d.fillna(0)
        d = d[(d['現金股利']!=0) | (d['股票股利']!=0)]
        d = d.drop_duplicates()
        def f(x):
            x = x.split('/')
            return str(int(x[0])+1911)+x[1]+x[2]
        d['資料日期'] = d['資料日期'].apply(f)
        d['MKT'] = '上市' if self.mkt_type=='sii' else '上櫃'
        cols = list(d.columns)
        d = d[cols[:1]+cols[-1:]+cols[1:-1]]
        self.data = d

# 減資換發新股
class CptlReduct:
    m_mapping = {'上市':'sii','上櫃':'otc'}
    def __init__(self, mkt_type, year, start='0101', end='1231', m_mapping=m_mapping):
        eg_year = year if year > 1000 else year+1911 #yyyy
        cn_year = year if year < 1000 else year-1911
        self.mkt_type = m_mapping[mkt_type]
        if self.mkt_type=='sii':
            self.year = eg_year 
            self.full_start = f'{eg_year}{start}'
            self.full_end = f'{eg_year}{end}'
            self.url = f'https://www.twse.com.tw/exchangeReport/TWTAUU?response=json&strDate={self.full_start}&endDate={self.full_end}'
        elif self.mkt_type=='otc':
            self.year = cn_year 
            self.full_start = f'{cn_year}/{start[:2]}/{start[2:]}'
            self.full_end = f'{cn_year}/{end[:2]}/{end[2:]}'
            self.url = f'https://www.tpex.org.tw/web/stock/exright/revivt/revivt_result.php?l=zh-tw&d={self.full_start}&ed={self.full_end}&s=0,asc,0&o=csv'
        self.headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36'}
        
    def add_raw(self):
        if self.mkt_type=='sii':
            r = requests.get(self.url, headers=self.headers)  
            d = json.loads(r.text)
            data = pd.DataFrame(data=d['data'], columns=d['fields'])
            data = data.rename(columns={'停止買賣前收盤價格':'停止買賣前價格'})
            self.raw_data = data
        elif self.mkt_type=='otc':
            r = requests.get(self.url, headers=self.headers)  
            d = pd.read_csv(StringIO(r.text), header = ["股票代號" in l for l in r.text.split("\n")].index(True))
            d = d[~d.股票代號.isnull()]
            d.股票代號 = d.股票代號.astype(int)
            d.股票代號 = d.股票代號.astype(str)
            data = d.rename(columns={'恢復買賣日期 ':'恢復買賣日期'
                                    ,'最後交易日之收盤價格':'停止買賣前價格'
                                    ,'減資恢復買賣開始日參考價格':'恢復買賣參考價'
                                    ,'開始交易基準價':'開盤競價基準'})
            data['恢復買賣日期'] = data['恢復買賣日期'].apply(lambda x:f'{x[:3]}/{x[3:5]}/{x[5:]}')
            self.raw_data = data

    def unify(self):
        data = self.raw_data
        data = data[data['停止買賣前價格']!=data['恢復買賣參考價']]
        data.drop(['漲停價格','跌停價格','開盤競價基準','除權參考價'], axis=1, inplace=True)
        
        # 102 年前上櫃無減資資料
        if self.mkt_type=='otc' and self.year<102:
            self.data = self.raw_data
            
        elif self.mkt_type=='sii':
            data['詳細資料'] = data['詳細資料'].apply(lambda x:x.split("'")[1][9:])
            def rdc(x):
                p1, p2, reason, dtl = x[0], x[1], x[2], x[3]
                if reason=='彌補虧損':
                    exchange_ratio,refund = float(p1)/float(p2)*1000,0
                else:
                    stockId = dtl.split('STK_NO=')[1].rstrip()
                    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36'}
                    basic_url = 'https://www.twse.com.tw/zh/'
                    url = basic_url+dtl
                    r = requests.get(url, headers=headers)
                    d = pd.read_html(StringIO(r.text))[0]
                    exchange_ratio = float(d.iloc[3][1].split(' ')[0])
                    refund = float(d.iloc[4][1].split(' ')[0])
                    time.sleep(4)
                return exchange_ratio,refund
            tmpDtl = data[['停止買賣前價格','恢復買賣參考價','減資原因','詳細資料']].apply(rdc, axis=1)                    
            data['每千股換發股數'] = tmpDtl.apply(lambda x:x[0])
            data['每股退還金額'] = tmpDtl.apply(lambda x:x[1])
            cols = ['恢復買賣日期', '股票代號', '名稱', '停止買賣前價格', '恢復買賣參考價', '減資原因', '每千股換發股數', '每股退還金額']
            data = data[cols]
            data = data.rename(columns={'恢復買賣日期':'資料日期'})
            for i in ['每千股換發股數', '每股退還金額']:
                data[i] = data[i].apply(lambda x:round(x,2))
            for i in ['停止買賣前價格', '恢復買賣參考價', '每千股換發股數', '每股退還金額']:
                data[i] = data[i].astype(float)

            def f(x):
                x = x.split('/')
                return str(int(x[0])+1911)+x[1]+x[2]
            data['資料日期'] = data['資料日期'].apply(f)
            data['MKT'] = '上市' if self.mkt_type=='sii' else '上櫃'
            cols = list(data.columns)
            data = data[cols[:1]+cols[-1:]+cols[1:-1]]
            self.data = data
            
        elif self.mkt_type=='otc' and self.year>=102:
            # 簡化計算
            def rdc(x):
                p1, p2 = x[0], x[1]
                exchange_ratio,refund = float(p1)/float(p2)*1000,0
                return exchange_ratio,refund
            tmpDtl = data[['停止買賣前價格','恢復買賣參考價']].apply(rdc, axis=1)                  
            data['每千股換發股數'] = tmpDtl.apply(lambda x:x[0])
            data['每股退還金額'] = tmpDtl.apply(lambda x:x[1])
            cols = ['恢復買賣日期', '股票代號', '名稱', '停止買賣前價格', '恢復買賣參考價', '減資原因', '每千股換發股數', '每股退還金額']
            data = data[cols]
            data = data.rename(columns={'恢復買賣日期':'資料日期'})
            for i in ['每千股換發股數', '每股退還金額']:
                data[i] = data[i].apply(lambda x:round(x,2))
            for i in ['停止買賣前價格', '恢復買賣參考價', '每千股換發股數', '每股退還金額']:
                data[i] = data[i].astype(float)

            def f(x):
                x = x.split('/')
                return str(int(x[0])+1911)+x[1]+x[2]
            data['資料日期'] = data['資料日期'].apply(f)
            data['MKT'] = '上市' if self.mkt_type=='sii' else '上櫃'
            cols = list(data.columns)
            data = data[cols[:1]+cols[-1:]+cols[1:-1]]
            self.data = data
            
        

        
        
        
        
