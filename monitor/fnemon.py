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

import logging
import sys
import re
import json

from pprint import pprint
from time import time, strftime, localtime
from pickle import loads
from binascii import b2a_hex as ahex
from binascii import a2b_hex as bhex
from os.path import getmtime
from collections import deque

from zope.interface import implementer

from twisted.python import log
from twisted.internet.protocol import ReconnectingClientFactory, Protocol
from twisted.protocols.basic import NetstringReceiver
from twisted.internet import reactor, task
from twisted.web.server import Site
from twisted.web.guard import HTTPAuthSessionWrapper, BasicCredentialFactory
from twisted.web.static import File
from twisted.web.resource import IResource, Resource
from twisted.cred.portal import IRealm, Portal
from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse

from autobahn.twisted.websocket import WebSocketServerProtocol, WebSocketServerFactory

from jinja2 import Environment, PackageLoader

#from dmr_utils.utils import hex_str_3

# exit more friendly-y if we don't have a config
try:
    import config
except Exception as e:
    print("Error importing the configuration file:")
    print(e)
    print("Bye")
    quit()

# Opcodes for the network-based reporting protocol
REPORT_OPCODES = {
    'CONFIG_REQ': b'\x00',
    'CONFIG_RSP': b'\x01',
    'RRULES_REQ': b'\x02',
    'RRULES_RSP': b'\x03',
    'CONFIG_UPD': b'\x04',
    'RRULES_UPD': b'\x05',
    'LINK_EVENT': b'\x06',
    'CALL_EVENT': b'\x07',
    'GRP_AFF_UPD': b'\x08',
    'RCON_REQ': b'\x09',
    'WHITELIST_RID_UPD': b'\x10',
}

WEBSOCK_OPCODES = {
    'QUIT': b'q',
    'CONFIG': b'c',
    'RULES': b'r',
    'AFFILIATION': b'g',
    'ACTIVITY': b'a',
    'LOG': b'l',
    'DIAG_LOG': b'd',
    'MESSAGE': b'm',
    'WHITELIST_RID': b'w',
}

# Global Variables
CONFIG           = {}
CTABLE           = {'MASTERS': {}, 'MASTER_CNT': 0, 'PEERS': {}, 'PEER_CNT': 0}

RULES            = {}
RTABLE           = {}
RTABLE['RULES']  = {}

GRP_AFF          = {}
GATABLE          = {}

WLIST_RID        = {}
WRIDTABLE        = {}

RULES_RX         = ''
CONFIG_RX        = ''
LOGBUF           = deque(100*[''], 100)

LOG_MAX          = 512
EOL_SCANAHEAD    = LOG_MAX / 2

# ---------------------------------------------------------------------------
#   String Utility Routines
# ---------------------------------------------------------------------------

# Convert a hex string to an int (peer ID, etc.)
def int_id(_hex_string):
    try:
        return int(ahex(_hex_string), 16)
    except TypeError:
        return _hex_string

# ---------------------------------------------------------------------------
#   Module Routines
# ---------------------------------------------------------------------------

