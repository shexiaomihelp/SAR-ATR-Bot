# @title 👇 V8.2 最終完整版程式碼 (已修正格式與語法錯誤)
import os
import sys
import subprocess
import time
import pandas as pd
import numpy as np
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

# 安裝套件
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'install_packages':
        install_packages()
        sys.exit(0)
    install_packages()

import yfinance as yf
import pandas_ta as ta
import requests
import json

# ==========================================
# ⚙️ 參數設定區
# ==========================================
# V8.1 核心變更：從環境變數讀取密鑰 (支援 GitHub Actions)
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID") 

if not LINE_ACCESS_TOKEN:
    print("警告：LINE 密鑰未設定或讀取失敗，發送功能將被跳過。")
    LINE_ACCESS_TOKEN = "DEBUG_TOKEN" 

# ------------------------------------------
# ⭐️ 您的最新清單與回測日期 ⭐️
# ------------------------------------------
TAIWAN_STOCK_LIST = ['2330.TW', '00878.TW', '00919.TW', '6919.TW', '0050.TW', '2308.TW', '2408.TW', '3293.TW', '6153.TW', '6177.TW', '2454.TW', '2449.TW', '2886.TW', '3260.TW', '6197.TW', '4749.TW', '9958.TW'] 
BACKTEST_START_DATE = '2020-01-01'
BACKTEST_END_DATE = '2025-11-01'
# ------------------------------------------

# 🚀 策略 1/2 參數 (SAR + MA5)
SAR_ACCEL = 0.02; SAR_MAX = 0.2; MA_SHORT_PERIOD = 5  
ATR_PERIOD = 22; CE_MULTIPLIER = 3.0   

# ⭐️ 波動度與風險配置參數
VOL_TARGET_RISK = 0.01 
TOTAL_CAPITAL = 100000 

# ⭐️ 策略 3 參數
RSI_PERIOD = 14
RSI_OVERSOLD_ENTRY = 30
RSI_OVERBOUGHT_EXIT = 70 
VMA_PERIOD = 20 

# ==========================================
# 🔧 核心資料與指標計算
# ==========================================
def calculate_indicators(df):
    """計算所有策略所需指標"""
    sar_df = ta.psar(df['High'], df['Low'], df['Close'], af=SAR_ACCEL, max_af=SAR_MAX)
    if sar_df is not None and not sar_df.empty:
        sar_cols = sar_df.columns
        df['SAR'] = sar_df[sar_cols[0]].fillna(sar_df[sar_cols[1]])
    else:
        df['SAR'] = df['Close']
    df['MA5'] = ta.sma(df['Close'], length=MA_SHORT_PERIOD)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=ATR_PERIOD)
    
    # 動態停損指標 (SAR 策略的核心)
    rolling_high = df['High'].rolling(window=ATR_PERIOD).max()
    df['CE_Dynamic'] = rolling_high - (df['ATR'] * CE_MULTIPLIER)
    
    df['RSI'] = ta.rsi(df['Close'], length=RSI_PERIOD)
    df['VMA'] = ta.sma(df['Volume'], length=VMA_PERIOD)
    
    df['SAR_Prev'] = df['SAR'].shift(1)
    df['Close_Prev'] = df['Close'].shift(1)
    return df.dropna()

def get_stock_data(ticker, start_date=None, end_date=None):
    if start_date is None: start_date = (datetime.now() - timedelta(days=500)).strftime('%Y-%m-%d')
    try:
        df = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=False)
        if df.empty or len(df) < 60: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
        df = calculate_indicators(df)
        return df
    except Exception: return None

def get_sp500_tickers():
    # 這是先前報錯 IndentationError 的區域，已確保縮排正確
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        return [t.replace('.','-') for t in pd.read_html(url)[0]['Symbol'].tolist()]
    except: return []

# ==========================================
# 📢 LINE 發送函式
# ==========================================
def send_line_push(msg):
    if LINE_ACCESS_TOKEN == "DEBUG_TOKEN":
        print("LINE 訊息未發送 (密鑰未設定)")
        return
    
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + LINE_ACCESS_TOKEN}
    if len(msg) > 1900: msg = msg[:1900] + "\n...(訊息過長截斷)"
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": msg}]}
    try:
        requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
    except Exception: 
        print("❌ LINE 發送例外")

