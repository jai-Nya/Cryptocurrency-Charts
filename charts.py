import tkinter as tk
from tkinter import ttk
import pandas as pd
from pybit.unified_trading import HTTP
from keys import api, secret
import sys
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import mplfinance as mpf
import threading
import requests

session = HTTP(api_key=api, api_secret=secret)
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

def get_price_precision(symbol):
    try:
        resp = session.get_instruments_info(category='linear', symbol=symbol)['result']['list'][0]
        tick_size = resp['priceFilter']['tickSize']
        price_precision = len(tick_size.split('.')[1].rstrip('0')) if '.' in tick_size else 0
        return price_precision
    except Exception as err:
        print(f"Error fetching price precision: {err}")
        return 0

def get_balance():
    try:
        resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        balance = float(resp['result']['list'][0]['coin'][0]['walletBalance'])
        return balance
    except Exception as e:
        print(f"Error fetching balance: {e}")
        return 0

def get_symbols():
    try:
        resp = session.get_instruments_info(category='linear')['result']['list']
        return [item['symbol'] for item in resp]
    except Exception as e:
        print(f"Error fetching symbols: {e}")
        return []

def fetch_ohlc_data(symbol, interval, limit=50):
    url = "https://api.bybit.com/v5/market/kline"
    params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()['result']['list']
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df['timestamp'] = pd.to_datetime(pd.to_numeric(df['timestamp']), unit='ms', utc=True)
        df.set_index('timestamp', inplace=True)
        df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric)
        df.drop(columns=["turnover"], inplace=True)
        return df.sort_index()
    except Exception as e:
        print(f"Error fetching OHLC data: {e}")
        return pd.DataFrame()

def fetch_order_book():
    global ask_labels, bid_labels
    try:
        symbol = symbol_var.get()
        base_currency = symbol.replace('USDT', '')
        url = "https://api.bybit.com/v5/market/orderbook"
        params = {"category": "linear", "symbol": symbol}
        response = requests.get(url, params=params).json()['result']
        N = 10
        price_precision = get_price_precision(symbol)
        quantity_precision = 4
        asks = [(float(p), float(q)) for p, q in response['a'][:N]]
        bids = [(float(p), float(q)) for p, q in response['b'][:N]]

        cumulative_ask_qty = 0
        for i, label in enumerate(ask_labels):
            if i < len(asks):
                price, qty = asks[i]
                cumulative_ask_qty += qty
                label.config(text=f"{price:.{price_precision}f}    {qty:.{quantity_precision}f}    {cumulative_ask_qty:.{quantity_precision}f}")
            else:
                label.config(text="")

        cumulative_bid_qty = 0
        for i, label in enumerate(bid_labels):
            if i < len(bids):
                price, qty = bids[i]
                cumulative_bid_qty += qty
                label.config(text=f"{price:.{price_precision}f}    {qty:.{quantity_precision}f}    {cumulative_bid_qty:.{quantity_precision}f}")
            else:
                label.config(text="")

        if bids and asks:
            mid_price = (bids[0][0] + asks[0][0]) / 2
            price_label.config(text=f"Mid Price: {mid_price:.{price_precision}f}")
        else:
            price_label.config(text="Mid Price: N/A")

    except Exception as e:
        print(f"Error fetching order book: {e}")
    root.after(510, fetch_order_book)

def place_order_market(symbol, side_order):
    try:
        if side_order not in ['buy', 'sell']:
            raise ValueError("Invalid order side")
        mark_price = float(session.get_tickers(category='linear', symbol=symbol)['result']['list'][0]['markPrice'])
        print(f'Placing {side_order.capitalize()} order for {symbol}. Mark price: {mark_price}')
        resp = session.place_order(category='linear', symbol=symbol, side=side_order, orderType='Market', qty=qty)
        print(f"Order placed: {resp}")
    except Exception as e:
        print(f"Error placing order: {e}")

def open_long_trade():
    place_order_market(symbol_var.get(), 'buy')

def open_short_trade():
    place_order_market(symbol_var.get(), 'sell')

def change_timeframe(new_timeframe):
    global timeframe
    timeframe = new_timeframe
    print(f"Timeframe changed to: {timeframe}")
    update_chart()

def update_chart():
    def fetch_and_update():
        symbol = symbol_var.get()
        ohlc_data = fetch_ohlc_data(symbol, timeframe)
        if not ohlc_data.empty:
            root.after(0, lambda: draw_chart(ohlc_data))
        else:
            print("No data fetched, skipping chart update.")
    threading.Thread(target=fetch_and_update).start()
    root.after(5000, update_chart)

def draw_chart(ohlc_data):
    ax1.clear()
    ax2.clear()
    mpf.plot(ohlc_data.tail(50), type='candle', ax=ax1, style='charles', volume=ax2)
    canvas.draw()