def process_act_log(_file):
    global LOG_MAX, EOL_SCANAHEAD
    _entries = []
    _line_cnt = 0
    try:
        with open(_file, 'r') as log:
            fwd_log = list(log)
            rev_log = reversed(fwd_log)
            for line in rev_log:
                if (re.search('(RF voice|RF encrypted voice|RF late entry|RF data|RF voice rejection)', line) != None and
                    re.search('(group grant|unit-to-unit grant)', line) != None and
                    re.search('(unit registration|group affiliation|unit deregistration|location registration request)', line) != None and
                    re.search('(status update|message update|call alert|ack response)', line) != None and
                    re.search('(cancel service|radio check|radio inhibit|radio uninhibit)', line) == None):
                    continue
                if (re.search('(end of)', line) != None):
                    continue

                peerId = line.split(' ')[0]
                logLineRaw = line.split(' ')[1:-1]
                rawData = logLineRaw[1:-1]

                dateUTC = rawData[0] + ' ' + rawData[1]
                mode = rawMode = rawData[2]
                src = rawData[3]
                type = ''
                typeClass = 'normal'
                alertClass = ''

                if (src == 'Net'):
                    continue

                if (re.search('(voice rejection)', line) != None):
                    alertClass = 'warning'
                    type = 'Voice Transmission (Rejected)'
                if (re.search('(voice transmission|voice header|late entry)', line) != None):
                    if (re.search('(encrypted)', line) != None):
                        typeClass = 'success'
                        type = 'Voice Transmission (Encrypt)'
                    else:
                        type = 'Voice Transmission'
                if (re.search('(data transmission|data header)', line) != None):
                    type = 'Data Transmission'
                if (re.search('(group grant request)', line) != None):
                    typeClass = 'success'
                    type = 'Group Grant Request'
                    if (re.search('(denied)', line) != None):
                        alertClass = 'warning'
                        type = type + ' (Denied)'
                    if (re.search('(queued)', line) != None):
                        alertClass = 'info'
                        type = type + ' (Queued)'
                if (re.search('(unit-to-unit grant request)', line) != None):
                    typeClass = 'success'
                    type = 'Unit-to-Unit Grant Request'
                    if (re.search('(denied)', line) != None):
                        alertClass = 'warning'
                        type = type + ' (Denied)'
                    if (re.search('(queued)', line) != None):
                        alertClass = 'info'
                        type = type + ' (Queued)'
                if (re.search('(group affiliation request)', line) != None):
                    typeClass = 'warning'
                    type = 'Group Affiliation'
                    if (re.search('(denied)', line) != None):
                        alertClass = 'warning'
                        type = type + ' (Denied)'
                if (re.search('(group affiliation query command)', line) != None):
                    typeClass = 'info'
                    type = 'Group Affiliation Query'
                if (re.search('(group affiliation query response)', line) != None):
                    typeClass = 'success'
                    type = 'Group Affiliation Query'
                if (re.search('(unit registration request)', line) != None):
                    typeClass = 'warning'
                    type = 'Unit Registration'
                    if (re.search('(denied)', line) != None):
                        alertClass = 'warning'
                        type = type + ' (Denied)'
                if (re.search('(unit registration command)', line) != None):
                    typeClass = 'info'
                    type = 'Unit Registration Command'
                if (re.search('(unit deregistration request)', line) != None):
                    typeClass = 'warning'
                    type = 'Unit De-Registration'
                    if (re.search('(denied)', line) != None):
                        alertClass = 'warning'
                        type = type + ' (Not Registered)'
                if (re.search('(location registration request)', line) != None):
                    typeClass = 'warning'
                    type = 'Location Registration'
                    if (re.search('(denied)', line) != None):
                        alertClass = 'warning'
                        type = type + ' (Denied)'
                if (re.search('(status update)', line) != None):
                    typeClass = 'info'
                    type = 'Status Update'
                if (re.search('(message update)', line) != None):
                    typeClass = 'info'
                    type = 'Message Update'
                if (re.search('(call alert)', line) != None):
                    typeClass = 'info'
                    type = 'Call Alert'
                if (re.search('(ack response)', line) != None):
                    typeClass = 'success'
                    type = 'ACK Response'
    #            if (re.search('(cancel service)', line) != None):
    #                typeClass = 'danger'
    #                type = 'Cancel Service'
                if (re.search('(radio check request)', line) != None):
                    typeClass = 'info'
                    type = 'Radio Check'
                if (re.search('(radio check response)', line) != None):
                    typeClass = 'success'
                    type = 'Radio Check ACK'
                if (re.search('(radio inhibit request)', line) != None):
                    typeClass = 'danger'
                    type = 'Radio Inhibit'
                if (re.search('(radio inhibit response)', line) != None):
                    typeClass = 'danger'
                    type = 'Radio Inhibit ACK'
                if (re.search('(radio uninhibit request)', line) != None):
                    typeClass = 'danger'
                    type = 'Radio Uninhibit'
                if (re.search('(radio uninhibit response)', line) != None):
                    typeClass = 'success'
                    type = 'Radio Uninhibit ACK'

                if (type == ''):
                    continue

                if (mode == 'DMR'):
                    mode = rawData[2] + ' TS' + rawData[5].replace(',', '')
                if ('data header' in line):
                    src = 'SMS'

                _from = _to = ''
                smsDur = ''
                actData = line.split('from ')
                if (len(actData) <= 1):
                    continue

                actData = actData[1].split('to ')
                _from = actData[0].replace(' ', '')
                _from = _from.replace('\n', '')

                # HACK: remove denied on the _from line
                if (re.search('(denied)', _from) != None):
                    _from = _from.replace('denied', '')

                if (len(actData) > 1):
                    _to = actData[1].replace('  ', ' ')
                    _to = _to.replace('\n', '')
                    if (' ' in _to):
                        toData = _to.split(' ')
                        if (len(toData) >= 2):
                            _to = toData[0] + ' ' + toData[1]
                        if (len(toData) == 4):
                            smsDur = toData[2] + ' ' + toData[3]

                if (re.search('(data transmission)', line) != None):
                    _to = 'N/A'

                if (re.search('(unit registration|group affiliation|unit deregistration|location registration)', line) != None or
                    re.search('(status update|message update|cancel service)', line) != None):
                    if (_to == ''):
                        _to = '16777213'    # WUID for SYSTEM

                if (_from == ''):
                    continue
                if (_to == ''):
                    continue

                _line_cnt += 1
                if (_line_cnt >= LOG_MAX):
                    break

                if (_from == '16777213'):
                    _from = 'SYSTEM'
                if (_to == '16777213'):
                    _to = 'SYSTEM'
                
                if (mode == 'P25'):
                    if (_from == '16777212'):
                        _from = 'FNE'
                    if (_to == '16777212'):
                        _to = 'FNE'

                dur = 'Timing unavailable'
                ber = 'No BER data'

                durAndBer = '<td colspan="2" class="table-col-disabled">No data or timing unavailable</td>'
                endOfCount = 0
                if (re.search('(voice transmission|voice header|late entry)', line) != None):
                    lineIdx = fwd_log.index(line)
                    for etLine in fwd_log[lineIdx:]:
                        if (endOfCount >= EOL_SCANAHEAD):
                            break

                        if (re.search('(RF end of|ended RF data transmission|transmission lost)', etLine) == None):
                            endOfCount += 1
                            continue
                        else:
                            etPeerId = etLine.split(' ')[0]
                            if (etPeerId != peerId):
                                endOfCount += 1
                                continue

                            rawStats = etLine.split(', ')
                            if (len(rawStats) >= 2):
                                dur = rawStats[1].rstrip().replace(' seconds', 's')
                            else:
                                dur = '0s'

                            if (len(rawStats) >= 3):
                                ber = rawStats[2].rstrip().replace('BER: ', '').replace('%', '')
                            else:
                                ber = '0.0'

                            break

                entry = {}
                entry['date'] = dateUTC
                entry['peerId'] = peerId
                entry['mode'] = mode
                entry['type_class'] = typeClass
                entry['alert_class'] = alertClass
                entry['type'] = type
                entry['from'] = _from
                entry['to'] = _to
                entry['duration'] = dur
                entry['ber'] = ber
                _entries.append(entry)
    except Exception as e:
        logging.error("Error opening activity log: {}".format(e))
    return (_entries)

