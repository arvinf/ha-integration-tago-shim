import sys, os
import struct
import time
import random
import hexdump
import socket
from enum import Enum
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.client.sync import ModbusTcpClient
from pymodbus.file_message import *
from pymodbus.pdu import ModbusRequest
from pymodbus.pdu import ModbusResponse
from pymodbus.transaction import ModbusRtuFramer
from pymodbus.factory import ClientDecoder
from threading import Lock
import logging
import crcmod

crc16 = None
def calc_modbuscrc(data):
    global crc16
    #return libscrc.modbus(data)
    if crc16 is None:
        crc16 = crcmod.mkCrcFun(0x18005, rev=True, initCrc=0xFFFF, xorOut=0x0000)
    return crc16(data)


class TagoEvents(object):
    def __init__(self, host, port):
        self.sock = None
        self.host = host
        self.port = port
        self.run_thread = True

    def stop(self):
        self.run_thread = False
        if self.sock:
            self.sock.close()

    def getNext(self):
        try:
            def modbus_get_next():
                try:
                    data = self.sock.recv(6)
                except socket.timeout:
                    self.sock.close()
                    self.sock = None
                    return

                if len(data) < 6:
                    return

                length = struct.unpack('>H', data[4:])[0]
                data = bytes()
                while len(data) < length:
                    data += self.sock.recv(length - len(data))

                return data

            while self.run_thread:
                if self.sock is None:
                    logging.info('Listening for events on {host}:{port}'.format(host=self.host, port=self.port))
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.sock.connect((self.host, self.port))
                    self.sock.settimeout(120)
                    logging.info('Connected to {host}:{port}'.format(host=self.host, port=self.port))

                data = modbus_get_next()
                if data is None:
                    continue
                # logging.info('\nPacket {} bytes'.format(len(data)))
                # hexdump.hexdump(data)

                (addr, fc, mei_code) = struct.unpack('<BBB', data[0:3])
                data = data[3:]

                now = int(time.time() * 1000)

                result = []
                ## tagonet message
                if fc == 43 and mei_code == 43:
                    if data[0] == ord('L'):
                        swaddr, key, duration = struct.unpack('BBB', data[1:4])
                        result.append({'event': 'keypress', 
                                       'ts': now,
                                       'keypad': swaddr, 
                                       'key': key, 
                                       'duration': duration})

                        logging.info('Switch Event from 0x{:2x} => addr: 0x{:2x} key: {} duration: {}'.format(addr, swaddr, key, duration))
                        if len(data) > 6:
                            data = data[5:]
                    if data[0] == ord('D'):
                        ch_count = len(data) - 1
                        dimmer_state = struct.unpack('B' * ch_count, data[1:])
                        state = ''.join(['ch {:d}: {: >3}% '.format(i + 1, int((n * 100 )/ 255)) for i, n in enumerate(dimmer_state)])
                        logging.info('Dimmer Event from 0x{:2x} => '.format(addr) + state)

                        state = [].append([{'ch' : i, 'value': int((n * 100 )/ 255)} for i, n in enumerate(dimmer_state)])
                        result.append({'event': 'dimmer_change', 
                                       'ts': now,
                                       'dimmer_addr': addr, 
                                       'state': state})
                if len(result):
                    return result

        except Exception as e:
            logging.error('TagoEvents Exception: {}'.format(e))
            try:
                self.sock.close()
            except:
                pass
            self.sock = None
            time.sleep(1)
            raise
        
        
