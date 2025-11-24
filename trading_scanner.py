# @title 動態 ATR 停利 + MA50 過濾策略 (v2.0 - 自動執行版)
import os
import sys
import subprocess
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ============ 必要套件自動安裝 ============
def install_packages():
    required = {'yfinance', 'pandas', 'pandas_ta', 'requests'}
    try:
        import pkg_resources
        installed = {pkg.key for pkg in pkg_resources.working_set}
        missing = required - installed
        if missing:
            print(f"安裝缺失套件: {missing}")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--quiet'] + list(missing))
    except:
        os.system('pip install --quiet yfinance pandas pandas_ta requests')

install_packages()

import yfinance as yf
import pandas_ta as ta
import requests
import json

# ==========================================
# ⚙️ 參數設定區
# ==========================================
# 程式會從 GitHub Secrets 讀取這個 Token
LINE_ACCESS_TOKEN = os.getenv("LINE_TOKEN")
LINE_USER_ID = "Uc40b972d11b7beec44c946051d87f7e1" # 您的使用者 ID

TAIWAN_STOCK_LIST = ['2330.TW', '00878.TW', '00919.TW', '6919.TW', '0050.TW', 
                     '2308.TW', '2408.TW', '3293.TW', '6153.TW', '6177.TW', 
                     '2454.TW', '2449.TW', '2886.TW', '3260.TW', '6197.TW', 
                     '4749.TW', '9958.TW']

BACKTEST_LIST = TAIWAN_STOCK_LIST.copy()
BACKTEST_START_DATE = '2020-01-01'
BACKTEST_END_DATE = '2024-11-01'

# 策略參數
SAR_ACCEL = 0.02
SAR_MAX = 0.2
MA_SHORT_PERIOD = 5
MA_LONG_PERIOD = 50
ADX_DMI_PERIOD = 14
ADX_TREND_THRESHOLD = 20

ATR_PERIOD = 14
ATR_SL_MULTIPLIER = 2.0      # 初始停損
ATR_TSL_MULTIPLIER = 3.0     # 動態停利（Trailing Stop）

# ==========================================
# 工具函式
# ==========================================
def send_line_push(msg):
    # 檢查 Token 是否存在
    if not LINE_ACCESS_TOKEN or LINE_ACCESS_TOKEN == "你的token放這裡或設環境變數":
        print("LINE_ACCESS_TOKEN 未設定或為預設值，跳過發送。")
        return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": msg[:4900]}]}
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e: 
        print(f"LINE 發送失敗: {e}")

def fix_ticker(ticker):
    return ticker.replace('.', '-')

# [get_stock_data 函數內容不變]... 
def get_stock_data(ticker, start_date=None, end_date=None):
    ticker = fix_ticker(ticker)
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=500)).strftime('%Y-%m-%d')
    try:
        df = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=False)
        if df.empty or len(df) < 100: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        # 技術指標計算
        sar_result = ta.psar(df['High'], df['Low'], df['Close'], af=SAR_ACCEL, max_af=SAR_MAX)
        # 結合 SAR 上升和下降趨勢點
        df['SAR'] = sar_result.iloc[:, 0].fillna(sar_result.iloc[:, 1])

        df['MA5'] = ta.sma(df['Close'], length=MA_SHORT_PERIOD)
        df['MA50'] = ta.sma(df['Close'], length=MA_LONG_PERIOD)
        
        adx_data = ta.adx(df['High'], df['Low'], df['Close'], length=ADX_DMI_PERIOD)
        df['ADX'] = adx_data.iloc[:, 0]
        df['DMI+'] = adx_data.iloc[:, 1]
        df['DMI-'] = adx_data.iloc[:, 2]
        
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=ATR_PERIOD)

        df['SAR_Prev'] = df['SAR'].shift(1)
        df['Close_Prev'] = df['Close'].shift(1)

        return df.dropna()
    except Exception as e:
        print(f"下載 {ticker} 失敗: {e}")
        return None

