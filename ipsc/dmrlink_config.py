#!/usr/bin/env python
#
# Digital Voice Modem - Fixed Network Equipment
# GPLv2 Open Source. Use is subject to license terms.
# DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
#
# @package DVM / FNE / dmrlink
#
###############################################################################
#   Copyright (C) 2016  Cortney T. Buffington, N0MJS <n0mjs@me.com>
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
#   Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
###############################################################################

# Full Imports
import ConfigParser
import sys

# Function Imports
from socket import gethostbyname 

def build_config(_config_file):
    config = ConfigParser.ConfigParser()

    if not config.read(_config_file):
            sys.exit('Configuration file \''+_config_file+'\' is not a valid configuration file! Exiting...')        

    CONFIG = {}
    CONFIG['Global'] = {}
    CONFIG['Reports'] = {}
    CONFIG['Log'] = {}
    CONFIG['Aliases'] = {}
    CONFIG['Systems'] = {}    
    
    try:
        for section in config.sections():
            if section == 'Global':
                CONFIG['Global'].update({
                    'Path': config.get(section, 'Path')
                })

            elif section == 'Reports':
                CONFIG['Reports'].update({
                    'Report': config.getboolean(section, 'Report'),
                    'ReportRCM': config.get(section, 'ReportRCM'),
                    'ReportInterval': config.getint(section, 'ReportInterval'),
                    'ReportPort': config.get(section, 'ReportPort'),
                    'ReportClients': config.get(section, 'ReportClients').split(',')
                })
                if CONFIG['Reports']['ReportPort']:
                    CONFIG['Reports']['ReportPort'] = int(CONFIG['Reports']['ReportPort'])
                if CONFIG['Reports']['ReportRCM']:
                    CONFIG['Reports']['ReportRCM'] = bool(CONFIG['Reports']['ReportRCM'])

            elif section == 'Log':
                CONFIG['Log'].update({
                    'LogFile': config.get(section, 'LogFile'),
                    'LogHandlers': config.get(section, 'LogHandlers'),
                    'LogLevel': config.get(section, 'LogLevel'),
                    'LogName': config.get(section, 'LogName'),
                    'RawPacketTrace': config.getboolean(section, 'RawPacketTrace'),
                    'LogPeerStatus': config.getboolean(section, 'LogPeerStatus'),
                    'LogMasterStatus': config.getboolean(section, 'LogMasterStatus')
                })
                
            elif section == 'Aliases':
                CONFIG['Aliases'].update({
                    'Path': config.get(section, 'Path'),
                    'WhitelistRIDsFile': config.get(section, 'WhitelistRIDsFile'),
                    'BlacklistRIDsFile': config.get(section, 'BlacklistRIDsFile'),
                    'StaleDays': config.getint(section, 'StaleDays') * 86400,
                })
                
            elif config.getboolean(section, 'Enabled'):
                CONFIG['Systems'].update({section: {'LOCAL': {}, 'MASTER': {}, 'PEERS': {}}})
                    
                CONFIG['Systems'][section]['LOCAL'].update({
                    # In case we want to keep config, but not actually connect to the network
                    'Enabled':      config.getboolean(section, 'Enabled'),
                
                    # These items are used to create the MODE byte
                    'PeerOper':    config.getboolean(section, 'PeerOper'),
                    'IPSCMode':    config.get(section, 'IPSCMode'),
                    'TS1Link':     config.getboolean(section, 'TS1Link'),
                    'TS2Link':     config.getboolean(section, 'TS2Link'),
                    'Mode': '',
                
                    # These items are used to create the multi-byte FLAGS field
                    'AuthEnabled':  config.getboolean(section, 'AuthEnabled'),
                    'CSBKCall':     config.getboolean(section, 'CSBKCall'),
                    'RCM':          config.getboolean(section, 'RCM'),
                    'ConApp':       config.getboolean(section, 'ConApp'),
                    'XNL_Call':     config.getboolean(section, 'XNL_Call'),
                    'XNL_Master':   config.getboolean(section, 'XNL_Master'),
                    'DataCall':     config.getboolean(section, 'DataCall'),
                    'VoiceCall':    config.getboolean(section, 'VoiceCall'),
                    'MasterPeer':   config.getboolean(section, 'MasterPeer'),
                    'Flags': '',
                
                    # Things we need to know to connect and be a peer in this IPSC
                    'PEER_ID':      hex(int(config.get(section, 'PeerId')))[2:].rjust(8, '0').decode('hex'),
                    'IP':           gethostbyname(config.get(section, 'IP')),
                    'PORT':         config.getint(section, 'Port'),
                    'AliveTimer':   config.getint(section, 'AliveTimer'),
                    'MaxMissed':    config.getint(section, 'MaxMissed'),
                    'AuthKey':      (config.get(section, 'AuthKey').rjust(40,'0')).decode('hex'),
                    'GroupHangtime': config.getint(section, 'GroupHangtime'),
                    'NUM_PEERS': 0,
                    })

                # Master means things we need to know about the master peer of the network
                CONFIG['Systems'][section]['MASTER'].update({
                    'PEER_ID': '\x00\x00\x00\x00',
                    'MODE': '\x00',
                    'MODE_DECODE': '',
                    'FLAGS': '\x00\x00\x00\x00',
                    'FLAGS_DECODE': '',
                    'STATUS': {
                        'CONNECTED':               False,
                        'PEER_LIST':               False,
                        'KEEP_ALIVES_SENT':        0,
                        'KEEP_ALIVES_MISSED':      0,
                        'KEEP_ALIVES_OUTSTANDING': 0,
                        'KEEP_ALIVES_RECEIVED':    0,
                        'KEEP_ALIVE_RX_TIME':      0
                        },
                    'IP': '',
                    'PORT': ''
                    })

                if not CONFIG['Systems'][section]['LOCAL']['MasterPeer']:
                    CONFIG['Systems'][section]['MASTER'].update({
                        'IP': gethostbyname(config.get(section, 'MasterIP')),
                        'PORT': config.getint(section, 'MasterPort')
                    })
            
                # Temporary locations for building MODE and FLAG data
                MODE_BYTE = 0
                FLAG_1 = 0
                FLAG_2 = 0
            
                # Construct and store the MODE field
                if CONFIG['Systems'][section]['LOCAL']['PeerOper']:
                    MODE_BYTE |= 1 << 6
                if CONFIG['Systems'][section]['LOCAL']['IPSCMode'] == 'ANALOG':
                    MODE_BYTE |= 1 << 4
                elif CONFIG['Systems'][section]['LOCAL']['IPSCMode'] == 'DIGITAL':
                    MODE_BYTE |= 1 << 5
                if CONFIG['Systems'][section]['LOCAL']['TS1Link']:
                    MODE_BYTE |= 1 << 3
                else:
                    MODE_BYTE |= 1 << 2
                if CONFIG['Systems'][section]['LOCAL']['TS2Link']:
                    MODE_BYTE |= 1 << 1
                else:
                    MODE_BYTE |= 1 << 0
                CONFIG['Systems'][section]['LOCAL']['MODE'] = chr(MODE_BYTE)

                # Construct and store the FLAGS field
                if CONFIG['Systems'][section]['LOCAL']['CSBKCall']:
                    FLAG_1 |= 1 << 7  
                if CONFIG['Systems'][section]['LOCAL']['RCM']:
                    FLAG_1 |= 1 << 6
                if CONFIG['Systems'][section]['LOCAL']['ConApp']:
                    FLAG_1 |= 1 << 5
                if CONFIG['Systems'][section]['LOCAL']['XNL_Call']:
                    FLAG_2 |= 1 << 7    
                if CONFIG['Systems'][section]['LOCAL']['XNL_Call'] and CONFIG['Systems'][section]['Local']['XNL_Master']:
                    FLAG_2 |= 1 << 6
                elif CONFIG['Systems'][section]['LOCAL']['XNL_Call'] and not CONFIG['Systems'][section]['Local']['XNL_Master']:
                    FLAG_2 |= 1 << 5
                if CONFIG['Systems'][section]['LOCAL']['AuthEnabled']:
                    FLAG_2 |= 1 << 4
                if CONFIG['Systems'][section]['LOCAL']['DataCall']:
                    FLAG_2 |= 1 << 3
                if CONFIG['Systems'][section]['LOCAL']['VoiceCall']:
                    FLAG_2 |= 1 << 2
                if CONFIG['Systems'][section]['LOCAL']['MasterPeer']:
                    FLAG_2 |= 1 << 0
                CONFIG['Systems'][section]['LOCAL']['FLAGS'] = '\x00\x00' + chr(FLAG_1) + chr(FLAG_2)
    
    except ConfigParser.Error, err:
        print(err)
        sys.exit('Could not parse configuration file, exiting...')
        
    return CONFIG

# ---------------------------------------------------------------------------
#   Program Entry Point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    import os
    import argparse
    from pprint import pprint
    
    # Change the current directory to the location of the application
    os.chdir(os.path.dirname(os.path.realpath(sys.argv[0])))

    # CLI argument parser - handles picking up the config file from the command line, and sending a "help" message
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', action='store', dest='CONFIG_FILE', help='/full/path/to/config.file (usually dmrlink.cfg)')
    cli_args = parser.parse_args()


    # Ensure we have a path for the config file, if one wasn't specified, then use the execution directory
    if not cli_args.CONFIG_FILE:
        cli_args.CONFIG_FILE = os.path.dirname(os.path.abspath(__file__))+'/dmrlink.cfg'
    
    
    pprint(build_config(cli_args.CONFIG_FILE))
