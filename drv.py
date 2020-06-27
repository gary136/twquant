import matplotlib.pyplot as plt
from .stockindc import *
from .gen import *

# 計算 YOY
def add_indicator_growth(d_current, d_last, special_indicator=None):
    cmpr = ['營業收入(百萬元)', '毛利率(%)', '營業利益率(%)', \
           '稅後純益率(%)', '資產報酬率(%)', '權益報酬率(%)', '現金再投資比率(%)'] if special_indicator==None else special_indicator

    # 命名新欄位
    names_mapping = {}
    for c in [c for c in cmpr if '營業收入' not in c]:
        names_mapping[c] = f'{c[:-3]} YOY(%)'
    orgn_col = ['公司代號']+cmpr
    drv_col = ['公司代號']+['營業收入 YOY(%)']+list(names_mapping.values())
    
    # 計算差異
    d_cmpr = pd.merge(d_current[orgn_col], d_last[orgn_col], how='left', on=['公司代號']) # 合併今年與去年
    d_cmpr['營業收入 YOY(%)'] = round(((d_cmpr['營業收入(百萬元)_x'] / d_cmpr['營業收入(百萬元)_y'])-1)*100, 2) # 計算變化
    for c in names_mapping:
        d_cmpr[names_mapping[c]] = d_cmpr[f'{c}_x'] - d_cmpr[f'{c}_y']
    d_cmpr = d_cmpr[drv_col]  # 只取包含 YOY(%) 的欄位
    
    # 合併 今年資料 與 算出之成長百分比
    d_res = pd.merge(d_current, d_cmpr, how='inner', on=['公司代號'])
    d_res = d_res.fillna(1e-4)
    
    return d_res

