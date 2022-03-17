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

from bitarray import bitarray
from time import time, sleep
from importlib import import_module

from twisted.python import log
from twisted.internet.protocol import Factory, Protocol
from twisted.protocols.basic import NetstringReceiver
from twisted.internet import reactor, task

from fne.fne_core import coreFNE, systems, fne_shutdown_handler, REPORT_OPCODES, reportFactory, config_reports, setup_activity_log
from fne import fne_config, fne_log, fne_const

# ---------------------------------------------------------------------------
#   Class Declaration
#     This implements the parrot network FNE logic.
# ---------------------------------------------------------------------------

class parrotFNE(coreFNE):
    def __init__(self, _name, _config, _logger, _act_log_file, _report):
        coreFNE.__init__(self, _name, _config, _logger, _act_log_file, _report)
        
        # Status information for the system, TS1 & TS2
        # 1 & 2 are "timeslot"
        # In TX_EMB_LC, 2-5 are burst B-E
        self.STATUS = {
            1: {
                'RX_START':     time(),
                'RX_SEQ':       '\x00',
                'RX_RFS':       '\x00',
                'TX_RFS':       '\x00',
                'RX_STREAM_ID': '\x00',
                'TX_STREAM_ID': '\x00',
                'RX_TGID':      '\x00\x00\x00',
                'TX_TGID':      '\x00\x00\x00',
                'RX_TIME':      time(),
                'TX_TIME':      time(),
                'RX_TYPE':      fne_const.DT_TERMINATOR_WITH_LC,
                'RX_LC':        '\x00',
                'TX_H_LC':      '\x00',
                'TX_T_LC':      '\x00',
                'TX_EMB_LC': {
                    1: '\x00',
                    2: '\x00',
                    3: '\x00',
                    4: '\x00',
                }
                },
            2: {
                'RX_START':     time(),
                'RX_SEQ':       '\x00',
                'RX_RFS':       '\x00',
                'TX_RFS':       '\x00',
                'RX_STREAM_ID': '\x00',
                'TX_STREAM_ID': '\x00',
                'RX_TGID':      '\x00\x00\x00',
                'TX_TGID':      '\x00\x00\x00',
                'RX_TIME':      time(),
                'TX_TIME':      time(),
                'RX_TYPE':      fne_const.DT_TERMINATOR_WITH_LC,
                'RX_LC':        '\x00',
                'TX_H_LC':      '\x00',
                'TX_T_LC':      '\x00',
                'TX_EMB_LC': {
                    1: '\x00',
                    2: '\x00',
                    3: '\x00',
                    4: '\x00',
                }
            }
        }
        self.CALL_DATA = []
        self.LAST_MODE = 'DMR'

    def dmrd_validate(self, _peer_id, _rf_src, _dst_id, _slot, _call_type, _frame_type, _dtype_vseq, _stream_id):
        return True

    def dmrd_received(self, _peer_id, _rf_src, _dst_id, _seq, _slot, _call_type, _frame_type, _dtype_vseq, _stream_id, _data):
        pkt_time = time()
        dmrpkt = _data[20:53]
        _bits = _data[15]
        
        if _call_type == 'group':
            if (self.LAST_MODE != 'DMR'):
                self._logger.info('(%s) DMRD: Previous call was not DMR, mixed call modes! Dropping call data.', self._system)
                self.CALL_DATA = []

            if (_rf_src == 0):
                self._logger.warning('(%s) DMRD: Received call from SRC_ID %s? Dropping call data.', self._system, _rf_src)
                self.CALL_DATA = []
                self.LAST_MODE = 'P25'
                return

            self.LAST_MODE = 'DMR'

            # Is this is a new call stream?
            if (_stream_id != self.STATUS[_slot]['RX_STREAM_ID']):
                self.STATUS['RX_START'] = pkt_time
                self._logger.info('(%s) DMRD: Traffic *CALL START     * PEER %s SRC_ID %s TGID %s TS %s [STREAM ID %s]', self._system,
                                  _peer_id, _rf_src, _dst_id, _slot, _stream_id)
            
            # Final actions - Is this a voice terminator?
            if (_frame_type == fne_const.FT_DATA_SYNC) and (_dtype_vseq == fne_const.DT_TERMINATOR_WITH_LC) and (self.STATUS[_slot]['RX_TYPE'] != fne_const.DT_TERMINATOR_WITH_LC):
                call_duration = pkt_time - self.STATUS['RX_START']
                self._logger.info('(%s) DMRD: Traffic *CALL END       * PEER %s SRC_ID %s TGID %s TS %s DUR %s [STREAM ID %s]', self._system,
                                  _peer_id, _rf_src, _dst_id, _slot, call_duration, _stream_id)
                self.CALL_DATA.append(_data)
                sleep(2)
                self._logger.info('(%s) DMRD: Playing back transmission from SRC_ID %s', self._system, _rf_src)
                for _peer in self.CALL_DATA:
                    self.send_peers(_peer)
                    sleep(0.06)
                self.CALL_DATA = []
            
            else:
                if not self.CALL_DATA:
                    self._logger.info('(%s) DMRD: Receiving transmission to be played back from SRC_ID %s', self._system, _rf_src)
                self.CALL_DATA.append(_data)
            
            # Mark status variables for use later
            self.STATUS[_slot]['RX_RFS'] = _rf_src
            self.STATUS[_slot]['RX_TYPE'] = _dtype_vseq
            self.STATUS[_slot]['RX_TGID'] = _dst_id
            self.STATUS[_slot]['RX_TIME'] = pkt_time
            self.STATUS[_slot]['RX_STREAM_ID'] = _stream_id

    def p25d_preprocess(self, _peer_id, _rf_src, _dst_id, _call_type, _duid, _dtype_vseq, _stream_id, _data):
        return

    def p25d_validate(self, _peer_id, _rf_src, _dst_id, _call_type, _duid, _dtype_vseq, _stream_id):
        return True

    def p25d_received(self, _peer_id, _rf_src, _dst_id, _call_type, _duid, _dtype_vseq, _stream_id, _data):
        pkt_time = time()
        p25pkt = _data[24:178]
        _slot = 1               # fake the slot data, P25 doesn't have this

        if _call_type == 'group':
            if (self.LAST_MODE != 'P25'):
                self._logger.info('(%s) P25D: Previous call was not P25, mixed call modes! Dropping call data.', self._system)
                self.CALL_DATA = []

            if (_rf_src == 0):
                self._logger.warning('(%s) P25D: Received call from SRC_ID %s? Dropping call data.', self._system, _rf_src)
                self.CALL_DATA = []
                self.LAST_MODE = 'P25'
                return

            self.LAST_MODE = 'P25'

            # Is this is a new call stream?
            if (_stream_id != self.STATUS[_slot]['RX_STREAM_ID']) and ((_duid != fne_const.P25_DUID_TDU) and (_duid != fne_const.P25_DUID_TDULC)):
                self.STATUS['RX_START'] = pkt_time
                self._logger.info('(%s) P25D: Traffic *CALL START    * PEER %s SRC_ID %s TGID %s [STREAM ID %s]', self._system,
                                  _peer_id, _rf_src, _dst_id, _stream_id)
        
            # Final actions - Is this a voice terminator?
            if ((_duid == fne_const.P25_DUID_TDU) or (_duid == fne_const.P25_DUID_TDULC)) and (self.STATUS[_slot]['RX_TYPE'] != fne_const.DT_TERMINATOR_WITH_LC):
                call_duration = pkt_time - self.STATUS['RX_START']
                self._logger.info('(%s) P25D: Traffic *CALL END      * PEER %s SRC_ID %s TGID %s DUR %s [STREAM ID %s]', self._system,
                                  _peer_id, _rf_src, _dst_id, call_duration, _stream_id)
                self.CALL_DATA.append(_data)
                sleep(2)
                self._logger.info('(%s) P25D: Playing back transmission from SRC_ID %s', self._system, _rf_src)
                for _peer in self.CALL_DATA:
                    self.send_peers(_peer)
                    sleep(0.06)
                self.CALL_DATA = []
            
            else:
                if not self.CALL_DATA:
                    self._logger.info('(%s) P25D: Receiving transmission to be played back from SRC_ID %s', self._system, _rf_src)
                self.CALL_DATA.append(_data)
            
            # Mark status variables for use later
            self.STATUS[_slot]['RX_RFS'] = _rf_src
            self.STATUS[_slot]['RX_TYPE'] = _dtype_vseq
            self.STATUS[_slot]['RX_TGID'] = _dst_id
            self.STATUS[_slot]['RX_TIME'] = pkt_time
            self.STATUS[_slot]['RX_STREAM_ID'] = _stream_id

    def peer_ignored(self, _peer_id, _rf_src, _dst_id, _call_type, _slot, _dtype_vseq, _stream_id, _is_source):
        return False

    def peer_connected(self, _peer_id, _peer):
        return

# ---------------------------------------------------------------------------
#   Program Entry Point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    from fne.fne_core import mk_id_dict
    from fne.fne_core import setup_fne
    
    # perform basic FNE setup
    config, logger, act_log_file = setup_fne()
    logger.info('Digital Voice Modem Parrot Service D01.00')

    # setup FNE report server
    report_server = config_reports(config, logger, reportFactory)
    
    # make dictionaries
    white_rids = mk_id_dict(config['Aliases']['Path'], config['Aliases']['WhitelistRIDsFile'])
    if white_rids:
        logger.info('ID MAPPER: white_rids dictionary is available')

    # FNE instance creation
    logger.info('Parrot FNE - SYSTEM STARTING...')
    for system in config['Systems']:
        if config['Systems'][system]['Enabled']:
            systems[system] = parrotFNE(system, config, logger, act_log_file, report_server)
            reactor.listenUDP(config['Systems'][system]['Port'], systems[system], interface = config['Systems'][system]['Address'])
            logger.debug('%s instance created: %s, %s', config['Systems'][system]['Mode'], system, systems[system])

    reactor.run()
