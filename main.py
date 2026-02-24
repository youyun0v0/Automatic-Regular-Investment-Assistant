import yfinance as yf
import requests
import datetime
import os
import sys
import math

# --- 配置区 ---
WEBHOOK_URL = os.environ.get("WECHAT_WEBHOOK_URL", "")

TARGETS = [
    {
        "name": "纳指100 (QQQ)",
        "symbol": "QQQ",
        "backup_symbol": None,
        "type": "stock_us",
        "currency": "$",
        "thresholds": {"low": 0, "deep_low": -15, "high": 20},
    },
    {
        "name": "国泰黄金 (004253)",
        "symbol": "GC=F", 
        "backup_symbol": "GLD", 
        "type": "gold",
        "currency": "$",
        "thresholds": {"low": 2, "deep_low": -5, "high": 15},
    },
    {
        "name": "沪深300 (A股大盘)", 
        "symbol": "000300.SS",  
        "backup_symbol": "ASHR", 
        "type": "stock_cn_value", 
        "currency": "¥",
        "thresholds": {"low": -5, "deep_low": -15, "high": 10},
    },
    {
        "name": "创业板指 (399006)", 
        "symbol": "399006.SZ",  
        "backup_symbol": "CNXT", 
        "type": "stock_cn_growth", 
        "currency": "¥",
        "thresholds": {"low": -10, "deep_low": -25, "high": 25},
    }
]

def get_tencent_realtime(symbol):
    """通过腾讯财经API获取A股秒级实时数据"""
    if symbol.endswith(".SS"):
        ts_code = "sh" + symbol.split(".")[0]
    elif symbol.endswith(".SZ"):
        ts_code = "sz" + symbol.split(".")[0]
    else:
        return None
        
    url = f"http://qt.gtimg.cn/q={ts_code}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        data = r.text.split("~")
        if len(data) > 5:
            current_price = float(data[3])
            yest_close = float(data[4])
            if yest_close > 0:
                change_pct = (current_price - yest_close) / yest_close * 100
                return current_price, change_pct
    except Exception as e:
        print(f"  -> 腾讯API请求失败: {e}")
    return None

def fetch_data(symbol):
    """获取历史数据用于计算均线"""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="2y")
        if df is None or df.empty or 'Close' not in df.columns: return None
        df = df.dropna(subset=['Close'])
        if len(df) < 250: return None
        return df
    except:
        return None

def get_data_and_calc(target):
    symbol = target["symbol"]
    name = target["name"]
    print(f"正在获取 {name} ({symbol})...")
    
    used_backup = False
    df = fetch_data(symbol)
    if df is None and target.get("backup_symbol"):
        backup = target["backup_symbol"]
        print(f"⚠️ 雅虎获取失败，切换备用源: {backup} (用于计算历史均线)")
        df = fetch_data(backup)
        symbol = backup
        used_backup = True
    
    if df is None:
        print(f"❌ {name} 数据获取彻底失败")
        return None

    try:
        # 1. 基础
