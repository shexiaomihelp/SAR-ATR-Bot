# @title 👇 最終整合版程式碼 (V5.1 邏輯 + 健壯結構)
import os
import sys
import subprocess
# 僅導入內建或不依賴 pip 安裝的套件
from datetime import datetime, timedelta

# ==========================================
# 0. 環境設置與套件安裝
# ==========================================
def install_packages():
    required = {'yfinance', 'pandas', 'pandas_ta', 'requests', 'lxml', 'html5lib'}
    try:
        import pkg_resources
        installed = {pkg.key for pkg in pkg_resources.working_set}
        missing = required - installed
        if missing:
            print(f"正在安裝缺少的套件: {missing}")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', *missing])
    except:
        os.system('pip install yfinance pandas pandas_ta requests lxml html5lib')

# ==========================================
# 安裝套件檢查與退出邏輯 (GitHub Actions 專用)
# ==========================================
if __name__ == "__main__":
    # 這個區塊專門用於 GitHub Actions 的安裝步驟
    if len(sys.argv) > 1 and sys.argv[1] == 'install_packages':
        install_packages()
        sys.exit(0)

# ==========================================
# 導入已安裝的套件 (確保在安裝邏輯之後才執行)
# ==========================================
import time # 內建套件
import pandas as pd
import numpy as np
import yfinance as yf
import pandas_ta as ta
import requests
import json

# ==========================================
# ⚙️ 參數設定區 (採用 V5.1 參數)
# ==========================================
# V8.2 安全修正：從環境變數讀取密鑰 (請在 GitHub Secrets 中設置)
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID") 

if not LINE_ACCESS_TOKEN:
    print("警告：LINE 密鑰未設定或讀取失敗，發送功能將被跳過。")
    LINE_ACCESS_TOKEN = "DEBUG_TOKEN" 

# ------------------------------------------
# ⭐️ 您的最新清單與回測日期 ⭐️
# ------------------------------------------
TAIWAN_STOCK_LIST = ['2330.TW', '00878.TW', '00919.TW', '6919.TW', '0050.TW', '2308.TW', '2408.TW', '3293.TW', '6153.TW', '6177.TW', '2454.TW', '2449.TW', '2886.TW', '3260.TW', '6197.TW', '4749.TW', '9958.TW'] 
BACKTEST_LIST = TAIWAN_STOCK_LIST
BACKTEST_START_DATE = '2020-01-01'
BACKTEST_END_DATE = '2025-11-01'
# ------------------------------------------

# 🚀 1. 進場參數
SAR_ACCEL = 0.02
SAR_MAX = 0.2
MA_SHORT_PERIOD = 5  # 必須站上 MA5

# 🛡️ 2. 出場與風控參數
ATR_PERIOD = 22      
CE_MULTIPLIER = 3.0  # 吊燈距離 (3倍 ATR，防洗盤用)
MAX_LOSS_PCT = 8.0   # 強制停損底線 (最大虧損不超過 8%)

# ==========================================
# 🔧 指標計算核心 (採用 V5.1 邏輯)
# ==========================================
def calculate_indicators(df):
    """計算 V5.1 所需指標，包含手寫的 Chandelier Exit"""
    
    # 1. SAR (使用 pandas_ta, 處理欄位合併)
    sar_df = ta.psar(df['High'], df['Low'], df['Close'], af=SAR_ACCEL, max_af=SAR_MAX)
    if sar_df is not None and not sar_df.empty:
        sar_cols = sar_df.columns
        df['SAR'] = sar_df[sar_cols[0]].fillna(sar_df[sar_cols[1]])
    else:
        df['SAR'] = df['Close'] 

    # 2. MA5
    df['MA5'] = ta.sma(df['Close'], length=MA_SHORT_PERIOD)
    
    # 3. ATR (用於計算吊燈)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=ATR_PERIOD)
    
    # 4. 手寫 Chandelier Exit (吊燈停利 - Long)
    rolling_high = df['High'].rolling(window=ATR_PERIOD).max()
    df['CE_Dynamic'] = rolling_high - (df['ATR'] * CE_MULTIPLIER)
    
    df['SAR_Prev'] = df['SAR'].shift(1)
    df['Close_Prev'] = df['Close'].shift(1)
    
    return df