class TagoDevice(object):
    class Actions(Enum):
        TOGGLE     = 0
        RAMP_TO    = 1
        RAMP_UP    = 2
        RAMP_DOWN  = 3

    class TagonetScanResponse(ModbusResponse):
        function_code = 43

        def __init__(self, **kwargs):
            ModbusResponse.__init__(self, **kwargs)
            self.address = 0
            self.targetid = None

        def encode(self):
            pass

        def decode(self, data):
            decoder = BinaryPayloadDecoder(data, byteorder='>')
            decoder.skip_bytes(2)
            self.code    = decoder.decode_8bit_uint()
            self.address = decoder.decode_8bit_uint()
            self.targetid = decoder.decode_string(32).decode('utf-8').strip('\0')
            # logging.info(data)

    class TagonetScanRequest(ModbusRequest):
        function_code = 43

        def __init__(self, reqid = 0, **kwargs):
            ModbusRequest.__init__(self, **kwargs)
            self.reqid = reqid & 0xFF

        def encode(self):
            msg = struct.pack('>BBBB', 43, ord('S'), ord('?'), self.reqid)
            return msg

        def decode(self, data):
            pass

        def execute(self, context):
            logging.info(context)
            return TagonetScanResponse(context)

    class TagonetSetAddressRequest(ModbusRequest):
        function_code = 43

        def __init__(self, address, targetid, **kwargs):
            ModbusRequest.__init__(self, **kwargs)
            self.address = address
            self.targetid = targetid

        def encode(self):
            msg = struct.pack('>BBBB', 43, ord('S'), ord('='), self.address)
            msg += bytes(self.targetid.encode('utf-8'))
            msg += struct.pack('B', 0)

            return msg

        def decode(self, data):
            pass

        def execute(self, context):
            return TagonetScanResponse(context)

    class TagonetLegacyKeypressRequest(ModbusRequest):
        function_code = 43

        def __init__(self, address=None, key=None, duration=None, **kwargs):
            ModbusRequest.__init__(self, **kwargs)
            self.address = address
            self.key = key
            self.duration = duration

        def encode(self):
            return struct.pack('>BBBBB', 43, ord('L'), self.address, self.key, self.duration)

        def decode(self, data):
            pass

        def execute(self, context):
            return ModbusResponse()

    class TagonetDirectActionRequest(ModbusRequest):
        function_code = 43

        def __init__(self, channel=None, action=None, value=None, rate=None, **kwargs):
            ModbusRequest.__init__(self, **kwargs)
            self.channel = channel
            self.action = action
            self.value = value
            self.rate = rate

        def encode(self):
            return struct.pack('>BBBBBB', 43, ord('A'), 
                                        self.channel, 
                                        self.action, 
                                        self.value,
                                        self.rate)

        def decode(self, data):
            pass

        def execute(self, context):
            return ModbusResponse()


    def __init__(self, host, port, timeout=2):
        self.lock   = Lock()
        self.host   = host
        self.port   = port
        self.client = ModbusTcpClient(host, port=port, timeout=timeout)
        self.client.silent_interval = 0.15
        self.client.register(self.TagonetScanResponse)
        self.client.connect()

    def getInfo(self, node):
        try:
            self.lock.acquire()
            res = self.client.read_holding_registers(0x400, 24, unit=node)
        finally:
            self.lock.release()
        
        decoder = BinaryPayloadDecoder.fromRegisters(res.registers, byteorder='>')

        model = decoder.decode_16bit_uint()
        fwver = decoder.decode_16bit_uint()
        cfgver = decoder.decode_16bit_uint()
        flags = decoder.decode_16bit_uint()
        uptime = decoder.decode_32bit_uint()
        scratch = decoder.decode_32bit_uint()
        did = decoder.decode_string(32).decode('utf-8', 'ignore').replace('\u0000', '')

        return {
            'device_id': did.strip(),
            'model': '{:04X}'.format(model),
            'firwmare_version': '{:04X}'.format(fwver),
            'config_version': '{:04x}'.format(cfgver),
            'flags': flags,
            'uptime': uptime,
        }

    def reboot(self, node, wait=1):
        try:
            self.lock.acquire()
            self.client.write_register(0x511, wait, unit=node)
        finally:
            self.lock.release()

    def identify(self, node, duration=5):
        try:
            self.lock.acquire()
            self.client.write_register(0x510, duration * 8, unit=node)
        finally:
            self.lock.release()

    def updateConfiguration(self, configfile, devid):
        cfg = Config(configfile)

        def updateDeviceConfig(cfg, devid):
            config = cfg.getDeviceConfigById(devid)

            regs = list()
            for n in config['events']:
                regs.append([(1 << 8) | int(n['address'], 0), 
                            (int(n['key']) << 8) | int(n['duration']),
                            (int(n['action_code']) << 8) | int(n['channel']),
                            (int(n['value']) << 8) | int(n['rate'])])

            regs.append([0, 0, 0, 0])

            cksum = calc_modbuscrc(bytes([x for sl in regs for item in sl for x in [item >> 8, item & 0xFF]]))

            node = int(config['modbus_address'], 0)
            logging.info('Updating config for {} at 0x{:2x}'.format(devid, node))

            ## get current version
            res = self.client.read_holding_registers(0x402, 1, unit=node)
            decoder = BinaryPayloadDecoder.fromRegisters(res.registers, byteorder='>')
            version = decoder.decode_16bit_uint();

            if version == cksum:
                logging.info('Device config has not changed ({:2x})'.format(version))
                return
            else:
                version = cksum

            offset = 0x1000
            for r in regs:
                self.client.write_registers(offset, r, unit=node)
                offset += 8

            self.client.write_registers(0x402, version, unit=node)
            logging.info('Wrote config {:2x}.'.format(version))

        try:
            self.lock.acquire()

            if len(devid):
                updateDeviceConfig(cfg, devid)
            else:
                devices = self.scanBus(0)
                for d in devices:
                    updateDeviceConfig(cfg, d['device'].strip())
        finally:
            self.lock.release()


    def scanBus(self, node):
        found = []
        reqid = random.randint(1, 255)
        logging.info('Scanning {} with session id {}'.format(node, reqid))
        try:
            self.lock.acquire()
            while True:
                resp = self.client.execute(self.TagonetScanRequest(unit=node, reqid=reqid))
                if not isinstance(resp, TagoDevice.TagonetScanResponse):
                    logging.info('No device found')
                    return found
                logging.info('Found device {} at address 0x{:2x}'.format(resp.targetid, resp.address))
                found.append({'device_id': resp.targetid, 'addr': resp.address})
                time.sleep(0.2)
        finally:
            self.lock.release()

    def assignAddress(self, node, targetid, address):
        logging.info('Assigning address on {} to {}'.format(targetid, address))
        try:
            self.lock.acquire()
            resp = self.client.execute(self.TagonetSetAddressRequest(address=address, targetid=targetid, unit=node))
            time.sleep(0.5)
            resp = self.client.read_holding_registers(0x400, 2, unit=address)
            logging.info('Changed address on {} to {}'.format(targetid, address))
            return True
        except Exception as e:
            logging.error('Address change failed: {}'.format(e))
            return False
        finally:
            self.lock.release()

    def emulateKeypress(self, node, addr, key, duration):
        try:
            self.lock.acquire()
            self.client.execute(self.TagonetLegacyKeypressRequest(addr, key, duration, unit=node))
        finally:
            self.lock.release()

    def directAction(self, node, channel, action, value, rate=100):
        try:
            self.lock.acquire()
            self.client.execute(self.TagonetDirectActionRequest(channel, action, value, rate, unit=node))
        finally:
            self.lock.release()

    ## The entire firmware has to be written in one pass and must be done in 
    ## increasing sequential address order. Firmware chunks offsets 
    ## must be aligned to 32-bit boundary.
    def updateFirmware(self, node, file):
        def writeRecord(node, fn, rn, rd):
            try:
                self.lock.acquire()
                self.client.execute(WriteFileRecordRequest([FileRecord(file_number=fn,
                                                                    record_number=rn, 
                                                                    record_data=rd)], 
                                                                    unit=node))
            finally:
                self.lock.release()

        with open(file, 'rb') as f:
            data = f.read()
            f.close()

        # data = data[0:244]

        if len(data) % 4:
            data += bytes('\0'.encode('utf-8') * (4 - (len(data) % 4)))
        crc = calc_modbuscrc(data)
        send_size = 64
        offset = 0

        logging.info('Firmware {} bytes. CRC: {:04X}'.format(len(data), crc))
        
        writeRecord(node=node, fn=0xFFFF, rn=0x00, rd=struct.pack('>I', len(data)))
        # time.sleep(0.1)
        ## send chunks of data 
        record = 1
        while offset < len(data):
            wrsize = min(send_size, len(data) - offset)
            chunk = bytes(data[offset : offset + wrsize])
            logging.info('\rSending bytes {} to {} of {} ({}%)'.format(offset, offset + wrsize, len(data), round(offset * 100 / len(data), 1) ), end='\r')
            # hexdump.hexdump(chunk)

            writeRecord(node=node, fn=0xFFFF, rn=record, rd=chunk)
            # time.sleep(0.1)
            record = record + 1
            offset += wrsize

        ## send end of chunks
        writeRecord(node=node, fn=0xFFFF, rn=9999, rd=struct.pack('>H', crc))
        time.sleep(0.1)

        logging.info('')
        try:
            res = self.client.read_holding_registers(0x800, 1, unit=node)
            decoder = BinaryPayloadDecoder.fromRegisters(res.registers, byteorder='>')
            calc_crc = decoder.decode_16bit_uint();
            if calc_crc != crc:
                logging.error('Calculated CRC {} does not match firwmare CRC {}. Failed'.format(calc_crc, crc))
                return False

            ## write CRC to firmware register to boot to new firmware
            self.client.write_register(0x800, crc, unit=node)
            time.sleep(1)
            res = self.client.read_holding_registers(0x800, 1, unit=node)
            decoder = BinaryPayloadDecoder.fromRegisters(res.registers, byteorder='>')
            calc_crc = decoder.decode_16bit_uint();
            if calc_crc == 0:
                logging.error('Firmware upgrade failed')
                return False
            else:
                logging.info('Firmware upgrade successful')
                return True
        finally:
            self.lock.release()