# 還原價格
class AdjPrice:    
    def __init__(self,p_current,p_next):
        self.p_current=p_current
        self.data=p_current
        self.p_next=p_next
        self.test_start_year=list(self.p_current.股價日期)[0].year
        self.test_end_year=list(self.p_next.股價日期)[0].year
        self.start_ymd=datetime.strftime(list(self.p_current.股價日期)[0], "%Y%m%d")
        self.end_ymd=datetime.strftime(list(self.p_next.股價日期)[0], "%Y%m%d")
        
    def addPrice(self):
        data = pd.merge(self.p_current, self.p_next, how='inner', on=('公司代號', '公司名稱'))
        data = data[data['收盤價_y']!=0]
        data = data[['公司代號', '公司名稱', '股價日期_x', '收盤價_x', '股價日期_y', '收盤價_y']]
        self.data=data
        
    def adjDiv(self):
        original_price_name = '收盤價_y'
        if self.test_start_year != self.test_end_year:
            div = pd.concat([pd.read_csv(f'./div/div_{self.test_start_year}.csv')\
                           ,pd.read_csv(f'./div/div_{self.test_end_year}.csv')], ignore_index=True)
            div = div[(div['資料日期']>=int(f'{self.start_ymd}')) & (div['資料日期']<int(f'{self.end_ymd}'))]            
        else:
            div = pd.read_csv(f'./div/div_{self.test_start_year}.csv')
            div = div[(div['資料日期']>=int(f'{self.start_ymd}')) & (div['資料日期']<int(f'{self.end_ymd}'))]            
        div = div.rename(columns={'股票代號':'公司代號'})
        div = div[['公司代號', '現金股利', '股票股利']]
        div.公司代號 = div.公司代號.astype(str)
        self.div = div
        self.data = pd.merge(self.data,div,how='left',on='公司代號')
        self.data.現金股利 = self.data.現金股利.fillna(0)
        self.data.股票股利 = self.data.股票股利.fillna(0)
        self.data['還原股利後價格'] = self.data[[original_price_name, '現金股利', '股票股利']].apply\
                                (lambda x:(x[0]*(1000+x[2])/1000)+x[1], axis=1)
        data = self.data.drop_duplicates()

        # address companines issueing multiple dividents
        mtp_div_companies = [k for (k,v) in Counter(data.公司代號).items() if v > 1]
        if mtp_div_companies!=[]:
            def recalculate_div(companyId,data):
                data_exclude = data[data.公司代號!=companyId]    
                tgt = data[data.公司代號==companyId]
                tgt = tgt.reset_index().drop('index', axis=1)
                div_cols = ['公司代號','現金股利','股票股利']
                recalculate_cols = ['還原股利後價格']
                same_cols = ['公司代號']+list(filter(lambda x:x not in div_cols+recalculate_cols, list(tgt.columns)))
                tgt_div = tgt[div_cols]
                tgt_div = tgt_div.groupby('公司代號').sum().reset_index()
                tgt_same = tgt.loc[[0]][same_cols]
                tgt = pd.merge(tgt_same,tgt_div,how='left',on='公司代號')
                tgt['還原股利後價格'] = tgt[[original_price_name, '現金股利', '股票股利']].apply\
                                        (lambda x:(x[0]*(1000+x[2])/1000)+x[1], axis=1)
                data = pd.concat([data_exclude,tgt],ignore_index=True)
                return data
            for i in mtp_div_companies:
                data = recalculate_div(i,data)
        self.data = data

    def adjEtf(self):
        original_price_name = '收盤價_y'
        if self.test_start_year != self.test_end_year:
            etf = pd.concat([pd.read_csv(f'./etf/etf_{self.test_start_year}.csv')\
                           ,pd.read_csv(f'./etf/etf_{self.test_end_year}.csv')], ignore_index=True)
            etf = etf[(etf['資料日期']>=int(f'{self.start_ymd}')) & (etf['資料日期']<int(f'{self.end_ymd}'))]            
        else:
            etf = pd.read_csv(f'./etf/etf_{self.test_start_year}.csv')
            etf = etf[(etf['資料日期']>=int(f'{self.start_ymd}')) & (etf['資料日期']<int(f'{self.end_ymd}'))]            
        etf = etf.rename(columns={'股票代號':'公司代號'})
        etf = etf[['公司代號', '現金股利', '股票股利']]
        etf.公司代號 = etf.公司代號.astype(str)
        self.etf = etf
        self.data = pd.merge(self.data,etf,how='left',on='公司代號')
        self.data.現金股利 = self.data.現金股利.fillna(0)
        self.data.股票股利 = self.data.股票股利.fillna(0)
        self.data['還原股利後價格'] = self.data[[original_price_name, '現金股利', '股票股利']].apply\
                                (lambda x:(x[0]*(1000+x[2])/1000)+x[1], axis=1)
        data = self.data.drop_duplicates()

        # address ETFs issueing multiple dividents
        mtp_div_ETFs = [k for (k,v) in Counter(data.公司代號).items() if v > 1]
        if mtp_div_ETFs!=[]:
            def recalculate_div(etfId,data):
                data_exclude = data[data.公司代號!=etfId]    
                tgt = data[data.公司代號==etfId]
                tgt = tgt.reset_index().drop('index', axis=1)
                div_cols = ['公司代號','現金股利','股票股利']
                recalculate_cols = ['還原股利後價格']
                same_cols = ['公司代號']+list(filter(lambda x:x not in div_cols+recalculate_cols, list(tgt.columns)))
                tgt_div = tgt[div_cols]
                tgt_div = tgt_div.groupby('公司代號').sum().reset_index()
                tgt_same = tgt.loc[[0]][same_cols]
                tgt = pd.merge(tgt_same,tgt_div,how='left',on='公司代號')
                tgt['還原股利後價格'] = tgt[[original_price_name, '現金股利', '股票股利']].apply\
                                        (lambda x:(x[0]*(1000+x[2])/1000)+x[1], axis=1)
                data = pd.concat([data_exclude,tgt],ignore_index=True)
                return data
            for i in mtp_div_ETFs:
                data = recalculate_div(i,data)
        self.data = data
        
    def adjRdc(self):
        original_price_name = '還原股利後價格'
        if self.test_start_year != self.test_end_year:
            rdc = pd.concat([pd.read_csv(f'./rdc/rdc_{self.test_start_year}.csv')\
                           ,pd.read_csv(f'./rdc/rdc_{self.test_end_year}.csv')], ignore_index=True)
            rdc = rdc[(rdc['資料日期']>=int(f'{self.start_ymd}')) & (rdc['資料日期']<int(f'{self.end_ymd}'))]            
        else:
            rdc = pd.read_csv(f'./rdc/rdc_{self.test_start_year}.csv')
            rdc = rdc[(rdc['資料日期']>=int(f'{self.start_ymd}')) & (rdc['資料日期']<int(f'{self.end_ymd}'))]            
        rdc = rdc.rename(columns={'股票代號':'公司代號'})
        rdc = rdc[['公司代號', '每千股換發股數', '每股退還金額']]
        rdc.公司代號 = rdc.公司代號.astype(str)
        self.rdc = rdc
        self.data = pd.merge(self.data,rdc,how='left',on='公司代號')
        self.data['每千股換發股數'] = self.data['每千股換發股數'].fillna(0)
        self.data['每股退還金額'] = self.data['每股退還金額'].fillna(0)
        self.data['還原股利及減資價格'] = self.data[[original_price_name, '每千股換發股數', '每股退還金額']].apply\
                                (lambda x:x[0] if x[1]==0 else x[0]*(x[1]/1000)+x[2], axis=1)
        data = self.data.drop_duplicates()
        
        # address companines engaging multiple reductions
        mtp_rdc_companies = [k for (k,v) in Counter(data.公司代號).items() if v > 1]
        if mtp_rdc_companies!=[]:
            def recalculate_rdc(companyId,data):
                data_exclude = data[data.公司代號!=companyId]    
                tgt = data[data.公司代號==companyId]
                tgt = tgt.reset_index().drop('index', axis=1)
                rdc_cols = ['公司代號', '每千股換發股數', '每股退還金額']
                recalculate_cols = ['還原股利及減資價格']
                same_cols = ['公司代號']+list(filter(lambda x:x not in rdc_cols+recalculate_cols, list(tgt.columns)))
                tgt_xhng = tgt[['公司代號', '每千股換發股數']]
                tgt_xhng = (tgt_xhng.groupby('公司代號').apply(np.prod)/1000).reset_index()
                tgt_withdraw = tgt[['公司代號', '每股退還金額']]
                tgt_withdraw = tgt_withdraw.groupby('公司代號').sum().reset_index()
                tgt_rdc = pd.merge(tgt_xhng,tgt_withdraw,how='inner',on='公司代號')                
                tgt_same = tgt.loc[[0]][same_cols]
                tgt = pd.merge(tgt_same,tgt_rdc,how='left',on='公司代號')
                tgt['還原股利及減資價格'] = tgt[[original_price_name, '每千股換發股數', '每股退還金額']].apply\
                                        (lambda x:x[0] if x[1]==0 else x[0]*(x[1]/1000)+x[2], axis=1)
                data = pd.concat([data_exclude,tgt],ignore_index=True)
                return data
            for i in mtp_rdc_companies:
                data = recalculate_rdc(i,data)
        self.data = data