def process_diag_log(_file):
    global LOG_MAX
    _lines = []
    _line_cnt = 0
    try:
        with open(_file, 'r') as log:
            fwd_log = list(log)
            rev_log = reversed(fwd_log)
            for line in rev_log:
                _line_cnt += 1
                if (_line_cnt >= LOG_MAX):
                    break

                _lines.append(line)
    except Exception as e:
        logging.error("Error opening activity log: {}".format(e))
    return (_lines)
            
# Build configuration and rules tables from config/rules dicts
# this currently is a timed call
def gen_activity():
    global WEBSOCK_OPCODES
    _entries = process_act_log(config.ACTIVITY_LOG)
    dashboard_server.broadcast(WEBSOCK_OPCODES['ACTIVITY'] + json.dumps(_entries).encode())

# ---------------------------------------------------------------------------
#   Group Affiliations Table Routines
# ---------------------------------------------------------------------------

def build_grp_aff_table(_grp_aff):
    _table = {}
    
    for _peer_id, _aff_data in _grp_aff.items():
        _tgid_entries = _grp_aff[_peer_id]
        for _tgid in _tgid_entries:
            _rid_entries = _tgid_entries[_tgid]
            for _rid in _rid_entries:
                _table[_rid] = {}
                _table[_rid]['PEER_ID'] = _peer_id
                _table[_rid]['DST_ID'] = _tgid
  
    return _table

