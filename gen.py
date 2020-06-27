from .stockindc import *

def tej_industry_data(fileName='tej.csv'):
    return pd.read_csv(fileName)

def join_tej(d, d_key='公司代號'):
    tej = tej_industry_data(fileName='tej.csv')
    tej = tej[['ID', 'NAME', 'MKT', 'INDUSTRY_NAME_1', 'INDUSTRY_NAME_2']]
    tej['ID'] = tej['ID'].astype(str)
    d = pd.merge(d, tej, how='inner', left_on=d_key, right_on='ID')
    d = d.drop(['ID', 'NAME'], axis=1)
    d.rename(columns = {'MKT':'市場'
                        ,'INDUSTRY_NAME_1':'主產業'
                        ,'INDUSTRY_NAME_2':'次產業'}
                        , inplace=True)
    d['市場'] = d['市場'].apply(lambda x:'上市' if x=='TSE' else '上櫃')
    cols = list(d.columns)
    cols = cols[:2]+cols[-3:]+cols[2:-3]
    d = d[cols]
    if '本益比' in cols:
        pe1 = d.groupby('主產業')['本益比'].median().reset_index().rename(columns={'本益比':'PE1 中位數'})
        pe2 = d.groupby('次產業')['本益比'].median().reset_index().rename(columns={'本益比':'PE2 中位數'})
        d = pd.merge(pd.merge(d,pe1),pe2)
        for i in ['PE1 中位數', 'PE2 中位數']:
            d[i] = d[i].replace(0, 1e-4)
    d['相對 PE1 比率'] = round(d['本益比'] / d['PE1 中位數'], 4)
    d['相對 PE2 比率'] = round(d['本益比'] / d['PE2 中位數'], 4)
    return d

# functions for processing convenience

# 取得該月首交易日
def FirstTxnDate(eg_yr, mkt='sii', mh=4, dt=11, ft=siiPrice, reverse=False):
    cn_yr = eg_yr-1911
    mh = str(mh) if mh>=10 else '0'+str(mh)
    dt = str(dt) if dt>=10 else '0'+str(dt)
    test_ymd = f'{eg_yr}{mh}{dt}'
    
    d_test = ft(test_ymd)
    while d_test is None:
        if reverse==False:
            d_plus_one = datetime.strptime(test_ymd, "%Y%m%d").date()+timedelta(days=1)
            test_ymd = datetime.strftime(d_plus_one, "%Y%m%d")
            d_test = siiPrice(test_ymd)
        elif reverse==True:
            d_minus_one = datetime.strptime(test_ymd, "%Y%m%d").date()-timedelta(days=1)
            test_ymd = datetime.strftime(d_minus_one, "%Y%m%d")
            d_test = siiPrice(test_ymd)

    eg_yr,mh,dt = test_ymd[:4],test_ymd[4:6],test_ymd[6:]
    
    if mkt=='sii':
        return f'{eg_yr}{mh}{dt}'
    elif mkt=='otc':
        return f'{cn_yr}/{mh}/{dt}'
    else:
        return None

# 取得該月末交易日
def LastTxnDate(eg_yr, mkt, mh=12, dt=31, ft=siiPrice):
    cn_yr = eg_yr-1911
    mh = str(mh) if mh>=10 else '0'+str(mh)
    dt = str(dt) if dt>=10 else '0'+str(dt)
    test_ymd = f'{eg_yr}{mh}{dt}'
    
    d_test = ft(test_ymd)
    while d_test is None:
        d_plus_one = datetime.strptime(test_ymd, "%Y%m%d").date()+ timedelta(days=-1)
        test_ymd = datetime.strftime(d_plus_one, "%Y%m%d")
        d_test = siiPrice(test_ymd)
        
    eg_yr,mh,dt = test_ymd[:4],test_ymd[4:6],test_ymd[6:]
    
    if mkt=='sii':
        return f'{eg_yr}{mh}{dt}'
    elif mkt=='otc':
        return f'{cn_yr}/{mh}/{dt}'
    else:
        return None

###############  combine various data ############### 

# 營益分析 inner join 財務結構分析
def YearlyRatio(y):
    # financeStatement - 年度財務比率數值
    # print(f'{y} stage = siiRatio', end=' ')
    x = FinanceRatio('上市', y, 4, '營益分析')
    x.add_raw()
    x.unify()
    incm = x.data
    x = FinanceRatio('上市', y, None, '財務結構分析')
    x.add_raw()
    x.unify()
    baln = x.data
    sii = pd.merge(incm[[i for i in incm.columns if i!='季']], baln, how='inner', on=['財報年度', '公司代號', '公司名稱'])
    # print('otcRatio')
    x = FinanceRatio('上櫃', y, 4, '營益分析')
    x.add_raw()
    x.unify()
    incm = x.data
    x = FinanceRatio('上櫃', y, None, '財務結構分析')
    x.add_raw()
    x.unify()
    baln = x.data
    otc = pd.merge(incm[[i for i in incm.columns if i!='季']], baln, how='inner', on=['財報年度', '公司代號', '公司名稱']) 
    ratio = pd.concat([sii,otc], axis=0, ignore_index=True)
    ratio = clean(ratio)
    return ratio





# (財務比率 left join 近3月營收 left join 測試日收盤價格) inner join TEJ
def YearlyFinanceReport(y, import_ratio=False, tej=True):
    # financeRatio - 年度財務比率數值
    if import_ratio==False:
        ratio = YearlyRatio(y)
    else:
        ratio = pd.read_csv(f'./fnt/fnt_{y}.csv')
        
    # revenue - 隔年1～3月的營收
    rvnu = last3MthRvnuGrw(y+1) # 隔年
    
    # price - 財報+隔年1～3月的營收 揭露後首個交易日的收盤價
    x = date.today()
    if x<=datetime.strptime(f'{x.year}0410', "%Y%m%d").date(): # 若在完整營收公布前想先看
        dt = FirstTxnDate(eg_yr=y+1, mkt='sii', mh=4, dt=1)
    else:
        dt = FirstTxnDate(eg_yr=y+1, mkt='sii') # 隔年
    price = allPrice(dt)
    price = price.drop('股價日期', axis=1).rename(columns = {'收盤價':'年報公佈後收盤價'})
    
    # merge & process data     
    for i in [ratio,rvnu,price]:
        i['公司代號'] = i['公司代號'].astype(str)
    data = reduce(lambda x,y:pd.merge(x,y,on=['公司代號','公司名稱'],how='left'), [ratio,rvnu,price])
    data = clean(data)
    data['每股盈餘(元)'] = data['每股盈餘(元)'].apply(lambda x:x if x!=0 else 1e-4)
    data['本益比'] = round(data['年報公佈後收盤價'] / data['每股盈餘(元)'], 2)
    cols = list(data.columns)
    cols = cols[1:3]+cols[:1]+cols[3:]
    data = data[cols]
    
    # tej
    if tej==True:
        data = join_tej(data)
    return data

def YearlyAdj(y, adjusting_report):
    mapping = {'etf':EtfDiv
            ,'div':Dividend
            ,'rdc':CptlReduct}
    f = mapping[adjusting_report]
    if f==EtfDiv:
        x = f(y)
        x.add_raw()
        x.unify()
        data = x.data
    else:
        x_sii = f('上市', y)
        x_sii.add_raw()
        x_sii.unify()
        x_otc = f('上櫃', y)
        x_otc.add_raw()
        x_otc.unify()
        data = pd.concat([x_sii.data, x_otc.data], ignore_index=True) if not x_otc.data.empty else x_sii.data
    return data