# [backtest_strategy 函數內容不變]...
def backtest_strategy(ticker, df):
    trades = []
    in_position = False
    entry_price = highest_price = initial_stop = 0

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]

        price = row['Close']
        high = row['High']
        atr = row['ATR']

        if not in_position:
            # 進場條件（四重確認）
            sar_buy = (prev['SAR'] > prev['Close']) and (row['SAR'] < price)
            above_ma5 = price > row['MA5']
            above_ma50 = price > row['MA50']
            strong_trend = row['ADX'] > ADX_TREND_THRESHOLD and row['DMI+'] > row['DMI-']

            if sar_buy and above_ma5 and above_ma50 and strong_trend:
                in_position = True
                entry_price = price
                highest_price = high
                initial_stop = entry_price - ATR_SL_MULTIPLIER * atr
                continue

        if in_position:
            highest_price = max(highest_price, high)
            trailing_stop = highest_price - ATR_TSL_MULTIPLIER * atr
            exit_reason = None
            exit_price = price

            if price <= initial_stop:
                exit_reason = f"初始停損 {ATR_SL_MULTIPLIER}xATR"
            elif price <= trailing_stop:
                exit_reason = f"動態停利 {ATR_TSL_MULTIPLIER}xATR"

            if exit_reason:
                pl_pct = (exit_price - entry_price) / entry_price * 100
                trades.append({'pl_pct': pl_pct, 'reason': exit_reason})
                in_position = False

    # 最後未平倉
    if in_position:
        last_price = df.iloc[-1]['Close']
        pl_pct = (last_price - entry_price) / entry_price * 100
        trades.append({'pl_pct': pl_pct, 'reason': '持有至結束'})

    return trades

# [format_report, run_backtest, daily_scan 函數內容不變]...
def format_report(ticker, trades):
    if not trades:
        return f"[{ticker}] 無交易訊號\n"
    
    df_t = pd.DataFrame(trades)
    win_rate = len(df_t[df_t.pl_pct > 0]) / len(df_t)
    total_ret = (1 + df_t.pl_pct/100).prod() - 1
    avg_win = df_t[df_t.pl_pct > 0].pl_pct.mean()
    avg_loss = df_t[df_t.pl_pct <= 0].pl_pct.mean()

    return (f"[{ticker}]\n"
            f"交易次數: {len(trades)}  勝率: {win_rate:.1%}  總報酬: {total_ret:+.1%}\n"
            f"平均獲利: {avg_win:+.1f}%  平均虧損: {avg_loss:.1f}%\n{'-'*40}\n")

def run_backtest():
    report = f"回測期間: {BACKTEST_START_DATE} ~ {BACKTEST_END_DATE}\n{'='*50}\n"
    for t in BACKTEST_LIST:
        df = get_stock_data(t, BACKTEST_START_DATE, BACKTEST_END_DATE)
        if df is None: continue
        trades = backtest_strategy(t, df)
        report += format_report(t, trades)
    print(report)
    send_line_push("回測完成！\n" + report)

def daily_scan():
    us_tickers = []
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        sp500 = pd.read_html(url)[0]['Symbol'].tolist()
        us_tickers = [fix_ticker(s) for s in sp500]
    except: pass

    all_stocks = TAIWAN_STOCK_LIST + us_tickers
    signals = []

    for ticker in all_stocks:
        df = get_stock_data(ticker)
        if df is None or len(df) < 50: continue
        today = df.iloc[-1]
        prev = df.iloc[-2]

        buy = (
            (prev['SAR'] > prev['Close']) and (today['SAR'] < today['Close']) and
            today['Close'] > today['MA5'] and
            today['Close'] > today['MA50'] and
            today['ADX'] > ADX_TREND_THRESHOLD and
            today['DMI+'] > today['DMI-']
        )

        if buy:
            stop_price = today['Close'] - ATR_SL_MULTIPLIER * today['ATR']
            stop_pct = (today['Close'] - stop_price) / today['Close'] * 100
            name = ticker.replace('.TW','').replace('.KS','')
            signals.append(
                f"【{name}】\n價: {today['Close']:.2f}\n"
                f"停損: {stop_price:.2f} (-{stop_pct:.1f}%)\n"
                f"ATR動態停利 {ATR_TSL_MULTIPLIER}x\n"
            )

    msg = f"每日選股 {datetime.now():%Y-%m-%d}\n"
    msg += "符合訊號:\n" + "\n".join(signals) if signals else "今日無買訊"
    print(msg)
    send_line_push(msg)


# ==========================================
# 主程式 (自動化環境直接執行 daily_scan)
# ==========================================
if __name__ == "__main__":
    daily_scan()
