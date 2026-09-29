#!/usr/bin/python3
"""Read only the two speaker-ID GPIOs listed in this XPS's ACPI SSDT32."""
import ctypes
import fcntl
import os
from pathlib import Path

assert Path('/sys/class/dmi/id/product_name').read_text().strip() == 'XPS 13 DX13260'
assert Path('/sys/class/dmi/id/product_sku').read_text().strip() == '0E53'
chips = [p for p in Path('/sys/bus/gpio/devices').glob('gpiochip*')
         if (p / 'firmware_node/path').exists()
         and (p / 'firmware_node/path').read_text().strip() == '\\_SB_.GPI4']
assert len(chips) == 1, chips

class Request(ctypes.Structure):
    _fields_ = [('offsets', ctypes.c_uint32 * 64), ('flags', ctypes.c_uint32),
                ('defaults', ctypes.c_uint8 * 64), ('label', ctypes.c_char * 32),
                ('lines', ctypes.c_uint32), ('fd', ctypes.c_int32)]

request = Request()
request.offsets[0], request.offsets[1] = 2, 3
request.flags = 1  # GPIOHANDLE_REQUEST_INPUT; no output or bias changes.
request.label = b'xps-speaker-id-check'
request.lines = 2
assert ctypes.sizeof(request) == 364
chipfd = os.open('/dev/' + chips[0].name, os.O_RDONLY)
try:
    fcntl.ioctl(chipfd, 0xC16CB403, request)
    try:
        values = bytearray(64)
        fcntl.ioctl(request.fd, 0xC040B408, values)
        print(f'{chips[0].name}: GPI4[2]={values[0]}, GPI4[3]={values[1]}', flush=True)
        print(f'Speaker ID = {values[0] | (values[1] << 1)}', flush=True)
    finally:
        os.close(request.fd)
finally:
    os.close(chipfd)
