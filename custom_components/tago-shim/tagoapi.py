from .tagonet import TagoDevice
from sqlitedict import SqliteDict
import random
import logging
import time
import threading
import os

class TagoApi(object):
    __VERSION__ = 1

    def current_sec_time(self):
        return round(time.time())

    def update_exec_time(self):
        self.last_exec_time  = self.current_sec_time()
                

    def __init__(self, host, port, dbpath='.'):
        logging.info('Host: {} Port: {} DbPath: {}'.format(host, port, dbpath))

        if not os.path.exists(dbpath):
            os.mkdir(dbpath)

        dbfile = '{}/devices.sqlite'.format(dbpath)
        self.host = host
        self.port = port
        self.net = TagoDevice(host, port)
        self.update_exec_time()
        self.devices = SqliteDict(dbfile, tablename='devices', 
                                            autocommit=True)
        self.channels = SqliteDict(dbfile, tablename='channels', 
                                            autocommit=True)
        if len(self.devices) == 0:
            try:
                self.rescan_bus()
            except Exception as e:
                logging.error(e)

        for k in self.devices.keys():
                logging.info('{}: {}'.format(k, self.devices[k]))

        # threading.Thread(target=self.watchdog).start()    

    ### Scan the bus and record device_ids and matching addresses.
    ### If any device with address 0xFF or duplicate address is found
    ### give it a new address
    def __scan_devices(self):
        def get_random_address():
            return random.randrange(3, 200)

        def dict_has_value(d, v):
            for k in d.keys():
                if d[k] == v:
                    return True
            return False

        duplicates = {}
        registery = {}
        logging.info('Looking for devices...')

        ## scan the bus
        found = self.net.scanBus(0x00)
        self.update_exec_time()
        for f in found:
            device_id = f['device_id']
            addr = f['addr']
            ## unassigned devices are tracked separately
            if addr == 0xff or dict_has_value(registery, addr):
                duplicates[device_id] = addr;
            else:
                registery[device_id] = addr

        new_addr = get_random_address()
        ## assign new addresses to duplicates and 0xFF
        for k in duplicates:
            while dict_has_value(registery, new_addr):
                new_addr = get_random_address()

            self.update_exec_time()
            if self.net.assignAddress(duplicates[k], k, new_addr):
                registery[k] = new_addr
                new_addr = get_random_address()
                logging.info('Assigned new address {} to {}'.format(new_addr, k))
            else:
                logging.error('Could not assign new address {} to {}'.format(new_addr, k))

        return registery

    def __lookup_addr(self, tid):
        if not tid in self.devices:
            raise Exception('Device {} not found'.format(tid))
        
        return self.devices[tid]['addr']

    def rename_device(self, tid, name):
        self.devices[tid] = {
            'name': name,
            'addr' : self.devices[tid]['addr']
        }

    def rename_channel(self, tid, ch, name):
        key = '{}/{}'.format(tid , ch)
        self.channels[key] = {'name': name}

    def scan(self, addr):
        return net.scanBus(int(addr))

    def assign_addr(self, tid, src, dst):
        self.update_exec_time()
        if self.net.assignAddress(src, tid, dst):
            devices[tid] = dst
            return True
        else:
            return False

    def device_info(self, tid):
        addr = self.__lookup_addr(tid)
        res = {'api_vesion': self.__VERSION__}

        self.update_exec_time()
        res.update(self.net.getInfo(addr))
        res.update({'dimmer_chs': 8,'relay_chs': 0})
        return res

    def identify_device(self, tid):
        self.net.identify(self.__lookup_addr(tid))
        self.update_exec_time()

    def reboot_device(self, tid):
        self.net.reboot(self.__lookup_addr(tid))
        self.update_exec_time()

    def device_action(self, tid, channel, action, value, rate):
        addr = self.__lookup_addr(tid)
        if (value < 0): value = 0
        if (value > 100): value = 100

        ## convert from 0 to 100 to 0 to 255
        value = int((value * 255) / 100)
        try: 
            action = action.upper()
            action = TagoDevice.Actions[action]
            
            self.net.directAction(addr, channel, action.value, value, rate)
            self.update_exec_time()
        except Exception as e: 
            logging.error('Action failed {}'.format(e))
            pass

    ## rescan all devices on the bus
    def rescan_bus(self):
        results = self.__scan_devices()

        # for d in self.devices:
            # if not d in results:
            #     del self.devices[d]
        
        for d in results:
            if d in self.devices:
                name = self.devices[d].get('name', d)
            else:
                name = d

            self.devices[d] = {
                'name': name,
                'addr': results[d]
            }

        return results

    ## list all devices
    def list_devices(self):
        results = {}
        for d in self.devices:
            name = self.devices[d]['name']
            results[d] = {'alias': name, 'addr': self.devices[d]['addr'],
                           'dimmers': {}}
            for i in range(8):
                key = '{}/{}'.format(d , i+1)
                results[d]['dimmers'][key] = {'ch': i+1}

                ## lookup channel alias if it exists
                if key in self.channels:
                    results[d]['dimmers'][key]['alias'] = self.channels[key]['name']

        return results
