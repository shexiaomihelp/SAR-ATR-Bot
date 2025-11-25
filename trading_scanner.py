# @title 動態 ATR 停利 + MA50 過濾策略 (v2.0 - 自動執行版)
import os
import sys
import subprocess
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ============ 必要套件自動安裝 ============
# 由於 GitHub Actions 環境乾淨，這裡確保套件安裝不會被程式碼中的 try-catch 阻擋
def install_packages():
    required = {'yfinance', 'pandas', 'pandas_ta', 'requests'}
    try:
        import pkg_resources
        installed = {pkg.key for pkg in pkg_resources.working_set}
        missing = required - installed
        if missing:
            print(f"安裝缺失套件: {missing}")
            # subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--quiet'] + list(missing))
            pass # 這裡在 Actions 中交給 YAML 處理，程式碼端只做檢查
    except:
        # os.system('pip install --quiet yfinance pandas pandas_ta requests')
        pass

# install_packages() # 在 Actions 環境中，這行註釋掉或不執行，交給 YAML 安裝

import yfinance as yf
import pandas_ta as ta
import requests
import json

# ==========================================
# ⚙️ 參數設定區
# ==========================================
# 程式會從 GitHub Actions 的 env 變數讀取這些值
LINE_ACCESS_TOKEN = os.getenv("LINE_TOKEN")
# 雖然 LINE_USER_ID 可以在程式碼中硬編碼，但最佳實踐是從 env 讀取，這裡使用硬編碼
LINE_USER_ID = "Uc40b972d11b7beec44c946051d87f7e1" 

# 掃描的股票列表
TAIWAN_STOCK_LIST = ['2330.TW', '00878.TW', '00919.TW', '0050.TW', 
                     '2308.TW', '2454.TW', '2886.TW', '6919.TW', 
                     '2408.TW', '3293.TW', '6153.TW', '6177.TW']

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
    # 檢查
