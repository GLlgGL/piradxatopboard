#!/usr/bin/env python3
import os.path
import time
import traceback
import threading
import multiprocessing as mp
import gpiod

import misc

pin = None

class Pwm:
    def __init__(self, chip):
        self.period_value = None
        try:
            int(chip)
            chip = f'pwmchip{chip}'
        except ValueError:
            pass
        self.filepath = f"/sys/class/pwm/{chip}/pwm0/"
        try:
            with open(f"/sys/class/pwm/{chip}/export", 'w') as f:
                f.write('0')
        except OSError:
            print("Warning: init pwm error")
            traceback.print_exc()

    def period(self, ns: int):
        self.period_value = ns
        with open(os.path.join(self.filepath, 'period'), 'w') as f:
            f.write(str(ns))

    def period_us(self, us: int):
        self.period(us * 1000)

    def enable(self, t: bool):
        with open(os.path.join(self.filepath, 'enable'), 'w') as f:
            f.write(f"{int(t)}")

    def write(self, duty: float):
        assert self.period_value, "The Period is not set."
        with open(os.path.join(self.filepath, 'duty_cycle'), 'w') as f:
            f.write(f"{int(self.period_value * duty)}")


class Gpio:
    def __init__(self, period_s):
        self.is_zero_duty = False
        try:
            fan_chip_env = os.environ.get('FAN_CHIP', '0')
            fan_line_env = os.environ.get('FAN_LINE', '27')

            self.chip_obj = gpiod.Chip(fan_chip_env)
            self.line = self.chip_obj.get_line(int(fan_line_env))
            self.line.request(consumer='fan', type=gpiod.LINE_REQ_DIR_OUT)

            self.value = [period_s / 2.0, period_s / 2.0]
            self.period_s = period_s
            self.thread = threading.Thread(target=self.tr, daemon=True)
            self.thread.start()
        except Exception:
            raise

    def tr(self):
        while True:
            if self.is_zero_duty:
                self.line.set_value(0)
                time.sleep(self.period_s)
            else:
                high_sleep = max(0.0, self.value[0])
                low_sleep = max(0.0, self.value[1])
                if high_sleep + low_sleep < self.period_s * 0.9:
                    low_sleep = self.period_s - high_sleep
                self.line.set_value(1)
                time.sleep(high_sleep)
                self.line.set_value(0)
                time.sleep(low_sleep)

    def write(self, duty: float):
        if duty <= 0.001:
            self.is_zero_duty = True
            self.value = [0.0, self.period_s]
        else:
            self.is_zero_duty = False
            duty = min(duty, 1.0)
            self.value = [duty * self.period_s, (1 - duty) * self.period_s]


def get_dc(cache={}):
    if misc.conf['run'].value == 0:
        return 0.999

    now = time.time()
    if now - cache.get('time', 0) > 30:
        cache['time'] = now

        cpu_temp = misc.read_temp()
        ssd_temps = misc.get_ssd_temps()
        max_ssd_temp = max(ssd_temps) if ssd_temps else 0

        dc_cpu = misc.fan_temp2dc(cpu_temp)
        dc_ssd = misc.ssd_temp2dc(max_ssd_temp)

        dc = max(dc_cpu, dc_ssd)
        cache['dc'] = dc

        print(f"[Fan] CPU: {cpu_temp:.1f}°C → DC {dc_cpu:.2f} | SSD: {max_ssd_temp:.1f}°C → DC {dc_ssd:.2f} | Final DC: {dc:.2f}")

    return cache['dc']


def change_dc(dc, cache={}):
    if dc != cache.get('dc'):
        cache['dc'] = dc
        pin.write(dc)


def running():
    global pin
    if os.environ.get('HARDWARE_PWM') == '1':
        chip = os.environ['PWMCHIP']
        pin = Pwm(chip)
        pin.period_us(40)
        pin.enable(True)
    else:
        pin = Gpio(0.025)
    while True:
        change_dc(get_dc())
        time.sleep(1)


if __name__ == '__main__':
    running()