# ---------------------------------------------------------------------------
#   Whitelist RID Table Routines
# ---------------------------------------------------------------------------

def build_whitelist_rid_table(_whitelist_rid):
    _table = []
    
    for _rid, _data in _whitelist_rid.items():
        _table.append(_rid)
  
    return _table

# ---------------------------------------------------------------------------
#   Connections Table Routines
# ---------------------------------------------------------------------------

# Build the connections table
def build_ctable(_config):
    _stats_table = {'MASTERS': {}, 'MASTER_CNT': 0, 'PEERS': {}, 'PEER_CNT': 0}
    for _hbp, _hbp_data in _config.items(): 
        if _hbp_data['Enabled'] == True:
            if _hbp_data['Mode'] == 'master':
                _stats_table['MASTERS'][_hbp] = {}
                _stats_table['MASTERS'][_hbp]['REPEAT'] = _hbp_data['Repeat']
                _stats_table['MASTERS'][_hbp]['PEERS'] = {}
                _stats_table['MASTERS'][_hbp]['PEER_CNT'] = 0
                for _peer in _hbp_data['PEERS']:
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)] = {}

                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['CONNECTION'] = _hbp_data['PEERS'][_peer]['CONNECTION']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['PINGS_RECEIVED'] = _hbp_data['PEERS'][_peer]['PINGS_RECEIVED']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['LAST_PING'] = _hbp_data['PEERS'][_peer]['LAST_PING']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['IP'] = _hbp_data['PEERS'][_peer]['IP']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['PORT'] = _hbp_data['PEERS'][_peer]['PORT']

                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['IDENTITY'] = _hbp_data['PEERS'][_peer]['IDENTITY']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['RX_FREQ'] = _hbp_data['PEERS'][_peer]['RX_FREQ']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['TX_FREQ'] = _hbp_data['PEERS'][_peer]['TX_FREQ']

                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['LATITUDE'] = _hbp_data['PEERS'][_peer]['LATITUDE']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['LONGITUDE'] = _hbp_data['PEERS'][_peer]['LONGITUDE']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['HEIGHT'] = _hbp_data['PEERS'][_peer]['HEIGHT']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['LOCATION'] = _hbp_data['PEERS'][_peer]['LOCATION']

                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['TX_OFFSET'] = _hbp_data['PEERS'][_peer]['TX_OFFSET']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['CH_BW'] = _hbp_data['PEERS'][_peer]['CH_BW']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['CHANNEL_ID'] = _hbp_data['PEERS'][_peer]['CHANNEL_ID']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['CHANNEL_NO'] = _hbp_data['PEERS'][_peer]['CHANNEL_NO']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['TX_POWER'] = _hbp_data['PEERS'][_peer]['TX_POWER']

                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['SOFTWARE_ID'] = _hbp_data['PEERS'][_peer]['SOFTWARE_ID']

                    _stats_table['MASTERS'][_hbp]['PEER_CNT'] += 1 
                _stats_table['MASTER_CNT'] += 1
            elif _hbp_data['Mode'] == 'peer':
                _stats_table['PEERS'][_hbp] = {}
                _stats_table['PEERS'][_hbp]['PEER_ID'] = _hbp_data['PeerId']
                _stats_table['PEERS'][_hbp]['IDENTITY'] = _hbp_data['Identity']
                _stats_table['PEERS'][_hbp]['RX_FREQ'] = _hbp_data['RxFrequency']
                _stats_table['PEERS'][_hbp]['TX_FREQ'] = _hbp_data['TxFrequency']
                _stats_table['PEERS'][_hbp]['LATITUDE'] = _hbp_data['Latitude']
                _stats_table['PEERS'][_hbp]['LONGITUDE'] = _hbp_data['Longitude']
                _stats_table['PEERS'][_hbp]['LOCATION'] = _hbp_data['Location']
                _stats_table['PEERS'][_hbp]['LOCATION'] = _hbp_data['Location']
                _stats_table['PEERS'][_hbp]['SOFTWARE_ID'] = _hbp_data['SoftwareId']
                _stats_table['PEERS'][_hbp]['STATS'] = _hbp_data['STATS']
                _stats_table['PEER_CNT'] += 1
                
    return(_stats_table)

