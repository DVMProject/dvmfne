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
#   Copyright (C) 2017  Mike Zingman, N4IRR <Not.A.Chance@NoWhere.com>
#   Copyright (C) 2021  Bryan Biedenkapp, N2PLL <gatekeep@gmail.com>
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
# This is a bridge application for IPSC networks.  It knows how to export AMBE
# frames and metadata to an external program/network.  It also knows how to import
# AMBE and metadata from an external network and send the DMR frames to IPSC networks.
###############################################################################
from __future__ import print_function

import sys, socket, ConfigParser, thread, traceback
import cPickle as pickle
import csv
import struct

from binascii import b2a_hex as h
from bitstring import BitArray
from time import time, sleep, clock, localtime, strftime
from random import randint

from twisted.python import log
from twisted.internet import reactor

from dmrlink import IPSC, systems, config_reports, reportFactory

from ipsc.ipsc_const import *
from ipsc.ipsc_mask import *

from dmr_utils import ambe_utils
from dmr_utils.tlv import tlvIPSC

from ipsc.ipsc_const import *
from ipsc.ipsc_mask import *
    
from fne.fne_core import hex_str_3, hex_str_4, int_id

# ---------------------------------------------------------------------------
#   Class Declaration
#     
# ---------------------------------------------------------------------------

class bridgeIPSC(IPSC):
    def __init__(self, _name, _config, _bridge_config, _logger, _report):
        IPSC.__init__(self, _name, _config, _logger, _report)

        self._busy_slots = [0, 0, 0]                        # Keep track of activity on each slot.  Make sure app is polite
        self.cc = 1

        self._tlvPort = 31003                               # Port to listen on for TLV frames to transmit to all peers
        self._gateway = "127.0.0.1"                         # IP address of bridge app
        self._gateway_port = 31000                          # Port bridge is listening on for TLV frames to decode
        
        #
        # Define default values for operation.  These will be overridden by the .cfg file if found
        #
        
        self._currentNetwork = str(_name)
        self.readConfigFile(_bridge_config, None, self._currentNetwork)
    
        logger.info('DMRLink IPSC Bridge')

        self.tlv_ipsc = tlvIPSC(self, _name, _config, _logger, self._tlvPort)

    def get_peer_id(self, import_id):
        return self._local_id

    # Now read the configuration file and parse out the values we need
    def defaultOption(self, config, sec, opt, defaultValue):
        try:
            _value = config.get(sec, opt).split(None)[0]    # Get the value from the named section
        except ConfigParser.NoOptionError as e:
            try:
                _value = config.get('BridgeGlobal', opt).split(None)[0] # Try the global BridgeGlobal section
            except ConfigParser.NoOptionError as e:
                _value = defaultValue                       # Not found anywhere, use the default value
        logger.info(opt + ' = ' + str(_value))
        return _value

    def readConfigFile(self, configFileName, sec, networkName='BridgeGlobal'):
        config = ConfigParser.ConfigParser()
        try:
            config.read(configFileName)
            
            if sec == None:
                sec = self.defaultOption(config, 'BridgeGlobal', 'section', networkName)
            if config.has_section(sec) == False:
                logger.info('Section ' + sec + ' was not found, using BridgeGlobal')
                sec = 'BridgeGlobal'

            self._tlvPort = int(self.defaultOption(config, sec, 'FromGatewayPort', self._tlvPort))
            self._gateway = self.defaultOption(config, sec, 'Gateway', self._gateway)
            self._gateway_port = int(self.defaultOption(config, sec, 'ToGatewayPort', self._gateway_port))

        except ConfigParser.NoOptionError as e:
            print('Using a default value:', e)
        except:
            traceback.print_exc()
            sys.exit('Configuration file \'' + configFileName + '\' is not a valid configuration file! Exiting...')

    # ************************************************
    #  CALLBACK FUNCTIONS FOR USER PACKET TYPES
    # ************************************************
    def group_voice(self, _src_id, _dst_id, _ts, _end, _peerId, _rtp, _data):
        _tx_slot = self.tlv_ipsc.tx[_ts]
        _payload_type = _data[30:31]
        _seq = int_id(_data[20:22])
        _tx_slot.frame_count += 1

        if _payload_type == BURST_DATA_TYPE['VOICE_HEADER']:
            _stream_id = int_id(_data[5:6])           # int8  looks like a sequence number for a packet
            if (_stream_id != _tx_slot.stream_id):
                self.tlv_ipsc.begin_group_call(_ts, _src_id, _dst_id, _peerId, self.cc, _seq, _stream_id)
            _tx_slot.lastSeq = _seq

        if _payload_type == BURST_DATA_TYPE['PI_HEADER']:
            _stream_id = int_id(_data[5:6])           # int8  looks like a sequence number for a packet
            _alg_id = int_id(_data[38:39])
            _key_id = int_id(_data[40:41])
            _mi = BitArray('0x' + h(_data[41:44]))
            if (_stream_id == _tx_slot.stream_id):
                self.tlv_ipsc.pi_params(_ts, _dst_id, _alg_id, _key_id, _mi.tobytes())

        if _payload_type == BURST_DATA_TYPE['VOICE_TERMINATOR']:
            self.tlv_ipsc.end_call(_tx_slot)

        if (_payload_type == BURST_DATA_TYPE['SLOT1_VOICE']) or (_payload_type == BURST_DATA_TYPE['SLOT2_VOICE']):
            _ambe_frames = BitArray('0x' + h(_data[33:52]))
            _ambe_frame1 = _ambe_frames[0:49]
            _ambe_frame2 = _ambe_frames[50:99]
            _ambe_frame3 = _ambe_frames[100:149]
            self.tlv_ipsc.export_voice(_tx_slot, _seq, _ambe_frame1.tobytes() + _ambe_frame2.tobytes() + _ambe_frame3.tobytes())
        pass

    def private_voice(self, _src_id, _dst_id, _ts, _end, _peerId, _rtp, _data):
        _tx_slot = self.tlv_ipsc.tx[_ts]
        _payload_type = _data[30:31]
        _seq = int_id(_data[20:22])
        _tx_slot.frame_count += 1

        # TODO TODO

        pass

