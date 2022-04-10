# TinyTuya Setup Wizard
# -*- coding: utf-8 -*-
"""
TinyTuya Network Scanner for Tuya based WiFi smart devices

Author: Jason A. Cox
For more information see https://github.com/jasonacox/tinytuya

Description
    Scan will scan the local network for Tuya devices and if a local devices.json is
    present in the local directory, will use the Local KEYs to poll the devices for 
    status.

"""
# Modules
from __future__ import print_function
from audioop import add  # python 2.7 support
import logging
import time
import json
import tinytuya
from hashlib import md5
import socket
import ipaddress  
import sys

try:
    # Optional libraries required for forced scanning
    from getmac import get_mac_address
    SCANLIBS = True
except:
    # Disable nmap scanning
    SCANLIBS = False

# Required module: pycryptodome
try:
    import Crypto
    from Crypto.Cipher import AES  # PyCrypto
except ImportError:
    Crypto = AES = None
    import pyaes  # https://github.com/ricmoo/pyaes

# Backward compatability for python2
try:
    input = raw_input
except NameError:
    pass

# Global Configs
DEFAULT_NETWORK = '192.168.0.0/24'
DEVICEFILE = "devices.json"
SNAPSHOTFILE = "tuyascan.json"
TCPTIMEOUT = 0.4

# Logging
log = logging.getLogger(__name__)

# Helper Functions
def getmyIP():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    r = s.getsockname()[0]
    s.close()
    return r
    

# Scan function shortcut
def scan(maxretry=None, color=True, forcescan=False):
    """Scans your network for Tuya devices with output to stdout"""
    # Terminal formatting
    (bold, subbold, normal, dim, alert, alertdim, cyan, red, yellow) = tinytuya.termcolor(color)
    devices(verbose=True, maxretry=maxretry, color=color, poll=True, forcescan=forcescan)


