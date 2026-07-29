import time
import logging
import pandas as pd
import numpy as np
import yfinance as yf
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import os
import os

# Render ke environment variables se keys uthana
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("8639171627:AAGQaG27vA5tw12iEtLfs0Nz-hvyFYrBt4s")

openai_client = OpenAI(api_key=OPENAI_API_KEY)
# 2. Telegram Bot Token read karein
TELEGRAM_BOT_TOKEN = os.getenv("8639171627:AAGQaG27vA5tw12iEtLfs0Nz-hvyFYrBt4s")

# 3. OpenAI Client initialize karein
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# ==================== 4-LENS ANALYSIS ENGINE ====================
def calculate_indicators(df):
    """Lens 1: Technical Indicators Calculation"""
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
    
    df['Support'] = df['Low'].rolling(window=20).min()
    df['Resistance'] = df['High'].rolling(window=20).max()
    return df

def analyze_stock_4lens(ticker):
    """Executes Deeepr AI style 4-Lens Evaluation"""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="3m", interval="1d")
        if df.empty or len(df) < 20:
            return None
        
        df = calculate_indicators(df)
        last_row = df.iloc[-1]
        
        close_price = round(float(last_row['Close']), 2)
        rsi = round(float(last_row['RSI']), 2)
        ema_9 = round(float(last_row['EMA_9']), 2)
        ema_20 = round(float(last_row['EMA_20']), 2)
        support = round(float(last_row['Support']), 2)
        resistance = round(float(last_row['Resistance']), 2)
        
        vol_change = round(((last_row['Volume'] - df['Volume'].mean()) / df['Volume'].mean()) * 100, 2)
        
        news_list = stock.news[:3] if hasattr(stock, 'news') and stock.news else []
        news_headlines = [item.get('title', '') for item in news_list]
        
        prompt = f"""
        Act as Deeepr AI Stock Evaluation Engine. Analyze {ticker} using 4-Lens Methodology:
        1. Technicals: Close={close_price}, RSI={rsi}, EMA9={ema_9}, EMA20={ema_20}, Supp={support}, Res={resistance}.
        2. Flow: Volume Change vs Avg = {vol_change}%.
        3. Recent News Headlines: {news_headlines}.
        
        Determine if there is a STRONG TRADE SIGNAL (BUY / SELL / NO_TRADE).
        If NO_TRADE, reply ONLY 'NO_TRADE'.
        If BUY or SELL, return format:
        SIGNAL: [BUY/SELL]
        ENTRY: [Price]
        SL: [Stop Loss]
        TP1: [Target 1]
        TP2: [Target 2]
        REASON: [2-line explanation combining Technical + Flow + News]
        """
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        
        ai_output = response.choices[0].message.content.strip()
        
        if "NO_TRADE" in ai_output:
            return None
            
        return {
            "ticker": ticker,
            "price": close_price,
            "rsi": rsi,
            "ai_signal": ai_output
        }
    except Exception as e:
        logging.error(f"Error analyzing {ticker}: {e}")
        return None

# ==================== TELEGRAM BOT HANDLERS ====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🚀 <b>Deeepr AI Stock Scanner Bot Active!</b>\n\n"
        "Commands:\n"
        "1. <code>/add SYMBOL</code> - Add stock to auto-research watchlist (e.g. /add RELIANCE.NS, /add TATAMOTORS.NS, /add AAPL)\n"
        "2. <code>/remove SYMBOL</code> - Remove stock from watchlist\n"
        "3. <code>/list</code> - View tracked stocks\n"
        "4. <code>/scan SYMBOL</code> - Run immediate 4-Lens AI Analysis"
    )
    await update.message.reply_text(welcome_text, parse_mode="HTML")

async def add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("⚠️ Please provide ticker name! Example: <code>/add TATAMOTORS.NS</code>", parse_mode="HTML")
        return
    
    ticker = context.args[0].upper()
    if ticker not in WATCHLIST:
        WATCHLIST[ticker] = []
    if chat_id not in WATCHLIST[ticker]:
        WATCHLIST[ticker].append(chat_id)
        
    await update.message.reply_text(f"✅ <b>{ticker}</b> added to background scanning watchlist!", parse_mode="HTML")

async def remove_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("⚠️ Please provide ticker name! Example: <code>/remove TATAMOTORS.NS</code>", parse_mode="HTML")
        return
    
    ticker = context.args[0].upper()
    if ticker in WATCHLIST and chat_id in WATCHLIST[ticker]:
        WATCHLIST[ticker].remove(chat_id)
        await update.message.reply_text(f"🗑️ <b>{ticker}</b> removed from watchlist.", parse_mode="HTML")
    else:
        await update.message.reply_text(f"⚠️ {ticker} was not in your watchlist.")

async def list_stocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_stocks = [ticker for ticker, chats in WATCHLIST.items() if chat_id in chats]
    if user_stocks:
        await update.message.reply_text(f"📊 <b>Your Watchlist:</b>\n" + "\n".join([f"• {s}" for s in user_stocks]), parse_mode="HTML")
    else:
        await update.message.reply_text("Your watchlist is empty. Add using <code>/add SYMBOL</code>", parse_mode="HTML")

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: <code>/scan SYMBOL</code>", parse_mode="HTML")
        return
    
    ticker = context.args[0].upper()
    await update.message.reply_text(f"🔍 Running 4-Lens Deeepr AI Analysis for <b>{ticker}</b>...", parse_mode="HTML")
    result = analyze_stock_4lens(ticker)
    
    if result:
        msg = f"🎯 <b>Deeepr AI Signal Generated: {ticker}</b>\n\n{result['ai_signal']}"
        await update.message.reply_text(msg, parse_mode="HTML")
    else:
        await update.message.reply_text(f"ℹ️ <b>{ticker}</b>: No high-probability setup found right now.", parse_mode="HTML")

async def auto_scan_job(context: ContextTypes.DEFAULT_TYPE):
    """Runs every 15 minutes to evaluate tracked stocks"""
    if not WATCHLIST:
        return
        
    for ticker, chat_ids in WATCHLIST.items():
        if not chat_ids:
            continue
        result = analyze_stock_4lens(ticker)
        if result:
            alert_msg = (
                f"🚨 <b>AUTOMATIC DEEEPR AI TRADE ALERT</b> 🚨\n"
                f"Stock: <b>{ticker}</b>\n\n"
                f"{result['ai_signal']}"
            )
            for cid in chat_ids:
                await context.bot.send_message(chat_id=cid, text=alert_msg, parse_mode="HTML")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("add", add_stock))
    app.add_handler(CommandHandler("remove", remove_stock))
    app.add_handler(CommandHandler("list", list_stocks))
    app.add_handler(CommandHandler("scan", scan_command))
    
    job_queue = app.job_queue
    job_queue.run_repeating(auto_scan_job, interval=900, first=10) # 900 Seconds = 15 Mins
    
    print("Bot is up and running...")
    app.run_polling()
