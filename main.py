#!/usr/bin/env python3
import os
import queue
import threading
import traceback
import time

import fan
import misc

try:
    import oled
    top_board = True  # ✅ OLED was imported successfully
except Exception as ex:
    traceback.print_exc()
    top_board = False

q = queue.Queue()
lock = threading.Lock()

action = {
    'none': lambda: 'nothing',
    'slider': lambda: oled.slider(lock),
    'switch': lambda: misc.fan_switch(),
    'reboot': lambda: misc.check_call('reboot'),
    'poweroff': lambda: misc.check_call('poweroff'),
}

def receive_key(q):
    while True:
        try:
            func = misc.get_func(q.get())
            action[func]()
        except Exception as e:
            print("Error in receive_key:", e)

if __name__ == '__main__':
    print("Top board:", top_board)
    if top_board:
        oled.welcome()
        threading.Thread(target=receive_key, args=(q,), daemon=True).start()
        threading.Thread(target=misc.watch_key, args=(q,), daemon=True).start()
        threading.Thread(target=oled.auto_slider, args=(lock,), daemon=True).start()
        threading.Thread(target=fan.running, daemon=True).start()

        try:
            while True:
                time.sleep(1)  # Keeps the main thread alive
        except KeyboardInterrupt:
            print("GoodBye ~")
            oled.goodbye()
    else:
        fan.running()
