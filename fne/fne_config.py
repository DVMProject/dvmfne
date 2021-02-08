#!/usr/bin/env python
#
# Digital Voice Modem - Fixed Network Equipment
# GPLv2 Open Source. Use is subject to license terms.
# DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
#
# @package DVM / FNE
#
###############################################################################
#   Copyright (C) 2016 Cortney T.  Buffington, N0MJS <n0mjs@me.com>
#   Copyright (C) 2017-2019 Bryan Biedenkapp <gatekeep@gmail.com>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software Foundation,
#   Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
###############################################################################
import ConfigParser
import sys

from socket import gethostbyname 

def build_config(_config_file):
    config = ConfigParser.ConfigParser()

    if not config.read(_config_file):
        sys.exit('Configuration file \'' + _config_file + '\' is not a valid configuration file! Exiting...')        

    CONFIG = {}
    CONFIG['Global'] = {}
    CONFIG['Reports'] = {}
    CONFIG['Log'] = {}
    CONFIG['Aliases'] = {}
    CONFIG['ExportAMBE'] = {}
    CONFIG['PacketData'] = {}
    CONFIG['Systems'] = {}

    try:
        for section in config.sections():
            if section == 'Global':
                CONFIG['Global'].update({
                    'Path': config.get(section, 'Path'),
                    'PingTime': config.getint(section, 'PingTime'),
                    'MaxMissed': config.getint(section, 'MaxMissed'),
                    'RconTool': config.get(section, 'RconTool')
                })

            elif section == 'Reports':
                CONFIG['Reports'].update({
                    'Report': config.getboolean(section, 'Report'),
                    'ReportInterval': config.getint(section, 'ReportInterval'),
                    'ReportPort': config.getint(section, 'ReportPort'),
                    'ReportClients': config.get(section, 'ReportClients').split(',')
                })

            elif section == 'Log':
                CONFIG['Log'].update({
                    'LogFile': config.get(section, 'LogFile'),
                    'LogHandlers': config.get(section, 'LogHandlers'),
                    'LogLevel': config.get(section, 'LogLevel'),
                    'LogName': config.get(section, 'LogName'),
                    'RawPacketTrace': config.getboolean(section, 'RawPacketTrace'),
                    'AllowActTrans': config.getboolean(section, 'AllowActTrans'),
                    'AllowDiagTrans': config.getboolean(section, 'AllowDiagTrans'),
                    'ActivityLogFile': config.get(section, 'ActivityLogFile'),
                    'DiagLogPath': config.get(section, 'DiagLogPath')
                })

            elif section == 'Aliases':
                CONFIG['Aliases'].update({
                    'Path': config.get(section, 'Path'),
                    'WhitelistRIDsFile': config.get(section, 'WhitelistRIDsFile'),
                    'BlacklistRIDsFile': config.get(section, 'BlacklistRIDsFile'),
                    'StaleTime': config.getint(section, 'StaleDays') * 86400,
                })

            elif section == 'ExportAMBE':
                CONFIG['ExportAMBE'].update({
                    'Address': gethostbyname(config.get(section, 'Address')),
                    'Port': config.getint(section, 'Port'),
                })

            elif section == 'PacketData':
                CONFIG['PacketData'].update({
                    'Port': config.getint(section, 'Port'),
                    'Gateway': gethostbyname(config.get(section, 'Gateway')),
                    'GatewayPort': config.getint(section, 'GatewayPort'),
                })

            elif config.getboolean(section, 'Enabled'):
                if config.get(section, 'Mode') == 'peer':
                    CONFIG['Systems'].update({section: {
                        'Mode': config.get(section, 'Mode'),
                        'Enabled': config.getboolean(section, 'Enabled'),
                        'ExportAMBE': config.getboolean(section, 'ExportAMBE'),
                        'PacketData': config.getboolean(section, 'PacketData'),
                        'Address': gethostbyname(config.get(section, 'Address')),
                        'Port': config.getint(section, 'Port'),
                        'MasterAddress': gethostbyname(config.get(section, 'MasterAddress')),
                        'MasterPort': config.getint(section, 'MasterPort'),
                        'Passphrase': config.get(section, 'Passphrase'),
                        'PeerId': hex(int(config.get(section, 'PeerId')))[2:].rjust(8,'0').decode('hex'),
                        'Identity': config.get(section, 'Identity').ljust(8)[:8],
                        'RxFrequency': config.get(section, 'RxFrequency').ljust(9)[:9],
                        'TxFrequency': config.get(section, 'TxFrequency').ljust(9)[:9],
                        'Latitude': config.get(section, 'Latitude').ljust(8)[:8],
                        'Longitude': config.get(section, 'Longitude').ljust(9)[:9],
                        'Location': config.get(section, 'Location').ljust(20)[:20],
                        'SoftwareId': config.get(section, 'SoftwareId').ljust(16)[:16],
                        'GroupHangtime': config.getint(section, 'GroupHangtime')
                    }})
                    CONFIG['Systems'][section].update({'STATS': {
                        'CONNECTION': 'NO',             # NO, RTPL_SENT, AUTHENTICATED, CONFIG-SENT, YES
                        'PINGS_SENT': 0,
                        'PINGS_ACKD': 0,
                        'PING_OUTSTANDING': False,
                        'LAST_PING_TX_TIME': 0,
                        'LAST_PING_ACK_TIME': 0,
                    }})
        
                elif config.get(section, 'Mode') == 'master':
                    CONFIG['Systems'].update({section: {
                        'Mode': config.get(section, 'Mode'),
                        'Enabled': config.getboolean(section, 'Enabled'),
                        'Repeat': config.getboolean(section, 'Repeat'),
                        'ExportAMBE': config.getboolean(section, 'ExportAMBE'),
                        'PacketData': config.getboolean(section, 'PacketData'),
                        'Address': gethostbyname(config.get(section, 'Address')),
                        'Port': config.getint(section, 'Port'),
                        'Passphrase': config.get(section, 'Passphrase'),
                        'GroupHangtime': config.getint(section, 'GroupHangtime'),
                    }})
                    CONFIG['Systems'][section].update({'PEERS': {}})
    
    except ConfigParser.Error, err:
        print "Cannot parse configuration file. %s" % err
        sys.exit('Could not parse configuration file, exiting...')
        
    return CONFIG


# ************************************************
#  MAIN PROGRAM LOOP
# ************************************************
if __name__ == '__main__':
    import sys
    import os
    import argparse

    from pprint import pprint
    
    # Change the current directory to the location of the application
    os.chdir(os.path.dirname(os.path.realpath(sys.argv[0])))

    # CLI argument parser - handles picking up the config file from the command
    # line, and sending a "help" message
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', action='store', dest='CONFIG_FILE', help='/full/path/to/config.file (usually fne.cfg)')
    cli_args = parser.parse_args()


    # Ensure we have a path for the config file, if one wasn't specified, then
    # use the execution directory
    if not cli_args.CONFIG_FILE:
        cli_args.CONFIG_FILE = os.path.dirname(os.path.abspath(__file__)) + '/fne.cfg'
    
    pprint(build_config(cli_args.CONFIG_FILE))
