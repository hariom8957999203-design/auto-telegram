import telebot
import yfinance as yf
import pandas as pd
import numpy as np
import threading
import time
import os
from flask import Flask

# =====================================================================
# 1. RENDER PORT BINDING ENGINE (24/7 Uptime)
# =====================================================================
app = Flask(__name__)

@app.route('/')
def home():
    return "⚡ QUANT AUTOMATED SCANNER ENGINE IS RUNNING 24/7 ⚡"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# =====================================================================
# 2. CONFIGURATION & EXACT USER WATCHLIST
# =====================================================================
API_TOKEN = '8639171627:AAGQaG27vA5tw12iEtLfs0Nz-hvyFYrBt4s' # <-- Apna Telegram Bot Token Yahan Daalein
CHAT_ID = '8110538450'    # <-- Apna Telegram Chat ID Yahan Daalein

# Aapke diye hue exact 23 stocks ki list (Sahi Ticker Format Mein)
WATCHLIST = [
    "NBCC.NS",         # 1. NBCC (NBSS)
    "UCOBANK.NS",      # 2. UCO Bank
    "IDEA.NS",         # 3. Vodafone Idea
    "IDBI.NS",         # 4. IDBI Bank
    "IFCI.NS",         # 5. IFCI
    "IOB.NS",          # 6. Indian Overseas Bank
    "PCJEWELLER.NS",   # 7. PC Jeweller
    "SEPC.NS",         # 8. SEPC
    "GTLINFRA.NS",     # 9. GTL / GTL Infra
    "JPPOWER.NS",      # 10. Jaiprakash Power Ventures
    "GMRINFRA.NS",     # 11. GMR Airports / Infrastructure
    "PNB.NS",          # 12. Punjab National Bank
    "RTNPOWER.NS",     # 13. RattanIndia Power
    "SOUTHBANK.NS",    # 14. South Indian Bank
    "CENTRALBK.NS",    # 15. Central Bank of India
    "PSB.NS",          # 18. Punjab & Sind Bank
    "NHPC.NS",         # 19. NHPC
    "SUZLON.NS",       # 20. Suzlon Energy
    "TRIDENT.NS",      # 21. Trident
    "IRB.NS"           # 23. IRB Infrastructure Developers
]

bot = telebot.TeleBot(API_TOKEN)

# Duplicate alert rokne ke liye tracker dictionary
last_sent_signals = {} 

# =====================================================================
# 3. REAL-TIME DATA & INDICATORS ENGINE
# =====================================================================
def get_realtime_df(symbol, period, interval):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)
        if df.empty: return df

        try:
            live_price = ticker.fast_info.get('lastPrice') or ticker.fast_info.get('last_price')
            if live_price and not np.isnan(live_price):
                live_price = float(live_price)
                df.loc[df.index[-1], 'Close'] = live_price
                if live_price > df.loc[df.index[-1], 'High']: df.loc[df.index[-1], 'High'] = live_price
                if live_price < df.loc[df.index[-1], 'Low']: df.loc[df.index[-1], 'Low'] = live_price
        except Exception:
            pass

        return df
    except Exception:
        return pd.DataFrame()

def clean_and_flatten_df(df):
    if df.empty: return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    cleaned_df = pd.DataFrame(index=df.index)
    for col in required_cols:
        if col in df.columns:
            cleaned_df[col] = pd.to_numeric(df[col].values.flatten(), errors='coerce')
    return cleaned_df.dropna(subset=['Close'])