# ==========================================
# 📊 輔助回測與配置函式
# ==========================================
def format_report(trades):
    if not trades: return {"win_rate": 0, "rr_ratio": 0, "total_trades": 0}
    df_t = pd.DataFrame(trades)
    win_cnt = len(df_t[df_t['profit_loss_pct'] > 0])
    loss_cnt = len(df_t) - win_cnt
    total_trades = len(df_t)
    win_rate = win_cnt / total_trades if total_trades > 0 else 0
    
    avg_win = df_t[df_t['profit_loss_pct']>0]['profit_loss_pct'].mean() if win_cnt > 0 else 0
    avg_loss = df_t[df_t['profit_loss_pct']<=0]['profit_loss_pct'].mean() if loss_cnt > 0 else 0
    rr_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    
    return {"win_rate": win_rate, "rr_ratio": rr_ratio, "total_trades": total_trades}

def calculate_volatility_size(current_price, final_stop, vol_target_risk, total_capital):
    """計算波動度目標配置下的部位大小。"""
    risk_per_share = current_price - final_stop
    
    if risk_per_share <= 0:
        return 0, 0
    
    max_risk_amount = total_capital * vol_target_risk
    shares = max_risk_amount / risk_per_share
    suggested_investment = shares * current_price
    
    return int(shares), suggested_investment

# ==========================================
# 📈 Mode 2 專用回測 (SAR 趨勢 - V8.0)
# ==========================================
def backtest_strategy_mode2(ticker, df):
    trades = []
    in_position = False
    entry_price = 0
    
    for i in range(len(df)):
        curr = df.iloc[i]; price = curr['Close']
        if pd.isna(curr['SAR_Prev']): continue
        
        # 出場邏輯 (V8.0: 僅使用動態 CE_Dynamic 停損)
        if in_position:
            current_stop_price = max(curr['CE_Dynamic'], 0)
            
            if price < current_stop_price:
                trades.append({'profit_loss_pct': (price - entry_price) / entry_price * 100})
                in_position = False
        
        # 進場邏輯
        if not in_position:
            sar_flip_up = (curr['SAR_Prev'] > curr['Close_Prev']) and (curr['SAR'] < price)
            above_ma5 = (price > curr['MA5'])
            if sar_flip_up and above_ma5:
                in_position = True
                entry_price = price
                
    if in_position:
        trades.append({'profit_loss_pct': (df.iloc[-1]['Close'] - entry_price) / entry_price * 100})
    return trades

# ==========================================
# 🔍 策略 1: SAR + MA5 掃描 (V8.0 - 含部位配置)
# ==========================================
def scan_market_mode1(stock_list):
    signals = []
    
    for ticker in stock_list:
        df = get_stock_data(ticker)
        if df is None or df.empty: continue
        
        curr = df.iloc[-1]; prev = df.iloc[-2]
        
        sar_flip_up = (prev['SAR'] > prev['Close']) and (curr['SAR'] < curr['Close'])
        above_ma5 = (curr['Close'] > curr['MA5'])
        
        if sar_flip_up and above_ma5:
            current_price = curr['Close']
            
            # V8.0 核心變更：純 ATR 動態停損
            final_stop = max(curr['CE_Dynamic'], 0) 
            risk_pct = (current_price - final_stop) / current_price * 100

            # V8.0 新增：計算波動度目標部位大小
            shares, investment_amount = calculate_volatility_size(
                current_price, final_stop, VOL_TARGET_RISK, TOTAL_CAPITAL
            )

            signals.append(
                f"🔥【Mode 1: SAR趨勢】{ticker.replace('.TW','')}\n"
                f"現價: {current_price:.2f}\n"
                f"訊號: SAR翻紅 + 站上MA5\n"
                f"🛡️ 建議停損: {final_stop:.2f} ({risk_pct:.1f}%)\n"
                f"💰 **部位配置 (風險 {VOL_TARGET_RISK:.0%})**\n"
                f"  - 建議股數: {shares} 股\n"
                f"  - 建議投入: {investment_amount:,.0f} 元 (總資產 {TOTAL_CAPITAL:,.0f} 元)\n"
            )
    return signals

