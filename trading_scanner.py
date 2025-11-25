# @title 👇 V8.3 最終修復版 (解決 ModuleNotFoundError)
import os
import sys
import subprocess
from datetime import datetime, timedelta

# 1. 先定義安裝功能 (只用內建功能，不依賴 pandas)
def install_packages():
    required = ['yfinance', 'pandas', 'pandas_ta', 'requests', 'lxml', 'html5lib']
    print("正在檢查並安裝套件...")
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + required)
    except Exception as e:
        print(f"安裝失敗 (嘗試備用方法): {e}")
        os.system('pip install yfinance pandas pandas_ta requests lxml html5lib')

# 2. 這是 GitHub Actions 專用的「只安裝不執行」開關
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'install_packages':
        install_packages()
        sys.exit(0) # 安裝完直接結束，不往下執行

# ==========================================
# 3. 只有安裝完才會執行到這裡 (安全匯入區)
# ==========================================
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import json

# 參數設定 (從 GitHub 讀取密碼)
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN", "DEBUG_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID", "")

# 您的股票清單
TAIWAN_STOCK_LIST = ['2330.TW', '00878.TW', '00919.TW', '6919.TW', '0050.TW', '2308.TW', '2408.TW', '3293.TW', '6153.TW', '6177.TW', '2454.TW', '2449.TW', '2886.TW', '3260.TW', '6197.TW', '4749.TW', '9958.TW'] 
BACKTEST_LIST = TAIWAN_STOCK_LIST
BACKTEST_START_DATE = '2020-01-01'
BACKTEST_END_DATE = '2025-11-01'

# 策略參數 (V5.1)
SAR_ACCEL = 0.02
SAR_MAX = 0.2
MA_SHORT_PERIOD = 5
ATR_PERIOD = 22      
CE_MULTIPLIER = 3.0
MAX_LOSS_PCT = 8.0

# 功能函式
def calculate_indicators(df):
    sar_df = ta.psar(df['High'], df['Low'], df['Close'], af=SAR_ACCEL, max_af=SAR_MAX)
    if sar_df is not None and not sar_df.empty:
        df['SAR'] = sar_df[sar_df.columns[0]].fillna(sar_df[sar_df.columns[1]])
    else:
        df['SAR'] = df['Close']
    df['MA5'] = ta.sma(df['Close'], length=MA_SHORT_PERIOD)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=ATR_PERIOD)
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
    if LINE_ACCESS_TOKEN == "DEBUG_TOKEN": return
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + LINE_ACCESS_TOKEN}
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": msg[:1900]}]}
    try: requests.post("https://api.line.me/v2/bot/message/push", headers=headers, data=json.dumps(payload), timeout=10)
    except: pass

def scan_market(stock_list):
    signals = []
    for ticker in stock_list:
        df = get_stock_data(ticker)
        if df is None: continue
        curr = df.iloc[-1]; prev = df.iloc[-2]
        
        if (prev['SAR'] > prev['Close']) and (curr['SAR'] < curr['Close']) and (curr['Close'] > curr['MA5']):
            hard_stop = curr['Close'] * (1 - MAX_LOSS_PCT / 100)
            final_stop = max(hard_stop, curr['SAR'])
            risk_pct = (curr['Close'] - final_stop) / curr['Close'] * 100
            signals.append(f"🔥【V5.1買進】{ticker.replace('.TW','')}\n現價: {curr['Close']:.2f}\n🛡️ 停損: {final_stop:.2f} ({risk_pct:.1f}%)")
    return signals

def backtest(stock_list):
    report = "📊 回測報告\n"
    for ticker in stock_list:
        df = get_stock_data(ticker)
        if df is None: continue
        # 簡易回測邏輯
        trades = []
        in_pos = False
        entry = 0
        stop = 0
        for i in range(len(df)):
            c = df.iloc[i]
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
    # 主程式邏輯
    try:
        # GitHub Actions 傳入參數判斷
        mode = sys.argv[1] if len(sys.argv) > 1 else '1'
    except: mode = '1'

    if mode == '2':
        msg = backtest(BACKTEST_LIST)
    else:
        res = scan_market(TAIWAN_STOCK_LIST)
        msg = f"📅 {datetime.now().strftime('%Y-%m-%d')} 選股\n" + ("\n".join(res) if res else "無訊號")
    
    print(msg)
    send_line_push(msg)