# ---------------------------------------------------------------------------
#   Rules Table Routines
# ---------------------------------------------------------------------------

def rules_sort(e):
    return e['SRC_GROUP']

def build_rules_table(_rules):
    _stats_table = {}
    _now = time()
    _cnow = strftime('%Y-%m-%d %H:%M:%S', localtime(_now))
    
    for _rule, _rule_data in _rules.items():
        _stats_table[_rule] = []

        _rules[_rule]['GROUP_VOICE'].sort(key=rules_sort)
        for rule_entry in _rules[_rule]['GROUP_VOICE']:
            rule_entry['SRC_GROUP'] = str(rule_entry['SRC_GROUP'])
            rule_entry['SRC_TS'] = str(rule_entry['SRC_TS'])
            rule_entry['DST_GROUP'] = str(rule_entry['DST_GROUP'])
            rule_entry['DST_TS'] = str(rule_entry['DST_TS'])

            rule_entry['ACTIVE'] = str(rule_entry['ACTIVE'])
            rule_entry['ROUTABLE'] = str(rule_entry['ROUTABLE'])

            for i in range(len(rule_entry['ON'])):
                rule_entry['ON'][i] = str(rule_entry['ON'][i])

            rule_entry['TRIG_ON'] = ', '.join(rule_entry['ON'])

            for i in range(len(rule_entry['OFF'])):
                rule_entry['OFF'][i] = str(rule_entry['OFF'][i])

            rule_entry['TRIG_OFF'] = ', '.join(rule_entry['OFF'])

            rule_entry['AFFILIATED'] = str(rule_entry['AFFILIATED'])

            if len(rule_entry['IGNORED']) > 0:
                if rule_entry['IGNORED'][0] == 0:
                    rule_entry['IGNORED_LST'] = 'ALL'
                else:
                    for i in range(len(rule_entry['IGNORED'])):
                        rule_entry['IGNORED'][i] = str(rule_entry['IGNORED'][i])

                    rule_entry['IGNORED_LST'] = ', '.join(rule_entry['IGNORED'])

            _stats_table[_rule].append(rule_entry)
    
    return _stats_table

# ---------------------------------------------------------------------------
#   Routines
# ---------------------------------------------------------------------------

def websock_update():
    global WEBSOCK_OPCODES
    if CONFIG:
        table = WEBSOCK_OPCODES['CONFIG'] + json.dumps(CTABLE).encode()
        dashboard_server.broadcast(table)
    if RULES:
        table = WEBSOCK_OPCODES['RULES'] + json.dumps(RTABLE['RULES']).encode()
        dashboard_server.broadcast(table)
    if GRP_AFF:
        table = WEBSOCK_OPCODES['AFFILIATION'] + json.dumps(GATABLE).encode()
        dashboard_server.broadcast(table)
    if WLIST_RID:
        table = WEBSOCK_OPCODES['WHITELIST_RID'] + json.dumps(WRIDTABLE).encode()
        dashboard_server.broadcast(table)

