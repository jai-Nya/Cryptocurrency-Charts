import tkinter as tk
from tkinter import messagebox, ttk
from time import sleep
import pandas as pd
from pybit.unified_trading import HTTP
from keys import api, secret
import sys
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import requests
import mplfinance as mpf
import threading

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
        self.text_widget.yview(tk.END)  # Auto-scroll to the bottom

    def flush(self):
        pass  # No need to implement for our purposes

def get_balance():
    try:
        resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        balance = float(resp['result']['list'][0]['coin'][0]['walletBalance'])
        return balance
    except Exception as err:
        print(err)
        return 0.0

def get_symbols():
    try:
        instruments = session.get_instruments_info(category='linear')['result']['list']
        return [item['symbol'] for item in instruments]
    except Exception as err:
        print(f" retrieving symbols: {err}")
        return []

def get_precisions(symbol):
    try:
        resp = session.get_instruments_info(category='linear', symbol=symbol)['result']['list'][0]
        price_filter = resp['priceFilter']['tickSize']
        price_precision = len(price_filter.split('.')[1]) if '.' in price_filter else 0
        qty_filter = resp['lotSizeFilter']['qtyStep']
        qty_precision = len(qty_filter.split('.')[1]) if '.' in qty_filter else 0
        return price_precision, qty_precision
    except Exception as err:
        print(err)
        return 0, 0

def get_ohlc(symbol, interval, limit=50):
    url = "https://api.bybit.com/v5/market/kline"
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    if data["retCode"] != 0:
        raise ValueError(f"API: {data['retMsg']}")
    records = data["result"]["list"]
    df = pd.DataFrame(records, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    df['timestamp'] = pd.to_numeric(df['timestamp'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df.set_index('timestamp', inplace=True)
    numeric_cols = ["open", "high", "low", "close", "volume"]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
    df.drop(columns=["turnover"], inplace=True)
    df.sort_index(inplace=True)
    return df

def place_order_market(symbol, side):
    try:
        price_precision, qty_precision = get_precisions(symbol)
        mark_price = float(session.get_tickers(category='linear', symbol=symbol)['result']['list'][0]['markPrice'])
        print(f'Placing {side.capitalize()} order for {symbol}. Mark price: {mark_price}')
        order_qty = round(qty / mark_price, qty_precision)
        sleep(2)
        if side == 'buy':
            side_order = 'Buy'
        elif side == 'sell':
            side_order = 'Sell'
        else:
            raise ValueError("Invalid side: must be 'buy' or 'sell'")

        resp = session.place_order(
            category='linear',
            symbol=symbol,
            side=side_order,
            orderType='Market',
            qty=order_qty,
            tpTriggerBy='MarkPrice',
            slTriggerBy='MarkPrice',
            leverage=leverage
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

def change_timeframe(new_timeframe):
    global timeframe
    timeframe = new_timeframe
    print(f"Timeframe changed to: {timeframe}")
    update_chart()

def fetch_ohlc_data(symbol, interval):
    try:
        return get_ohlc(symbol, interval)
    except Exception as e:
        print(f"Error fetching OHLC data: {e}")
        return pd.DataFrame()

def update_chart():
    def fetch_and_update():
        symbol = symbol_var.get()
        ohlc_data = fetch_ohlc_data(symbol, timeframe)

        if ohlc_data.empty:
            print("No data fetched, skipping chart update.")
            return

        # Update the chart safely on the main thread
        root.after(0, lambda: draw_chart(ohlc_data))

    threading.Thread(target=fetch_and_update).start()

    # Schedule the next update
    root.after(5000, update_chart)  # Update every 5 seconds
    
def draw_chart(ohlc_data):
    """Updates the chart visuals safely on the main thread."""
    ax1.clear()
    ax2.clear()

    # Plot the data
    mpf.plot(
        ohlc_data.tail(50),  # Limit to last 50 candles
        type='candle',
        ax=ax1,
        style='charles',
        volume=ax2
    )

    # Update titles and thresholds
    ax1.set_title(f'{symbol_var.get()} Price')
    ax2.axhline(
        y=ohlc_data['volume'].mean() * 1.1,
        color='r', linestyle='--', linewidth=1, label='Volume Threshold'
    )
    ax2.legend()

    canvas.draw()

def on_focus_in(event):
    update_chart()  # Update chart when window gains focus

def get_max_leverage(symbol):
    """Get the maximum leverage for the given symbol."""
    try:
        instrument_info = session.get_instruments_info(category='linear', symbol=symbol)['result']['list'][0]
        max_leverage = float(instrument_info['leverageFilter']['maxLeverage'])  # Convert to float
        return int(max_leverage)  # Cast to int
    except Exception as err:
        print(f"Error fetching max leverage for {symbol}: {err}")
        return 50  # Default leverage if API fails

def update_leverage(new_leverage):
    """Update the global leverage variable."""
    global leverage
    leverage = int(new_leverage)
    print(f"Leverage updated to: {leverage}x")

def update_leverage_slider():
    """Update the leverage slider range based on the selected symbol."""
    try:
        selected_symbol = symbol_var.get()
        max_leverage = get_max_leverage(selected_symbol)
        leverage_slider.config(from_=1, to=max_leverage)
        leverage_slider.set(min(leverage_slider.get(), max_leverage))  # Adjust current value if needed
        print(f"Leverage slider updated for {selected_symbol}: 1x to {max_leverage}x")
    except Exception as err:
        print(f"Error updating leverage slider: {err}")

def on_symbol_change(event):
    """Handle symbol change event."""
    print(f"Selected symbol: {symbol_var.get()}")
    update_leverage_slider()

def main():
    try:
        global root, ax1, ax2, canvas, symbol_var, leverage_slider
        root = tk.Tk()
        root.title("Trading Bot")
        root.geometry("1200x800")
        root.state('zoomed')

        # Right frame for controls
        right_frame = tk.Frame(root)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)
        
        # Leverage slider frame
        leverage_frame = tk.Frame(right_frame)
        leverage_frame.pack(pady=10)

        leverage_label = tk.Label(leverage_frame, text="Leverage:", font=("Arial", 12))
        leverage_label.pack(pady=5)

        leverage_slider = tk.Scale(
            leverage_frame,
            from_=1, to=50,  # Default range, will update dynamically
            orient=tk.HORIZONTAL,
            length=200,
            command=update_leverage
        )
        leverage_slider.set(leverage)  # Set the default value
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

        # Center frame for chart
        center_frame = tk.Frame(root)
        center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(10, 8),
            gridspec_kw={'height_ratios': [3, 1]}
        )
        canvas = FigureCanvasTkAgg(fig, master=center_frame)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Terminal output
        terminal = tk.Text(center_frame, height=10, wrap=tk.WORD, font=("Courier", 10))
        terminal.pack(fill=tk.BOTH, expand=True, pady=10)
        sys.stdout = TextRedirector(terminal)

        # Initial setup
        update_leverage_slider()  # Set leverage slider for the default symbol
        update_chart()  # Initial chart update

        root.bind("<FocusIn>", on_focus_in)
        root.mainloop()
    except Exception as e:
        messagebox.show("", str(e))

if __name__ == "__main__":
    main()