# ==========================================
# 🌟 策略 3: 動態停損計算核心 (V8.0)
# ==========================================
def calculate_dynamic_stop_loss(ticker, entry_price_str, start_date):
    """計算持倉股票的當前動態停損點 (基於 SAR 策略的 ATR 邏輯)"""
    try:
        entry_price = float(entry_price_str)
    except ValueError:
        return f"錯誤：進場價格 '{entry_price_str}' 必須是有效的數字。"
        
    df = get_stock_data(ticker, start_date=start_date, end_date=None)
    if df is None or len(df) < ATR_PERIOD + 2:
        return f"錯誤：無法取得 {ticker} 足夠資料 (至少 {ATR_PERIOD+2} 天) 來計算動態停損。"

    curr = df.iloc[-1]
    
    # 核心邏輯：動態停損點只取動態底線 (CE_Dynamic)
    dynamic_stop = curr['CE_Dynamic']
    final_stop = max(dynamic_stop, 0) 
    
    current_price = curr['Close']
    risk_pct = (current_price - final_stop) / current_price * 100
    last_data_date = df.index[-1].strftime('%Y-%m-%d')
    
    if current_price < final_stop:
        signal_status = f"🔴 **已觸發停損**"
    else:
        signal_status = f"🟢 **仍在持倉區間**"

    report = f"🛡️【Mode 3 動態停損計算：{ticker.replace('.TW','')}】\n"
    report += f"============================\n"
    report += f"📅 資料日期: {last_data_date}\n"
    report += f"💰 進場成本: {entry_price:.2f}\n"
    report += f"📈 當前價格: {current_price:.2f}\n"
    report += f"----------------------------\n"
    report += f"**🎯 建議停損點 (純 ATR 邏輯): {final_stop:.2f}**\n"
    report += f"   - 距離現價風險: {risk_pct:.1f}%\n"
    report += f"   - 當前動態底線: {dynamic_stop:.2f}\n"
    report += f"狀態: {signal_status}\n"
    
    return report

# ==========================================
# 🚀 主程式入口 (V8.2 - 語法已修正)
# ==========================================
def run_scan_or_backtest(mode):
    targets = TAIWAN_STOCK_LIST
    targets_to_scan = targets + get_sp500_tickers()[:30]
    
    if mode == '1':
        # Mode 1: SAR 趨勢選股掃描
        results = scan_market_mode1(targets_to_scan)
        title = "SAR 趨勢追蹤 (Mode 1)"
        header = f"📅 {datetime.now().strftime('%Y-%m-%d')} {title} 快報\n{'='*25}\n"
        content = "\n".join(results) if results else f"今日無符合 {title} 訊號"
        final_msg = header + content
        
    elif mode == '2':
        # Mode 2: SAR 歷史回測
        full_report = f"📊 SAR 趨勢回測報告 (Mode 2) \n"
        full_report += f"期間: {BACKTEST_START_DATE}~{BACKTEST_END_DATE}\n{'='*25}\n"
        
        for t in targets:
            print(f"正在回測 {t}...")
            df = get_stock_data(t, start_date=BACKTEST_START_DATE, end_date=BACKTEST_END_DATE)
            if df is not None:
                trades = backtest_strategy_mode2(t, df)
                metrics = format_report(trades)
                full_report += f"[{t.replace('.TW','')}] 交易: {metrics['total_trades']} | 勝率: {metrics['win_rate']:.1%} | 盈虧比: {metrics['rr_ratio']:.2f}\n"
        
        final_msg = full_report

    elif mode == '3':
        # Mode 3: 持倉動態停損計算
        try:
            target_ticker = input("請輸入持倉股號代碼 (例如 2330 或 TSLA): ").strip().upper()
            if not target_ticker: return "請提供有效的股號代碼。"
            
            if target_ticker.isdigit() and len(target_ticker) <= 4:
                target_ticker += '.TW'

            entry_price_input = input("請輸入您的進場成本價格 (數字): ").strip()
            
            if not entry_price_input: return "請提供進場成本價格。"
            
        except Exception as e: return f"輸入失敗: {e}"
        
        final_msg = calculate_dynamic_stop_loss(target_ticker, entry_price_input, BACKTEST_START_DATE)
        
    else: 
        final_msg = "輸入無效。請輸入 1, 2, 或 3。"
        
    print(final_msg)
    send_line_push(final_msg)


if __name__ == "__main__":
    
    # 這裡的邏輯已經在程式開頭確保只在需要時執行 install_packages，然後退出。
    # 正常執行時，會從這裡開始：
    
    print("=== V8.2 交易系統 - 最終版 (縮排與語法已校正) ===")
    print("1: 每日選股掃描 (SAR 趨勢 + 波動度部位配置)")
    print("2: 歷史回溯測試 (SAR 趨勢策略)")
    print("3: **持倉動態 ATR 停損計算**")
    
    try:
        # 處理 GitHub Actions 的模擬輸入
        if len(sys.argv) > 1 and sys.argv[1].isdigit():
             mode = sys.argv[1]
        else:
             mode = input("請輸入數字 (1, 2, 或 3): ").strip()
             
    except: 
        mode = '1'
    
    run_scan_or_backtest(mode)
