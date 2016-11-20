"""
This is Ampio to IP gateway
"""

import struct
import asyncio
import logging

from ampioip.frame import UserFrame, PasswordFrame, InfoFrame, CANFrame, CANSetBinary, CANSetByte,\
    ServerFrame, CANSetByteToDevice
from ampioip.utils import frame_to_str


class AmpioClient(asyncio.Protocol):
    def __init__(self, loop, host, port, username='admin', password='12345'):
        self.loop = loop
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.connected = False
        self.queue = asyncio.Queue()
        self._ready = asyncio.Event()
        self.states = {}
        self.address_listeners = {}
        asyncio.ensure_future(self._send_messages())

    def connection_made(self, transport):
        """Callback when connection made."""
        logging.info("Connected successfully")
        self.transport = transport
        self.connected = True
        self._ready.set()
        asyncio.async(self.send_message(UserFrame(username=self.username).frame))
        asyncio.async(self.send_message(PasswordFrame(password=self.password).frame))
        asyncio.async(self.send_message(InfoFrame().frame))

    def data_received(self, frame):
        """Callback when data received."""
        index = 0
        part = 0
        while index < len(frame):
            header = frame[index:index + 6]
            preamble, msg_len = struct.unpack("<HL", header)
            if preamble != 0xd42d:
                logging.error("Overrun Error")
                return

            data = frame[index + 6:]
            payload = data[1:msg_len - 2]
            crc = struct.unpack("<H", data[msg_len - 2:msg_len])[0]
            calculated_crc = self._calc_crc(payload)
            if crc != calculated_crc:
                logging.error("CRC Error: {}".format(":".join("{:02x}".format(c) for c in data)))

            index += (6 + msg_len)
            part += 1
            asyncio.async(self._process_frame(data[:msg_len - 2]))

    def _calc_crc(self, data):
        """Calculate frame CRC."""
        crc = 0x2d
        for b in data:
            crc += b
        return crc

    @asyncio.coroutine
    def _process_frame(self, msg):
        """Process server frame."""
        logging.debug("[I][TYPE {}]: {}".format(msg[0], ":".join("{:02x}".format(c) for c in msg[1:])))

        if msg[0] == 0x00:  # CAN FRAME
            frame = msg[1:]
            while len(frame) >= 13:
                self._process_can_frame(frame[0:13])
                frame = frame[13:]

    def _process_can_frame(self, frame):
        """Process CAN frame."""
        can = CANFrame(frame)
        logging.debug("[I]{}".format(can))

        if can.d0 == 0xfe:
            if can.type == CANFrame.Binary:  # input/output report
                logging.debug("[I][CAN]: Frame type: {} Binary I/O: Inputs={:024b} Outputs:{:024b}".format(
                    can.type, can.inputs, can.outputs))
                self._send_update(can.mac, "input", can.inputs)
                self._send_update(can.mac, "output", can.outputs)

            elif can.d1 == 0x10:
                logging.debug("[I][CAN]: Frame type: {} Date Time".format(can.type))

            elif can.d1 == 0x11:
                logging.debug("[I][CAN]: Frame type: {} NTP".format(can.type))

            elif can.d1 == 0x2a:  # Wireless
                logging.debug("[I][CAN]: Frame type: {} Radio".format(can.type))

            elif can.type == CANFrame.Temp:
                logging.debug("[I][CAN]: Frame type: {} Temperature".format(can.type))
                # self._send_temp(can.mac, "temp", can.temp)

            elif can.type == CANFrame.TempF1:
                logging.debug("[I][CAN]: Frame type: {} Temperature Float Value Sensors 1-3".format(can.type))
                self._send_temp(can.mac, "tempF", can.tempF)

            elif can.type == CANFrame.TempF2:
                logging.debug("[I][CAN]: Frame type: {} Temperature Float Value Sensors 4-6".format(can.type))
                self._send_temp(can.mac, "tempF", can.tempF, offset=4)

            elif can.type == CANFrame.Byte1_6:
                logging.debug("[I][CAN]: Frame type: {} Byte Value Sensors 1-6".format(can.type))
                self._send_byte(can.mac, "byte", can.bytes)

            elif can.type == CANFrame.Byte7_12:
                logging.debug("[I][CAN]: Frame type: {} Byte Value Sensors 7-12".format(can.type))
                self._send_byte(can.mac, "byte", can.bytes, offset=7)

            elif can.type == CANFrame.Byte13_18:
                logging.debug("[I][CAN]: Frame type: {} Byte Value Sensors 13-18".format(can.type))
                self._send_byte(can.mac, "byte", can.bytes, offset=13)

            else:
                logging.debug("[I][CAN]: Frame type: {} not implemented".format(can.type))

        elif can.d0 == 0x10:
            logging.debug("[I][CAN]: D0={} Client application communication".format(can.d0))
        elif can.d0 == 0x11:
            logging.debug("[I][CAN]: D0={} Debug information".format(can.d0))
        else:
            logging.debug("[I][CAN]: D0={} UNKNOWN".format(can.d0))

    def _send_update(self, mac, value_type, value):
        def bits(n):
            """
            Generator returning sequence of power of 2 values for bits set to 1 in n
            :param n: number
            :return: tuple sequence of index of bit set to 1 and power of 2 values for bits set to 1
            """
            while n:
                b = n & (~n + 1)
                yield (b & -b).bit_length() - 1, b
                n ^= b

        try:
            previous = self.states[(mac, value_type)]
            change = previous ^ value
        except KeyError:  # if data not stored before
            change = 0xffffff

        for i, b in bits(change):
            data = 1 if b & value != 0 else 0
            self.received_message(mac, i, value_type, data)
        self.states[(mac, value_type)] = value

    def _send_temp(self, mac, value_type, values, offset=1):
        try:
            previous = self.states[(mac, value_type)]
        except KeyError:
            previous = [None] * 6
            self.states[(mac, value_type)] = previous

        for i, value in enumerate(values, start=offset):
            if value != previous[i - 1]:
                self.received_message(mac, i, value_type, value)
                self.states[(mac, value_type)][i - 1] = value

    def _send_byte(self, mac, value_type, values, offset=1):
        try:
            previous = self.states[(mac, value_type)]
        except KeyError:
            previous = [None] * 18
            self.states[(mac, value_type)] = previous

        for i, value in enumerate(values, start=offset):
            if previous[i - 1] != value:
                self.received_message(mac, i, value_type, value)
                self.states[(mac, value_type)][i - 1] = value

    def register_listener(self, mac, index, type, func):
        try:
            listeners = self.address_listeners[(mac, index, type)]
        except KeyError:
            listeners = []
            self.address_listeners[(mac, index, type)] = listeners

        if not func in listeners:
            listeners.append(func)

        return True

    def unregister_listener(self, mac, index, type, func):
        listeners = self.address_listeners[(mac, index, type)]
        if listeners is None:
            return False

        if func in listeners:
            listeners.remove(func)
            return True

        return False

    def received_message(self, mac, index, type, data):

        try:
            listeners = self.address_listeners[(mac, index, type)]
        except KeyError:
            listeners = []

        for listener in listeners:
            listener(mac, index, type, data)


    def connection_lost(self, exc):
        """Callback when connection lost."""
        self.connected = False
        logging.info('The server closed the connection')
        logging.info('Reconnect in 5 sec')
        self.reconnect(5)

    def __call__(self):
        # Protocol factory. Called by loop.create_connection
        return self

    def excetpion_handler(self, loop, context):
        """Handle exception."""
        logging.debug('Exception: {}'.format(context))
        # exc = context['exception']
        if not self.connected:
            logging.info('Could not connect.')
            self.reconnect(5)
        self.connected = False

    def reconnect(self, delay):
        """Reconnect to the server."""
        self.loop.call_later(delay, self.connect, self.loop, self.host, self.port)

    @asyncio.coroutine
    def send_message(self, data):
        yield from self.queue.put(data)

    @asyncio.coroutine
    def _send_messages(self):
        yield from self._ready.wait()
        while True:
            data = yield from self.queue.get()
            logging.debug("[O]{}".format(frame_to_str(data)))
            self.transport.write(data)

    @asyncio.coroutine
    def binary_output(self, mac, index, value):
        if mac > 1:
            pass
        else:
            mask = (1 << index) & 0xff
            value = 255 if value else 0
            print("MASK: {}".format(mask))
            can = CANSetBinary(mask, value=value)
            frame = ServerFrame(type=5, payload=can.frame)
            yield from self.queue.put(frame.frame)

    @asyncio.coroutine
    def byte_output(self, mac, index, value):
        if mac > 1:
            can = CANSetByteToDevice(mac, index, value)

            frame = ServerFrame(type=0, payload=can.frame)
            yield from self.queue.put(frame.frame)
            pass
        else:
            pass
            # yield from self.queue.put(frame.frame)

    @classmethod
    def connect(cls, loop, host, port):
        logging.info('Trying to connect to {}:{}'.format(host, port))
        client = cls(loop, host, port)
        loop.set_exception_handler(client.excetpion_handler)
        coro = loop.create_connection(client, host, port)
        asyncio.ensure_future(coro)
        return client
