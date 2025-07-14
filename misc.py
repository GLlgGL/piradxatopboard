#!/usr/bin/env python3
import re
import os
import time
import subprocess
import multiprocessing as mp
import traceback

import gpiod
from configparser import ConfigParser
from collections import defaultdict, OrderedDict

# Used by OLED display
cmds = {
    'blk': "lsblk | awk '{print $1}'",
    'up': "echo `uptime -p | sed -e 's/hours*/hr/' -e 's/minutes*/min/'`",
    'temp': "cat /sys/class/thermal/thermal_zone0/temp",
    'ip': "hostname -I | awk '{printf \"IP %s\", $1}'",
    'cpu': "uptime | awk '{printf \"CPU Load: %.2f\", $(NF-2)}'",
    'men': "free -m | awk 'NR==2{printf \"Mem: %s/%sMB\", $3,$2}'",
    'disk': "df -h | awk '$NF==\"/\"{printf \"Disk: %d/%dGB %s\", $3,$2,$5}'",
    'raid': "df -h /dev/md0 | awk 'NR==2 {printf \"RAID: %s/%s (%s)\", $3, $2, $5}'"
}

def get_info(key):
    if key == 'up':
        output = check_output(cmds[key])
        output = output.lstrip('up ').replace(',', '')  # Remove leading "up " and commas
        output = output.replace(' hours', ' hr').replace(' hour', ' hr')
        output = output.replace(' minutes', ' min').replace(' minute', ' min')
        output = output.replace(' seconds', ' s').replace(' second', ' s')
        return output
    return check_output(cmds[key])

def check_output(cmd):
    return subprocess.check_output(cmd, shell=True, text=True).strip()

def check_call(cmd):
    return subprocess.check_call(cmd, shell=True)


def get_cpu_temp():
    t = float(get_info('temp')) / 1000
    if conf['oled']['f-temp']:
        return "CPU Temp: {:.0f}°F".format(t * 1.8 + 32)
    else:
        return "CPU Temp: {:.1f}°C".format(t)

def read_temp():
    return float(check_output("cat /sys/class/thermal/thermal_zone0/temp")) / 1000

def get_blk():
    conf['disk'] = [x for x in check_output("lsblk | awk '{print $1}'").splitlines() if x.startswith('sd')]

def read_conf():
    conf = defaultdict(dict)
    try:
        cfg = ConfigParser()
        cfg.read('/etc/rockpi-penta.conf')

        # CPU fan thresholds
        conf['fan']['lv0'] = cfg.getfloat('fan', 'lv0')
        conf['fan']['lv1'] = cfg.getfloat('fan', 'lv1')
        conf['fan']['lv2'] = cfg.getfloat('fan', 'lv2')
        conf['fan']['lv3'] = cfg.getfloat('fan', 'lv3')

        # SSD fan thresholds
        conf['fan_ssd']['lv0'] = cfg.getfloat('fan_ssd', 'lv0')
        conf['fan_ssd']['lv1'] = cfg.getfloat('fan_ssd', 'lv1')
        conf['fan_ssd']['lv2'] = cfg.getfloat('fan_ssd', 'lv2')
        conf['fan_ssd']['lv3'] = cfg.getfloat('fan_ssd', 'lv3')

        # Key config
        conf['key']['click'] = cfg.get('key', 'click')
        conf['key']['twice'] = cfg.get('key', 'twice')
        conf['key']['press'] = cfg.get('key', 'press')

        # Time
        conf['time']['twice'] = cfg.getfloat('time', 'twice')
        conf['time']['press'] = cfg.getfloat('time', 'press')

        # OLED and slider
        conf['slider']['auto'] = cfg.getboolean('slider', 'auto')
        conf['slider']['time'] = cfg.getfloat('slider', 'time')
        conf['oled']['rotate'] = cfg.getboolean('oled', 'rotate')
        conf['oled']['f-temp'] = cfg.getboolean('oled', 'f-temp')

    except Exception:
        traceback.print_exc()
        # Defaults
        conf['fan'] = {'lv0': 40, 'lv1': 45, 'lv2': 50, 'lv3': 55}
        conf['fan_ssd'] = {'lv0': 45, 'lv1': 50, 'lv2': 55, 'lv3': 60}
        conf['key'] = {'click': 'slider', 'twice': 'switch', 'press': 'none'}
        conf['time'] = {'twice': 0.7, 'press': 1.8}
        conf['slider'] = {'auto': True, 'time': 10}
        conf['oled'] = {'rotate': False, 'f-temp': False}

    return conf