# Process in coming messages and take the correct action depending on the opcode
def process_message(_message):
    global CTABLE, CONFIG, RULES, RTABLE, GRP_AFF, GATABLE, WLIST_RID, WRIDTABLE, CONFIG_RX, RULES_RX, WEBSOCK_OPCODES
    opcode = _message[:1]
    _now = strftime('%Y-%m-%d %H:%M:%S %Z', localtime(time()))
    
    if opcode == REPORT_OPCODES['CONFIG_RSP']:
        logging.debug('got CONFIG_RSP opcode')
        CONFIG = load_dictionary(_message)
        CONFIG_RX = strftime('%Y-%m-%d %H:%M:%S', localtime(time()))
        CTABLE = build_ctable(CONFIG)
    
    elif opcode == REPORT_OPCODES['RRULES_RSP']:
        logging.debug('got RRULES_RSP opcode')
        RULES = load_dictionary(_message)
        RULES_RX = strftime('%Y-%m-%d %H:%M:%S', localtime(time()))
        RTABLE['RULES'] = build_rules_table(RULES)
    
    elif opcode == REPORT_OPCODES['GRP_AFF_UPD']:
        logging.debug('got GRP_AFF_UPD opcode')
        GRP_AFF = load_dictionary(_message)
        GATABLE = build_grp_aff_table(GRP_AFF)
        
    elif opcode == REPORT_OPCODES['LINK_EVENT']:
        logging.info('LINK_EVENT Received: {}'.format(repr(_message[1:])))
        
    elif opcode == REPORT_OPCODES['CALL_EVENT']:
        logging.info('CALL_EVENT: {}'.format(repr(_message[1:])))
        #p = _message[1:].split(",")
        p = _message[1:].decode().split(",")
        if p[0] == 'GROUP VOICE':
            if p[1] == 'END':
                log_message = '[{}] ({}) {} {}: System: {}; Peer: {}; Subscriber: {}; TS: {}; TGID: {}; Duration: {}s'.format(_now, p[2], p[0], p[1], p[3], p[5], p[6], p[7], p[8], p[9])
            elif p[1] == 'START':
                log_message = '[{}] ({}) {} {}: System: {}; Peer: {}; Subscriber: {}; TS: {}; TGID: {}'.format(_now, p[2], p[0], p[1], p[3], p[5], p[6], p[7], p[8])
            elif p[1] == 'END WITHOUT MATCHING START':
                log_message = '[{}] ({}) {} {} on System {}: Peer: {}; Subscriber: {}; TS: {}; TGID: {}'.format(_now, p[2], p[0], p[1], p[3], p[5], p[6], p[7], p[8])
            else:
                log_message = '[{}] UNKNOWN GROUP VOICE LOG MESSAGE'.format(_now)
        elif p[0] == 'PRV VOICE':
            if p[1] == 'END':
                log_message = '[{}] ({}) {} {}: System: {}; Peer: {}; Subscriber: {}; TS: {}; TGID: {}; Duration: {}s'.format(_now, p[2], p[0], p[1], p[3], p[5], p[6], p[7], p[8], p[9])
            elif p[1] == 'START':
                log_message = '[{}] ({}) {} {}: System: {}; Peer: {}; Subscriber: {}; TS: {}; TGID: {}'.format(_now, p[2], p[0], p[1], p[3], p[5], p[6], p[7], p[8])
            elif p[1] == 'END WITHOUT MATCHING START':
                log_message = '[{}] ({}) {} {} on System {}: Peer: {}; Subscriber: {}; TS: {}; TGID: {}'.format(_now, p[2], p[0], p[1], p[3], p[5], p[6], p[7], p[8])
            else:
                log_message = '[{}] UNKNOWN PRV VOICE LOG MESSAGE'.format(_now)
        elif p[0] == 'CALL ROUTE':
            log_message = '[{}] ({}) {} {}: System: {}; Target: {}; TS: {}; TGID: {}'.format(_now, p[2], p[0], p[1], p[3], p[4], p[5], p[6])
        elif p[0] == 'REJECT ACL':
            log_message = '[{}] ({}) {} {}: System: {}; Peer: {}; Subscriber: {}; TS: {}; TGID: {}'.format(_now, p[2], p[0], p[1], p[3], p[5], p[6], p[7], p[8])
        elif p[0] == 'TSBK':
            if p[1] == 'ADJ STS BCS':
                log_message = '[{}] ({}) {} {}: System: {}; Peer: {}'.format(_now, p[2], p[0], p[1], p[3], p[5])
            else:
                log_message = '[{}] ({}) {} {}: System: {}; Peer: {}; Subscriber: {}; TS: {}; TGID: {}'.format(_now, p[2], p[0], p[1], p[3], p[5], p[6], p[7], p[8])
        elif p[0] == 'PDU':
                log_message = '[{}] ({}) {} {}: System: {}; Peer: {}; Subscriber: {}; TS: {}'.format(_now, p[2], p[0], p[1], p[3], p[5], p[6], p[7])
        else:
            log_message = '[{}] UNKNOWN LOG MESSAGE: {}'.format(_now, p[0])
            
        dashboard_server.broadcast(WEBSOCK_OPCODES['LOG'] + log_message.encode())
        LOGBUF.append(log_message)
    
    elif opcode == REPORT_OPCODES['WHITELIST_RID_UPD']:
        logging.debug('got WHITELIST_RID_UPD opcode')
        WLIST_RID = load_dictionary(_message)
        WRIDTABLE = build_whitelist_rid_table(WLIST_RID)

    else:
        logging.error('Report unrecognized opcode %s PACKET %s', opcode, ahex(_message))
        
