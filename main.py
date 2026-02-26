import yfinance as yf
import requests
import datetime
import os
import sys
import math

# --- 配置区 ---
WEBHOOK_URL = os.environ.get("WECHAT_WEBHOOK_URL", "")

TARGETS = [
    # 1. 美股成长 (进攻)
    {
        "name": "纳指100 (QQQ)",
        "symbol": "QQQ",
        "backup_symbol": None,
        "type": "stock_us",
        "currency": "$",
        "thresholds": {"low": 0, "deep_low": -15, "high": 20},
    },
    # 2. 美股大盘 (稳健底仓)
    {
        "name": "标普500 (SPY)",
        "symbol": "SPY", 
        "backup_symbol": "VOO", 
        "type": "stock_us",
        "currency": "$",
        "thresholds": {"low": 0, "deep_low": -10, "high": 15}, 
    },
    # 3. 全球避险 (防守)
    {
        "name": "国泰黄金 (004253)",
        "symbol": "GC=F", 
        "backup_symbol": "GLD", 
        "type": "gold",
        "currency": "$",
        "thresholds": {"low": 2, "deep_low": -5, "high": 15},
    },
    # 4. A股高弹性 (激进)
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
    if symbol.endswith(".SS"): ts_code = "sh" + symbol.split(".")[0]
    elif symbol.endswith(".SZ"): ts_code = "sz" + symbol.split(".")[0]
    else: return None
        
    url = f"http://qt.gtimg.cn/q={ts_code}"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        data = r.text.split("~")
        if len(data) > 5:
            current_price = float(data[3])
            yest_close = float(data[4])
            if yest_close > 0:
                return current_price, (current_price - yest_close) / yest_close * 100
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
    except: return None

def get_data_and_calc(target):
    symbol = target["symbol"]
    name = target["name"]
    print(f"正在获取 {name} ({symbol})...")
    
    used_backup = False
    df = fetch_data(symbol)
    if df is None and target.get("backup_symbol"):
        backup = target["backup_symbol"]
        print(f"⚠️ 雅虎获取失败，切换备用源: {backup}")
        df = fetch_data(backup)
        symbol = backup
        used_backup = True
    
    if df is None:
        print(f"❌ {name} 数据获取彻底失败")
        return None

    try:
        # 1. 基础计算
        df_current_price = float(df['Close'].iloc[-1])
        prev_price = float(df['Close'].iloc[-2])
        daily_change = (df_current_price - prev_price) / prev_price * 100
        
        ma250 = float(df['Close'].rolling(window=250).mean().iloc[-1])
        high_250 = float(df['Close'].rolling(window=250).max().iloc[-1])
        if math.isnan(ma250): return None 

        bias = (df_current_price - ma250) / ma250 * 100
        drawdown = (df_current_price - high_250) / high_250 * 100
        display_price = df_current_price

        # 2. A股强制实时覆盖
        if 'cn' in target['type']:
            rt_data = get_tencent_realtime(target['symbol']) 
            if rt_data:
                rt_price, rt_change = rt_data
                display_price = rt_price   
                daily_change = rt_change   
                print(f"  -> ⚡ 成功强制覆盖国内实时行情: {rt_price}, {round(rt_change, 2)}%")
                
                if not used_backup:
                    bias = (rt_price - ma250) / ma250 * 100
                    drawdown = (rt_price - high_250) / high_250 * 100
                else:
                    print("  -> ℹ️ 历史均线使用了海外ETF，展示价格已替换为国内实时指数")

        return {
            "name": name,
            "date": datetime.datetime.utcnow().strftime('%Y-%m-%d'),
            "price": round(display_price, 2),
            "daily_change": round(daily_change, 2), 
            "bias": round(bias, 2),
            "drawdown": round(drawdown, 2),
            "target_config": target
        }
    except Exception as e:
        print(f"❌ 计算指标出错 {name}: {e}")
        return None

def generate_advice(data):
    t = data['target_config']
    bias = data['bias']
    dd = data['drawdown']
    th = t['thresholds']
    
    advice, level = "", "normal"
    
    # 黄金策略
    if t['type'] == 'gold':
        if bias < th['deep_low']: 
            advice, level = "💎 **极度低估**：罕见机会，建议 **2.0倍 囤货**", "opportunity"
        elif bias < 0: 
            advice, level = "📀 **跌破年线**：低于成本，建议 **1.5倍 买入**", "opportunity"
        elif bias < th['low']:
            advice, level = "⚖️ **支撑位**：回踩年线，建议 **1.2倍 上车**", "opportunity"
        elif bias > th['high']:
            advice, level = "🔥 **短期过热**：建议 **暂停买入**", "risk"
        else:
            advice, level = "😐 **趋势向上**：建议 **正常定投**", "normal"

    # A股成长策略
    elif t['type'] == 'stock_cn_growth':
        if bias < th['deep_low']: 
            advice, level = "⚡ **血流成河**：崩盘下跌，建议 **4.0倍 极限抄底**", "opportunity"
        elif bias < th['low']:    
            advice, level = "📉 **击穿防线**：跌破年线，建议 **2.0倍 越跌越买**", "opportunity"
        elif dd < -30:            
            advice, level = "🎢 **深幅回撤**：回撤超30%，建议 **1.5倍 捡带血筹码**", "opportunity"
        elif bias > th['high']:   
            advice, level = "💣 **极度泡沫**：建议 **清仓止盈 走人**", "risk"
        else:
            advice, level = "🎲 **高波震荡**：看不清方向，建议 **少投 或 观望**", "normal"

    # 美股策略 (纳指 & 标普通用)
    else: 
        if bias < th['deep_low']: 
            advice, level = "💎 **钻石坑**：极度贪婪时刻，建议 **3倍 梭哈**", "opportunity"
        elif bias < 0:
            advice, level = "📀 **黄金坑**：年线下方，建议 **2倍 加码**", "opportunity"
        elif dd < -15:
            advice, level = "📉 **急跌机会**：回撤超15%，建议 **1.5倍 捡筹码**", "opportunity"
        elif bias > th['high']:
            advice, level = "🚫 **极度过热**：建议 **止盈 或 观望**", "risk"
        else:
            advice, level = "😐 **正常区间**：建议 **正常定投**", "normal"
            
    return advice, level

def get_pretty_strategy_text():
    text = "\n\n---\n### 📖 策略说明书\n"
    for t in TARGETS:
        name_short = t['name'].split("(")[0]
        th = t['thresholds']
        t_type = t['type']
        
        if 'us' in t_type: icon = "🇺🇸"
        elif 'gold' in t_type: icon = "🧈"
        elif 'growth' in t_type: icon = "⚡"
        else: icon = "🇨🇳"
        
        text += f"**{icon} {name_short}**\n"
        
        if 'growth' in t_type:
            text += f"- ⚡ **血流成河**: 偏离 < {th['deep_low']}% (4倍抄底)\n"
            text += f"- 💣 **极度泡沫**: 偏离 > {th['high']}% (清仓走人)\n"
        elif 'gold' in t_type:
            text += f"- 💎 **极度低估**: 偏离 < {th['deep_low']}% (2倍囤货)\n"
            text += f"- 🔥 **短期过热**: 偏离 > {th['high']}% (暂停买入)\n"
        else:
            text += f"- 💎 **钻石坑位**: 偏离 < {th['deep_low']}% (3倍梭哈)\n"
            text += f"- 🚫 **极度过热**: 偏离 > {th['high']}% (止盈/观望)\n"
        text += "\n"
    text += "> <font color=\"comment\">注：偏离指当前价与年线(MA250)的距离</font>"
    return text

def send_combined_notification(results):
    if not results: return
    
    bjt_time = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M')
    markdown_content = f"## 🤖 全球定投日报\n**时间**: {bjt_time}\n\n"
    
    for item in results:
        advice, level = generate_advice(item)
        title_color = "warning" if level == "risk" else "info"
        if level == "normal": title_color = "comment"
        
        t = item['target_config']
        t_type = t['type']
        currency = t.get('currency', '')
        
        if 'us' in t_type: icon = "🇺🇸"
        elif 'gold' in t_type: icon = "🧈"
        elif 'growth' in t_type: icon = "⚡"
        else: icon = "🇨🇳"
        
        change = item['daily_change']
        if change > 0: change_str = f"+{change}% 📈"
        elif change < 0: change_str = f"{change}% 📉"
        else: change_str = "0.00% ➖"
        
        block = f"""
---
### {icon} <font color="{title_color}">{item['name']}</font>
- **当前价格**: {currency}{item['price']} ({change_str})
- **年线乖离**: {item['bias']}%
- **高点回撤**: {item['drawdown']}%
> **策略**: {advice}
"""
        markdown_content += block

    markdown_content += get_pretty_strategy_text()
    payload = {"msgtype": "markdown", "markdown": {"content": markdown_content.strip()}}
    
    if WEBHOOK_URL:
        try:
            requests.post(WEBHOOK_URL, json=payload)
            print("✅ 消息发送成功")
        except Exception as e:
            print(f"❌ 发送失败: {e}")
    else:
        print(markdown_content)

if __name__ == "__main__":
    results = []
    print("🚀 启动分析...")
    for target in TARGETS:
        data = get_data_and_calc(target)
        if data: results.append(data)
    
    send_combined_notification(results)
    print("🏁 结束")
