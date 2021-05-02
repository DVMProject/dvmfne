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
#   Copyright (C) 2017-2021 Bryan Biedenkapp <gatekeep@gmail.com>
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
from __future__ import print_function

import sys
import struct
import sys
import socket
import ConfigParser
import thread
import traceback

from bitarray import bitarray
from bitstring import BitArray
from bitstring import BitString
from time import time, sleep
from importlib import import_module
from binascii import b2a_hex as ahex
from random import randint
from threading import Lock
from time import time, sleep, clock, localtime, strftime

from twisted.python import log
from twisted.internet.protocol import Factory, Protocol
from twisted.protocols.basic import NetstringReceiver
from twisted.internet import reactor, task

from fne.fne_core import hex_str_3, int_id, coreFNE, systems, fne_shutdown_handler, REPORT_OPCODES, reportFactory, config_reports, setup_activity_log
from fne import fne_config, fne_log, fne_const

from dmr_utils.tlv import tlvFNE
from dmr_utils import decode, bptc, const, golay, qr, ambe_utils

# ---------------------------------------------------------------------------
#   Class Declaration
#     This implements the IPSC bridge network FNE logic.
# ---------------------------------------------------------------------------

class bridgeFNE(coreFNE):
    def __init__(self, _name, _config, _bridge_config, _logger, _act_log_file, _report):
        coreFNE.__init__(self, _name, _config, _logger, _act_log_file, _report)

        self._tlvPort = 31003                               # Port to listen on for TLV frames to transmit to all peers
        self._gateway = "127.0.0.1"                         # IP address of bridge app
        self._gateway_port = 31000                          # Port bridge is listening on for TLV frames to decode

        self.load_configuration(_bridge_config)

        self.tlv_fne = tlvFNE(self, _name, _config, _logger, self._tlvPort)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def dmrd_validate(self, _peer_id, _rf_src, _dst_id, _slot, _call_type, _frame_type, _dtype_vseq, _stream_id):
        return True

    # Callback with DMR data from peer/master.  Send this data to any
    # partner listening
    def dmrd_received(self, _peer_id, _rf_src, _dst_id, _seq, _slot, _call_type, _frame_type, _dtype_vseq, _stream_id, _data):
        dmrpkt = _data[20:53]
        _tx_slot = self.tlv_fne.tx[_slot]
        _seq = ord(_data[4])
        _tx_slot.frame_count += 1

        if (_stream_id != _tx_slot.stream_id):
            self.tlv_fne.begin_call(_slot, True, _rf_src, _dst_id, _peer_id, _tx_slot.cc, _seq, _stream_id)
            _tx_slot.lastSeq = _seq

        if (_frame_type == fne_const.FT_DATA_SYNC) and (_dtype_vseq == fne_const.DT_VOICE_PI_HEADER):
            header = decode.decode_lc_header(dmrpkt)
            lc = header['LC']
            _alg_id = lc[0]
            _key_id = lc[2]
            _mi = lc[3:7]
            self.tlv_fne.pi_params(_slot, _dst_id, _alg_id, _key_id, _mi)

        if (_frame_type == fne_const.FT_DATA_SYNC) and (_dtype_vseq == fne_const.DT_TERMINATOR_WITH_LC) and (_tx_slot.type != fne_const.DT_TERMINATOR_WITH_LC):
            self.tlv_fne.end_call(_tx_slot)

        if (int_id(_data[15]) & 0x20) == 0:
            _dmr_frame = BitArray('0x' + ahex(_data[20:]))
            _ambe = _dmr_frame[0:108] + _dmr_frame[156:264]
            self.tlv_fne.export_voice(_tx_slot, _seq, _ambe.tobytes())
        else:
            _tx_slot.lastSeq = _seq

    def p25d_preprocess(self, _peer_id, _rf_src, _dst_id, _call_type, _duid, _dtype_vseq, _stream_id, _data):
        return

    def p25d_validate(self, _peer_id, _rf_src, _dst_id, _call_type, _duid, _dtype_vseq, _stream_id):
        return False

    def p25d_received(self, _peer_id, _rf_src, _dst_id, _call_type, _duid, _dtype_vseq, _stream_id, _data):
        return

    def peer_ignored(self, _peer_id, _rf_src, _dst_id, _call_type, _slot, _dtype_vseq, _stream_id, _is_source):
        return False

    def peer_connected(self, _peer_id, _peer):
        return

    def get_peer_id(self, import_id):
        if self._config['Mode'] == 'peer': # only peers have PeerId defined, masters do not
            return self._config['PeerId']
        return import_id

    # Load configuration from file
    def load_configuration(self, _file_name):
        config = ConfigParser.ConfigParser()
        if not config.read(_file_name):
            sys.exit('Configuration file \'' + _file_name + '\' is not a valid configuration file! Exiting...')
        try:
            for section in config.sections():
                if section == 'BridgeGlobal':
                    self._tlvPort = int(config.get(section, 'FromGatewayPort').split(None)[0])    # Port to listen on for AMBE frames to transmit to all peers
                    self._gateway = config.get(section, 'Gateway').split(None)[0]                 # IP address of bridge app
                    self._gateway_port = int(config.get(section, 'ToGatewayPort').split(None)[0]) # Port bridge is listening on for AMBE frames to decode

        except ConfigParser.Error, err:
            traceback.print_exc()
            sys.exit('Could not parse configuration file, ' + _file_name + ', exiting...')

    # The methods below are overridden becuse the launchUDP thread can also
    # wite to a master or peer async and confuse the master
    # A lock is used to synchronize the two threads so that the resource is
    # protected
    def send_master(self, _packet):
        mutex.acquire()
        coreFNE.send_master(self, _packet)
        mutex.release()
    
    def send_peers(self, _packet):
        mutex.acquire()
        coreFNE.send_peers(self, _packet)
        mutex.release()

