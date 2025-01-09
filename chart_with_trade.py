import tkinter as tk
from tkinter import messagebox, ttk
from threading import Thread
from time import sleep
import pandas as pd
from pybit.unified_trading import HTTP
from keys import api, secret
import sys
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import requests
import mplfinance as mpf


session = HTTP(
    api_key=api,
    api_secret=secret
)

# Config:
tp = 0.012  # Take Profit +1.2%
sl = 0.009  # Stop Loss -0.9%
timeframe = 15  # 15 minutes
mode = 1  # 1 - Isolated, 0 - Cross
leverage = 10
qty = 50    # Amount of USDT for one order

class TextRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, message):
        self.text_widget.insert(tk.END, message)
        self.text_widget.yview(tk.END)  # Auto-scroll to the bottom

    def flush(self):
        pass  # No need to implement for our purposes


# Getting balance on Bybit Derivatrives Asset (in USDT)
def get_balance():
    try:
        resp = session.get_wallet_balance(accountType="CONTRACT", coin="USDT")['result']['list'][0]['coin'][0]['walletBalance']
        resp = float(resp)
        return resp
    except Exception as err:
        print(err)

print(f'Your balance: {get_balance()} USDT')


# Getting all available symbols from Derivatives market (like 'BTCUSDT', 'XRPUSDT', etc)
def get_tickers():
    try:
        resp = session.get_tickers(category="linear")['result']['list']
        symbols = []
        for elem in resp:
            if 'USDT' in elem['symbol'] and not 'USDC' in elem['symbol']:
                symbols.append(elem['symbol'])
        return symbols
    except Exception as err:
        print(err)


# Klines is the candles of some symbol (up to 1500 candles). Dataframe, last elem has [-1] index
def klines(symbol):
    try:
        resp = session.get_kline(
            category='linear',
            symbol=symbol,
            interval=timeframe,
            limit=500
        )['result']['list']
        resp = pd.DataFrame(resp)
        resp.columns = ['Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Turnover']
        resp = resp.set_index('Time')
        resp = resp.astype(float)
        resp = resp[::-1]
        return resp
    except Exception as err:
        print(err)


# Getting your current positions. It returns symbols list with opened positions
def get_positions():
    try:
        resp = session.get_positions(
            category='linear',
            settleCoin='USDT'
        )['result']['list']
        pos = []
        for elem in resp:
            pos.append(elem['symbol'])
        return pos
    except Exception as err:
        print(err)


# Getting last 50 PnL. I used it to check strategies performance
def get_pnl():
    try:
        resp = session.get_closed_pnl(category="linear", limit=50)['result']['list']
        pnl = 0
        for elem in resp:
            pnl += float(elem['closedPnl'])
        return pnl
    except Exception as err:
        print(err)

def get_symbols():
    try:
        return [item['symbol'] for item in session.get_instruments_info(category='linear')['result']['list']]
    except Exception as err:
        print(f"Error retrieving symbols: {err}")
        return []


# Changing mode and leverage: 
def set_mode(symbol):
    try:
        resp = session.switch_margin_mode(
            category='linear',
            symbol=symbol,
            tradeMode=mode,
            buyLeverage=leverage,
            sellLeverage=leverage
        )
        print(resp)
    except Exception as err:
        print(err)


# Getting number of decimal digits for price and qty
def get_precisions(symbol):
    try:
        resp = session.get_instruments_info(
            category='linear',
            symbol=symbol
        )['result']['list'][0]
        price = resp['priceFilter']['tickSize']
        if '.' in price:
            price = len(price.split('.')[1])
        else:
            price = 0
        qty = resp['lotSizeFilter']['qtyStep']
        if '.' in qty:
            qty = len(qty.split('.')[1])
        else:
            qty = 0

        return price, qty
    except Exception as err:
        print(err)
        

