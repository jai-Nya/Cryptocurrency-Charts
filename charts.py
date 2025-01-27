import tkinter as tk
from tkinter import messagebox, ttk
from time import sleep
import pandas as pd
from pybit.unified_trading import HTTP
from keys import api, secret
import sys
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import mplfinance as mpf
import threading
import requests
import traceback

session = HTTP(api_key=api, api_secret=secret)

global timeframe

timeframe = 1
leverage = 10
qty = 50

class TextRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, message):
        self.text_widget.insert(tk.END, message)
        self.text_widget.yview(tk.END)

    def flush(self):
        pass

def get_precisions(symbol):
    """Fetches price and quantity precisions for a symbol."""
    try:
        resp = session.get_instruments_info(category='linear', symbol=symbol)['result']['list'][0]
        price_filter = resp['priceFilter']['tickSize']
        if '.' in price_filter:
            price_precision = len(price_filter.split('.')[1].rstrip('0'))
        else:
            price_precision = 0
        return price_precision, 0
    except Exception as err:
        print(f"Error fetching precisions: {err}")
        return 0, 0

def get_balance():
    """Fetches the account balance."""
    try:
        resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        balance = float(resp['result']['list'][0]['coin'][0]['walletBalance'])
        return balance
    except Exception as e:
        print(f"Error fetching balance: {e}")
        return 0

def get_symbols():
    """Fetches available trading symbols."""
    try:
        resp = session.get_instruments_info(category='linear')['result']['list']
        symbols = [item['symbol'] for item in resp]
        return symbols
    except Exception as e:
        print(f"Error fetching symbols: {e}")
        return []

