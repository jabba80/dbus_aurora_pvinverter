#!/usr/bin/env python3

"""
A class to put a simple service on the dbus, according to victron standards, with constantly updating
paths. See example usage below. It is used to generate dummy data for other processes that rely on the
dbus. See files in dbus_vebus_to_pvinverter/test and dbus_vrm/test for other usage examples.

To change a value while testing, without stopping your dummy script and changing its initial value, write
to the dummy data via the dbus. See example.

https://github.com/victronenergy/dbus_vebus_to_pvinverter/tree/master/test
"""
from gi.repository import GLib
import platform
import argparse
import logging
import sys
import os

import time, datetime
from aurorapy.client import AuroraError, AuroraSerialClient

# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '../ext/velib_python'))
from vedbus import VeDbusService



class DbusDummyService(object):

    grid_voltage = 0
    grid_current = 0
    grid_power = 0
    cum_energy_total = 0

    def __init__(self, servicename, deviceinstance, paths, productname='Aurora PV-Inverter', connection='ttyUSB0', productid=45069):
        self._dbusservice = VeDbusService(servicename)
        self._paths = paths

        logging.info("%s /DeviceInstance = %d" % (servicename, deviceinstance))

        # Create the management objects, as specified in the ccgx dbus-api document
        self._dbusservice.add_path('/Mgmt/ProcessName', __file__)
        self._dbusservice.add_path('/Mgmt/ProcessVersion', 'Unkown version, and running on Python ' + platform.python_version())
        self._dbusservice.add_path('/Mgmt/Connection', connection)

        # Create the mandatory objects
        self._dbusservice.add_path('/DeviceInstance', deviceinstance)
        self._dbusservice.add_path('/ProductId', productid)
        self._dbusservice.add_path('/ProductName', productname)
        self._dbusservice.add_path('/FirmwareVersion', 0)
        self._dbusservice.add_path('/HardwareVersion', 0)
        self._dbusservice.add_path('/Connected', 1)
        self._dbusservice.add_path('/Position', 0)
        self._dbusservice.add_path('/StatusCode', 0)
        self._dbusservice.add_path('/Role', 'pvinverter')
        self._dbusservice.add_path('/DbusInvalid', None)

        for path, settings in self._paths.items():
            self._dbusservice.add_path(
                path, settings['initial'], gettextcallback=settings['textformat'], writeable=True, onchangecallback=self._handlechangedvalue)

        GLib.timeout_add(10000, self._update)

    def _update(self):
        self._getInverterData()
        with self._dbusservice as s:
            s["/Ac/Power"] = round(self.grid_power,2)
            s["/Ac/Current"] = round(self.grid_current,2)
            s["/Ac/L1/Voltage"] = round(self.grid_voltage,2)
            s["/Ac/L1/Current"] = round((self.grid_current/3.0),2)
            s["/Ac/L1/Power"] = round((self.grid_power/3.0),2)
            s["/Ac/L2/Voltage"] = round(self.grid_voltage,2)
            s["/Ac/L2/Current"] = round((self.grid_current/3.0),2)
            s["/Ac/L2/Power"] = round((self.grid_power/3.0),2)
            s["/Ac/L3/Voltage"] = round(self.grid_voltage,2)
            s["/Ac/L3/Current"] = round((self.grid_current/3.0),2)
            s["/Ac/L3/Power"] = round((self.grid_power/3.0),2)
            s["/Ac/Energy/Forward"] = round((self.cum_energy_total/1000.0),2)
            s["/Ac/L1/Energy/Forward"] = round((self.cum_energy_total/3000.0),2)
            s["/Ac/L2/Energy/Forward"] = round((self.cum_energy_total/3000.0),2)
            s["/Ac/L3/Energy/Forward"] = round((self.cum_energy_total/3000.0),2)
            s["/Ac/MaxPower"] = 10000
            s["/StatusCode"] = 7

        return True

    def _handlechangedvalue(self, path, value):
        logging.debug("someone else updated %s to %s" % (path, value))
        return True # accept the change
    
    def _getInverterData(self):
        # Assign correct client to measure
        client = AuroraSerialClient(port='/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A50285BI-if00-port0', address=3, baudrate=19200, parity='N',
                                    stop_bits=1, timeout=5)
    

        try:
            # Open client connection
            logging.debug("Opening RS485-Connection")
            client.connect()
            # Try to get the clients current timestamp
            client_time = client.time_date()
            # Only try to measure rest if timestamp is correctly received
            if client_time != -1:
                logging.debug("\nClient:", client.address, datetime.datetime.fromtimestamp(client_time))
                self.grid_voltage = client.measure(1)
                logging.debug("Grid Voltage: %.2f V" % self.grid_voltage)
                self.grid_current = client.measure(2)
                logging.debug("Grid Current: %.2f A" % self.grid_current)
                self.grid_power = client.measure(3)
                logging.debug("Grid Power: %.2f W" % self.grid_power)
                self.cum_energy_total = client.cumulated_energy(5)
                logging.debug("Total %.2f kWh" % (self.cum_energy_total / 1000.0))
            else:
                logging.debug("Client not online")
                # Close client connection
                client.close()
        except AuroraError as e:
            logging.error(str(e))
        
        finally:
            # Close RS-485 port
            logging.debug("Closing RS485-Connection")
            client.close()

        return True