def get_stock_data(ticker, start_date=None, end_date=None):
    if start_date is None: start_date = (datetime.now() - timedelta(days=500)).strftime('%Y-%m-%d')
    try:
        df = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=False)
        if df.empty or len(df) < 60: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
        
        df = calculate_indicators(df)
        return df.dropna()
    except Exception as e:
        print(f"下載 {ticker} 失敗: {e}")
        return None

# ==========================================
# 📢 LINE 發送函式 (採用 V8.2 安全邏輯)
# ==========================================
def send_line_push(msg):
    if LINE_ACCESS_TOKEN == "DEBUG_TOKEN":
        print("LINE 訊息未發送 (密鑰未設定或讀取失敗)")
        return
        
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + LINE_ACCESS_TOKEN}
    if len(msg) > 1900: msg = msg[:1900] + "\n...(訊息過長截斷)"
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": msg}]}
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        if response.status_code == 200:
            print("✅ LINE 訊息發送成功")
        else:
            print(f"❌ LINE 發送失敗: {response.status_code} - {response.text}")
    except Exception as e: 
        print(f"❌ LINE 發送例外: {e}")

# ==========================================
# 📊 回測邏輯 (V5.1 - 含雙重風控)
# ==========================================
def backtest_strategy(ticker, df):
    trades = []
    in_position = False
    entry_price = 0
    current_stop_price = 0 # 當前的實際停損價 (取吊燈與硬停損的較高者)
    
    for i in range(len(df)):
        curr = df.iloc[i]
        price = curr['Close']
        
        sar = curr['SAR']
        prev_sar = curr['SAR_Prev']
        prev_close = curr['Close_Prev']
        ce_dynamic = curr['CE_Dynamic']
        
        if pd.isna(prev_sar): continue
        
        # --- 持倉管理 (出場邏輯) ---
        if in_position:
            # 1. 更新停損價
            hard_stop = entry_price * (1 - MAX_LOSS_PCT / 100)
            
            # 實際停損價 = MAX(之前的停損價, 新的吊燈價, 硬性停損價)
            # 確保停損線只會往上推，不會低於硬性停損底線
            new_stop = max(current_stop_price, ce_dynamic, hard_stop)
            current_stop_price = new_stop
            
            # 2. 檢查是否觸發出場
            if price < current_stop_price:
                profit_loss = (price - entry_price) / entry_price
                
                reason = "觸及吊燈移動停利" if price > entry_price else "觸及停損保護"
                
                trades.append({
                    'profit_loss_pct': profit_loss * 100, 
                    'reason': reason
                })
                in_position = False
        
        # --- 進場邏輯 ---
        if not in_position:
            sar_flip_up = (prev_sar > prev_close) and (sar < price)
            above_ma5 = (price > curr['MA5'])
            
            if sar_flip_up and above_ma5:
                in_position = True
                entry_price = price
                # 初始停損價設定
                hard_stop = entry_price * (1 - MAX_LOSS_PCT / 100)
                # 初始停損取：吊燈或硬性停損中較高者
                current_stop_price = max(ce_dynamic, hard_stop)
                
    if in_position:
        last_price = df.iloc[-1]['Close']
        profit_loss = (last_price - entry_price) / entry_price
        trades.append({'profit_loss_pct': profit_loss * 100, 'reason': '持有至期末'})
    return trades

def format_report(ticker, trades):
    if not trades: return ""
    df_t = pd.DataFrame(trades)
    win_cnt = len(df_t[df_t['profit_loss_pct'] > 0])
    loss_cnt = len(df_t) - win_cnt
    win_rate = win_cnt / len(df_t)
    total_ret = (1 + df_t['profit_loss_pct']/100).prod() - 1
    
    avg_win = df_t[df_t['profit_loss_pct']>0]['profit_loss_pct'].mean() if win_cnt > 0 else 0
    avg_loss = df_t[df_t['profit_loss_pct']<=0]['profit_loss_pct'].mean() if loss_cnt > 0 else 0
    rr_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    
    return (f"[{ticker.replace('.TW','')}]\n"
            f"交易: {len(df_t)} | 勝率: {win_rate:.0%}\n"
            f"總報酬: {total_ret:.1%} | 盈虧比: {rr_ratio:.2f}\n"
            f"----------------\n")