def fetch_ohlc_data(symbol, interval, limit=50):
    """Fetches OHLC data for a symbol."""
    url = "https://api.bybit.com/v5/market/kline"
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()['result']['list']
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df['timestamp'] = pd.to_numeric(df['timestamp'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        df.set_index('timestamp', inplace=True)
        numeric_cols = ["open", "high", "low", "close", "volume"]
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric)
        df.drop(columns=["turnover"], inplace=True)
        df.sort_index(inplace=True)
        return df
    except Exception as e:
        print(f"Error fetching OHLC data: {e}")
        return pd.DataFrame()

def place_order_market(symbol, side_order):
    """Places a market order."""
    try:
        if side_order not in ['buy', 'sell']:
            raise ValueError("side_order must be 'buy' or 'sell'")

        mark_price = float(session.get_tickers(category='linear', symbol=symbol)['result']['list'][0]['markPrice'])
        print(f'Placing {side_order.capitalize()} order for {symbol}. Mark price: {mark_price}')

        order_qty = qty

        resp = session.place_order(
            category='linear',
            symbol=symbol,
            side=side_order,
            orderType='Market',
            qty=order_qty
        )
        print(f"Order placed: {resp}")
    except Exception as e:
        print(f"Error placing order: {e}")

def open_long_trade():
    """Opens a long trade."""
    symbol = symbol_var.get()
    place_order_market(symbol, 'buy')

def open_short_trade():
    """Opens a short trade."""
    symbol = symbol_var.get()
    place_order_market(symbol, 'sell')

def change_timeframe(new_timeframe):
    """Changes the chart timeframe."""
    global timeframe
    timeframe = new_timeframe
    print(f"Timeframe changed to: {timeframe}")
    update_chart()

def update_chart():
    """Updates the chart."""
    def fetch_and_update():
        symbol = symbol_var.get()
        ohlc_data = fetch_ohlc_data(symbol, timeframe)

        if ohlc_data.empty:
            print("No data fetched, skipping chart update.")
            return

        root.after(0, lambda: draw_chart(ohlc_data))

    threading.Thread(target=fetch_and_update).start()

    root.after(5000, update_chart)

def draw_chart(ohlc_data):
    """Updates the chart visuals safely on the main thread."""
    ax1.clear()
    ax2.clear()

    mpf.plot(
        ohlc_data.tail(50),
        type='candle',
        ax=ax1,
        style='charles',
        volume=ax2
    )

    canvas.draw()

def fetch_current_price():
    """Fetches current price and updates the price label."""
    try:
        symbol = symbol_var.get()
        resp = session.get_tickers(category='linear', symbol=symbol)
        if 'result' in resp and 'list' in resp['result']:
            price = float(resp['result']['list'][0]['markPrice'])
            price_precision, _ = get_precisions(symbol)
            formatted_price = f"{price:.{price_precision}f}"
            price_label.config(text=f"Current Price: {formatted_price}")
    except Exception as e:
        print(f"Error fetching current price: {e}")

    # Schedule the next call
    root.after(1000, fetch_current_price)

def on_symbol_change(event):
    """Handles symbol change events."""
    update_leverage_slider()

def update_leverage(new_leverage):
    """Updates the global leverage variable."""
    global leverage
    leverage = int(new_leverage)
    print(f"Leverage updated to: {leverage}x")

def update_leverage_slider():
    """Updates the leverage slider range based on the selected symbol."""
    try:
        selected_symbol = symbol_var.get()
        max_leverage = get_max_leverage(selected_symbol)
        leverage_slider.config(from_=1, to=max_leverage)
        leverage_slider.set(min(leverage_slider.get(), max_leverage))  # Adjust current value if needed
        print(f"Leverage slider updated for {selected_symbol}: 1x to {max_leverage}x")
    except Exception as e:
        print(f"Error updating leverage slider: {e}")

def get_max_leverage(symbol):
    """Gets the maximum leverage for a symbol."""
    try:
        instrument_info = session.get_instruments_info(category='linear', symbol=symbol)['result']['list'][0]
        max_leverage = float(instrument_info['leverageFilter']['maxLeverage'])
        return max_leverage
    except Exception as e:
        print(f"Error fetching max leverage: {e}")
        return 1

def main():
    try:
        global root, ax1, ax2, canvas, symbol_var, leverage_slider, price_label
        root = tk.Tk()
        root.title("Trading Bot")
        root.geometry("1200x800")
        root.state('zoomed')

        # Center frame for chart
        center_frame = tk.Frame(root)
        center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Right frame for controls
        right_frame = tk.Frame(root)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        # Price frame
        price_frame = tk.Frame(root)
        price_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        # Price label in price_frame
        price_label = tk.Label(price_frame, text="", font=("Arial", 14))
        price_label.pack(pady=10)

        # Leverage slider frame
        leverage_frame = tk.Frame(right_frame)
        leverage_frame.pack(pady=10)

        leverage_label = tk.Label(leverage_frame, text="Leverage:", font=("Arial", 12))
        leverage_label.pack(pady=5)

        leverage_slider = tk.Scale(
            leverage_frame,
            from_=1, to=50,
            orient=tk.HORIZONTAL,
            length=200,
            command=update_leverage
        )
        leverage_slider.set(leverage)
        leverage_slider.pack()

        # Timeframe selection frame
        timeframe_frame = tk.Frame(right_frame)
        timeframe_frame.pack(pady=10)

        timeframe_label = tk.Label(timeframe_frame, text="Timeframe:", font=("Arial", 12))
        timeframe_label.pack(pady=5)

        # Timeframe buttons
        timeframes = [
            ("1m", "1"),
            ("3m", "3"),
            ("5m", "5"),
            ("15m", "15"),
            ("30m", "30"),
            ("1h", "60"),
            ("4h", "240"),
            ("1d", "D")
        ]

        for tf_label, tf_value in timeframes:
            tf_button = tk.Button(
                timeframe_frame,
                text=tf_label,
                command=lambda x=tf_value: change_timeframe(x),
                font=("Arial", 10)
            )
            tf_button.pack(side=tk.LEFT, padx=2)

        balance_label = tk.Label(right_frame, text=f"Balance: {get_balance()} USDT", font=("Arial", 14))
        balance_label.pack(pady=10)

        symbols = get_symbols()
        symbol_var = tk.StringVar(value=symbols[0])
        symbol_dropdown = ttk.Combobox(
            right_frame,
            textvariable=symbol_var,
            values=symbols,
            font=("Arial", 12)
        )
        symbol_dropdown.pack(pady=5)
        symbol_dropdown.bind("<<ComboboxSelected>>", on_symbol_change)

        long_button = tk.Button(
            right_frame,
            text="Open Long Position",
            command=open_long_trade,
            font=("Arial", 12)
        )
        long_button.pack(pady=5)

        short_button = tk.Button(
            right_frame,
            text="Open Short Position",
            command=open_short_trade,
            font=("Arial", 12)
        )
        short_button.pack(pady=5)

        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(10, 8),
            gridspec_kw={'height_ratios': [3, 1]}
        )
        canvas = FigureCanvasTkAgg(fig, master=center_frame)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        terminal = tk.Text(center_frame, height=10, wrap=tk.WORD, font=("Courier", 10))
        terminal.pack(fill=tk.BOTH, expand=True, pady=10)
        sys.stdout = TextRedirector(terminal)

        # Initial setup
        update_leverage_slider()
        update_chart()
        fetch_current_price()

        def on_closing():
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_closing)
        root.mainloop()

    except Exception as e:
        print(f"Error in main application: {e}")

if __name__ == "__main__":
    main()