def fan_temp2dc(t):
    levels = conf['fan']
    if t >= levels['lv3']:
        return 1.00
    elif t >= levels['lv2']:
        return 0.75
    elif t >= levels['lv1']:
        return 0.50
    elif t >= levels['lv0']:
        return 0.25
    return 0.0

def ssd_temp2dc(t):
    levels = conf['fan_ssd']
    if t >= levels['lv3']:
        return 1.00
    elif t >= levels['lv2']:
        return 0.75
    elif t >= levels['lv1']:
        return 0.50
    elif t >= levels['lv0']:
        return 0.25
    return 0.0

def get_ssd_temps(devices=None):
    temps = []
    if not devices:
        devices = conf.get('disk', []) or ['sda', 'sdb', 'sdc', 'sdd']

    for dev in devices:
        temp = None
        try:
            output = check_output(f"smartctl -A /dev/{dev}")
            for line in output.splitlines():
                if any(key in line for key in ['Temperature_Celsius', 'Composite Temperature', 'Airflow_Temperature_Cel']):
                    parts = line.split()
                    # RAW_VALUE is usually the last field
                    for part in reversed(parts):
                        if part.isdigit():
                            temp = int(part)
                            break
                    if temp is not None:
                        break
        except Exception as e:
            print(f"[WARN] Failed to read /dev/{dev}: {e}")
        temps.append(temp if temp is not None else 'N/A')
    return temps

def fan_switch():
    conf['run'].value = not conf['run'].value

def get_func(key):
    return conf['key'].get(key, 'none')

def read_key(pattern, size):
    CHIP_NAME = os.environ['BUTTON_CHIP']
    LINE_NUMBER = os.environ['BUTTON_LINE']

    chip = gpiod.Chip(str(CHIP_NAME))
    line = chip.get_line(int(LINE_NUMBER))
    line.request(consumer='hat_button', type=gpiod.LINE_REQ_DIR_OUT)
    line.set_value(1)

    s = ''
    while True:
        s = s[-size:] + str(line.get_value())
        for t, p in pattern.items():
            if p.match(s):
                return t
        time.sleep(0.1)

def watch_key(q=None):
    size = int(conf['time']['press'] * 10)
    wait = int(conf['time']['twice'] * 10)
    pattern = {
        'click': re.compile(r'1+0+1{%d,}' % wait),
        'twice': re.compile(r'1+0+1+0+1{3,}'),
        'press': re.compile(r'1+0{%d,}' % size),
    }

    while True:
        q.put(read_key(pattern, size))

# Needed for OLED
def get_disk_info(cache={}):
    if not cache.get('time') or time.time() - cache['time'] > 30:
        info = {}
        cmd = "df -h | awk '$NF==\"/\"{printf \"%s\", $5}'"
        info['root'] = check_output(cmd)
        for x in conf['disk']:
            cmd = "df -Bg | awk '$1==\"/dev/{}\" {{printf \"%s\", $5}}'".format(x)
            info[x] = check_output(cmd)
        cache['info'] = list(zip(*info.items()))
        cache['time'] = time.time()

    return cache['info']

def slider_next(pages):
    conf['idx'].value += 1
    return pages[conf['idx'].value % len(pages)]

def slider_sleep():
    time.sleep(conf['slider']['time'])

# Global config dict
conf = {'disk': [], 'idx': mp.Value('d', -1), 'run': mp.Value('d', 1)}
conf.update(read_conf())