def YearlyPrice(yr):
    p_1 = allPrice(FirstTxnDate(yr))
    p_2 = allPrice(FirstTxnDate(yr+1, mh=4, dt=10, reverse=True))
    x = AdjPrice(p_1,p_2)
    x.addPrice()
    x.adjDiv()
    x.adjRdc()
    return x.data

def YearlyComparingStock(yr,comparing_stock = '0050'):
    tgt_1 = siiPrice(FirstTxnDate(yr), corporation_only=False)
    tgt_2 = siiPrice(FirstTxnDate(yr+1,reverse=True), corporation_only=False)
    tgt_1 = tgt_1[tgt_1.證券代號==comparing_stock].rename(columns={'證券代號':'公司代號', '證券名稱':'公司名稱'})
    tgt_2 = tgt_2[tgt_2.證券代號==comparing_stock].rename(columns={'證券代號':'公司代號', '證券名稱':'公司名稱'})
    x = AdjPrice(tgt_1, tgt_2)
    x.addPrice()
    x.adjEtf()
    return x.data

# 還原價格 - 年報酬 - 同期台灣50之報酬
class BackTesting:    
    def __init__(self,financial_data,adjusted_price,comparing_stock):
        self.financial_data=financial_data
        self.price=adjusted_price[['公司代號', '公司名稱', '股價日期_x', '收盤價_x', '股價日期_y', '還原股利及減資價格']]
        self.comparing_stock=comparing_stock
        self.statement_year=list(financial_data.財報年度)[0]
        self.test_start_year=list(adjusted_price.股價日期_x)[0].year
        self.test_end_year=list(adjusted_price.股價日期_y)[0].year
        self.start_ymd=datetime.strftime(list(adjusted_price.股價日期_x)[0], "%Y%m%d")
        self.end_ymd=datetime.strftime(list(adjusted_price.股價日期_y)[0], "%Y%m%d")
        self.data = pd.merge(financial_data.drop('年報公佈後收盤價', axis=1), self.price, how='inner', on=('公司代號', '公司名稱'))

    def getRvn(self):
        self.data = self.data.rename(columns={'還原股利及減資價格':'還原股價'})
        self.data['年報酬(%)'] = round(((self.data['還原股價']/self.data['收盤價_x'])-1)*100,2)
        self.data['還原股價'] = self.data['還原股價'].apply(lambda x:round(x,2))
            
    def get_comparing_metrics(self):
        ix1 = self.comparing_stock.收盤價_x[0]
        ix2 = round(self.comparing_stock.還原股利後價格[0], 2)
        rev = round(((ix2)/ix1 -1)*100, 2)
        self.comparing_metrics = ix1,ix2,rev       
        self.data['勝過台灣50'] = self.data['年報酬(%)'].apply(lambda x:'Y' if x>self.comparing_metrics[2] else 'N')
        self.data['屌打台灣50'] = self.data['年報酬(%)'].apply(lambda x:'Y' if x>self.comparing_metrics[2]+7.5 else 'N')
        self.win_rate = round(len([i for i in list(self.data['勝過台灣50'])\
                                if i!='N']) / len(list(self.data['勝過台灣50'])) * 100, 2)

    def introduction(self):
        print(f'use {self.statement_year} finance statement (which cannot be accessed till {int(self.start_ymd)-1}) to evaluate performance from {self.start_ymd} to {self.end_ymd}')
        
    @staticmethod
    def import_criteria(testing_object,function_with_criteria,verbose=True):
        data = function_with_criteria(testing_object.data)                    
        rtn = np.array(data['年報酬(%)'])
        rtn = rtn[~np.isnan(rtn)]
        rtn = np.array(list(filter(lambda x:x!=np.inf, rtn)))
        yearly_rtn = round(rtn.mean(), 2)
        excess_rtn = yearly_rtn - testing_object.comparing_metrics[2]
        win_rate = round(len([i for i in list(data['勝過台灣50']) if i!='N']) / len(list(data['勝過台灣50'])) * 100, 2)
        if verbose==True:
            print(f'財報年度 = {testing_object.statement_year}, 回測期間 = {testing_object.start_ymd}~{testing_object.end_ymd}')
            print(f'台灣50指數 {testing_object.comparing_metrics[0]} -> {testing_object.comparing_metrics[1]}, 年報酬 = {testing_object.comparing_metrics[2]}%, 未篩選前隨機個股報酬>台灣50比例 = {testing_object.win_rate}%')
            print(f'篩選股數 = {data.shape[0]}, 年報酬 = {yearly_rtn}%, 超額報酬 = {excess_rtn}%, 篩選個股報酬>台灣50比例 = {win_rate}%\n')
        return data, yearly_rtn
                
    @staticmethod
    def parse_criteria(df, crts):
        for i in crts:
            df = df[i]
        return df
    