# Scan function
def devices(verbose=False, maxretry=None, color=True, poll=True, forcescan=False):
    """Scans your network for Tuya devices and returns dictionary of devices discovered
        devices = tinytuya.deviceScan(verbose)

    Parameters:
        verbose = True or False, print formatted output to stdout [Default: False]
        maxretry = The number of loops to wait to pick up UDP from all devices
        color = True or False, print output in color [Default: True]
        poll = True or False, poll dps status for devices if possible
        forcescan = True or false, force network scan for device IP addresses

    Response:
        devices = Dictionary of all devices found

    To unpack data, you can do something like this:

        devices = tinytuya.deviceScan()
        for ip in devices:
            id = devices[ip]['gwId']
            key = devices[ip]['productKey']
            vers = devices[ip]['version']
            dps = devices[ip]['dps']

    """
    havekeys = False
    tuyadevices = []

    # Terminal formatting
    (bold, subbold, normal, dim, alert, alertdim, cyan, red, yellow) = tinytuya.termcolor(color)

    # Lookup Tuya device info by (id) returning (name, key)
    def tuyaLookup(deviceid):
        for i in tuyadevices:
            if i["id"] == deviceid:
                if "mac" in i:
                    return (i["name"], i["key"], i["mac"])
                else:
                    return (i["name"], i["key"], "")
        return ("", "", "")

    # Check to see if we have additional Device info
    try:
        # Load defaults
        with open(DEVICEFILE) as f:
            tuyadevices = json.load(f)
            havekeys = True
            log.debug("loaded=%s [%d devices]" % (DEVICEFILE, len(tuyadevices)))
            # If no maxretry value set, base it on number of devices
            if maxretry is None:
                maxretry = len(tuyadevices) + tinytuya.MAXCOUNT
    except:
        # No Device info
        pass

    # If no maxretry value set use default
    if maxretry is None:
        maxretry = tinytuya.MAXCOUNT

    # Enable UDP listening broadcasting mode on UDP port 6666 - 3.1 Devices
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    client.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    client.bind(("", tinytuya.UDPPORT))
    client.settimeout(tinytuya.TIMEOUT)
    # Enable UDP listening broadcasting mode on encrypted UDP port 6667 - 3.3 Devices
    clients = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    clients.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    clients.bind(("", tinytuya.UDPPORTS))
    clients.settimeout(tinytuya.TIMEOUT)

    if verbose:
        print(
            "\n%sTinyTuya %s(Tuya device scanner)%s [%s]\n"
            % (bold, normal, dim, tinytuya.__version__)
        )
        if havekeys:
            print("%s[Loaded devices.json - %d devices]\n" % (dim, len(tuyadevices)))
        print(
            "%sScanning on UDP ports %s and %s for devices (%s retries)...%s\n"
            % (subbold, tinytuya.UDPPORT, tinytuya.UDPPORTS, maxretry, normal)
        )

    if forcescan:
        if not SCANLIBS:
            if verbose:
                print(alert + 
                    '    ERROR: force network scanning requested but not available - disabled.\n' 
                    '           (Requires: pip install getmac)\n' + dim)
            forcescan = False
        else:
            if verbose:
                print(subbold + "    Option: " + dim + "Network force scanning requested.\n")

    devices = {}
    count = 0
    counts = 0
    spinnerx = 0
    spinner = "|/-\\|"
    ip_list = {}

    if forcescan:
        # Force Scan - Get list of all local ip addresses
        try: 
            # Fetch my IP address and assume /24 network
            ip = getmyIP()
            network = ipaddress.IPv4Interface(u''+ip+'/24').network
            log.debug("Starting brute force network scan %r", network)
        except:
            network = DEFAULT_NETWORK
            ip = None
            log.debug("Unable to get local network, using default %r", network)
            if verbose:
                print(alert + 
                    'ERROR: Unable to get your IP address and network automatically.' 
                    '       (using %s)' % network + normal)
        
        try:
            # Warn user of scan duration
            if verbose:
                print("\n" + bold + "Scanning local network.  This may take a while..." + dim)
                print(bold + '\n    Running Scan...' + dim)
            # Loop through each host
            for addr in ipaddress.IPv4Network(network):
                # Fetch my IP address and assume /24 network
                if verbose:
                    print(dim + '\r      Host: ' + subbold + '%s ...' % addr + normal, end='')
                a_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                a_socket.settimeout(TCPTIMEOUT)
                location = (str(addr), tinytuya.TCPPORT)
                result_of_check = a_socket.connect_ex(location)
                if result_of_check == 0:
                    # TODO: Verify Tuya Device
                    ip = "%s" % addr
                    mac = get_mac_address(ip=ip)
                    ip_list[ip] = mac
                    log.debug("Found Device [%s]" % mac)
                    if verbose:
                        print(" Found Device [%s]" % mac)
                a_socket.close()
            
            if verbose:
                print(dim + '\r      Done                           ' +normal + 
                            '\n\nDiscovered %d Tuya Devices\n' % len(ip_list))

        except:
            log.debug("Error scanning network - Ignoring")
            if verbose:
                print('\n' + alert + '    Error scanning network - Ignoring' + dim)
            forcescan = False

    log.debug("Listening for Tuya devices on UDP 6666 and 6667")
    while (count + counts) <= maxretry:
        note = "invalid"
        if verbose:
            print("%sScanning... %s\r" % (dim, spinner[spinnerx]), end="")
            spinnerx = (spinnerx + 1) % 4
            sys.stdout.flush()
            time.sleep(0.1)

        if count <= counts:  # alternate between 6666 and 6667 ports
            try:
                data, addr = client.recvfrom(4048)
            except KeyboardInterrupt as err:
                log.debug("Keyboard Interrupt - Exiting")
                if verbose:
                    print("\n**User Break**")
                exit()
            except Exception as err:
                # Timeout
                count = count + 1
                continue
        else:
            try:
                data, addr = clients.recvfrom(4048)
            except KeyboardInterrupt as err:
                log.debug("Keyboard Interrupt - Exiting")
                if verbose:
                    print("\n**User Break**")
                exit()
            except Exception as err:
                # Timeout
                counts = counts + 1
                continue
        ip = addr[0]
        gwId = productKey = version = dname = dkey = mac = mac2 = suffix = ""
        result = data
        try:
            result = data[20:-8]
            try:
                result = tinytuya.decrypt_udp(result)
            except:
                result = result.decode()

            result = json.loads(result)
            log.debug("Received valid UDP packet: %r" % result)

            note = "Valid"
            ip = result["ip"]
            gwId = result["gwId"]
            productKey = result["productKey"]
            version = result["version"]
        except:
            if verbose:
                print(alertdim + "*  Unexpected payload=%r\n" + normal, result)
            result = {"ip": ip}
            note = "Unknown"
            log.debug("Invalid UDP Packet: %r" % result)

        # check to see if we have seen this device before and add to devices array
        if tinytuya.appenddevice(result, devices) is False:

            # new device found - back off count if we keep getting new devices
            if version == "3.1":
                count = tinytuya.floor(count - 1)
            else:
                counts = tinytuya.floor(counts - 1)
            # check if we have MAC address
            if havekeys:
                try:
                    # Try to pull name and key data
                    (dname, dkey, mac2) = tuyaLookup(gwId)
                except:
                    pass
            if mac2 == "" and ip in ip_list:
                mac = ip_list[ip]
            else:
                mac = mac2
            suffix = dim + ", MAC = " + mac + ""
            if verbose:
                if dname == "":
                    devicename = "Unknown v%s%s Device%s" % (normal, version, dim)
                else:
                    devicename = normal + dname + dim
                print(
                    "%s   Product ID = %s  [%s payload]:\n    %sAddress = %s,  %sDevice ID = %s, %sLocal Key = %s,  %sVersion = %s%s"
                    % (
                        devicename,
                        productKey,
                        note,
                        subbold,
                        ip,
                        cyan,
                        gwId,
                        red,
                        dkey,
                        yellow,
                        version,
                        suffix
                    )
                )

            try:
                if poll:
                    time.sleep(0.1)  # give device a break before polling
                    if version == "3.1":
                        # Version 3.1 - no device key requires - poll for status data points
                        d = tinytuya.OutletDevice(gwId, ip, dkey)
                        d.set_version(3.1)
                        dpsdata = d.status()
                        if "dps" not in dpsdata:
                            if verbose:
                                if "Error" in dpsdata:
                                    print(
                                        "%s    Access rejected by %s: %s"
                                        % (alertdim, ip, dpsdata["Error"])
                                    )
                                else:
                                    print(
                                        "%s    Invalid response from %s: %r"
                                        % (alertdim, ip, dpsdata)
                                    )
                            devices[ip]["err"] = "Unable to poll"
                        else:
                            devices[ip]["dps"] = dpsdata
                            if verbose:
                                print(dim + "    Status: %s" % dpsdata["dps"])
                    else:
                        # Version 3.3+ requires device key
                        if dkey != "":
                            d = tinytuya.OutletDevice(gwId, ip, dkey)
                            d.set_version(3.3)
                            dpsdata = d.status()
                            if "dps" not in dpsdata:
                                if verbose:
                                    if "Error" in dpsdata:
                                        print(
                                            "%s    Access rejected by %s: %s"
                                            % (alertdim, ip, dpsdata["Error"])
                                        )
                                    else:
                                        print(
                                            "%s    Check DEVICE KEY - Invalid response from %s: %r"
                                            % (alertdim, ip, dpsdata)
                                        )
                                devices[ip]["err"] = "Unable to poll"
                            else:
                                devices[ip]["dps"] = dpsdata
                                if verbose:
                                    print(dim + "    Status: %s" % dpsdata["dps"])
                        else:
                            if verbose:
                                print(
                                    "%s    No Stats for %s: DEVICE KEY required to poll for status%s"
                                    % (alertdim, ip, dim)
                                )
                    # else
                # if poll
            except:
                if verbose:
                    print(alertdim + "    Unexpected error for %s: Unable to poll" % ip)
                devices[ip]["err"] = "Unable to poll"
            if dname != "":
                devices[ip]["name"] = dname
                devices[ip]["key"] = dkey
            if mac != "":
                devices[ip]["mac"] = mac
        else:
            if version == "3.1":
                count = count + 1
            else:
                counts = counts + 1

    if verbose:
        print(
            "                    \n%sScan Complete!  Found %s devices."
            % (normal, len(devices))
        )
        # Save polling data snapshot
        current = {'timestamp' : time.time(), 'devices' : devices}
        output = json.dumps(current, indent=4) 
        print(bold + "\n>> " + normal + "Saving device snapshot data to " + SNAPSHOTFILE + "\n")
        with open(SNAPSHOTFILE, "w") as outfile:
            outfile.write(output)

    log.debug("Scan complete with %s devices found" % len(devices))
    clients.close()
    client.close()
    return devices


if __name__ == '__main__':

    try:
        scan()
    except KeyboardInterrupt:
        pass
