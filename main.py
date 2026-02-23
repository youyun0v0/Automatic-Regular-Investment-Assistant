import yfinance as yf
import requests
import datetime
import os
import sys

# --- 配置区 ---
# 从环境变量获取 Webhook，如果没有则使用空字符串（这会导致报错，提醒你去设置）
WEBHOOK_URL = os.environ.get("WECHAT_WEBHOOK_URL", "")
# 标的：纳指100 ETF
TICKER = "QQQ" 

def get_market_data_advanced():
    """获取数据：计算年线偏离度和高点回撤"""
    print(f"正在获取 {TICKER} 数据...")
    
    # 获取过去 2 年数据 (计算年线需要250个交易日)
    try:
        df = yf.download(TICKER, period="2y", progress=False)
    except Exception as e:
        print(f"下载数据失败: {e}")
        sys.exit(1)
    
    if df.empty:
        print("未获取到数据，请检查网络或股票代码")
        sys.exit(1)

    # 获取最新收盘价 (.item() 将 numpy 类型转为 python原生 float)
    current_price = df['Close'].iloc[-1].item()
    last_date = df.index[-1].strftime('%Y-%m-%d')
    
    # 1. 计算年线 (MA250) 及 偏离度 (Bias)
    # 如果数据不足250天，这里会报错，所以前面获取了2y数据
    ma250 = df['Close'].rolling(window=250).mean().iloc[-1].item()
    bias = (current_price - ma250) / ma250 * 100
    
    # 2. 计算距离 250 天内最高价的回撤幅度 (Drawdown)
    high_250 = df['Close'].rolling(window=250).max().iloc[-1].item()
    drawdown = (current_price - high_250) / high_250 * 100
    
    return {
        "date": last_date,
        "price": round(current_price, 2),
        "ma250": round(ma250, 2),
        "bias": round(bias, 2),       
        "drawdown": round(drawdown, 2)
    }

def get_strategy_advanced(data):
    """根据偏离度和回撤生成建议"""
    bias = data['bias']
    dd = data['drawdown']
    
    advice = ""
    color = "info" # 默认绿色
    
    # --- 策略逻辑 ---
    if bias < -10:
        advice = "💎 **钻石坑位**：低于年线10%以上\n👉 建议：**2.0倍 - 3.0倍 梭哈级定投**"
        color = "info" 
    elif bias < 0:
        advice = "📀 **黄金坑位**：价格在年线下方\n👉 建议：**1.5倍 - 2.0倍 加倍定投**"
        color = "info"
    elif dd < -15:
        advice = "📉 **急跌机会**：较高点回撤超15%\n👉 建议：**1.5倍 捡筹码**"
        color = "info"
    elif 0 <= bias < 15:
        advice = "😐 **正常区间**：趋势向上但未过热\n👉 建议：**1.0倍 正常定投**"
        color = "warning" # 橙色
    elif bias >= 15 and bias < 25:
        advice = "🔥 **略微过热**：偏离年线超15%\n👉 建议：**0.5倍 减少定投**"
        color = "warning"
    else: # bias >= 25
        advice = "🚫 **极度过热**：偏离年线超25%\n👉 建议：**暂停买入 或 止盈**"
        color = "warning" # 红色
        
    return advice, color

def send_wechat_notification(data, advice, color="info"):
    """发送消息到企业微信"""
    
    if not WEBHOOK_URL:
        print("错误：未设置 WECHAT_WEBHOOK_URL 环境变量！")
        return

    # 根据策略决定标题颜色 (markdown中绿色通常用info, 橙红用warning)
    title_color = "info" if color == "info" else "warning"

    markdown_content = f"""
## <font color="{title_color}">🤖 纳斯达克定投助手</font>
**日期**: {data['date']}
**标的**: {TICKER} (纳指100)

---
### 📊 核心指标
- **当前价格**: ${data['price']}
- **年线位置**: ${data['ma250']}
- **年线偏离**: <font color="{title_color}">{data['bias']}%</font>
- **高点回撤**: {data['drawdown']}%

---
### 💡 投资建议
{advice}
    """
    
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": markdown_content.strip()
        }
    }
    
    try:
        resp = requests.post(WEBHOOK_URL, json=payload)
        resp.raise_for_status() # 如果是 4xx/5xx 错误直接抛出异常
        
        # 检查企业微信特有的错误码
        result = resp.json()
        if result.get("errcode") == 0:
            print("✅ 消息发送成功！")
        else:
            print(f"❌ 企业微信拒绝接收: {result}")
            sys.exit(1) # 让 Actions 变红
            
    except Exception as e:
        print(f"❌ 网络请求发送失败: {e}")
        sys.exit(1)

# --- 主程序入口 ---
if __name__ == "__main__":
    try:
        # 1. 获取数据 (使用 Advanced 版本)
        market_data = get_market_data_advanced()
        
        # 2. 生成策略
        advice_text, color_code = get_strategy_advanced(market_data)
        
        # 3. 发送通知
        send_wechat_notification(market_data, advice_text, color_code)
        
    except Exception as e:
        print(f"❌ 脚本运行出错: {e}")
        sys.exit(1)
