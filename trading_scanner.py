# @title 👇 V9.0 最終穩定版 (已移除 pandas-ta)
import os
import sys
import json
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

# ==========================================
# ⚙️ 參數設定區
# ==========================================
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID") 

# 股票清單
TAIWAN_STOCK_LIST = ['2330.TW', '00878.TW', '00919.TW', '6919.TW', '0050.TW', '2308.TW', '2408.TW', '3293.TW', '6153.TW', '6177.TW', '2454.TW', '2449.TW', '2886.TW', '3260.TW', '6197.TW', '4749.TW', '9958.TW'] 
BACKTEST_LIST = TAIWAN_STOCK_LIST
BACKTEST_START_DATE = '2020-01-01'
BACKTEST_END_DATE = '2025-11-01'

# 策略參數
SAR_ACCEL = 0.02
SAR_MAX = 0.2
MA_SHORT_PERIOD = 5  
ATR_PERIOD = 22      
CE_MULTIPLIER = 3.0  
MAX_LOSS_PCT = 8.0   

# ==========================================
# 🔧 功能函式
# ==========================================

# 替換 SAR 計算 (使用 TA-Lib 或複雜算法，此處為簡化版或佔位符)
# 由於無法使用 pandas-ta，我們將使用 pandas 內建功能或手動計算
def calculate_sar(df, af=SAR_ACCEL, max_af=SAR_MAX):
    # 此處 SAR 實現較為複雜，為保持程式運行，我們暫時使用 MA 作為替代或進行簡化。
    # **注意：這不是標準的 SAR，僅為保持流程運作，需要時再加入完整的 SAR 算法。**
    df['SAR'] = df['Close'].rolling(window=20).mean() # 臨時替代
    return df

def calculate_atr(df, length=ATR_PERIOD):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.ewm(span=length, adjust=False).mean()
    return df

def calculate_indicators(df):
    df = calculate_sar(df)
    df = calculate_atr(df)
    
    df['MA5'] = df['Close'].rolling(window=MA_SHORT_PERIOD).mean() # ta.sma -> pandas rolling mean
    
    # 計算 CE_Dynamic
    df['CE_Dynamic'] = df['High'].rolling(window=ATR_PERIOD).max() - (df['ATR'] * CE_MULTIPLIER)
    
    df['SAR_Prev'] = df['SAR'].shift(1)
    df['Close_Prev'] = df['Close'].shift(1)
    return df

def get_stock_data(ticker):
    try:
        df = yf.download(ticker, start=(datetime.now() - timedelta(days=500)).strftime('%Y-%m-%d'), progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
        return calculate_indicators(df).dropna()
    except: return None

def send_line_push(msg):
    if not LINE_ACCESS_TOKEN: return
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + LINE_ACCESS_TOKEN}
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": msg[:1900]}]}
    try: requests.post("https://api.line.me/v2/bot/message/push", headers=headers, data=json.dumps(payload), timeout=10)
    except: pass

def scan_market(stock_list):
    signals = []
    print(f"🔍 開始掃描 {len(stock_list)} 檔股票...")
    for ticker in stock_list:
        df = get_stock_data(ticker)
        if df is None: continue
        # 由於 SAR 已經替換為 MA，這裡的邏輯需要調整以反映指標變化
        curr = df.iloc[-1]; prev = df.iloc[-2]
        
        # 這是基於 MA 的簡化訊號：SAR向上突破MA5
        if (prev['SAR'] > prev['Close']) and (curr['SAR'] < curr['Close']) and (curr['Close'] > curr['MA5']):
            hard_stop = curr['Close'] * (1 - MAX_LOSS_PCT / 100)
            final_stop = max(hard_stop, curr['SAR'])
            risk_pct = (curr['Close'] - final_stop) / curr['Close'] * 100
            signals.append(f"🔥【V9.0買進】{ticker.replace('.TW','')}\n現價: {curr['Close']:.2f}\n🛡️ 停損: {final_stop:.2f} ({risk_pct:.1f}%)")
            print(f"發現訊號: {ticker}")
    return signals

def backtest(stock_list):
    report = "📊 回測報告\n"
    for ticker in stock_list:
        df = get_stock_data(ticker)
        if df is None: continue
        trades = []
        in_pos = False
        entry = 0
        stop = 0
        for i in range(len(df)):
            c = df.iloc[i]
            # 這是基於 MA 的簡化訊號
            if not in_pos and c['SAR_Prev'] > c['Close_Prev'] and c['SAR'] < c['Close'] and c['Close'] > c['MA5']:
                in_pos = True; entry = c['Close']; stop = max(c['CE_Dynamic'], entry*(1-MAX_LOSS_PCT/100))
            elif in_pos:
                stop = max(stop, c['CE_Dynamic'], entry*(1-MAX_LOSS_PCT/100))
                if c['Close'] < stop:
                    in_pos = False; trades.append((c['Close'] - entry)/entry)
        wins = [t for t in trades if t > 0]
        if trades:
            report += f"{ticker.replace('.TW','')}: {len(trades)}交易 | 勝率 {len(wins)/len(trades):.0%}\n"
    return report

if __name__ == "__main__":
    try: mode = sys.argv[1] if len(sys.argv) > 1 else '1'
    except: mode = '1'

    if mode == '2':
        msg = backtest(BACKTEST_LIST)
    else:
        res = scan_market(TAIWAN_STOCK_LIST)
        msg = f"📅 {datetime.now().strftime('%Y-%m-%d')} 選股快報\n{'='*15}\n" + ("\n".join(res) if res else "無訊號")
    
    print(msg)
    send_line_push(msg)
def send_line_push(msg):
    LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
    LINE_USER_ID = os.environ.get("LINE_USER_ID")
    
    if not LINE_ACCESS_TOKEN or not LINE_USER_ID:
        print("WARNING: LINE_ACCESS_TOKEN or LINE_USER_ID is missing from environment variables.")
        return
        
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + LINE_ACCESS_TOKEN}
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": msg[:1900]}]}
    
    print(f"Attempting to send LINE message to user ID: {LINE_USER_ID}") 
    
    try: 
        response = requests.post("https://api.line.me/v2/bot/message/push", 
                                 headers=headers, 
                                 data=json.dumps(payload), 
                                 timeout=10)
        
        print(f"LINE API Response Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"LINE API Push FAILED. Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"LINE Push Network Error: {e}")
    except Exception as e:
        print(f"LINE Push Unexpected Error: {e}")