def load_dictionary(_message):
    data = _message[1:]
    logging.debug('Successfully decoded dictionary')
    return loads(data)
 
# ---------------------------------------------------------------------------
#   Class Declaration
#     This implements the socket-based reporting logic.
# ---------------------------------------------------------------------------

class report(NetstringReceiver):
    def __init__(self, factory):
        self._factory = factory

    def connectionMade(self):
        self._factory.connection = self
        logging.info('Reporting server connected: %s', self.transport.getPeer())

    def connectionLost(self, reason):
        pass
        
    def stringReceived(self, data):
        logging.debug("Received message: {}".format(data))
        process_message(data)

# ---------------------------------------------------------------------------
#   Class Declaration
#     This implements the report service factory.
# ---------------------------------------------------------------------------

class reportClientFactory(ReconnectingClientFactory):
    def __init__(self):
        self.connection = {}
        
    def startedConnecting(self, connector):
        global WEBSOCK_OPCODES
        logging.info('Connecting to FNE server.')
        if 'dashboard_server' in locals() or 'dashboard_server' in globals():
            dashboard_server.broadcast(WEBSOCK_OPCODES['QUIT'] + b'Connection to FNE Established')

    def buildProtocol(self, addr):
        logging.info('Connected.')
        self.resetDelay()
        return report(self)

    def clientConnectionLost(self, connector, reason):
        global WEBSOCK_OPCODES
        logging.info('Lost connection.  Reason: %s', reason)
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)
        dashboard_server.broadcast(WEBSOCK_OPCODES['QUIT'] + b'Connection to FNE Lost')

    def clientConnectionFailed(self, connector, reason):
        logging.info('Connection failed. Reason: %s', reason)
        ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)

    def send_message(self, message):
        self.connection.sendString(message)

# ---------------------------------------------------------------------------
#   Class Declaration
#     This implements the dashboard communications.
# ---------------------------------------------------------------------------