def on_symbol_change(event):
    update_leverage_slider()
    base_currency = symbol_var.get().replace('USDT', '')
    asks_header.config(text=f"Price (USDT)    Qty ({base_currency})    Total ({base_currency})")
    bids_header.config(text=f"Price (USDT)    Qty ({base_currency})    Total ({base_currency})")

def update_leverage(new_leverage):
    global leverage
    leverage = int(new_leverage)

def update_leverage_slider():
    try:
        max_leverage = get_max_leverage(symbol_var.get())
        leverage_slider.config(from_=1, to=max_leverage)
        leverage_slider.set(min(leverage_slider.get(), max_leverage))
    except Exception as e:
        print(f"Error updating leverage slider: {e}")

def get_max_leverage(symbol):
    try:
        info = session.get_instruments_info(category='linear', symbol=symbol)['result']['list'][0]
        return float(info['leverageFilter']['maxLeverage'])
    except Exception as e:
        print(f"Error fetching max leverage: {e}")
        return 1

def main():
    try:
        global root, ax1, ax2, canvas, symbol_var, leverage_slider, price_label
        global ask_labels, bid_labels, asks_header, bids_header
        root = tk.Tk()
        root.title("Bybit Application")
        root.state('zoomed')

        symbols = get_symbols()
        symbol_var = tk.StringVar(value=symbols[0])
        base_currency = symbol_var.get().replace('USDT', '')

        center_frame = tk.Frame(root)
        center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        right_frame = tk.Frame(root)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        price_frame = tk.Frame(root)
        price_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        order_book_frame = tk.Frame(price_frame)
        order_book_frame.pack(pady=10)

        N = 10
        ask_labels = []
        bid_labels = []

        asks_frame = tk.Frame(order_book_frame)
        asks_frame.pack(side=tk.TOP)
        asks_header = tk.Label(asks_frame, text=f"Price (USDT)    Qty ({base_currency})    Total ({base_currency})", font=("Arial", 10, "bold"))
        asks_header.pack(side=tk.TOP)
        for _ in range(N):
            label = tk.Label(asks_frame, text="", fg='red', font=("Arial", 10))
            label.pack(side=tk.BOTTOM, anchor='w')
            ask_labels.append(label)

        price_label = tk.Label(order_book_frame, text="", font=("Arial", 14))
        price_label.pack()

        bids_frame = tk.Frame(order_book_frame)
        bids_frame.pack(side=tk.TOP)
        bids_header = tk.Label(bids_frame, text=f"Price (USDT)    Qty ({base_currency})    Total ({base_currency})", font=("Arial", 10, "bold"))
        bids_header.pack(side=tk.TOP)
        for _ in range(N):
            label = tk.Label(bids_frame, text="", fg='green', font=("Arial", 10))
            label.pack(side=tk.TOP, anchor='w')
            bid_labels.append(label)

        leverage_frame = tk.Frame(right_frame)
        leverage_frame.pack(pady=10)
        tk.Label(leverage_frame, text="Leverage:", font=("Arial", 12)).pack(pady=5)
        leverage_slider = tk.Scale(leverage_frame, from_=1, to=50, orient=tk.HORIZONTAL, length=200, command=update_leverage)
        leverage_slider.set(leverage)
        leverage_slider.pack()

        timeframe_frame = tk.Frame(right_frame)
        timeframe_frame.pack(pady=10)
        tk.Label(timeframe_frame, text="Timeframe:", font=("Arial", 12)).pack(pady=5)
        timeframes = [("1m", "1"), ("3m", "3"), ("5m", "5"), ("15m", "15"), ("30m", "30"), ("1h", "60"), ("4h", "240"), ("1d", "D")]
        for tf_label, tf_value in timeframes:
            tk.Button(timeframe_frame, text=tf_label, command=lambda x=tf_value: change_timeframe(x), font=("Arial", 10)).pack(side=tk.LEFT, padx=2)

        tk.Label(right_frame, text=f"Balance: {get_balance()} USDT", font=("Arial", 14)).pack(pady=10)

        symbol_dropdown = ttk.Combobox(right_frame, textvariable=symbol_var, values=symbols, font=("Arial", 12))
        symbol_dropdown.pack(pady=5)
        symbol_dropdown.bind("<<ComboboxSelected>>", on_symbol_change)

        tk.Button(right_frame, text="Open Long Position", command=open_long_trade, font=("Arial", 12)).pack(pady=5)
        tk.Button(right_frame, text="Open Short Position", command=open_short_trade, font=("Arial", 12)).pack(pady=5)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), gridspec_kw={'height_ratios': [3, 1]})
        canvas = FigureCanvasTkAgg(fig, master=center_frame)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        terminal = tk.Text(center_frame, height=10, wrap=tk.WORD, font=("Courier", 10))
        terminal.pack(fill=tk.BOTH, expand=True, pady=10)
        sys.stdout = TextRedirector(terminal)

        update_leverage_slider()
        update_chart()
        fetch_order_book()

        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.mainloop()
    except Exception as e:
        print(f"Error in main application: {e}")

if __name__ == "__main__":
    main()
