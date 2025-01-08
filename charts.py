import requests
import pandas as pd
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk
from tkinter import ttk

def fetch_ohlc_data(symbol, interval, limit=200):
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

def plot_candlestick(ax, ohlc_data):
    width, width2 = 2, 1
    for idx, row in ohlc_data.iterrows():
        color = 'green' if row['close'] >= row['open'] else 'red'
        ax.plot([idx, idx], [row['low'], row['high']], color=color, linewidth=width2)
        ax.plot([idx, idx], [row['open'], row['close']], color=color, linewidth=width)

def update_chart(*args):
    global update_job_id
    if args and update_job_id is not None:
        root.after_cancel(update_job_id)
        update_job_id = None
    try:
        interval, symbol = timeframe_var.get(), symbol_var.get()
        ohlc_data = fetch_ohlc_data(symbol, interval, limit)
        xlim, ylim = ax_main.get_xlim(), ax_main.get_ylim()
        ax_main.clear()
        ax_volume.clear()
        plot_candlestick(ax_main, ohlc_data)
        ax_volume.bar(ohlc_data.index, ohlc_data['volume'], color='blue', width=0.0005)
        ax_main.set_ylabel('Price')
        ax_volume.set_ylabel('Volume')
        if xlim != (0.0, 1.0) and ylim != (0.0, 1.0):
            ax_main.set_xlim(xlim)
            ax_main.set_ylim(ylim)
        canvas.draw()
    except Exception as e:
        print(f"Error updating chart: {e}")
    finally:
        update_job_id = root.after(1000, update_chart)

def on_closing():
    global update_job_id
    print("Closing application...")
    if update_job_id is not None:
        root.after_cancel(update_job_id)
        update_job_id = None
    root.quit()
    print("Application closed.")

press, x0, y0 = False, None, None

def zoom(event):
    if event.inaxes == ax_main:
        scale_factor = 1.1
        xdata, ydata = event.xdata, event.ydata
        current_xlim, current_ylim = ax_main.get_xlim(), ax_main.get_ylim()
        if event.button == 'up':
            scale_factor = 1 / scale_factor
        elif event.button == 'down':
            scale_factor = scale_factor
        new_width = (current_xlim[1] - current_xlim[0]) * scale_factor
        new_height = (current_ylim[1] - current_ylim[0]) * scale_factor
        relx = (current_xlim[1] - xdata) / (current_xlim[1] - current_xlim[0])
        rely = (current_ylim[1] - ydata) / (current_ylim[1] - current_ylim[0])
        ax_main.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * relx])
        ax_main.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * rely])
        canvas.draw_idle()

def on_press(event):
    global press, x0, y0
    if event.inaxes == ax_main and event.button == 1:
        press = True
        x0 = event.xdata
        y0 = event.ydata

def on_release(event):
    global press, x0, y0
    press = False
    x0 = None
    y0 = None

def on_motion(event):
    global press, x0, y0
    if press and event.inaxes == ax_main:
        dx = x0 - event.xdata
        dy = y0 - event.ydata
        current_xlim, current_ylim = ax_main.get_xlim(), ax_main.get_ylim()
        ax_main.set_xlim(current_xlim + dx)
        ax_main.set_ylim(current_ylim + dy)
        x0 = event.xdata
        y0 = event.ydata
        canvas.draw_idle()

if __name__ == "__main__":
    limit = 200
    root = tk.Tk()
    root.title("Real-Time Crypto Chart")
    update_job_id = None
    root.protocol("WM_DELETE_WINDOW", on_closing)
    control_frame = tk.Frame(root)
    control_frame.pack(side=tk.TOP, fill=tk.X)
    symbol_options = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    symbol_var = tk.StringVar(value="BTCUSDT")
    symbol_label = tk.Label(control_frame, text="Select Symbol:")
    symbol_label.pack(side=tk.LEFT, padx=5)
    symbol_menu = ttk.OptionMenu(control_frame, symbol_var, symbol_var.get(), *symbol_options, command=update_chart)
    symbol_menu.pack(side=tk.LEFT)
    timeframe_options = ["1", "3", "5", "15", "30", "60", "240", "D"]
    timeframe_var = tk.StringVar(value="15")
    timeframe_label = tk.Label(control_frame, text="Select Timeframe:")
    timeframe_label.pack(side=tk.LEFT, padx=5)
    timeframe_menu = ttk.OptionMenu(control_frame, timeframe_var, timeframe_var.get(), *timeframe_options, command=update_chart)
    timeframe_menu.pack(side=tk.LEFT)
    fig, (ax_main, ax_volume) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas.draw()
    canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)
    canvas.mpl_connect('scroll_event', zoom)
    canvas.mpl_connect('button_press_event', on_press)
    canvas.mpl_connect('button_release_event', on_release)
    canvas.mpl_connect('motion_notify_event', on_motion)
    update_chart()
    root.mainloop()
    print("Main loop exited. Exiting the program.")