def calculate_indicators(df):
    df = clean_and_flatten_df(df)
    if len(df) < 50: return df

    df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()

    tp = (df['High'] + df['Low'] + df['Close']) / 3
    df['VWAP'] = (tp * df['Volume']).rolling(20).sum() / (df['Volume'].rolling(20).sum() + 1e-10)

    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    df['RSI'] = 100 - (100 / (1 + rs))

    df['VOL_MA'] = df['Volume'].rolling(20).mean()

    high, low, close_prev = df['High'], df['Low'], df['Close'].shift(1)
    tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(14).mean()

    upmove = df['High'].diff()
    downmove = df['Low'].shift(1) - df['Low']
    plus_dm = np.where((upmove > downmove) & (upmove > 0), upmove, 0.0)
    minus_dm = np.where((downmove > upmove) & (downmove > 0), downmove, 0.0)
    tr_sum = tr.rolling(14).sum() + 1e-10
    plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(14).sum() / tr_sum)
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(14).sum() / tr_sum)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    df['ADX'] = dx.rolling(14).mean()

    atr_multiplier = 2.0
    hl2 = (df['High'] + df['Low']) / 2
    df['UB'] = hl2 + (atr_multiplier * df['ATR'])
    df['LB'] = hl2 - (atr_multiplier * df['ATR'])
    df['ST_DIR'] = 1
    
    for i in range(1, len(df)):
        if df['Close'].iloc[i-1] > df['UB'].iloc[i-1]: df.loc[df.index[i], 'UB'] = min(df['UB'].iloc[i], df['UB'].iloc[i-1])
        if df['Close'].iloc[i-1] < df['LB'].iloc[i-1]: df.loc[df.index[i], 'LB'] = max(df['LB'].iloc[i], df['LB'].iloc[i-1])
        if df['Close'].iloc[i] > df['UB'].iloc[i-1]: df.loc[df.index[i], 'ST_DIR'] = 1
        elif df['Close'].iloc[i] < df['LB'].iloc[i-1]: df.loc[df.index[i], 'ST_DIR'] = -1
        else: df.loc[df.index[i], 'ST_DIR'] = df['ST_DIR'].iloc[i-1]

    df.ffill(inplace=True)
    df.fillna(0.0, inplace=True)
    return df

# =====================================================================
# 4. LIVE SIGNAL GENERATOR
# =====================================================================
def generate_signals(df_curr, df_macro):
    if len(df_curr) < 2 or len(df_macro) < 2:
        return "HOLD", 0.0, 1.0, "Data insufficient"

    m = df_macro.iloc[-1]
    macro_bullish = (m['Close'] > m['EMA_200']) or (m['ST_DIR'] == 1)
    macro_bearish = (m['Close'] < m['EMA_200']) or (m['ST_DIR'] == -1)

    p = df_curr.iloc[-1]
    close, ema9, ema21, vwap = float(p['Close']), float(p['EMA_9']), float(p['EMA_21']), float(p['VWAP'])
    rsi, adx, atr = float(p['RSI']), float(p['ADX']), float(p['ATR'])
    volume, vol_ma, st_dir = float(p['Volume']), float(p['VOL_MA']), p['ST_DIR']

    is_volume_confirmed = volume > (vol_ma * 0.85)
    is_trend_strong = adx > 15.0

    if (ema9 > ema21) and (close > vwap) and (st_dir == 1) and macro_bullish:
        if (40.0 <= rsi <= 75.0) and is_volume_confirmed and is_trend_strong:
            return "BUY", close, atr, "Live Breakout Confirmed"

    elif (ema9 < ema21) and (close < vwap) and (st_dir == -1) and macro_bearish:
        if (25.0 <= rsi <= 60.0) and is_volume_confirmed and is_trend_strong:
            return "SELL", close, atr, "Live Breakdown Confirmed"

    return "HOLD", close, atr, "No trade setup"

def calculate_risk(signal, entry, atr):
    risk = (atr * 1.5) if atr > 0 else (entry * 0.012)
    if "BUY" in signal:
        return round(entry - risk, 2), round(entry + (risk * 1.5), 2), round(entry + (risk * 3.0), 2)
    elif "SELL" in signal:
        return round(entry + risk, 2), round(entry - (risk * 1.5), 2), round(entry - (risk * 3.0), 2)
    return "N/A", "N/A", "N/A"

