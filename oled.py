#!/usr/bin/python3
import os
import time

import adafruit_ssd1306
import board
import digitalio
import busio
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
import multiprocessing as mp

import misc

font = {
    '10': ImageFont.truetype('fonts/DejaVuSansMono-Bold.ttf', 10),
    '11': ImageFont.truetype('fonts/DejaVuSansMono-Bold.ttf', 11),
    '12': ImageFont.truetype('fonts/DejaVuSansMono-Bold.ttf', 12),
    '14': ImageFont.truetype('fonts/DejaVuSansMono-Bold.ttf', 14),
}


def disp_init():
    RESET = getattr(board.pin, os.environ['OLED_RESET'])
    i2c = busio.I2C(getattr(board.pin, os.environ['SCL']), getattr(board.pin, os.environ['SDA']))
    disp = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c, reset=digitalio.DigitalInOut(RESET))
    disp.fill(0)
    disp.show()
    return disp


disp = disp_init()

image = Image.new('1', (disp.width, disp.height))
draw = ImageDraw.Draw(image)


def disp_show():
    im = image.rotate(180) if misc.conf['oled']['rotate'] else image
    disp.image(im)
    disp.write_framebuf()
    draw.rectangle((0, 0, disp.width, disp.height), outline=0, fill=0)


def welcome():
    draw.text((0, 0), 'ROCKPi SATA HAT', font=font['14'], fill=255)
    draw.text((32, 16), 'Loading...', font=font['12'], fill=255)
    disp_show()


def goodbye():
    draw.text((32, 8), 'Good Bye ~', font=font['14'], fill=255)
    disp_show()
    time.sleep(2)
    disp_show()  # clear


def put_disk_info():
    devices = misc.conf.get('disk', []) or ['sda', 'sdb', 'sdc', 'sdd']
    temps = misc.get_ssd_temps(devices)

    if not temps or all(t == 'N/A' for t in temps):
        return [{'xy': (0, 2), 'text': 'No SSD temp data', 'fill': 255, 'font': font['12']}]

    page = []
    line_height = 12  # Adjust for font size and spacing
    for i in range(0, len(devices), 2):
        left_dev = devices[i].upper()
        left_temp = temps[i] if i < len(temps) else 'N/A'
        left_text = f"{left_dev}: {left_temp}°C" if left_temp != 'N/A' else f"{left_dev}: N/A"

        right_text = ''
        if i + 1 < len(devices):
            right_dev = devices[i + 1].upper()
            right_temp = temps[i + 1] if (i + 1) < len(temps) else 'N/A'
            right_text = f"{right_dev}: {right_temp}°C" if right_temp != 'N/A' else f"{right_dev}: N/A"

        # Position left text at x=0, right text at x=70 (adjust as needed)
        page.append({'xy': (0, (i//2) * line_height), 'text': left_text, 'fill': 255, 'font': font['12']})
        if right_text:
            page.append({'xy': (70, (i//2) * line_height), 'text': right_text, 'fill': 255, 'font': font['12']})

    return page

def gen_pages():
    pages = {
        0: [
            {'xy': (0, -2), 'text': misc.get_info('up'), 'fill': 255, 'font': font['11']},
            {'xy': (0, 10), 'text': misc.get_cpu_temp(), 'fill': 255, 'font': font['11']},
            {'xy': (0, 21), 'text': misc.get_info('ip'), 'fill': 255, 'font': font['11']},
        ],
        1: [
            {'xy': (0, 2), 'text': misc.get_info('cpu'), 'fill': 255, 'font': font['12']},
            {'xy': (0, 18), 'text': misc.get_info('men'), 'fill': 255, 'font': font['12']},
        ],
        2: put_disk_info(),
        3: [
            {'xy': (0, 12), 'text': misc.get_info('raid'), 'fill': 255, 'font': font['10']},
        ]
    }

    return pages


def slider(lock):
    with lock:
        for item in misc.slider_next(gen_pages()):
            draw.text(**item)
        disp_show()


def auto_slider(lock):
    while misc.conf['slider']['auto']:
        slider(lock)
        misc.slider_sleep()
    else:
        slider(lock)


if __name__ == '__main__':
    # for test
    lock = mp.Lock()
    auto_slider(lock)