# === All code below is to simply run it from the commandline for debugging purposes ===

# It will created a dbus service called com.victronenergy.pvinverter.output.
# To try this on commandline, start this program in one terminal, and try these commands
# from another terminal:
# dbus com.victronenergy.pvinverter.output
# dbus com.victronenergy.pvinverter.output /Ac/Energy/Forward GetValue
# dbus com.victronenergy.pvinverter.output /Ac/Energy/Forward SetValue %20
#
# Above examples use this dbus client: http://code.google.com/p/dbus-tools/wiki/DBusCli
# See their manual to explain the % in %20

def main():
    #configure logging
    logging.basicConfig(    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S',
                            level=logging.INFO,
                            handlers=[
                                logging.FileHandler("%s/current.log" % (os.path.dirname(os.path.realpath(__file__)))),
                                logging.StreamHandler()
                            ])

    from dbus.mainloop.glib import DBusGMainLoop
    # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
    DBusGMainLoop(set_as_default=True)

    #formatting
    _kwh = lambda p, v: (str(round(v, 2)) + 'kWh')
    _a = lambda p, v: (str(round(v, 1)) + 'A')
    _w = lambda p, v: (str(round(v, 1)) + 'W')
    _v = lambda p, v: (str(round(v, 1)) + 'V')

    pvac_output = DbusDummyService(
        servicename='com.victronenergy.pvinverter.ttyUSB0',
        deviceinstance=0,
        paths={
            '/Ac/Power':{'initial': 0, 'textformat': _w},
            '/Ac/Current':{'initial': 0, 'textformat': _a},
            '/Ac/L1/Voltage':{'initial': 0, 'textformat': _v},
            '/Ac/L1/Current':{'initial': 0, 'textformat': _a},
            '/Ac/L1/Power':{'initial': 0, 'textformat': _w},
            '/Ac/L2/Voltage':{'initial': 0, 'textformat': _v},
            '/Ac/L2/Current':{'initial': 0, 'textformat': _a},
            '/Ac/L2/Power':{'initial': 0, 'textformat': _w},
            '/Ac/L3/Voltage':{'initial': 0, 'textformat': _v},
            '/Ac/L3/Current':{'initial': 0, 'textformat': _a},
            '/Ac/L3/Power':{'initial': 0, 'textformat': _w},
            '/Ac/Energy/Forward':{'initial': None, 'textformat': _kwh},
            '/Ac/L1/Energy/Forward':{'initial': None, 'textformat': _kwh},
            '/Ac/L2/Energy/Forward':{'initial': None, 'textformat': _kwh},
            '/Ac/L3/Energy/Forward':{'initial': None, 'textformat': _kwh},
            '/Ac/MaxPower':{'initial': 0, 'textformat': _w},
            
            # '/Position': {'initial': 0, 'update': 0},
            # '/StatusCode': {'initial': 0, 'update': 0},
            # '/Role': {'initial': 'pvinverter', 'update': 0},
            # '/DbusInvalid': {'initial': None},
        })

    logging.info('Connected to dbus, and switching over to GLib.MainLoop() (= event based)')
    mainloop = GLib.MainLoop()
    mainloop.run()


if __name__ == "__main__":
    main()

