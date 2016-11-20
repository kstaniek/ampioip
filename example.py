"""
To test Ampio Client
"""

import asyncio
import logging
import multiprocessing

from ampioip import AmpioClient


HOST = '192.168.1.140'
PORT = 1235


logging.basicConfig(format='%(asctime)-15s %(levelname)8s: %(message)s', level=logging.DEBUG)


def binary(mac, index, type, data):
    print("Event received: MAC={:04x} T={} I={} D={}".format(mac, type, index, data))

def temp(mac, index, type, data):
    print("Event received: MAC={:04x} Temperature T={} I={} D={}".format(mac, type, index, data))


def panel_led(mac, index, type, data):
    print("Event received: MAC={:04x} Panel Led T={} I={} D={}".format(mac, type, index, data))


def mled(mac, index, type, data):
    print("Event received: MAC={:04x} MLED T={} I={} D={}".format(mac, type, index, data))

@asyncio.coroutine
def feed_messages(protocol):
    """ An example function that sends the same message repeatedly. """

    value = 0

    while True:
        yield from protocol.byte_output(0x1305, 0, value)
        yield from asyncio.sleep(1)
        value = value + 1 if value < 255 else 0

# MAC: 0x0000111f MDOT-9
# MAC: 0x00000001 MSERV-3s
# MAC: 0x00001305 MLED-1S

def client():

    loop = asyncio.get_event_loop()
    amp = AmpioClient.connect(loop, HOST, PORT)

    # LCD Panel Touch
    amp.register_listener(0x111f, 0, 'input', binary)
    amp.register_listener(0x111f, 1, 'input', binary)
    amp.register_listener(0x111f, 4, 'input', binary)

    # LCD Panel LEd
    amp.register_listener(0x111f, 0, 'output', panel_led)
    amp.register_listener(0x111f, 8, 'output', panel_led)

    # Server temp
    amp.register_listener(0x0001, 1, 'tempF', temp)

    # Server output
    amp.register_listener(0x0001, 0, 'output', binary)
    amp.register_listener(0x0001, 1, 'output', binary)


    # MLED binary
    amp.register_listener(0x1305, 0, 'output', binary)
    amp.register_listener(0x1305, 0, 'output', binary)

    # MLED
    amp.register_listener(0x1305, 1, 'byte', mled)
    amp.register_listener(0x1305, 2, 'byte', mled)

    asyncio.async(feed_messages(amp))

    loop.run_forever()
    loop.close()


def main():
    client_process = multiprocessing.Process(target=client, name='client')
    client_process.start()
    input("Press Enter to continue...\n")

    try:
        client_process.join(1)
    finally:
        client_process.terminate()
        client_process.join()


if __name__ == '__main__':
    main()