class dashboard(WebSocketServerProtocol):
    def onConnect(self, request):
        logging.info('Client connecting: %s', request.peer)

    def onOpen(self):
        global WEBSOCK_OPCODES
        logging.info('WebSocket connection open.')
        self.factory.register(self)
        websock_update()
        gen_activity()
        for _message in LOGBUF:
            if _message:
                self.sendMessage(WEBSOCK_OPCODES['LOG'] + _message.encode())

    def onMessage(self, payload, isBinary):
        global WEBSOCK_OPCODES, REPORT_OPCODES, report_client
        if isBinary:
            logging.info('Binary message received: %s bytes', len(payload))
        else:
            _payload = payload.decode('ascii')
            _opcode = payload[:1]
            if (_opcode == WEBSOCK_OPCODES['MESSAGE']):
                _arguments = _payload.split(',')
                _peer_id = _arguments[0][1:]
                _command = _arguments[1]
                _command_arg = _arguments[2]
                _dmr_slot = _arguments[3]
                _mot_mfid = _arguments[4]
                logging.info('Received system command: PEER ID %s COMMAND %s DMR SLOT %s ARGUMENT %s MOT MFID %s', 
                             _peer_id, _command, _dmr_slot, _command_arg, _mot_mfid)
                if 'report_client' in locals() or 'report_client' in globals():
                    _message = (',' + _peer_id + ',' + _command + ',' + _command_arg + ',' + _dmr_slot + ',' + _mot_mfid).encode('ascii')
                    report_client.send_message(REPORT_OPCODES['RCON_REQ'] + _message)
            elif (_opcode == WEBSOCK_OPCODES['DIAG_LOG']):
                _arguments = _payload.split(',')
                _peer_id = _arguments[0][1:]
                diag_log = process_diag_log(config.LOG_PATH + _peer_id + '.log')
                self.sendMessage(WEBSOCK_OPCODES['DIAG_LOG'] + json.dumps(diag_log).encode())
            else:
                logging.info('Text message received: %s', _payload)

    def connectionLost(self, reason):
        WebSocketServerProtocol.connectionLost(self, reason)
        self.factory.unregister(self)

    def onClose(self, wasClean, code, reason):
        logging.info('WebSocket connection closed: %s', reason)

# ---------------------------------------------------------------------------
#   Class Declaration
#     This implements the dashboard service factory.
# ---------------------------------------------------------------------------

class dashboardFactory(WebSocketServerFactory):
    def __init__(self, url):
        WebSocketServerFactory.__init__(self, url)
        self.clients = []

    def register(self, client):
        if client not in self.clients:
            logging.info('registered client %s', client.peer)
            self.clients.append(client)

    def unregister(self, client):
        if client in self.clients:
            logging.info('unregistered client %s', client.peer)
            self.clients.remove(client)

    def broadcast(self, msg):
        logging.debug('broadcasting message to: %s', self.clients)
        for c in self.clients:
            c.sendMessage(msg)
            logging.debug('message sent to %s', c.peer)

# ---------------------------------------------------------------------------
#   Class Declaration
#     
# ---------------------------------------------------------------------------

@implementer(IRealm)
class publicHTMLRealm(object):
    def requestAvatar(self, avatarId, mind, *interfaces):
        if IResource in interfaces:
            return (IResource, siteResource, lambda: None)
        raise NotImplementedError()

# ---------------------------------------------------------------------------
#   Program Entry Point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse
    import sys
    import os
    import signal

    # Change the current directory to the location of the application
    os.chdir(os.path.dirname(os.path.realpath(sys.argv[0])))

    logging.basicConfig(level = logging.INFO, handlers = [logging.FileHandler(config.PATH + 'logfile.log'), logging.StreamHandler()])

    logging.debug('Logging system started, anything from here on gets logged')
    logging.info('FNEmonitor - SYSTEM STARTING...')
    observer = log.PythonLoggingObserver()
    observer.start()
    
    # Start update loop
    update_stats = task.LoopingCall(websock_update)
    update_stats.start(config.FREQUENCY)

    # Connect to fne_core
    report_client = reportClientFactory()
    reactor.connectTCP(config.FNEMON_IP, config.FNEMON_PORT, report_client)
    
    # Create websocket server to push content to clients
    dashboard_server = dashboardFactory('ws://*:9000')
    dashboard_server.protocol = dashboard
    reactor.listenTCP(9000, dashboard_server)

    # Start activity update loop
    update_act = task.LoopingCall(gen_activity)
    update_act.start(config.ACT_FREQUENCY)

    siteResource = File('./webroot')

    #TODO: password access doesn't work now
    #i should figure out why, but this was a hack at best

    passwd_db = InMemoryUsernamePasswordDatabaseDontUse()
    passwd_db.addUser(config.HTACCESS_USER, config.HTACCESS_PASS)
    portal = Portal(publicHTMLRealm(), [passwd_db])

    #portal = Portal(publicHTMLRealm())
    resource = HTTPAuthSessionWrapper(portal, [BasicCredentialFactory('auth')])

    # Create static web server to push initial index.html
    website = Site(resource)
    reactor.listenTCP(config.WEB_SERVER_PORT, website)

    reactor.run()