# ---------------------------------------------------------------------------
#   Program Entry Point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse
    import os
    import sys
    import signal
    from fne.fne_core import mk_id_dict

    from ipsc.dmrlink_log import config_logging    
    from ipsc.dmrlink_config import build_config
    
    # Change the current directory to the location of the application
    os.chdir(os.path.dirname(os.path.realpath(sys.argv[0])))

    # CLI argument parser - handles picking up the config file from the command line, and sending a "help" message
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', action='store', dest='ConfigFile', help='/full/path/to/config.file (usually dmrlink.cfg)')
    parser.add_argument('-b', '--bridge', action = 'store', dest = 'BridgeFile', help = '/full/path/to/dmrlink_ipsc_bridge.cfg')
    parser.add_argument('-l', '--log_level', action='store', dest='LogLevel', help='Override config file logging level.')
    cli_args = parser.parse_args()

    if not cli_args.ConfigFile:
        cli_args.ConfigFile = os.path.dirname(os.path.abspath(__file__)) + '/dmrlink.cfg'
    if not cli_args.BridgeFile:
        cli_args.BridgeFile = os.path.dirname(os.path.abspath(__file__)) + '/dmrlink_ipsc_bridge.cfg'
    
    # Call the external routine to build the configuration dictionary
    config = build_config(cli_args.ConfigFile)
    
    # Call the external routing to start the system logger
    if cli_args.LogLevel:
        config['Log']['LogLevel'] = cli_args.LogLevel

    logger = config_logging(config['Log'])  

    logger.debug('Logging system started, anything from here on gets logged')
    logger.info('Digital Voice Modem IPSC -> FNE Bridge Service D01.00')

    observer = log.PythonLoggingObserver()
    observer.start()

    # Make Dictionaries
    white_rids = mk_id_dict(config['Aliases']['Path'], config['Aliases']['WhitelistRIDsFile'])
    if white_rids:
        logger.info('ID MAPPER: white_rids dictionary is available')

    black_rids = mk_id_dict(config['Aliases']['Path'], config['Aliases']['BlacklistRIDsFile'])
    if black_rids:
        logger.info('ID MAPPER: black_rids dictionary is available')
    
    # Shut ourselves down gracefully with the IPSC peers.
    def sig_handler(_signal, _frame):
        logger.info('*** DMRLINK IS TERMINATING WITH SIGNAL %s ***', str(_signal))
    
        for system in systems:
            this_ipsc = systems[system]
            logger.info('De-Registering from IPSC %s', system)
            de_reg_req_pkt = this_ipsc.hashed_packet(this_ipsc._local['AuthKey'], this_ipsc.DE_REG_REQ_PKT)
            this_ipsc.send_to_ipsc(de_reg_req_pkt)
        reactor.stop()

    # Set signal handers so that we can gracefully exit if need be
    for sig in [signal.SIGTERM, signal.SIGINT, signal.SIGQUIT]:
        signal.signal(sig, sig_handler)

    # setup the reporting loop
    report_server = config_reports(config, logger, reportFactory)

    # IPSC instance creation
    for system in config['Systems']:
        if config['Systems'][system]['LOCAL']['Enabled']:
            systems[system] = bridgeIPSC(system, config, cli_args.BridgeFile, logger, report_server)
            reactor.listenUDP(config['Systems'][system]['LOCAL']['PORT'], systems[system], interface = config['Systems'][system]['LOCAL']['IP'])
            logger.debug('Instance created: %s, %s', system, systems[system])
    
    reactor.run()