################# example function_with_criteria #################
# def example_function(d):
#     c = [
#          d['資產報酬率 YOY(%)']>2.5
#         ,d['本益比']<35
#         ,d['近3月累計營收 YOY(%)']>-2.5
#         ]
#     return drv.BackTesting.parse_criteria(d, c)
################# example function_with_criteria #################




# 第一次需要執行
def download(x, start_year, end_year,force_writing=False):
    def check_then_write(function, dir_name):
        # check if dir exist
        if not os.path.exists(f'./{dir_name}'):
            os.mkdir(f'./{dir_name}')
            
        for y in range(start_year,end_year+1):
            # check if file exist
            file_path = os.path.join(f'./{dir_name}', f'{dir_name}_{y}.csv')
            print(f'current addressing file = {file_path}')
            if os.path.exists(file_path):
                if force_writing==True:
                    pass
                else:
                    writing_check = input('override existing file? ')
                    if writing_check!='y':
                        break
                if function in (YearlyRatio,YearlyPrice,YearlyComparingStock): 
                    data = function(y)
                elif function==YearlyFinanceReport: 
                    data = function(y, import_ratio=True) 
                else: 
                    data = function(y, adjusting_report=dir_name)
                data.to_csv(file_path, index=False, encoding='utf_8_sig')
            else:
                if function in (YearlyRatio,YearlyPrice,YearlyComparingStock): 
                    data = function(y)
                elif function==YearlyFinanceReport: 
                    data = function(y, import_ratio=True) 
                else: 
                    data = function(y, adjusting_report=dir_name)
                data.to_csv(file_path, index=False, encoding='utf_8_sig')

    if x=='ratio':
        check_then_write(YearlyRatio, 'fnt')
    elif x=='rpt':
        check_then_write(YearlyFinanceReport, x)
    elif x in ('etf', 'div', 'rdc'):
        check_then_write(YearlyAdj, x)
    elif x=='adjusting_price':
        check_then_write(YearlyPrice, x)
    elif x=='comparing_stock':
        check_then_write(YearlyComparingStock, x)

