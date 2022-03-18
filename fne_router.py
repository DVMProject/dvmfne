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
#   Copyright (C) 2022 Natalie Moore <natalie@natnat.xyz>
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

import sys, traceback
import pickle

from binascii import b2a_hex as ahex
from bitarray import bitarray
from time import time
from importlib import import_module

from twisted.python import log
from twisted.internet.protocol import Factory, Protocol
from twisted.protocols.basic import NetstringReceiver
from twisted.internet import reactor, task

from fne.fne_core import int_to_bytes, short_to_bytes, bytes_to_int, coreFNE, systems, fne_shutdown_handler, REPORT_OPCODES, reportFactory, config_reports, setup_activity_log
from fne import fne_config, fne_log, fne_const

from dmr_utils import lc, bptc, const

# ---------------------------------------------------------------------------
#   Module Routines
# ---------------------------------------------------------------------------

def get_valid(_id, _dict):
    if _id in _dict:
        return True
    else:
        return False
    return False

def get_valid_ignore(_peer_id, _id, _dict):
    if _id in _dict:
        if _peer_id in _dict[_id]:
            return True
        else:
            if len(_dict[_id]) > 0:
                if _dict[_id][0] == 0:
                    return True
            return False
    else:
        return False
    return False

# Import bridging rules
# Note: A stanza *must* exist for any MASTER or PEER configured in the main
# configuration file and listed as "active".  It can be empty,
# but it has to exist.
def make_rules(_fne_routing_rules):
    global RULES, rule_file
    try:
        if _fne_routing_rules not in sys.modules: 
            rule_file = import_module(_fne_routing_rules)
            #logger.info('Routing rules file found and rules imported')
        else:
            rule_file = reload(rule_file)
            #logger.info('Routing rules file found and rules reloaded')
    except:
        logger.error('Routing rules file not found or invalid')
        return RULES
    
    # Convert integer GROUP ID numbers from the config into hex strings
    # we need to send in the actual data packets.
    for _system in rule_file.RULES:
        if _system not in config['Systems']:
            logger.error('Routing rules found for system %s, not configured main configuration', _system)
            continue

        config['Systems'][_system]['ACTIVE_TG_IDS'] = {}
        config['Systems'][_system]['DEACTIVE_TG_IDS'] = {}
        config['Systems'][_system]['TG_IGNORE_IDS'] = {}
        config['Systems'][_system]['TG_ALLOW_AFF'] = []

        for _rule in rule_file.RULES[_system]['GROUP_VOICE']:
            _rule['SRC_TS'] = _rule['SRC_TS']
            _rule['DST_TS'] = _rule['DST_TS']

            if rule_file.RULES[_system]['SEND_TGID'] == True:
                if _rule['ACTIVE'] == True:
                    config['Systems'][_system]['ACTIVE_TG_IDS'][_rule['SRC_GROUP']] = (_rule['NAME'], _rule['SRC_TS'])
                else:
                    config['Systems'][_system]['DEACTIVE_TG_IDS'][_rule['SRC_GROUP']] = (_rule['NAME'], _rule['SRC_TS'])

            config['Systems'][_system]['TG_IGNORE_IDS'][_rule['SRC_GROUP']] = [int(x) for x in _rule['IGNORED']]
            if _rule['AFFILIATED'] == True:
                config['Systems'][_system]['TG_ALLOW_AFF'].append(_rule['SRC_GROUP'])

            for i, e in enumerate(_rule['ON']):
                _rule['ON'][i] = _rule['ON'][i]
            
            for i, e in enumerate(_rule['OFF']):
                _rule['OFF'][i] = _rule['OFF'][i]
            
            _rule['TIMEOUT'] = _rule['TIMEOUT'] * 60
            _rule['TIMER'] = time() + _rule['TIMEOUT']

            # if we're reloading rules lets restore states
            if RULES:
                for _loaded_rule in RULES[_system]['GROUP_VOICE']:
                    if _loaded_rule['NAME'] == _rule['NAME']:
                        _rule['ROUTABLE'] = _loaded_rule['ROUTABLE']
                        _rule['TO_TYPE'] = _loaded_rule['TO_TYPE']
                        _rule['TIMER'] = _loaded_rule['TIMER']
                        break

            logger.info('Rule (%s) NAME: %s SRC_TGID: %s DST_TGID: %s SRC_TS: %s DST_TS: %s ACTIVE: %s ROUTABLE: %s TO_TYPE: %s AFFILIATED: %s IGNORED: %s', _system, _rule['NAME'], _rule['SRC_GROUP'], _rule['DST_GROUP'], _rule['SRC_TS'], _rule['DST_TS'], _rule['ACTIVE'], _rule['ROUTABLE'], _rule['TO_TYPE'], _rule['AFFILIATED'], _rule['IGNORED'])

    for _system in config['Systems']:
        if _system not in rule_file.RULES:
            logger.error('Routing rules not found for system %s', _system)
    return rule_file.RULES

# Run this every minute for rule timer updates
def rule_timer_loop():
    _now = time()
    for _system in RULES:
        for _rule in RULES[_system]['GROUP_VOICE']:
            if _rule['ACTIVE'] == False:
                continue
            if _rule['TO_TYPE'] == 'ON':
                if _rule['ROUTABLE'] == True:
                    if _rule['TIMER'] < _now:
                        _rule['ROUTABLE'] = False
                        logger.info('(%s) TG Routing timeout DEACTIVATE routing name %s, Target %s, TS %s, TGID %s',  _system, _rule['NAME'], _rule['DST_NET'], _rule['DST_TS'], _rule['DST_GROUP'])
                    else:
                        timeout_in = _rule['TIMER'] - _now
                        logger.info('(%s) TG Routing ACTIVE with ON timer running Timeout eligible in %ds, Rule name %s, Target %s, TS %s, TGID %s', _system, timeout_in, _rule['NAME'], _rule['DST_NET'], _rule['DST_TS'], _rule['DST_GROUP'])
            elif _rule['TO_TYPE'] == 'OFF':
                if _rule['ROUTABLE'] == False:
                    if _rule['TIMER'] < _now:
                        _rule['ROUTABLE'] = True
                        logger.info('(%s) TG Routing timeout ACTIVATE Rule name %s, Target %s, TS %s, TGID %s', _system, _rule['NAME'], _rule['DST_NET'], _rule['DST_TS'], _rule['DST_GROUP'])
                    else:
                        timeout_in = _rule['TIMER'] - _now
                        logger.info('(%s) TG Routing DEACTIVATE with OFF timer running Timeout eligible in %ds, Rule name %s, Target %s, TS %s, TGID %s', _system, timeout_in, _rule['NAME'], _rule['DST_NET'], _rule['DST_TS'], _rule['DST_GROUP'])
            else:
                logger.debug('Routable rule timer loop made no rule changes')

# ---------------------------------------------------------------------------
#   Class Declaration
#     This implements the router network FNE logic.
# ---------------------------------------------------------------------------