# ==========================================
# 🔍 每日掃描邏輯 (採用 V5.1 邏輯)
# ==========================================
def get_sp500_tickers():
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        return [t.replace('.','-') for t in pd.read_html(url)[0]['Symbol'].tolist()]
    except: return []

def scan_market(stock_list):
    print(f"🔍 開始掃描 {len(stock_list)} 檔股票 (V5.1 風控版)...")
    signals = []
    
    for ticker in stock_list:
        df = get_stock_data(ticker)
        if df is None: continue
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 進場條件
        sar_flip_up = (prev['SAR'] > prev['Close']) and (curr['SAR'] < curr['Close'])
        above_ma5 = (curr['Close'] > curr['MA5'])
        
        if sar_flip_up and above_ma5:
            
            current_price = curr['Close']
            
            # 1. 計算硬性停損底線
            hard_stop = current_price * (1 - MAX_LOSS_PCT / 100)
            
            # 2. 計算 SAR 停損 (如果 SAR 在價格下方)
            sar_stop = curr['SAR']
            
            # 3. 最終建議停損：取兩個安全線中較高者 (即離現價最近的風險底線)
            final_stop = max(hard_stop, sar_stop) 
            
            # 確保計算後的數字顯示是負數
            risk_pct = (current_price - final_stop) / current_price * 100
            
            name = ticker.replace('.TW','')
            signals.append(
                f"🔥【V5.1買進】{name}\n"
                f"現價: {current_price:.2f}\n"
                f"訊號: SAR翻紅 + 站上MA5\n"
                f"🛡️ 建議停損: {final_stop:.2f} ({risk_pct:.1f}%)\n"
                f"(含強制 {MAX_LOSS_PCT}% 風控底線)"
            )
            print(f"發現訊號: {ticker}")
            
    return signals

# ==========================================
# 🚀 主程式入口
# ==========================================
if __name__ == "__main__":
    
    # 這裡的邏輯已經在程式開頭確保只在需要時執行 install_packages，然後退出。
    
    print(f"=== V5.1 交易系統 (SAR/MA5 + 吊燈 + {MAX_LOSS_PCT}%強制風控) ===")
    print("1. 每日選股掃描 (台股 + 美股)")
    print("2. 歷史回溯測試 (BACKTEST_LIST)")
    
    try:
        # 處理 GitHub Actions 的模擬輸入
        if len(sys.argv) > 1 and sys.argv[1].isdigit():
             mode = sys.argv[1]
        else:
             mode = input("請輸入數字 (1 或 2): ").strip()
             
    except: 
        mode = '1'
        
    if mode == '2':
        # 回測模式
        full_report = f"📊 V5.1 回測報告 ({BACKTEST_START_DATE}~{BACKTEST_END_DATE})\n"
        full_report += f"策略: SAR翻紅+MA5 | 出場: 吊燈(3.0ATR) 或 強制-{MAX_LOSS_PCT}%\n\n"
        
        for t in BACKTEST_LIST:
            print(f"正在回測 {t}...")
            df = get_stock_data(t, start_date=BACKTEST_START_DATE, end_date=BACKTEST_END_DATE)
            if df is not None:
                trades = backtest_strategy(t, df)
                full_report += format_report(t, trades)
        
        print(full_report)
        send_line_push(full_report)
        
    else:
        # 掃描模式 (預設)
        sp500 = get_sp500_tickers()
        targets = TAIWAN_STOCK_LIST + sp500[:30]
        
        results = scan_market(targets)
        
        header = f"📅 {datetime.now().strftime('%Y-%m-%d')} V5.1 選股快報\n{'='*15}\n"
        content = "\n".join(results) if results else "今日無符合訊號"
        final_msg = header + content
        
        print(final_msg)
        send_line_push(final_msg)