def SingleYearTesting(y, criteria, verbose=True):
    rpt = pd.read_csv(f'./rpt/rpt_{y}.csv')
        
    fnt = pd.read_csv(f'./fnt/fnt_{y-1}.csv')
    
    drv_rpt = add_indicator_growth(rpt, fnt)
    drv_rpt.公司代號 = drv_rpt.公司代號.astype(str)
    
    ajst_price = pd.read_csv(f'./adjusting_price/adjusting_price_{y+1}.csv')
    ajst_price.公司代號 = ajst_price.公司代號.astype(str)
    for stock_date in ('股價日期_x', '股價日期_y'):
        ajst_price[stock_date] = ajst_price[stock_date]\
                                    .apply(lambda x:datetime.strptime(x, "%Y-%m-%d") if type(x)==str else x)
        
    cmpr_stock = pd.read_csv(f'./comparing_stock/comparing_stock_{y+1}.csv')
    cmpr_stock.公司代號 = cmpr_stock.公司代號.astype(str)
    for stock_date in ('股價日期_x', '股價日期_y'):
        cmpr_stock[stock_date] = cmpr_stock[stock_date]\
                                    .apply(lambda x:datetime.strptime(x, "%Y-%m-%d") if type(x)==str else x)

    test_object = BackTesting(drv_rpt,ajst_price,cmpr_stock)
    if verbose==True:
        test_object.introduction()
    test_object.getRvn()
    test_object.get_comparing_metrics()
    data, rtn_for_stock = BackTesting.import_criteria(test_object, criteria, verbose=verbose)
    return test_object, data, rtn_for_stock

def SearchBestCriteria(start_year, end_year, criteria, verbose=True, graph=True):
    prm_list = []
    statement_time_period = list(range(start_year, end_year+1))
    for y in range(start_year, end_year+1):
        test_object, data, rtn_for_stock = SingleYearTesting(y, criteria, verbose=verbose)
        prm_list.append([data,test_object.comparing_metrics[2], rtn_for_stock])
        
    price_time_period = np.array(list(range(start_year+1,end_year+2)))
        
    data_of_criteria_array, rtn_for_tw50_array, rtn_for_criteria_array = np.array(prm_list)[:,0],np.array(prm_list)[:,1],np.array(prm_list)[:,2]
    
    if graph==True:
        plt.figure(figsize=(9,4))
        plt.plot(price_time_period,rtn_for_tw50_array,label='tw50')
        plt.plot(price_time_period,rtn_for_criteria_array,label='自選etf')
        plt.title('tw50 v.s 自選etf')
        plt.xlabel('Year', fontsize=12)
        plt.ylabel('報酬率', fontsize=12)
        plt.legend()
        def hstRevn(t):
            return round((reduce(lambda x,y:(100+x)*(100+y), t)/100**len(t)-1)*100, 2)
        print('歷史績效:')
        if len(price_time_period)>=3:
            print(f'近 3 年報酬 tw50={hstRevn(rtn_for_tw50_array[-3:])}% v.s 自選etf={hstRevn(rtn_for_criteria_array[-3:])}%')
        if len(price_time_period)>=5:
            print(f'近 5 年報酬 tw50={hstRevn(rtn_for_tw50_array[-5:])}% v.s 自選etf={hstRevn(rtn_for_criteria_array[-5:])}%')
        if len(price_time_period)>=8:
            print(f'近 8 年報酬 tw50={hstRevn(rtn_for_tw50_array[-8:])}% v.s 自選etf={hstRevn(rtn_for_criteria_array[-8:])}%')
        if len(price_time_period) not in (3,5,8):
            print(f'近 {len(rtn_for_tw50_array)} 年報酬 tw50={hstRevn(rtn_for_tw50_array)}% v.s 自選etf={hstRevn(rtn_for_criteria_array)}%')
    d_criteria = dict(zip([i-1 for i in price_time_period], data_of_criteria_array))
    return d_criteria, rtn_for_tw50_array, rtn_for_criteria_array