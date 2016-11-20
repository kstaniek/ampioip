"""
This is CAN/Ampio frame implementation
"""

import struct


class FixedField:
    def __init__(self, fmt_char, offset):
        self.fmt_char = fmt_char
        self.offset = offset

    def __get__(self, instance, owner):
        value = struct.unpack_from(self.fmt_char, instance.frame, self.offset)
        return value[0]

    def __set__(self, instance, value):
        struct.pack_into(self.fmt_char, instance.frame, self.offset, value)


class VariableByteField:
    def __init__(self, offset, callback):
        self.offset = offset
        self.callback = callback

    def __set__(self, instance, value):
        # get the end index from instance attribute
        try:
            end = instance.__end
        except AttributeError:
            # id not exists store the offset (zero lenght)
            instance.__end = end = self.offset

        # delete the previous data
        del instance.frame[self.offset:end]

        if isinstance(value, str):
            byte_value = bytearray(value, encoding='ascii')
        elif isinstance(value, FrameClass):
            byte_value = value.frame
        else:
            byte_value = bytearray(value)

        # store the new field end index into instance attribute
        instance.__end = self.offset + len(byte_value)
        # insert new value into instance frame starting from offset
        instance.frame[:self.offset] += byte_value
        self._callback(instance)

    def __get__(self, instance, owner):
        return instance.frame[self.offset:instance.__end]

    def _callback(self, instance):
        callback = getattr(instance, self.callback)
        if hasattr(callback, '__call__'):
            callback()


class FrameClass:
    def __init__(self, raw=None):
        if raw:
            self.frame = bytearray(raw)
        else:
            self.frame = bytearray(self._size)
        self.length = 8

    def __repr__(self):
        return ":".join("{:02x}".format(c) for c in self.frame)


class CANFrame(FrameClass):
    Temp = 5
    TempF1 = 6
    TempF2 = 7
    Byte1_6 = 12
    Byte7_12 = 13
    Byte13_18 = 14
    Binary = 15

    _size = 13
    mac = FixedField("I", 0)
    length = FixedField("B", 4)
    d0 = FixedField("B", 5)
    d1 = FixedField("B", 6)
    type = FixedField("B", 6)
    d2 = FixedField("B", 7)
    mac2 = FixedField(">I", 5)
    d3 = FixedField("B", 8)
    d4 = FixedField("B", 9)
    d5 = FixedField("B", 10)
    d6 = FixedField("B", 11)
    d7 = FixedField("B", 12)

    def __repr__(self):
        return "[CAN]: MAC={:04x} len={:01x} d0={:02x} d1={:02x} d2={:02x} d3={:02x} d4={:02x} d5={:02x} d6={:02x} " \
               "d7={:02x}".format(self.mac, self.length, self.d0, self.d1, self.d2, self.d3, self.d4, self.d5, self.d6, self.d7)

    @property
    def inputs(self):
        return (self.d4 << 16 | self.d3 << 8 | self.d2) & 0xffffff

    @property
    def outputs(self):
        return (self.d7 << 16 | self.d6 << 8 | self.d5) & 0xffffff

    @property
    def temp(self):
        f = self.frame
        return list(map(lambda x: x - 100, [t for t in f[7:] if t != 0]))

    @property
    def tempF(self):
        f = self.frame
        return [((f[i] + f[i + 1] * 256) - 1000) / 10 for i in range(7, 13, 2) if f[i] + f[i + 1] != 0]

    @property
    def bytes(self):
        return [i for i in self.frame[7:]]


class CANSetBinary(CANFrame):
    def __init__(self, mask, value):
        CANFrame.__init__(self)
        self.length = 0
        self.d0 = mask
        self.d1 = value


class CANSetByte(CANFrame):
    def __init__(self, mac, mask, value):
        CANFrame.__init__(self)
        self.mac = mac
        self.length = 0
        self.d0 = mask
        self.d1 = value


class CANSetByteToDevice(CANFrame):
    """
    Frame to set byte for device (not server)
                                        d0 d1 d2 d3 d3 d5 d6 d7
    2d d4 10 00 00 00 00 0f 00 00 00 08 00 00 13 05 07 01 02 00 66 00
                                                                ^^^^^ CRC
                                                          ^^ byte
                                                       ^^ mask
                                                    ^^ opcode
                                        ^^^^^^^^^^^ device mac
                                     ^^ length
                         ^^^^^^^^^^^ special mac (sent to server)


    """
    def __init__(self, mac, mask, value):
        CANFrame.__init__(self)
        self.mac = 0x0f000000
        self.mac2 = mac
        self.d4 = 7
        self.d5 = mask
        self.d6 = value


class ServerFrame(FrameClass):
    _size = 9
    preamble = FixedField("<H", 0)
    size = FixedField("I", 2)
    type = FixedField("B", 6)
    payload = VariableByteField(7, 'update')
    crc = FixedField("<H", -2)

    def __init__(self, type, payload):
        FrameClass.__init__(self)
        self.preamble = 0xd42d
        self.type = type
        self.payload = payload
        self.update()

    def update(self):
        self._calc_crc()
        self._calc_size()

    def _calc_crc(self):
        crc = 0x2d
        for b in self.payload:
            crc += b
        self.crc = crc

    def _calc_size(self):
        self.size = 3 + len(self.payload)


class UserFrame(ServerFrame):
    def __init__(self, username=b'admin'):
        ServerFrame.__init__(self, 10, username)
        #super(UserFrame, self).__init__(10, username)


class PasswordFrame(ServerFrame):
    def __init__(self, password=b'12345'):
        ServerFrame.__init__(self, 11, password)


class InfoFrame(ServerFrame):
    def __init__(self):
        ServerFrame.__init__(self, 12, b'ok')