class routerFNE(coreFNE):
    def __init__(self, _name, _config, _logger, _act_log_file, _report):
        coreFNE.__init__(self, _name, _config, _logger, _act_log_file, _report)
        
        # Status information for the system, TS1 & TS2
        # 1 & 2 are "timeslot"
        # In TX_EMB_LC, 2-5 are burst B-E
        self.STATUS = {
            1: {
                'RX_START':     time(),
                'RX_PEER_ID':   0,
                'RX_SEQ':       0,
                'RX_RFS':       0,
                'TX_RFS':       0,
                'RX_STREAM_ID': 0,
                'TX_STREAM_ID': 0,
                'RX_TGID':      0,
                'TX_TGID':      0,
                'TX_PI_TGID':   0,
                'RX_TIME':      time(),
                'TX_TIME':      time(),
                'RX_TYPE':      fne_const.DT_TERMINATOR_WITH_LC,
                'RX_LC':        0,
                'RX_PI_LC':     0,
                'TX_H_LC':      0,
                'TX_P_LC':      0,
                'TX_T_LC':      0,
                'TX_EMB_LC': {
                    1: 0,
                    2: 0,
                    3: 0,
                    4: 0,
                    },
                'P25_RX_CT':    'group'
                },
            2: {
                'RX_START':     time(),
                'RX_PEER_ID':   0,
                'RX_SEQ':       0,
                'RX_RFS':       0,
                'TX_RFS':       0,
                'RX_STREAM_ID': 0,
                'TX_STREAM_ID': 0,
                'RX_TGID':      0,
                'TX_TGID':      0,
                'TX_PI_TGID':   0,
                'RX_TIME':      time(),
                'TX_TIME':      time(),
                'RX_TYPE':      fne_const.DT_TERMINATOR_WITH_LC,
                'RX_LC':        0,
                'RX_PI_LC':     0,
                'TX_H_LC':      0,
                'TX_P_LC':      0,
                'TX_T_LC':      0,
                'TX_EMB_LC': {
                    1: 0,
                    2: 0,
                    3: 0,
                    4: 0,
                    },
                'P25_RX_CT':    'group'
                }
            }

        rid_tid_update_timer = task.LoopingCall(self.rid_tid_update_loop)
        rid_tid_update_timer.start(240)

    def dmrd_validate(self, _peer_id, _rf_src, _dst_id, _slot, _call_type, _frame_type, _dtype_vseq, _stream_id):
        pkt_time = time()

        if get_valid(_rf_src, black_rids) == True:
            if (_stream_id != self.STATUS[_slot]['RX_STREAM_ID']):
                # Mark status variables for use later
                self.STATUS[_slot]['RX_START'] = pkt_time
                self.STATUS[_slot]['RX_PEER_ID'] = _peer_id
                self.STATUS[_slot]['RX_RFS'] = _rf_src
                self.STATUS[_slot]['RX_TYPE'] = _dtype_vseq
                self.STATUS[_slot]['RX_TGID'] = _dst_id
                self.STATUS[_slot]['RX_STREAM_ID'] = _stream_id
                self._logger.warning('(%s) DMRD: Traffic *REJECT ACL      * PEER %s SRC_ID %s DST_ID %s [STREAM ID %s] (Blacklisted RID)', self._system,
                                     _peer_id, _rf_src, _dst_id, _stream_id)
                
                if config['Reports']['Report']:
                    self._report.send_routeEvent('REJECT ACL,BLACKLISTED RID,DMR,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, _slot, _dst_id))
            return False

        # Always validate a terminator if the source is valid
        if (_frame_type == fne_const.FT_DATA_SYNC) and (_dtype_vseq == fne_const.DT_TERMINATOR_WITH_LC):
            return True
        
        if _call_type == 'group':
            if (RULES[self._system]['SEND_TGID'] == True) and (get_valid(_dst_id, config['Systems'][self._system]['ACTIVE_TG_IDS']) == False):
                if (_stream_id != self.STATUS[_slot]['RX_STREAM_ID']):
                    # Mark status variables for use later
                    self.STATUS[_slot]['RX_START'] = pkt_time
                    self.STATUS[_slot]['RX_PEER_ID'] = _peer_id
                    self.STATUS[_slot]['RX_RFS'] = _rf_src
                    self.STATUS[_slot]['RX_TYPE'] = _dtype_vseq
                    self.STATUS[_slot]['RX_TGID'] = _dst_id
                    self.STATUS[_slot]['RX_STREAM_ID'] = _stream_id
                    self._logger.warning('(%s) DMRD: Traffic *REJECT ACL      * PEER %s SRC_ID %s DST_ID %s [STREAM ID %s] (Illegal TGID)', self._system,
                                         _peer_id, _rf_src, _dst_id, _stream_id)
            
                    if config['Reports']['Report']:
                        self._report.send_routeEvent('REJECT ACL,ILLEGAL TGID,DMR,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, _slot, _dst_id))
                return False

        return True

    def dmrd_received(self, _peer_id, _rf_src, _dst_id, _seq, _slot, _call_type, _frame_type, _dtype_vseq, _stream_id, _data):
        pkt_time = time()
        dmrpkt = _data[20:53]
        _bits = _data[15]

        if ((_frame_type == fne_const.FT_DATA_SYNC) and ((_dtype_vseq == fne_const.DT_DATA_HEADER) or (_dtype_vseq == fne_const.DT_RATE_12_DATA) or
                                                         (_dtype_vseq == fne_const.DT_RATE_34_DATA) or (_dtype_vseq == fne_const.DT_RATE_1_DATA))):
            self._logger.info('(%s) DMRD: Traffic *DATA            * PEER %s SRC_ID %s DST_ID %s [STREAM ID %s]', self._system,
                              _peer_id, _rf_src, _dst_id, _stream_id)
            
            if config['Reports']['Report']:
                self._report.send_routeEvent('PDU,DATA,DMR,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, _slot, _dst_id))
            return

        if _call_type == 'group':
            # Is this a new call stream?
            if (_stream_id != self.STATUS[_slot]['RX_STREAM_ID']):
                if (self.STATUS[_slot]['RX_TYPE'] != fne_const.DT_TERMINATOR_WITH_LC) and (pkt_time < (self.STATUS[_slot]['RX_TIME'] + fne_const.STREAM_TO)) and (_rf_src != self.STATUS[_slot]['RX_RFS']):
                    self._logger.warning('(%s) DMRD: Traffic *CALL COLLISION  * PEER %s SRC_ID %s TGID %s TS %s [STREAM ID %s] (Collided with existing call)', self._system,
                                         _peer_id, _rf_src, _dst_id, _slot, _stream_id)
                    
                    if config['Reports']['Report']:
                        self._report.send_routeEvent('GROUP VOICE,CALL COLLISION,DMR,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, _slot, _dst_id))
                    return
                
                # This is a new call stream
                self.STATUS[_slot]['RX_START'] = pkt_time
                self._logger.info('(%s) DMRD: Traffic *CALL START      * PEER %s SRC_ID %s TGID %s TS %s [STREAM ID %s]', self._system,
                                  _peer_id, _rf_src, _dst_id, _slot, _stream_id)

                if config['Reports']['Report']:
                    self._report.send_routeEvent('GROUP VOICE,START,DMR,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, _slot, _dst_id))

                # If we can, use the LC from the voice header as to keep all
                # options intact
                if _frame_type == fne_const.FT_DATA_SYNC and _dtype_vseq == fne_const.DT_VOICE_LC_HEADER:
                    lcHeader = lc.decode_lc_header(dmrpkt)
                    self.STATUS[_slot]['RX_LC'] = lcHeader['LC'][:9]
                
                # If we don't have a voice header then don't wait to decode it
                # from the Embedded LC
                # just make a new one from the HBP header.  This is good
                # enough, and it saves lots of time
                else:
                    self.STATUS[_slot]['RX_LC'] = const.LC_OPT + short_to_bytes(_dst_id) + short_to_bytes(_rf_src)

                self.STATUS[_slot]['RX_PI_LC'] = const.LC_PI_OPT + b'\x00\x00\x00' + b'\x00\x00'
                self._logger.debug('(%s) TS %s [STREAM ID %s] RX_LC %s', self._system, _slot, _stream_id, ahex(self.STATUS[_slot]['RX_LC']))

            # If we can, use the PI LC from the PI voice header as to keep all
            # options intact
            if _frame_type == fne_const.FT_DATA_SYNC and _dtype_vseq == fne_const.DT_VOICE_PI_HEADER:
                lcHeader = lc.decode_lc_header(dmrpkt)
                _alg_id = lcHeader['LC'][0]
                _key_id = lcHeader['LC'][2]
                self._logger.info('(%s) DMRD: Traffic *CALL PI PARAMS  * PEER %s DST_ID %s TS %s ALGID %s KID %s [STREAM ID %s]', self._system,
                                        _peer_id, _dst_id, _slot, _alg_id, _key_id, _stream_id)

                self.STATUS[_slot]['RX_PI_LC'] = lcHeader['LC'][:10]

                self._logger.debug('(%s) TS %s [STREAM ID %s] RX_PI_LC %s', self._system, _slot, _stream_id, ahex(self.STATUS[_slot]['RX_PI_LC']))

            for rule in RULES[self._system]['GROUP_VOICE']:
                _target = rule['DST_NET']

                # skip if the target doesn't exist
                if not (_target in systems):
                    continue

                _target_status = systems[_target].STATUS
                
                if (rule['SRC_GROUP'] == _dst_id and rule['SRC_TS'] == _slot and rule['ACTIVE'] == True and rule['ROUTABLE'] == True):
                    
                    # BEGIN CONTENTION HANDLING
                    #
                    # The rules for each of the 4 "ifs" below are listed here
                    # for readability.  The Frame To Send is:
                    #   From a different group than last RX from this system,
                    #   but it has been less than Group Hangtime
                    #   From a different group than last TX to this system,
                    #   but it has been less than Group Hangtime
                    #   From the same group as the last RX from this system,
                    #   but from a different subscriber, and it has been less
                    #   than stream timeout
                    #   From the same group as the last TX to this system,
                    #   but from a different subscriber, and it has been less
                    #   than stream timeout
                    # The "continue" at the end of each means the next
                    # iteration of the for loop that tests for matching rules
                    #
                    if ((rule['DST_GROUP'] != _target_status[rule['DST_TS']]['RX_TGID']) and ((pkt_time - _target_status[rule['DST_TS']]['RX_TIME']) < RULES[_target]['GROUP_HANGTIME'])):
                        if _frame_type == fne_const.FT_DATA_SYNC and _dtype_vseq == fne_const.DT_VOICE_LC_HEADER:
                            self._logger.info('(%s) DMRD: Call not routed to TGID %s, target active or in group hangtime: PRID %s TS %s TGID %s', self._system,
                                              rule['DST_GROUP'], _target, rule['DST_TS'], _target_status[rule['DST_TS']]['RX_TGID'])

                            if config['Reports']['Report']:
                                self._report.send_routeEvent('CALL ROUTE,FAILED,DMR,{},{},{},{}'.format(self._system, _target, rule['DST_TS'], rule['DST_GROUP']))
                        continue    
                    if ((rule['DST_GROUP'] != _target_status[rule['DST_TS']]['TX_TGID']) and ((pkt_time - _target_status[rule['DST_TS']]['TX_TIME']) < RULES[_target]['GROUP_HANGTIME'])):
                        if _frame_type == fne_const.FT_DATA_SYNC and _dtype_vseq == fne_const.DT_VOICE_LC_HEADER:
                            self._logger.info('(%s) DMRD: Call not routed to TGID %s, target in group hangtime: PRID %s TS %s TGID %s', self._system,
                                              rule['DST_GROUP'], _target, rule['DST_TS'], _target_status[rule['DST_TS']]['TX_TGID'])
                            
                            if config['Reports']['Report']:
                                self._report.send_routeEvent('CALL ROUTE,FAILED,DMR,{},{},{},{}'.format(self._system, _target, rule['DST_TS'], rule['DST_GROUP']))
                        continue
                    if (rule['DST_GROUP'] == _target_status[rule['DST_TS']]['RX_TGID']) and ((pkt_time - _target_status[rule['DST_TS']]['RX_TIME']) < fne_const.STREAM_TO):
                        if _frame_type == fne_const.FT_DATA_SYNC and _dtype_vseq == fne_const.DT_VOICE_LC_HEADER:
                            self._logger.info('(%s) DMRD: Call not routed to TGID %s, matching call already active on target: PRID %s TS %s TGID %s', self._system,
                                              rule['DST_GROUP'], _target, rule['DST_TS'], _target_status[rule['DST_TS']]['RX_TGID'])

                            if config['Reports']['Report']:
                                self._report.send_routeEvent('CALL ROUTE,FAILED,DMR,{},{},{},{}'.format(self._system, _target, rule['DST_TS'], rule['DST_GROUP']))
                        continue
                    if (rule['DST_GROUP'] == _target_status[rule['DST_TS']]['TX_TGID']) and (_rf_src != _target_status[rule['DST_TS']]['TX_RFS']) and ((pkt_time - _target_status[rule['DST_TS']]['TX_TIME']) < fne_const.STREAM_TO):
                        if _frame_type == fne_const.FT_DATA_SYNC and _dtype_vseq == fne_const.DT_VOICE_LC_HEADER:
                            self._logger.info('(%s) DMRD: Call not routed for SUB %s, call route in progress on target: PRID %s TS %s TGID %s SUB %s', self._system,
                                              _rf_src, _target, rule['DST_TS'], _target_status[rule['DST_TS']]['TX_TGID'], _target_status[rule['DST_TS']]['TX_RFS'])

                            if config['Reports']['Report']:
                                self._report.send_routeEvent('CALL ROUTE,FAILED,DMR,{},{},{},{}'.format(self._system, _target, rule['DST_TS'], rule['DST_GROUP']))
                        continue

                    # Set values for the contention handler to test next time
                    # there is a frame to forward
                    _target_status[rule['DST_TS']]['TX_TIME'] = pkt_time
                    
                    if (_stream_id != self.STATUS[_slot]['RX_STREAM_ID']) or (_target_status[rule['DST_TS']]['TX_RFS'] != _rf_src) or (_target_status[rule['DST_TS']]['TX_TGID'] != rule['DST_GROUP']):
                        # Record the DST TGID and Stream ID
                        _target_status[rule['DST_TS']]['TX_TGID'] = rule['DST_GROUP']
                        _target_status[rule['DST_TS']]['TX_PI_TGID'] = 0
                        _target_status[rule['DST_TS']]['TX_STREAM_ID'] = _stream_id
                        _target_status[rule['DST_TS']]['TX_RFS'] = _rf_src

                        # Generate LCs (full and EMB) for the TX stream
                        dst_lc = self.STATUS[_slot]['RX_LC'][0:3] + short_to_bytes(rule['DST_GROUP']) + short_to_bytes(_rf_src)
                        _target_status[rule['DST_TS']]['TX_H_LC'] = bptc.encode_header_lc(dst_lc)
                        _target_status[rule['DST_TS']]['TX_T_LC'] = bptc.encode_terminator_lc(dst_lc)
                        _target_status[rule['DST_TS']]['TX_EMB_LC'] = bptc.encode_emblc(dst_lc)

                        dst_pi_lc = self.STATUS[_slot]['RX_PI_LC'][0:7] + rule['DST_GROUP'] + b'\x00\x00'
                        _target_status[rule['DST_TS']]['TX_P_LC'] = bptc.encode_header_pi(dst_pi_lc)

                        self._logger.debug('(%s) TS %s [STREAM ID %s] TX_H_LC %s', self._system, _slot, _stream_id, ahex(dst_lc))
                        self._logger.debug('(%s) TS %s [STREAM ID %s] TX_P_LC %s', self._system, _slot, _stream_id, ahex(dst_pi_lc))

                        self._logger.debug('(%s) DMR Packet DST TGID %s does not match SRC TGID %s - Generating FULL and EMB LCs', 
                                           self._system, rule['DST_GROUP'], _dst_id)
                        self._logger.info('(%s) DMRD: Call routed to SYSTEM %s TS %s TGID %s',
                                          self._system, _target, rule['DST_TS'], rule['DST_GROUP'])
                        if config['Reports']['Report']:
                            self._report.send_routeEvent('CALL ROUTE,TO,DMR,{},{},{},{}'.format(self._system, _target, rule['DST_TS'], rule['DST_GROUP']))

                    _pi_dst_id = self.STATUS[_slot]['RX_PI_LC'][7:10]
                    if (_pi_dst_id != 0) and (_target_status[rule['DST_TS']]['TX_PI_TGID'] != rule['DST_GROUP']):
                        # Record the DST TGID and Stream ID
                        _target_status[rule['DST_TS']]['TX_PI_TGID'] = rule['DST_GROUP']

                        # Generate LCs (full and EMB) for the TX stream
                        dst_pi_lc = self.STATUS[_slot]['RX_PI_LC'][0:7] + short_to_bytes(rule['DST_GROUP']) + b'\x00\x00'
                        _target_status[rule['DST_TS']]['TX_P_LC'] = bptc.encode_header_pi(dst_pi_lc)

                        self._logger.debug('(%s) TS %s [STREAM ID %s] TX_P_LC %s', self._system, _slot, _stream_id, ahex(dst_pi_lc))
                        self._logger.info('(%s) DMRD: Call PI parameters routed to SYSTEM %s TS %s TGID %s',
                                          self._system, _target, rule['DST_TS'], rule['DST_GROUP'])
                    
                    # Handle any necessary re-writes for the destination
                    if rule['SRC_TS'] != rule['DST_TS']:
                        _tmp_bits = _bits ^ 1 << 7
                    else:
                        _tmp_bits = _bits
                    
                    try:
                        _tgt_peer_id = self._CONFIG['Systems'][_target]['PeerId']
                    except KeyError:
                        _tgt_peer_id = self.STATUS[_slot]['RX_PEER_ID']

                    # somehow we've gotten a 0 for the peer ID -- so now we'll spoof the bitch
                    if (_tgt_peer_id == 0):
                        self._logger.warning('(%s) DMRD: Some how we got a 0 peer ID? This shouldn\'t happen, spoofing to %s',
                                            self._system, _peer_id)
                        _tgt_peer_id = _peer_id

                    _tmp_data = _data[:8] + short_to_bytes(rule['DST_GROUP']) + int_to_bytes(_tgt_peer_id) + chr(_tmp_bits) + _data[16:20]
                    
                    # MUST TEST FOR NEW STREAM AND IF SO, RE-WRITE THE LC FOR THE TARGET
                    # MUST RE-WRITE DESTINATION TGID IF DIFFERENT
                    # if _dst_id != rule['DST_GROUP']:
                    dmrbits = bitarray(endian='big')
                    dmrbits.frombytes(dmrpkt)
                    # Create a voice header packet (FULL LC)
                    if _frame_type == fne_const.FT_DATA_SYNC and _dtype_vseq == fne_const.DT_VOICE_LC_HEADER:
                        dmrbits = _target_status[rule['DST_TS']]['TX_H_LC'][0:98] + dmrbits[98:166] + _target_status[rule['DST_TS']]['TX_H_LC'][98:197]
                    # Create a voice PI header packet (FULL LC)
                    elif _frame_type == fne_const.FT_DATA_SYNC and _dtype_vseq == fne_const.DT_VOICE_PI_HEADER:
                        dmrbits = _target_status[rule['DST_TS']]['TX_P_LC'][0:98] + dmrbits[98:166] + _target_status[rule['DST_TS']]['TX_P_LC'][98:197]
                    # Create a voice terminator packet (FULL LC)
                    elif _frame_type == fne_const.FT_DATA_SYNC and _dtype_vseq == fne_const.DT_TERMINATOR_WITH_LC:
                        dmrbits = _target_status[rule['DST_TS']]['TX_T_LC'][0:98] + dmrbits[98:166] + _target_status[rule['DST_TS']]['TX_T_LC'][98:197]
                    # Create a Burst B-E packet (Embedded LC)
                    elif _dtype_vseq in [1,2,3,4]:
                        dmrbits = dmrbits[0:116] + _target_status[rule['DST_TS']]['TX_EMB_LC'][_dtype_vseq] + dmrbits[148:264]
                    dmrpkt = dmrbits.tobytes()
                    _tmp_data = _tmp_data + dmrpkt + _data[53:55]
                    
                    # Transmit the packet to the destination system
                    systems[_target].send_system(_tmp_data)
                    self._logger.debug('(%s) DMR Packet routed by rule %s to %s SYSTEM %s',
                                    self._system, rule['NAME'], self._CONFIG['Systems'][_target]['Mode'], _target)

            # Final actions - Is this a voice terminator?
            if (_frame_type == fne_const.FT_DATA_SYNC) and (_dtype_vseq == fne_const.DT_TERMINATOR_WITH_LC) and (self.STATUS[_slot]['RX_TYPE'] != fne_const.DT_TERMINATOR_WITH_LC):
                call_duration = pkt_time - self.STATUS[_slot]['RX_START']
                self._logger.info('(%s) DMRD: Traffic *CALL END        * PEER %s SRC_ID %s TGID %s TS %s DUR %s [STREAM ID: %s]', self._system,
                                  _peer_id, _rf_src, _dst_id, _slot, call_duration, _stream_id)

                if config['Reports']['Report']:
                    self._report.send_routeEvent('GROUP VOICE,END,DMR,{},{},{},{},{},{},{:.2f}'.format(self._system, _stream_id, _peer_id, _rf_src, _slot, _dst_id, call_duration))
                
                #
                # Begin in-band signalling for call end.  This has nothign to
                # do with routing traffic directly.
                #
                
                # Iterate the rules dictionary
                for rule in RULES[self._system]['GROUP_VOICE']:
                    _target = rule['DST_NET']
            
                    # TGID matches a rule source, reset its timer
                    if _slot == rule['SRC_TS'] and _dst_id == rule['SRC_GROUP'] and ((rule['TO_TYPE'] == 'ON' and (rule['ROUTABLE'] == True)) or (rule['TO_TYPE'] == 'OFF' and rule['ROUTABLE'] == False)):
                        rule['TIMER'] = pkt_time + rule['TIMEOUT']
                        self._logger.info('(%s) DMRD: Source group transmission match for rule %s. Reset timeout to %s', self._system, rule['NAME'], rule['TIMER'])
                
                        # Scan for reciprocal rules and reset their timers as
                        # well.
                        for target_rule in RULES[_target]['GROUP_VOICE']:
                            if target_rule['NAME'] == rule['NAME']:
                                target_rule['TIMER'] = pkt_time + target_rule['TIMEOUT']
                                self._logger.info('(%s) DMRD: Reciprocal group transmission match for rule %s on IPSC %s. Reset timeout to %s', self._system, target_rule['NAME'], _target, rule['TIMER'])
            
                    # TGID matches an ACTIVATION trigger
                    if _dst_id in rule['ON']:
                        # Set the matching rule as ROUTABLE
                        rule['ROUTABLE'] = True
                        rule['TIMER'] = pkt_time + rule['TIMEOUT']
                        self._logger.info('(%s) DMRD: Primary routing Rule %s changed to state: %s', self._system, rule['NAME'], rule['ROUTABLE'])
                
                        # Set reciprocal rules for other IPSCs as ROUTABLE
                        for target_rule in RULES[_target]['GROUP_VOICE']:
                            if target_rule['NAME'] == rule['NAME']:
                                target_rule['ROUTABLE'] = True
                                target_rule['TIMER'] = pkt_time + target_rule['TIMEOUT']
                                self._logger.info('(%s) DMRD: Reciprocal routing Rule %s in IPSC %s changed to state: %s', self._system, target_rule['NAME'], _target, rule['ROUTABLE'])
                        
                    # TGID matches an DE-ACTIVATION trigger
                    if _dst_id in rule['OFF']:
                        # Set the matching rule as ROUTABLE
                        rule['ROUTABLE'] = False
                        self._logger.info('(%s) DMRD: Routing Rule %s changed to state: %s', self._system, rule['NAME'], rule['ROUTABLE'])
                
                        # Set reciprocal rules for other IPSCs as ROUTABLE
                        _target = rule['DST_NET']
                        for target_rule in RULES[_target]['GROUP_VOICE']:
                            if target_rule['NAME'] == rule['NAME']:
                                target_rule['ROUTABLE'] = False
                                self._logger.info('(%s) DMRD: DMR Reciprocal routing Rule %s in IPSC %s changed to state: %s', self._system, target_rule['NAME'], _target, rule['ROUTABLE'])
                #
                # END IN-BAND SIGNALLING
                #
                
            # Mark status variables for use later
            self.STATUS[_slot]['RX_PEER_ID'] = _peer_id
            self.STATUS[_slot]['RX_RFS'] = _rf_src
            self.STATUS[_slot]['RX_TYPE'] = _dtype_vseq
            self.STATUS[_slot]['RX_TGID'] = _dst_id
            self.STATUS[_slot]['RX_TIME'] = pkt_time
            self.STATUS[_slot]['RX_STREAM_ID'] = _stream_id

        elif _call_type == 'unit':
            # Is this a new call stream?
            if (_stream_id != self.STATUS[_slot]['RX_STREAM_ID']):
                if (self.STATUS[_slot]['RX_TYPE'] != fne_const.DT_TERMINATOR_WITH_LC) and (pkt_time < (self.STATUS[_slot]['RX_TIME'] + fne_const.STREAM_TO)) and (_rf_src != self.STATUS[_slot]['RX_RFS']):
                    self._logger.warning('(%s) DMRD: Traffic *CALL COLLISION  * PEER %s SRC_ID %s DST_ID %s TS %s [STREAM ID %s] (Collided with existing call)', self._system,
                                         _peer_id, _rf_src, _dst_id, _slot, _stream_id)

                    if config['Reports']['Report']:
                        self._report.send_routeEvent('PRV VOICE,CALL COLLISION,DMR,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, _slot, _dst_id))
                    return
                
                # This is a new call stream
                self.STATUS[_slot]['RX_START'] = pkt_time
                self._logger.info('(%s) DMRD: Traffic *PRV CALL START  * PEER %s SRC_ID %s DST_ID %s TS %s [STREAM ID %s]', self._system,
                                  _peer_id, _rf_src, _dst_id, _slot, _stream_id)

                if config['Reports']['Report']:
                    self._report.send_routeEvent('PRV VOICE,START,DMR,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, _slot, _dst_id))

            # Final actions - Is this a voice terminator?
            if (_frame_type == fne_const.FT_DATA_SYNC) and (_dtype_vseq == fne_const.DT_TERMINATOR_WITH_LC) and (self.STATUS[_slot]['RX_TYPE'] != fne_const.DT_TERMINATOR_WITH_LC):
                call_duration = pkt_time - self.STATUS[_slot]['RX_START']
                self._logger.info('(%s) DMRD: Traffic *PRV CALL END    * PEER %s SRC_ID %s DST_ID %s TS %s DUR %s [STREAM ID: %s]', self._system,
                                  _peer_id, _rf_src, _dst_id, _slot, call_duration, _stream_id)

                if config['Reports']['Report']:
                    self._report.send_routeEvent('PRV VOICE,END,DMR,{},{},{},{},{},{},{:.2f}'.format(self._system, _stream_id, _peer_id, _rf_src, _slot, _dst_id, call_duration))

            # Mark status variables for use later
            self.STATUS[_slot]['RX_PEER_ID'] = _peer_id
            self.STATUS[_slot]['RX_RFS'] = _rf_src
            self.STATUS[_slot]['RX_TYPE'] = _dtype_vseq
            self.STATUS[_slot]['RX_TGID'] = _dst_id
            self.STATUS[_slot]['RX_TIME'] = pkt_time
            self.STATUS[_slot]['RX_STREAM_ID'] = _stream_id

    def p25d_preprocess(self, _peer_id, _rf_src, _dst_id, _call_type, _duid, _dtype_vseq, _stream_id, _data):
        pkt_time = time()
        p25pkt = _data[24:178]
        _lcf = int(_data[4])
        _slot = 1               # fake the slot data, P25 doesn't have this

        # Log but ignore TSDU or PDU packets here
        if ((_duid == fne_const.P25_DUID_TSDU) or (_duid == fne_const.P25_DUID_PDU)):
            if (_duid == fne_const.P25_DUID_TSDU):
                if (_lcf == fne_const.P25_TSBK_IOSP_GRP_AFF):
                    self._logger.info('(%s) P25D: Traffic *TSBK GRP AFF    * PEER %s SRC_ID %s DST_ID %s [STREAM ID %s]', self._system,
                                      _peer_id, _rf_src, _dst_id, _stream_id)
                    self.update_grp_aff(_peer_id, _rf_src, _dst_id, _stream_id)

                    if config['Reports']['Report']:
                        self._report.send_routeEvent('TSBK,GRP AFF,P25,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, 1, _dst_id))
                elif (_lcf == fne_const.P25_TSBK_OSP_U_DEREG_ACK):
                    self._logger.info('(%s) P25D: Traffic *TSBK U DEREG ACK* PEER %s SRC_ID %s [STREAM ID %s]', self._system,
                                      _peer_id, _dst_id, _stream_id)

                    self.remove_grp_aff(_peer_id, _dst_id, _stream_id)

                    if config['Reports']['Report']:
                        self._report.send_routeEvent('TSBK,U DEREG ACK,P25,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, 1, _dst_id))
                elif (_lcf == fne_const.P25_TSBK_OSP_ADJ_STS_BCAST):
                    self._logger.info('(%s) P25D: Traffic *TSBK ADJ STS BCS* PEER %s [STREAM ID %s]', self._system,
                                      _peer_id, _stream_id)

                    if config['Reports']['Report']:
                        self._report.send_routeEvent('TSBK,ADJ STS BCS,P25,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, 1, _dst_id))
                elif (_lcf == fne_const.P25_LCF_TSBK_CALL_ALERT):
                    self._logger.info('(%s) P25D: Traffic *TSBK CALL ALERT * PEER %s SRC_ID %s DST_ID %s [STREAM ID %s]', self._system,
                                      _peer_id, _rf_src, _dst_id, _stream_id)

                    if config['Reports']['Report']:
                        self._report.send_routeEvent('TSBK,CALL ALERT,P25,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, 1, _dst_id))
                elif (_lcf == fne_const.P25_LCF_TSBK_ACK_RSP_FNE):
                    self._logger.info('(%s) P25D: Traffic *TSBK ACK RSP    * PEER %s SRC_ID %s DST_ID %s [STREAM ID %s]', self._system,
                                      _peer_id, _rf_src, _dst_id, _stream_id)

                    if config['Reports']['Report']:
                        self._report.send_routeEvent('TSBK,ACK RSP,P25,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, 1, _dst_id))
            elif (_duid == fne_const.P25_DUID_PDU):
                self._logger.info('(%s) P25D: Traffic *DATA            * PEER %s SRC_ID %s DST_ID %s [STREAM ID %s]', self._system,
                                  _peer_id, _rf_src, _dst_id, _stream_id)

                if config['Reports']['Report']:
                    self._report.send_routeEvent('PDU,DATA,P25,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, 1, _dst_id))

        return

    def p25d_validate(self, _peer_id, _rf_src, _dst_id, _call_type, _duid, _dtype_vseq, _stream_id):
        pkt_time = time()
        _slot = 1

        if get_valid(_rf_src, black_rids) == True:
            if (_stream_id != self.STATUS[_slot]['RX_STREAM_ID']):
                # Mark status variables for use later
                self.STATUS[_slot]['RX_START'] = pkt_time
                self.STATUS[_slot]['RX_PEER_ID'] = _peer_id
                self.STATUS[_slot]['RX_RFS'] = _rf_src
                self.STATUS[_slot]['RX_TYPE'] = _dtype_vseq
                self.STATUS[_slot]['RX_TGID'] = _dst_id
                self.STATUS[_slot]['RX_STREAM_ID'] = _stream_id
                self._logger.warning('(%s) P25D: Traffic *REJECT ACL      * PEER %s SRC_ID %s DST_ID %s DUID %s [STREAM ID %s] (Blacklisted RID)', self._system,
                                     _peer_id, _rf_src, _dst_id, _duid, _stream_id)

                if config['Reports']['Report']:
                    self._report.send_routeEvent('REJECT ACL,BLACKLISTED RID,P25,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, 1, _dst_id))
            return False

        # Always validate a TSDU or PDU if the source is valid
        if ((_duid == fne_const.P25_DUID_TSDU) or (_duid == fne_const.P25_DUID_PDU)):
            return True

        # Always validate a terminator if the source is valid
        if ((_duid == fne_const.P25_DUID_TDU) or (_duid == fne_const.P25_DUID_TDULC)):
            return True
        
        if _call_type == 'group':
            if (RULES[self._system]['SEND_TGID'] == True) and (get_valid(_dst_id, config['Systems'][self._system]['ACTIVE_TG_IDS']) == False):
                if (_stream_id != self.STATUS[_slot]['RX_STREAM_ID']):
                    # Mark status variables for use later
                    self.STATUS[_slot]['RX_START'] = pkt_time
                    self.STATUS[_slot]['RX_PEER_ID'] = _peer_id
                    self.STATUS[_slot]['RX_RFS'] = _rf_src
                    self.STATUS[_slot]['RX_TYPE'] = _dtype_vseq
                    self.STATUS[_slot]['RX_TGID'] = _dst_id
                    self.STATUS[_slot]['RX_STREAM_ID'] = _stream_id
                    self.STATUS[_slot]['P25_RX_CT'] = 'group'
                    self._logger.warning('(%s) P25D: Traffic *REJECT ACL      * PEER %s SRC_ID %s DST_ID %s DUID %s [STREAM ID %s] (Illegal TGID)', self._system,
                                         _peer_id, _rf_src, _dst_id, _duid, _stream_id)

                    if config['Reports']['Report']:
                        self._report.send_routeEvent('REJECT ACL,ILLEGAL TGID,P25,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, 1, _dst_id))
                return False

        elif _call_type == 'unit':
            if ((get_valid(_rf_src, white_rids) == False and get_valid(_dst_id, white_rids) == False) or
               (get_valid(_rf_src, white_rids) == False or get_valid(_dst_id, white_rids) == False)):
                if (_stream_id != self.STATUS[_slot]['RX_STREAM_ID']):
                    # Mark status variables for use later
                    self.STATUS[_slot]['RX_START'] = pkt_time
                    self.STATUS[_slot]['RX_PEER_ID'] = _peer_id
                    self.STATUS[_slot]['RX_RFS'] = _rf_src
                    self.STATUS[_slot]['RX_TYPE'] = _dtype_vseq
                    self.STATUS[_slot]['RX_TGID'] = _dst_id
                    self.STATUS[_slot]['RX_STREAM_ID'] = _stream_id
                    self.STATUS[_slot]['P25_RX_CT'] = 'unit'
                    self._logger.warning('(%s) P25D: Traffic *REJECT ACL      * PEER %s SRC_ID %s DST_ID %s DUID %s [STREAM ID %s] (Illegal RID)', self._system,
                                         _peer_id, _rf_src, _dst_id, _duid, _stream_id)

                    if config['Reports']['Report']:
                        self._report.send_routeEvent('REJECT ACL,ILLEGAL RID,P25,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, 1, _dst_id))
                return False
        
        return True

    def p25d_received(self, _peer_id, _rf_src, _dst_id, _call_type, _duid, _dtype_vseq, _stream_id, _data):
        pkt_time = time()
        p25pkt = _data[24:178]
        _lcf = int(_data[4])
        _slot = 1               # fake the slot data, P25 doesn't have this

        # Ignore TSDU or PDU packets here
        if ((_duid == fne_const.P25_DUID_TSDU) or (_duid == fne_const.P25_DUID_PDU)):
            return

        # Override call type if necessary
        if ((_duid == fne_const.P25_DUID_TDU) or (_duid == fne_const.P25_DUID_TDULC)) and (self.STATUS[_slot]['RX_TYPE'] != fne_const.DT_TERMINATOR_WITH_LC):
            if self.STATUS[_slot]['P25_RX_CT'] != _call_type:
                _call_type = self.STATUS[_slot]['P25_RX_CT']

        if _call_type == 'group':
            # Is this a new call stream?
            if (_stream_id != self.STATUS[_slot]['RX_STREAM_ID']) and ((_duid != fne_const.P25_DUID_TDU) and (_duid != fne_const.P25_DUID_TDULC)):
                if (self.STATUS[_slot]['RX_TYPE'] != fne_const.DT_TERMINATOR_WITH_LC) and (pkt_time < (self.STATUS[_slot]['RX_TIME'] + fne_const.STREAM_TO)) and (_rf_src != self.STATUS[_slot]['RX_RFS']):
                    self._logger.warning('(%s) P25D: Traffic *CALL COLLISION  * PEER %s SRC_ID %s TGID %s [STREAM ID %s] (Collided with existing call)', self._system,
                                         _peer_id, _rf_src, _dst_id, _stream_id)

                    if config['Reports']['Report']:
                        self._report.send_routeEvent('GROUP VOICE,CALL COLLISION,P25,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, _slot, _dst_id))
                    return
                
                # This is a new call stream
                self.STATUS[_slot]['RX_START'] = pkt_time
                self._logger.info('(%s) P25D: Traffic *CALL START      * PEER %s SRC_ID %s TGID %s [STREAM ID %s]', self._system,
                                  _peer_id, _rf_src, _dst_id, _stream_id)

                self.STATUS[_slot]['P25_RX_CT'] = 'group'

                if config['Reports']['Report']:
                    self._report.send_routeEvent('GROUP VOICE,START,P25,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, _slot, _dst_id))

            for rule in RULES[self._system]['GROUP_VOICE']:
                _target = rule['DST_NET']

                # skip if the target doesn't exist
                if not (_target in systems):
                    continue

                _target_status = systems[_target].STATUS
               
                if ((_duid == fne_const.P25_DUID_TDU) or (_duid == fne_const.P25_DUID_TDULC)):
                    _dst_id = self.STATUS[_slot]['RX_TGID']
                    _rf_src = self.STATUS[_slot]['RX_RFS']
 
                if (rule['SRC_GROUP'] == _dst_id and rule['ACTIVE'] == True and rule['ROUTABLE'] == True):
                        
                    # BEGIN CONTENTION HANDLING
                    #
                    # The rules for each of the 4 "ifs" below are listed here
                    # for readability.  The Frame To Send is:
                    #   From a different group than last RX from this system,
                    #   but it has been less than Group Hangtime
                    #   From a different group than last TX to this system,
                    #   but it has been less than Group Hangtime
                    #   From the same group as the last RX from this system,
                    #   but from a different subscriber, and it has been less
                    #   than stream timeout
                    #   From the same group as the last TX to this system,
                    #   but from a different subscriber, and it has been less
                    #   than stream timeout
                    # The "continue" at the end of each means the next
                    # iteration of the for loop that tests for matching rules
                    #
                    if ((rule['DST_GROUP'] != _target_status[rule['DST_TS']]['RX_TGID']) and ((pkt_time - _target_status[rule['DST_TS']]['RX_TIME']) < RULES[_target]['GROUP_HANGTIME'])):
                        self._logger.info('(%s) P25D: Call not routed to TGID %s, target active or in group hangtime: PRID %s TGID %s', self._system,
                                          rule['DST_GROUP'], _target, _target_status[rule['DST_TS']]['RX_TGID'])
                        
                        if config['Reports']['Report']:
                            self._report.send_routeEvent('CALL ROUTE,FAILED,P25,{},{},{},{}'.format(self._system, _target, 1, rule['DST_GROUP']))
                        continue    
                    if ((rule['DST_GROUP'] != _target_status[rule['DST_TS']]['TX_TGID']) and ((pkt_time - _target_status[rule['DST_TS']]['TX_TIME']) < RULES[_target]['GROUP_HANGTIME'])):
                        self._logger.info('(%s) P25D: Call not routed to TGID %s, target in group hangtime: PRID %s TGID %s', self._system,
                                          rule['DST_GROUP'], _target, _target_status[rule['DST_TS']]['TX_TGID'])
                        
                        if config['Reports']['Report']:
                            self._report.send_routeEvent('CALL ROUTE,FAILED,P25,{},{},{},{}'.format(self._system, _target, 1, rule['DST_GROUP']))
                        continue
                    if (rule['DST_GROUP'] == _target_status[rule['DST_TS']]['TX_TGID']) and (_rf_src != _target_status[rule['DST_TS']]['TX_RFS']) and ((pkt_time - _target_status[rule['DST_TS']]['TX_TIME']) < fne_const.STREAM_TO):
                        self._logger.info('(%s) P25D: Call not routed for SRC_ID %s, call route in progress on target: PRID %s TGID %s SRC_ID %s', self._system,
                                          _rf_src, _target, _target_status[rule['DST_TS']]['TX_TGID'], _target_status[rule['DST_TS']]['TX_RFS'])
                        
                        if config['Reports']['Report']:
                            self._report.send_routeEvent('CALL ROUTE,FAILED,P25,{},{},{},{}'.format(self._system, _target, 1, rule['DST_GROUP']))
                        continue

                    # Set values for the contention handler to test next time
                    # there is a frame to forward
                    _target_status[rule['DST_TS']]['TX_TIME'] = pkt_time
                    
                    if (_stream_id != self.STATUS[_slot]['RX_STREAM_ID']) or (_target_status[rule['DST_TS']]['TX_RFS'] != _rf_src) or (_target_status[rule['DST_TS']]['TX_TGID'] != rule['DST_GROUP']):       
                        # Record the DST TGID and Stream ID
                        _target_status[rule['DST_TS']]['TX_TGID'] = rule['DST_GROUP']
                        _target_status[rule['DST_TS']]['TX_STREAM_ID'] = _stream_id
                        _target_status[rule['DST_TS']]['TX_RFS'] = _rf_src
                        self._logger.info('(%s) P25D: Call routed to SYSTEM %s TGID %s', self._system, _target, rule['DST_GROUP'])

                        if config['Reports']['Report']:
                            self._report.send_routeEvent('CALL ROUTE,TO,P25,{},{},{},{}'.format(self._system, _target, 1, rule['DST_GROUP']))

                    try:
                        _tgt_peer_id = self._CONFIG['Systems'][_target]['PeerId']
                    except KeyError:
                        _tgt_peer_id = self.STATUS[_slot]['RX_PEER_ID']

                    # somehow we've gotten a 0 for the peer ID -- so now we'll spoof the bitch
                    if (_tgt_peer_id == 0):
                        self._logger.warning('(%s) P25D: Some how we got a 0 peer ID? This shouldn\'t happen, spoofing to %s',
                                            self._system, _peer_id)
                        _tgt_peer_id = _peer_id

                    _tmp_data = _data[:8] + short_to_bytes(rule['DST_GROUP']) + int_to_bytes(_tgt_peer_id) + _data[15:24]
                    _tmp_data = _tmp_data + p25pkt
                    
                    # Transmit the packet to the destination system
                    systems[_target].send_system(_tmp_data)
                    self._logger.debug('(%s) P25 Packet routed by rule %s to %s SYSTEM %s', self._system, rule['NAME'], self._CONFIG['Systems'][_target]['Mode'], _target)
            
            # Final actions - Is this a voice terminator?
            if ((_duid == fne_const.P25_DUID_TDU) or (_duid == fne_const.P25_DUID_TDULC)) and (self.STATUS[_slot]['RX_TYPE'] != fne_const.DT_TERMINATOR_WITH_LC):
                call_duration = pkt_time - self.STATUS[_slot]['RX_START']
                _dst_id = self.STATUS[_slot]['RX_TGID']
                _rf_src = self.STATUS[_slot]['RX_RFS']
                self._logger.info('(%s) P25D: Traffic *CALL END        * PEER %s SRC_ID %s TGID %s DUR %s [STREAM ID %s]', self._system,
                                  _peer_id, _rf_src, _dst_id, call_duration, _stream_id)

                self.STATUS[_slot]['P25_RX_CT'] = 'group'

                if config['Reports']['Report']:
                    self._report.send_routeEvent('GROUP VOICE,END,P25,{},{},{},{},{},{},{:.2f}'.format(self._system, _stream_id, _peer_id, _rf_src, _slot, _dst_id, call_duration))

                #
                # Begin in-band signalling for call end.  This has nothign to
                # do with routing traffic directly.
                #
                
                # Iterate the rules dictionary
                for rule in RULES[self._system]['GROUP_VOICE']:
                    _target = rule['DST_NET']
            
                    # TGID matches a rule source, reset its timer
                    if _dst_id == rule['SRC_GROUP'] and ((rule['TO_TYPE'] == 'ON' and (rule['ROUTABLE'] == True)) or (rule['TO_TYPE'] == 'OFF' and rule['ROUTABLE'] == False)):
                        rule['TIMER'] = pkt_time + rule['TIMEOUT']
                        self._logger.info('(%s) P25D: Source group transmission match for rule %s. Reset timeout to %s', self._system, rule['NAME'], rule['TIMER'])
                
                        # Scan for reciprocal rules and reset their timers as
                        # well.
                        for target_rule in RULES[_target]['GROUP_VOICE']:
                            if target_rule['NAME'] == rule['NAME']:
                                target_rule['TIMER'] = pkt_time + target_rule['TIMEOUT']
                                self._logger.info('(%s) P25D: Reciprocal group transmission match for rule %s on IPSC %s. Reset timeout to %s', self._system, target_rule['NAME'], _target, rule['TIMER'])
            
                    # TGID matches an ACTIVATION trigger
                    if _dst_id in rule['ON']:
                        # Set the matching rule as ROUTABLE
                        rule['ROUTABLE'] = True
                        rule['TIMER'] = pkt_time + rule['TIMEOUT']
                        self._logger.info('(%s) P25D: Primary routing Rule %s changed to state: %s', self._system, rule['NAME'], rule['ROUTABLE'])
                
                        # Set reciprocal rules for other IPSCs as ROUTABLE
                        for target_rule in RULES[_target]['GROUP_VOICE']:
                            if target_rule['NAME'] == rule['NAME']:
                                target_rule['ROUTABLE'] = True
                                target_rule['TIMER'] = pkt_time + target_rule['TIMEOUT']
                                self._logger.info('(%s) P25D: Reciprocal routing Rule %s in IPSC %s changed to state: %s', self._system, target_rule['NAME'], _target, rule['ROUTABLE'])
                        
                    # TGID matches an DE-ACTIVATION trigger
                    if _dst_id in rule['OFF']:
                        # Set the matching rule as ROUTABLE
                        rule['ROUTABLE'] = False
                        self._logger.info('(%s) P25D: Routing Rule %s changed to state: %s', self._system, rule['NAME'], rule['ROUTABLE'])
                
                        # Set reciprocal rules for other IPSCs as ROUTABLE
                        _target = rule['DST_NET']
                        for target_rule in RULES[_target]['GROUP_VOICE']:
                            if target_rule['NAME'] == rule['NAME']:
                                target_rule['ROUTABLE'] = False
                                self._logger.info('(%s) P25D: Reciprocal routing Rule %s in IPSC %s changed to state: %s', self._system, target_rule['NAME'], _target, rule['ROUTABLE'])
                #
                # END IN-BAND SIGNALLING
                #

            # Mark status variables for use later
            self.STATUS[_slot]['RX_PEER_ID'] = _peer_id
            self.STATUS[_slot]['RX_RFS'] = _rf_src
            self.STATUS[_slot]['RX_TYPE'] = _dtype_vseq
            self.STATUS[_slot]['RX_TGID'] = _dst_id
            self.STATUS[_slot]['RX_TIME'] = pkt_time
            self.STATUS[_slot]['RX_STREAM_ID'] = _stream_id

        elif _call_type == 'unit':
            # Is this a new call stream?
            if (_stream_id != self.STATUS[_slot]['RX_STREAM_ID']) and ((_duid != fne_const.P25_DUID_TDU) and (_duid != fne_const.P25_DUID_TDULC)):
                if (self.STATUS[_slot]['RX_TYPE'] != fne_const.DT_TERMINATOR_WITH_LC) and (pkt_time < (self.STATUS[_slot]['RX_TIME'] + fne_const.STREAM_TO)) and (_rf_src != self.STATUS[_slot]['RX_RFS']):
                    self._logger.warning('(%s) P25D: Traffic *CALL COLLISION  * PEER %s SRC_ID %s DST_ID %s [STREAM ID %s] (Collided with existing call)', self._system,
                                         _peer_id, _rf_src, _dst_id, _stream_id)

                    if config['Reports']['Report']:
                        self._report.send_routeEvent('PRV VOICE,CALL COLLISION,P25,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, _slot, _dst_id))
                    return
                
                # This is a new call stream
                self.STATUS[_slot]['RX_START'] = pkt_time
                self._logger.info('(%s) P25D: Traffic *PRV CALL START  * PEER %s SRC_ID %s DST_ID %s [STREAM ID %s]', self._system,
                                  _peer_id, _rf_src, _dst_id, _stream_id)

                self.STATUS[_slot]['P25_RX_CT'] = 'unit'

                if config['Reports']['Report']:
                    self._report.send_routeEvent('PRV VOICE,START,P25,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, _slot, _dst_id))

            # Final actions - Is this a voice terminator?
            if ((_duid == fne_const.P25_DUID_TDU) or (_duid == fne_const.P25_DUID_TDULC)) and (self.STATUS[_slot]['RX_TYPE'] != fne_const.DT_TERMINATOR_WITH_LC):
                call_duration = pkt_time - self.STATUS[_slot]['RX_START']
                _dst_id = self.STATUS[_slot]['RX_TGID']
                _rf_src = self.STATUS[_slot]['RX_RFS']
                self._logger.info('(%s) P25D: Traffic *PRV CALL END    * PEER %s SRC_ID %s DST_ID %s DUR %s [STREAM ID %s]', self._system,
                                  _peer_id, _rf_src, _dst_id, call_duration, _stream_id)

                self.STATUS[_slot]['P25_RX_CT'] = 'group'

                if config['Reports']['Report']:
                    self._report.send_routeEvent('PRV VOICE,END,P25,{},{},{},{},{},{},{:.2f}'.format(self._system, _stream_id, _peer_id, _rf_src, _slot, _dst_id, call_duration))

            # Mark status variables for use later
            self.STATUS[_slot]['RX_PEER_ID'] = _peer_id
            self.STATUS[_slot]['RX_RFS'] = _rf_src
            self.STATUS[_slot]['RX_TYPE'] = _dtype_vseq
            self.STATUS[_slot]['RX_TGID'] = _dst_id
            self.STATUS[_slot]['RX_TIME'] = pkt_time
            self.STATUS[_slot]['RX_STREAM_ID'] = _stream_id

    def peer_ignored(self, _peer_id, _rf_src, _dst_id, _call_type, _slot, _dtype_vseq, _stream_id, _is_source):
        # Unit to unit call is always passed...
        if _call_type == 'unit':
            return False

        if get_valid_ignore(_peer_id, _dst_id, config['Systems'][self._system]['TG_IGNORE_IDS']) == True:
            if (_dst_id in config['Systems'][self._system]['TG_ALLOW_AFF']):
                if (_peer_id in GRP_AFF.keys()):
                    if (_dst_id in GRP_AFF[_peer_id].keys()):
                        if (len(GRP_AFF[_peer_id][_dst_id]) > 0):
                            return False

            if (_stream_id != self.STATUS[_slot]['RX_STREAM_ID']):
                if _is_source == True:
                    # Mark status variables for use later
                    self.STATUS[_slot]['RX_PEER_ID'] = _peer_id
                    self.STATUS[_slot]['RX_RFS'] = _rf_src
                    self.STATUS[_slot]['RX_TYPE'] = _dtype_vseq
                    self.STATUS[_slot]['RX_TGID'] = _dst_id
                    self.STATUS[_slot]['RX_STREAM_ID'] = _stream_id

                self._logger.warning('(%s) Traffic *REJECT ACL      * PEER %s SRC_ID %s DST_ID %s [STREAM ID %s] (Ignored Peer)', self._system,
                                     _peer_id, _rf_src, _dst_id, _stream_id)

                if config['Reports']['Report']:
                    self._report.send_routeEvent('REJECT ACL,IGNORED PEER,ACL,{},{},{},{},{},{}'.format(self._system, _stream_id, _peer_id, _rf_src, _slot, _dst_id))

            return True
        return False

    def peer_connected(self, _peer_id, _peer):
        global white_rids
        if white_rids:
            self.send_peer_wrids(_peer_id, white_rids)

        global black_rids
        if black_rids:
            self.send_peer_brids(_peer_id, black_rids)

        _tg_ids = config['Systems'][self._system]['ACTIVE_TG_IDS']
        if _tg_ids:
            self.send_peer_tgids(_peer_id, _tg_ids)

        _deactive_tg_ids = config['Systems'][self._system]['DEACTIVE_TG_IDS']
        if _deactive_tg_ids:
            self.send_peer_disabled_tgids(_peer_id, _deactive_tg_ids)

    def update_grp_aff(self, _peer_id, _rf_src, _dst_id, _stream_id):
        # make sure the peer exists in the affiliations table
        if (not _peer_id in GRP_AFF.keys()):
            GRP_AFF[_peer_id] = {}

        # remove the source RID from any other affiliated TGs
        try:
            idx = GRP_AFF[_peer_id][_dst_id].index(_rf_src)
            self.remove_grp_aff(_peer_id, _rf_src, _stream_id)
        except:
            pass

        # make sure the peer exists in the affiliations table
        if (not _dst_id in GRP_AFF[_peer_id].keys()):
            GRP_AFF[_peer_id][_dst_id] = []
            self._logger.info('(%s) P25D: PEER %s Added TGID %s to affiliations table [STREAM ID %s]', self._system, _peer_id, _dst_id, _stream_id)

        # add the source RID to the affiliated TGs
        GRP_AFF[_peer_id][_dst_id].append(_rf_src)
        self._logger.info('(%s) P25D: PEER %s Added SRC_ID %s affiliation to TGID %s [STREAM ID %s]', self._system, _peer_id, _rf_src, _dst_id, _stream_id)

    def remove_grp_aff(self, _peer_id, _rf_src, _stream_id):
        _dst_id = 0

        # make sure the peer exists in the affiliations table
        if (not _peer_id in GRP_AFF.keys()):
            GRP_AFF[_peer_id] = {}

        # iterate through affiliations and perform affiliation clean up
        for tgid in GRP_AFF[_peer_id]:
            if (_rf_src in GRP_AFF[_peer_id][tgid]):
                try:
                    idx = GRP_AFF[_peer_id][tgid].index(_rf_src)
                    del GRP_AFF[_peer_id][tgid][idx]
                    self._logger.info('(%s) P25D: PEER %s Removed SRC_ID %s affiliation from TGID %s [STREAM ID %s]', self._system, _peer_id, _rf_src, tgid, _stream_id)

                    # if there are no more affiliations delete the TG from the affiliations table
                    if len(GRP_AFF[_peer_id][tgid]) == 0:
                        _dst_id = tgid
                    break
                except:
                    pass
        
        if _dst_id != 0:
            del GRP_AFF[_peer_id][_dst_id]
            self._logger.info('(%s) P25D: PEER %s Removed TGID %s from affiliations table [STREAM ID %s]', self._system, _peer_id, _dst_id, _stream_id)

    def rid_tid_update_loop(self):
        from fne.fne_core import mk_id_dict

        self._logger.debug('(ALL SYSTEMS) RID/TID update timer loop started')
        global RULES
        try:
            if RULES[self._system]['MASTER'] == True:
                RULES = make_rules('fne_routing_rules')

            if RULES[self._system]['SEND_TGID'] == True:
                _tg_ids = config['Systems'][self._system]['ACTIVE_TG_IDS']
                if _tg_ids:
                    self._logger.debug('ID MAPPER: tg_ids dictionary is available, and being sent to peers')
                    self.master_send_tgids(self._system, _tg_ids)

                _deactive_tg_ids = config['Systems'][self._system]['DEACTIVE_TG_IDS']
                if _deactive_tg_ids:
                    self._logger.debug('ID MAPPER: deactive_tg_ids dictionary is available, and being sent to peers')
                    self.master_send_disabled_tgids(self._system, _deactive_tg_ids)
        except Exception:
            logger.error('Failed processing and sending rules for %s', self._system)

        global white_rids
        white_rids = mk_id_dict(self._CONFIG['Aliases']['Path'], self._CONFIG['Aliases']['WhitelistRIDsFile'])
        if white_rids:
            self._logger.debug('ID MAPPER: white_rids dictionary is available, and being sent to peers')
            self.master_send_wrids(white_rids)

        global black_rids
        black_rids = mk_id_dict(self._CONFIG['Aliases']['Path'], self._CONFIG['Aliases']['BlacklistRIDsFile'])
        if black_rids:
            self._logger.debug('ID MAPPER: black_rids dictionary is available, and being sent to peers')
            self.master_send_brids(black_rids)
        
# ---------------------------------------------------------------------------
#   Class Declaration
#     This implements the report service factory.
# ---------------------------------------------------------------------------

class routeReportFactory(reportFactory):
    def send_timed(self):
        rulesSerialized = pickle.dumps(RULES, protocol=pickle.HIGHEST_PROTOCOL)
        self.send_clients(REPORT_OPCODES['RRULES_RSP'] + rulesSerialized)

        grpAffSerialized = pickle.dumps(GRP_AFF, protocol=pickle.HIGHEST_PROTOCOL)
        self.send_clients(REPORT_OPCODES['GRP_AFF_UPD'] + grpAffSerialized)

        if white_rids:
            wridSerialized = pickle.dumps(white_rids, protocol=pickle.HIGHEST_PROTOCOL)
            self.send_clients(REPORT_OPCODES['WHITELIST_RID_UPD'] + wridSerialized)
        
    def send_routeEvent(self, _data):
        self.send_clients(REPORT_OPCODES['CALL_EVENT'] + _data.encode())

# ---------------------------------------------------------------------------
#   Program Entry Point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    from fne.fne_core import mk_id_dict
    from fne.fne_core import setup_fne

    # perform basic FNE setup
    config, logger, act_log_file = setup_fne()
    logger.info('Digital Voice Modem Router Service D02.00')
    
    # make dictionaries
    white_rids = mk_id_dict(config['Aliases']['Path'], config['Aliases']['WhitelistRIDsFile'])
    if white_rids:
        logger.info('ID MAPPER: white_rids dictionary is available')

    black_rids = mk_id_dict(config['Aliases']['Path'], config['Aliases']['WhitelistRIDsFile'])
    if black_rids:
        logger.info('ID MAPPER: black_rids dictionary is available')

    for system in config['Systems']:
        config['Systems'][system]['ACTIVE_TG_IDS'] = {}
        config['Systems'][system]['DEACTIVE_TG_IDS'] = {}
        config['Systems'][system]['TG_IGNORE_IDS'] = {}
        config['Systems'][system]['TG_ALLOW_AFF'] = []
    
    RULES = {}
    GRP_AFF = {}

    # build the routing rules file
    RULES = make_rules('fne_routing_rules')

    # setup FNE report server
    report_server = config_reports(config, logger, routeReportFactory)
    
    # FNE instance creation
    for system in config['Systems']:
        if config['Systems'][system]['Enabled']:
            systems[system] = routerFNE(system, config, logger, act_log_file, report_server)
            reactor.listenUDP(config['Systems'][system]['Port'], systems[system], interface = config['Systems'][system]['Address'])
            logger.debug('%s instance created: %s, %s', config['Systems'][system]['Mode'], system, systems[system])
            
    # initialize the rule timer -- this is for user activated stuff
    rule_timer = task.LoopingCall(rule_timer_loop)
    rule_timer.start(60)

    reactor.run()