# =====================================================================
# 5. AUTOMATED WATCHLIST SCANNER (24/7 AUTO ALERTS)
# =====================================================================
def auto_market_scanner():
    while True:
        try:
            for symbol in WATCHLIST:
                df_curr_raw = get_realtime_df(symbol, period="1mo", interval="15m")
                df_macro_raw = get_realtime_df(symbol, period="3mo", interval="1h")

                if df_curr_raw.empty or df_macro_raw.empty: continue

                df_curr = calculate_indicators(df_curr_raw)
                df_macro = calculate_indicators(df_macro_raw)

                signal, entry, atr, reason = generate_signals(df_curr, df_macro)

                # Send Telegram alert ONLY when a NEW BUY or SELL triggers
                if signal in ["BUY", "SELL"]:
                    if last_sent_signals.get(symbol) != signal:
                        last_sent_signals[symbol] = signal
                        sl, t1, t2 = calculate_risk(signal, entry, atr)
                        
                        label = "🟢 [AUTO BUY SIGNAL]" if signal == "BUY" else "🔴 [AUTO SELL SIGNAL]"
                        msg = (
                            f"{label}\n"
                            f"Stock: **{symbol}**\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"💰 **ENTRY PRICE:** ₹{round(entry, 2)}\n"
                            f"🛑 **STOP LOSS:** ₹{sl}\n"
                            f"🎯 **TARGET 1:** ₹{t1}\n"
                            f"🎯 **TARGET 2:** ₹{t2}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📋 **REASON:** _{reason}_"
                        )
                        if CHAT_ID and CHAT_ID != 'YAHAN_APNA_CHAT_ID_DALEIN':
                            bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
                else:
                    last_sent_signals[symbol] = "HOLD"

                time.sleep(2)
        except Exception as e:
            print(f"Scanner Error: {e}")

        time.sleep(180) # Scans every 3 minutes

# =====================================================================
# 6. TELEGRAM COMMAND HANDLERS
# =====================================================================
@bot.message_handler(commands=['start', 'status'])
def show_status(message):
    bot.reply_to(message, "📡 Tracking your 23 custom stocks...")
    summary = "📊 **YOUR STOCKS WATCHLIST STATUS** 📊\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    for symbol in WATCHLIST:
        try:
            df_curr_raw = get_realtime_df(symbol, period="1mo", interval="15m")
            df_macro_raw = get_realtime_df(symbol, period="3mo", interval="1h")
            if df_curr_raw.empty: continue
            
            df_curr = calculate_indicators(df_curr_raw)
            df_macro = calculate_indicators(df_macro_raw)
            
            signal, entry, _, _ = generate_signals(df_curr, df_macro)
            icon = "🟢" if signal == "BUY" else ("🔴" if signal == "SELL" else "🟡")
            summary += f"{icon} **{symbol}**: `{signal}` @ ₹{round(entry, 2)}\n"
        except Exception:
            summary += f"⚠️ **{symbol}**: Data Error\n"
            
    bot.reply_to(message, summary, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def process_manual_request(message):
    symbol = message.text.upper().replace(" ", "").strip()
    if symbol.startswith('/'): return

    bot.reply_to(message, f"⚡ Fetching Real-Time Market Ticks for {symbol}...")
    try:
        df_curr_raw = get_realtime_df(symbol, period="1mo", interval="15m")
        df_macro_raw = get_realtime_df(symbol, period="3mo", interval="1h")

        if df_curr_raw.empty or df_macro_raw.empty:
            bot.reply_to(message, f"❌ `{symbol}` invalid symbol. Put .NS for NSE stocks.")
            return

        df_curr = calculate_indicators(df_curr_raw)
        df_macro = calculate_indicators(df_macro_raw)
        signal, entry, atr, log_reason = generate_signals(df_curr, df_macro)

        sl, t1, t2 = calculate_risk(signal, entry, atr)
        label = "🟡 HOLD"
        if "BUY" in signal: label = "🟢 BUY ALERT"
        if "SELL" in signal: label = "🔴 SELL ALERT"

        dashboard = (
            f"{label}\n"
            f"Asset: **{symbol}**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 **ACTION:** `{signal}`\n"
            f"💰 **LIVE PRICE:** ₹{round(entry, 2)}\n"
            f"🛑 **SL:** ₹{sl} | 🎯 **T1:** ₹{t1} | 🎯 **T2:** ₹{t2}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 **NOTE:** _{log_reason}_"
        )
        bot.reply_to(message, dashboard, parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "⚠️ Market Stream Error. Try again.")

# =====================================================================
# 7. MAIN EXECUTION ENGINE
# =====================================================================
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=auto_market_scanner, daemon=True).start()
    print("🚀 Quantum automated scanner bot active.")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