# ---------------------------------------------------------------------------
#   Program Entry Point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse
    import os

    from fne.fne_core import mk_id_dict
    from fne.fne_core import setup_fne
    
    # perform basic FNE setup
    config, logger, act_log_file = setup_fne()
    logger.info('Digital Voice Modem FNE -> IPSC Bridge Service D01.00')

    # CLI argument parser - handles picking up the config file from the command
    # line, and sending a "help" message
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', action = 'store', dest = 'ConfigFile', help = '/full/path/to/config.file (usually fne.cfg)')
    parser.add_argument('-b', '--bridge', action = 'store', dest = 'BridgeFile', help = '/full/path/to/fne_bridge.cfg')
    parser.add_argument('-l', '--logging', action = 'store', dest = 'LogLevel', help = 'Override config file logging level.')
    cli_args = parser.parse_args()

    if not cli_args.BridgeFile:
        cli_args.BridgeFile = os.path.dirname(os.path.abspath(__file__)) + '/fne_bridge.cfg'

    # setup FNE report server
    report_server = config_reports(config, logger, reportFactory)
    
    # make dictionaries
    white_rids = mk_id_dict(config['Aliases']['Path'], config['Aliases']['WhitelistRIDsFile'])
    if white_rids:
        logger.info('ID MAPPER: white_rids dictionary is available')

    black_rids = mk_id_dict(config['Aliases']['Path'], config['Aliases']['WhitelistRIDsFile'])
    if black_rids:
        logger.info('ID MAPPER: black_rids dictionary is available')
    
    # FNE instance creation
    for system in config['Systems']:
        if config['Systems'][system]['Enabled']:
            systems[system] = bridgeFNE(system, config, cli_args.BridgeFile, logger, act_log_file, report_server)
            reactor.listenUDP(config['Systems'][system]['Port'], systems[system], interface = config['Systems'][system]['Address'])
            logger.debug('%s instance created: %s, %s', config['Systems'][system]['Mode'], system, systems[system])

    reactor.run()