def get_ohlc(symbol, interval, limit=50):
    url = f"https://api.bybit.com/v5/market/kline"
    params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    if data["retCode"] != 0:
        raise ValueError(f"API Error: {data['retMsg']}")
    records = data["result"]["list"]
    df = pd.DataFrame(records, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    df['timestamp'] = pd.to_numeric(df['timestamp'])  # Explicitly cast to numeric type
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df.set_index('timestamp', inplace=True)
    numeric_cols = ["open", "high", "low", "close", "volume"]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
    df.drop(columns=["turnover"], inplace=True)
    df.sort_index(inplace=True)
    return df

def update_ohlc():
    symbol = symbol_var.get()
    interval = timeframe
    ohlc_data = get_ohlc(symbol, interval)
    root.after(60000, update_ohlc)


# Placing order with Market price. Placing TP and SL as well
def place_order_market(symbol, side):
    price_precision = get_precisions(symbol)[0]
    qty_precision = get_precisions(symbol)[1]
    mark_price = session.get_tickers(
        category='linear',
        symbol=symbol
    )['result']['list'][0]['markPrice']
    mark_price = float(mark_price)
    print(f'Placing {side} order for {symbol}. Mark price: {mark_price}')
    order_qty = round(qty/mark_price, qty_precision)
    sleep(2)
    if side == 'buy':
        try:
            tp_price = round(mark_price + mark_price * tp, price_precision)
            sl_price = round(mark_price - mark_price * sl, price_precision)
            resp = session.place_order(
                category='linear',
                symbol=symbol,
                side='Buy',
                orderType='Market',
                qty=order_qty,
                takeProfit=tp_price,
                stopLoss=sl_price,
                tpTriggerBy='MarkPrice',
                slTriggerBy='MarkPrice'
            )
            print(resp)
        except Exception as err:
            print(err)

    if side == 'sell':
        try:
            tp_price = round(mark_price - mark_price * tp, price_precision)
            sl_price = round(mark_price + mark_price * sl, price_precision)
            resp = session.place_order(
                category='linear',
                symbol=symbol,
                side='Sell',
                orderType='Market',
                qty=order_qty,
                takeProfit=tp_price,
                stopLoss=sl_price,
                tpTriggerBy='MarkPrice',
                slTriggerBy='MarkPrice'
            )
            print(resp)
        except Exception as err:
            print(err)
            
def open_long_trade():
    symbol = symbol_var.get()
    place_order_market(symbol, 'buy')

def open_short_trade():
    symbol = symbol_var.get()
    place_order_market(symbol, 'sell')


def update_parameters():
    global timeframe, leverage
    try:
        timeframe, leverage = int(timeframe_entry.get()), int(leverage_entry.get())
        balance = get_balance()
        print(f"Parameters updated: Balance: {balance}, Timeframe: {timeframe}, Leverage: {leverage}")
        update_chart()
    except ValueError as e:
        print(f"Invalid input: {e}")

def update_chart():
    try:
        if not root.focus_get() or not root.focus_get().winfo_exists():
            return  # Do not update the chart if the window is not focused or the widget does not exist
    except tk.TclError:
        return  # Handle the case where focus_get returns an invalid widget

    interval = timeframe
    symbol = target_symbol
    ohlc_data = get_ohlc(symbol, interval)
    if ohlc_data.empty:
        return

    ax1.clear()
    ax2.clear()

    # Plot candlestick chart
    mpf.plot(ohlc_data, type='candle', ax=ax1, style='charles', volume=ax2)

    ax1.set_title(f'{symbol} Price')
    ax1.set_ylabel('Price')
    ax2.set_title('Volume')
    ax2.set_ylabel('Volume')

    # Display OHLC data on the chart
    last_row = ohlc_data.iloc[-1]
    ohlc_text = f"Open: {last_row['open']}, High: {last_row['high']}, Low: {last_row['low']}, Close: {last_row['close']}"
    ax1.text(0.02, 0.98, ohlc_text, transform=ax1.transAxes, fontsize=8, verticalalignment='top')

    # Calculate and plot the volume threshold
    volume_threshold = ohlc_data['volume'].mean() * 1.1
    ax2.axhline(y=volume_threshold, color='r', linestyle='--', linewidth=1, label='Volume Threshold')
    ax2.legend()

    canvas.draw()
    
    # Schedule the next update in 1000 milliseconds (1 second)
    root.after(1000, update_chart)

def on_focus_in(event):
    update_chart()  # Start updating the chart when the window gains focus

def on_focus_out(event):
    pass  # Do nothing when the window loses focus

def on_symbol_change(event):
    global target_symbol
    target_symbol = symbol_var.get()
    print(f"Selected symbol: {target_symbol}")
    
    
def main():
    try:
        global root, ax1, ax2, canvas, symbol_var, timeframe_entry, leverage_entry, balance_label, positions_label
        root = tk.Tk()
        root.title("Trading Bot")
        root.geometry("1200x800")
        root.state('zoomed')

        # Create frames for layout
        right_frame = tk.Frame(root)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        center_frame = tk.Frame(root)
        center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        bottom_frame = tk.Frame(root)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)

        # Right frame widgets
        balance_label = tk.Label(right_frame, text="Balance: Loading...", font=("Arial", 14))
        balance_label.pack(pady=10)

        positions_label = tk.Label(right_frame, text="Positions: Loading...", font=("Arial", 14))
        positions_label.pack(pady=10)

        symbols = get_symbols()
        symbol_var = tk.StringVar(value=symbols[0])
        symbol_dropdown = ttk.Combobox(right_frame, textvariable=symbol_var, values=symbols, font=("Arial", 12))
        symbol_dropdown.pack(pady=5)
        symbol_dropdown.bind("<<ComboboxSelected>>", on_symbol_change)

        timeframe_label = tk.Label(right_frame, text="Enter Timeframe (minutes):", font=("Arial", 12))
        timeframe_label.pack(pady=5)
        timeframe_entry = tk.Entry(right_frame, font=("Arial", 12))
        timeframe_entry.pack(pady=5)

        leverage_label = tk.Label(right_frame, text="Enter Leverage:", font=("Arial", 12))
        leverage_label.pack(pady=5)
        leverage_entry = tk.Entry(right_frame, font=("Arial", 12))
        leverage_entry.pack(pady=5)

        long_button = tk.Button(right_frame, text="Long", command=open_long_trade, font=("Arial", 12))
        long_button.pack(pady=5)
        short_button = tk.Button(right_frame, text="Short", command=open_short_trade, font=("Arial", 12))
        short_button.pack(pady=5)

        # Center frame for chart
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), gridspec_kw={'height_ratios': [3, 1]})
        canvas = FigureCanvasTkAgg(fig, master=center_frame)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Bottom frame for terminal
        terminal = tk.Text(center_frame, height=10, wrap=tk.WORD, font=("Courier", 10))
        terminal.pack(fill=tk.BOTH, expand=True, pady=10)
        sys.stdout = TextRedirector(terminal)

        # Initial call to start the chart updates
        update_chart()

        root.bind("<FocusIn>", on_focus_in)
        root.bind("<FocusOut>", on_focus_out)

        root.mainloop()
    except Exception as e:
        messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    main()