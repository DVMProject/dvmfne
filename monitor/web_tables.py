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
from __future__ import print_function

import logging
import sys
import subprocess
import re

from pprint import pprint
from time import time, strftime, localtime
from cPickle import loads
from binascii import b2a_hex as h
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

from dmr_utils.utils import hex_str_3, int_id

from config import *

# Opcodes for the network-based reporting protocol
REPORT_OPCODES = {
    'CONFIG_REQ': '\x00',
    'CONFIG_SND': '\x01',
    'RRULES_REQ': '\x02',
    'RRULES_SND': '\x03',
    'CONFIG_UPD': '\x04',
    'RRULES_UPD': '\x05',
    'LINK_EVENT': '\x06',
    'CALL_EVENT': '\x07',
    'GRP_AFF_UPD': '\x08',
}

# Global Variables:
CONFIG           = {}
CTABLE           = {'MASTERS': {}, 'MASTER_CNT': 0, 'PEERS': {}, 'PEER_CNT': 0}
RULES            = {}
RTABLE           = {}
RTABLE['RULES']  = {}
GRP_AFF          = {}
GATABLE          = {}
RULES_RX         = ''
CONFIG_RX        = ''
LOGBUF           = deque(100*[''], 100)
RED              = '#d9534f'
GREEN            = '#5cb85c'
BLUE             = '#5bc0de'
ORANGE           = '#cc6500'
WHITE            = '#ffffff'

LOG_MAX          = 100
EOL_SCANAHEAD    = LOG_MAX / 2

# ---------------------------------------------------------------------------
#   Module Routines
# ---------------------------------------------------------------------------

# For importing HTML templates
def get_template(_file):
    with open(_file, 'r') as html:
        return html.read()

def process_act_log(_file):
    global LOG_MAX, EOL_SCANAHEAD
    _entries = []
    _line_cnt = 0
    with open(_file, 'r') as log:
        fwd_log = list(log)
        rev_log = reversed(fwd_log)
        for line in rev_log:
            if (re.search('(received RF|received group grant|received unit-to-unit grant|received unit registration|received group affiliation|received unit deregistration|received status update|received message update|received call alert|received ack response|received cancel service|received radio check|received radio inhibit|recieved radio uninhibit)', line) == None):
                continue
            if (re.search('(end of)', line) != None):
                continue

            warningRow = False
            peerId = line.split(' ')[0]
            logLineRaw = line.split(' ')[1:-1]
            rawData = logLineRaw[1:-1]

            dateUTC = rawData[0] + ' ' + rawData[1]
            mode = rawMode = rawData[2]
            src = rawData[3]
            type = ''

            if (src == 'Net'):
                continue

            if (re.search('(voice transmission|voice header|late entry)', line) != None):
                type = '<span class="span-normal">Voice Transmission</span>'
            if (re.search('(data transmission|data header)', line) != None):
                type = '<span class="span-normal">Data Transmission</span>'
#            if (re.search('(group grant request)', line) != None):
#                type = '<span class="span-success">Group Grant Request</span>'
#            if (re.search('(unit-to-unit grant request)', line) != None):
#                type = '<span class="span-success">Unit-to-Unit Grant Request</span>'
            if (re.search('(group affiliation request)', line) != None):
                type = '<span class="span-warning">Group Affiliation</span>'
            if (re.search('(group affiliation query command)', line) != None):
                type = '<span class="span-info">Group Affiliation Query</span>'
            if (re.search('(group affiliation query response)', line) != None):
                type = '<span class="span-success">Group Affiliation Query</span>'
            if (re.search('(unit registration request)', line) != None):
                type = '<span class="span-warning">Unit Registration</span>'
            if (re.search('(unit registration command)', line) != None):
                type = '<span class="span-info">Unit Registration Command</span>'
            if (re.search('(unit deregistration request)', line) != None):
                type = '<span class="span-warning">Unit De-Registration</span>'
            if (re.search('(status update)', line) != None):
                type = '<span class="span-info">Status Update</span>'
            if (re.search('(message update)', line) != None):
                type = '<span class="span-info">Message Update</span>'
            if (re.search('(call alert)', line) != None):
                type = '<span class="span-info">Call Alert</span>'
            if (re.search('(ack response)', line) != None):
                type = '<span class="span-success">ACK Response</span>'
#            if (re.search('(cancel service)', line) != None):
#                type = '<span class="span-danger">Cancel Service</span>'
            if (re.search('(radio check request)', line) != None):
                type = '<span class="span-info">Radio Check</span>'
            if (re.search('(radio check response)', line) != None):
                type = '<span class="span-success">Radio Check ACK</span>'
            if (re.search('(radio inhibit request)', line) != None):
                type = '<span class="span-danger">Radio Inhibit</span>'
                warningRow = True
            if (re.search('(radio inhibit response)', line) != None):
                type = '<span class="span-success">Radio Inhibit ACK</span>'
                warningRow = True
            if (re.search('(radio uninhibit request)', line) != None):
                type = '<span class="span-danger">Radio Uninhibit</span>'
                warningRow = True
            if (re.search('(radio uninhibit response)', line) != None):
                type = '<span class="span-success">Radio Uninhibit ACK</span>'
                warningRow = True

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

            if (re.search('(unit registration request|unit deregistration request|status update|message update|cancel service)', line) != None):
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

            name = '&nbsp;(' + _from + ')'

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
                        dur = ber = 'N/A'
                        if (mode == 'P25'):
                            if (len(rawStats) >= 2):
                                dur = '<td>' + rawStats[1].rstrip().replace(' seconds', 's') + '</td>'
                            else:
                                dur = '<td>0s</td>'

                            if (len(rawStats) >= 3):
                                ber = rawStats[2].rstrip().replace('BER: ', '').replace('%', '')
                            else:
                                ber = '0.0'
                        elif ((mode == 'DMR TS1') or (mode == 'DMR TS2')):
                            if (len(rawStats) >= 3):
                                dur = '<td>' + rawStats[2].rstrip().replace(' seconds', 's') + '</td>'
                            else:
                                dur = '<td>0s</td>'

                            if (len(rawStats) >= 4):
                                ber = rawStats[3].rstrip().replace('BER: ', '').replace('%', '')
                            else:
                                ber = '0.0'

                        if (ber == 'N/A'):
                            ber = '<td class="table-col-disabled">' + ber + '%</td>'
                        else:
                            if (float(ber) >= 0.0) and (float(ber) <= 1.9):
                                ber = '<td class="table-col-success">' + ber + '%</td>'
                            elif (float(ber) >= 2.0) and (float(ber) <= 2.9):
                                ber = '<td class="table-col-warn">' + ber + '%</td>'
                            elif (float(ber) >= 3.0):
                                ber = '<td class="table-col-danger">' + ber + '%</td>'
                        
                        durAndBer = dur + ber
                        break

            warnClass = ''
            if (warningRow):
                warnClass = 'class="table-row-danger"'

            entry = '<tr ' + warnClass + '>'
            entry += '<td style="text-align: left;">' + dateUTC + '</td>'
            entry += '<td>' + peerId + '</td>'
            entry += '<td>' + mode + '</td>'
            entry += '<td class="table-col-disabled"><b>' + type + '</b></td>'
            entry += '<td>' + _from + '</td>'
            entry += '<td>' + _to + '</td>'
            entry += durAndBer
            entry += '</tr>'
            _entries.append(entry)
    return (_entries)
            
# Build configuration and rules tables from config/rules dicts
# this currently is a timed call
def gen_activity():
    global ACTIVITY_LOG
    if True:
        _entries = process_act_log(ACTIVITY_LOG)
        dashboard_server.broadcast('c')
        for _message in _entries:
            if _message:
                dashboard_server.broadcast('a' + _message)

# Build the connections table
def build_ctable(_config):
    _stats_table = {'MASTERS': {}, 'MASTER_CNT': 0, 'PEERS': {}, 'PEER_CNT': 0}
    for _hbp, _hbp_data in _config.iteritems(): 
        if _hbp_data['Enabled'] == True:
            if _hbp_data['Mode'] == 'master':
                _stats_table['MASTERS'][_hbp] = {}
                _stats_table['MASTERS'][_hbp]['REPEAT'] = _hbp_data['Repeat']
                _stats_table['MASTERS'][_hbp]['PEERS'] = {}
                _stats_table['MASTERS'][_hbp]['PEER_CNT'] = 0
                for _peer in _hbp_data['PEERS']:
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)] = {}
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['CALLSIGN'] = _hbp_data['PEERS'][_peer]['CALLSIGN']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['CONNECTION'] = _hbp_data['PEERS'][_peer]['CONNECTION']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['IP'] = _hbp_data['PEERS'][_peer]['IP']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['PINGS_RECEIVED'] = _hbp_data['PEERS'][_peer]['PINGS_RECEIVED']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['LAST_PING'] = _hbp_data['PEERS'][_peer]['LAST_PING']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['PORT'] = _hbp_data['PEERS'][_peer]['PORT']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['RX_FREQ'] = _hbp_data['PEERS'][_peer]['RX_FREQ']
                    _stats_table['MASTERS'][_hbp]['PEERS'][int_id(_peer)]['TX_FREQ'] = _hbp_data['PEERS'][_peer]['TX_FREQ']
                    _stats_table['MASTERS'][_hbp]['PEER_CNT'] += 1 
                _stats_table['MASTER_CNT'] += 1
            elif _hbp_data['Mode'] == 'peer':
                _stats_table['PEERS'][_hbp] = {}
                _stats_table['PEERS'][_hbp]['CALLSIGN'] = _hbp_data['Callsign']
                _stats_table['PEERS'][_hbp]['PEER_ID'] = int_id(_hbp_data['PeerId'])
                _stats_table['PEERS'][_hbp]['MASTER_IP'] = _hbp_data['MasterAddress']
                _stats_table['PEERS'][_hbp]['STATS'] = _hbp_data['STATS']
                _stats_table['PEERS'][_hbp]['RX_FREQ'] = _hbp_data['RxFrequency']
                _stats_table['PEERS'][_hbp]['TX_FREQ'] = _hbp_data['TxFrequency']
                _stats_table['PEER_CNT'] += 1
                
    return(_stats_table)

def build_grp_aff_table(_grp_aff):
    _table = {}
    
    for _peer_id, _aff_data in _grp_aff.iteritems():
        _tgid_entries = _grp_aff[_peer_id]
        for _tgid in _tgid_entries:
            _rid_entries = _tgid_entries[_tgid]
            for _rid in _rid_entries:
                _table[_rid] = {}
                _table[_rid]['PEER_ID'] = _peer_id
                _table[_rid]['DST_ID'] = _tgid
  
    return _table

# ---------------------------------------------------------------------------
#   Rules Table Routines
# ---------------------------------------------------------------------------

def rules_sort(e):
    return e['SRC_GROUP'];

def build_rules_table(_rules):
    _stats_table = {}
    _now = time()
    _cnow = strftime('%Y-%m-%d %H:%M:%S', localtime(_now))
    
    for _rule, _rule_data in _rules.iteritems():
        _stats_table[_rule] = []

        _rules[_rule]['GROUP_VOICE'].sort(key=rules_sort)
        for rule_entry in _rules[_rule]['GROUP_VOICE']:
            rule_entry['SRC_GROUP'] = str(int_id(rule_entry['SRC_GROUP']))
            rule_entry['SRC_TS'] = str(rule_entry['SRC_TS'])
            rule_entry['DST_GROUP'] = str(int_id(rule_entry['DST_GROUP']))
            rule_entry['DST_TS'] = str(rule_entry['DST_TS'])

            rule_entry['ACTIVE'] = str(rule_entry['ACTIVE'])
            rule_entry['ROUTABLE'] = str(rule_entry['ROUTABLE'])

            for i in range(len(rule_entry['ON'])):
                rule_entry['ON'][i] = str(int_id(rule_entry['ON'][i]))

            rule_entry['TRIG_ON'] = ', '.join(rule_entry['ON'])

            for i in range(len(rule_entry['OFF'])):
                rule_entry['OFF'][i] = str(int_id(rule_entry['OFF'][i]))

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

# Build configuration and rules tables from config/rules dicts
# this currently is a timed call
build_time = time()
def build_stats():
    global build_time
    now = time()
    if True: #now > build_time + 1:
        if CONFIG:
            table = 'd' + dtemplate.render(_table=CTABLE)
            dashboard_server.broadcast(table)
            if (CTABLE['MASTER_CNT'] > 0) and (PRIMARY_MASTER != ''):
                table = 'm' + cmdtemplate.render(_table=CTABLE['MASTERS'][PRIMARY_MASTER])
                dashboard_server.broadcast(table)
        if RULES:
            table = 'b' + btemplate.render(_table=RTABLE['RULES'])
            dashboard_server.broadcast(table)
        if GRP_AFF:
            table = 'g' + gtemplate.render(_table=GATABLE)
            dashboard_server.broadcast(table)
        build_time = now

# Process in coming messages and take the correct action depending on the opcode
def process_message(_message):
    global CTABLE, CONFIG, RULES, RTABLE, GRP_AFF, GATABLE, CONFIG_RX, RULES_RX
    opcode = _message[:1]
    _now = strftime('%Y-%m-%d %H:%M:%S %Z', localtime(time()))
    
    if opcode == REPORT_OPCODES['CONFIG_SND']:
        logging.debug('got CONFIG_SND opcode')
        CONFIG = load_dictionary(_message)
        CONFIG_RX = strftime('%Y-%m-%d %H:%M:%S', localtime(time()))
        CTABLE = build_ctable(CONFIG)
    
    elif opcode == REPORT_OPCODES['RRULES_SND']:
        logging.debug('got RRULES_SND opcode')
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
        p = _message[1:].split(",")
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
            log_message = '[{}] UNKNOWN LOG MESSAGE'.format(_now)
            
        dashboard_server.broadcast('l' + log_message)
        LOGBUF.append(log_message)
    else:
        logging.debug('got unknown opcode: {}, message: {}'.format(repr(opcode), repr(_message[1:])))
        
def load_dictionary(_message):
    data = _message[1:]
    return loads(data)
    logging.debug('Successfully decoded dictionary')
 
# ---------------------------------------------------------------------------
#   Class Declaration
#     This implements the socket-based reporting logic.
# ---------------------------------------------------------------------------

class report(NetstringReceiver):
    def __init__(self):
        pass

    def connectionMade(self):
        pass

    def connectionLost(self, reason):
        pass
        
    def stringReceived(self, data):
        process_message(data)

# ---------------------------------------------------------------------------
#   Class Declaration
#     This implements the report service factory.
# ---------------------------------------------------------------------------

class reportClientFactory(ReconnectingClientFactory):
    def __init__(self):
        pass
        
    def startedConnecting(self, connector):
        logging.info('Initiating Connection to Server.')
        if 'dashboard_server' in locals() or 'dashboard_server' in globals():
            dashboard_server.broadcast('q' + 'Connection to FNE Established')

    def buildProtocol(self, addr):
        logging.info('Connected.')
        logging.info('Resetting reconnection delay')
        self.resetDelay()
        return report()

    def clientConnectionLost(self, connector, reason):
        logging.info('Lost connection.  Reason: %s', reason)
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)
        dashboard_server.broadcast('q' + 'Connection to FNE Lost')

    def clientConnectionFailed(self, connector, reason):
        logging.info('Connection failed. Reason: %s', reason)
        ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)

# ---------------------------------------------------------------------------
#   Class Declaration
#     This implements the dashboard communications.
# ---------------------------------------------------------------------------

class dashboard(WebSocketServerProtocol):
    def onConnect(self, request):
        logging.info('Client connecting: %s', request.peer)

    def onOpen(self):
        logging.info('WebSocket connection open.')
        self.factory.register(self)
        self.sendMessage('d' + str(dtemplate.render(_table=CTABLE)))
        self.sendMessage('b' + str(btemplate.render(_table=RTABLE['RULES'])))
        self.sendMessage('g' + str(gtemplate.render(_table=GATABLE)))
        for _message in LOGBUF:
            if _message:
                self.sendMessage('l' + _message)
        gen_activity()
        if (CTABLE['MASTER_CNT'] > 0) and (PRIMARY_MASTER != ''):
            self.sendMessage('m' + str(cmdtemplate.render(_table=CTABLE['MASTERS'][PRIMARY_MASTER])))

    def onMessage(self, payload, isBinary):
        if isBinary:
            logging.info('Binary message received: %s bytes', len(payload))
        else:
            _payload = payload.decode('utf8')
            _opcode = _payload[:1]
            if (_opcode == 'm') and (PRIMARY_MASTER != ''):
                _arguments = _payload.split(',')
                _peer_ip = _arguments[0][1:]
                _command = _arguments[1]
                _command_arg = _arguments[2]
                _dmr_slot = _arguments[3]
                _mot_mfid = _arguments[4]
                logging.info('Received system command: PEER IP %s COMMAND %s ARGUMENT %s MOT MFID %s', 
                             _peer_ip, _command, _command_arg, _mot_mfid)
                if DVM_CMD_TOOL != '':
                    if _mot_mfid == 'true':
                        subprocess.call([DVM_CMD_TOOL, '-a', _peer_ip, 'p25-set-mfid', '144'])

                    if _dmr_slot == '0':
                        subprocess.call([DVM_CMD_TOOL, '-a', _peer_ip, _command, _command_arg])
                    else:
                        subprocess.call([DVM_CMD_TOOL, '-a', _peer_ip, _command, _dmr_slot, _command_arg])

                    if _mot_mfid == 'true':
                        subprocess.call([DVM_CMD_TOOL, '-a', _peer_ip, 'p25-set-mfid', '0'])
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
            c.sendMessage(msg.encode('utf8'))
            logging.debug('message sent to %s', c.peer)

# ---------------------------------------------------------------------------
#   Class Declaration
#     This implements the root resource for the site.
# ---------------------------------------------------------------------------

class siteResource(Resource):
    isLeaf = True
    def getChild(self, path, request):
        return self

    def render(self, request):
        logging.info('static website requested: %s', request)
        if request.uri == '/':
            return index_html
        else:
            return 'Bad request'

# ---------------------------------------------------------------------------
#   Class Declaration
#     
# ---------------------------------------------------------------------------

@implementer(IRealm)
class publicHTMLRealm(object):
    def requestAvatar(self, avatarId, mind, *interfaces):
        if IResource in interfaces:
            return (IResource, siteResource(), lambda: None)
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

    logging.basicConfig(level = logging.INFO, handlers = [logging.FileHandler(PATH + 'logfile.log'), logging.StreamHandler()])

    logging.debug('Logging system started, anything from here on gets logged')
    logging.info('FNEmonitor - SYSTEM STARTING...')
    observer = log.PythonLoggingObserver()
    observer.start()
    
    env = Environment(
        loader = PackageLoader('web_tables', 'templates')
    )

    cmdtemplate = env.get_template('cmd_panel.html')
    dtemplate = env.get_template('link_table.html')
    btemplate = env.get_template('rules_table.html')
    gtemplate = env.get_template('group_affil_table.html')
    
    # Create Static Website index file
    index_html = get_template(PATH + 'index_template.html')
    index_html = index_html.replace('<<<system_name>>>', REPORT_NAME)
    
    # Start update loop
    update_stats = task.LoopingCall(build_stats)
    update_stats.start(FREQUENCY)

    # Connect to HBlink
    reactor.connectTCP(FNEMON_IP, FNEMON_PORT, reportClientFactory())
    
    # Create websocket server to push content to clients
    dashboard_server = dashboardFactory('ws://*:9000')
    dashboard_server.protocol = dashboard
    reactor.listenTCP(9000, dashboard_server)
   
    # Start activity update loop
    update_act = task.LoopingCall(gen_activity)
    update_act.start(10)

    passwd_db = InMemoryUsernamePasswordDatabaseDontUse()
    passwd_db.addUser(HTACCESS_USER, HTACCESS_PASS)

    portal = Portal(publicHTMLRealm(), [passwd_db])
    resource = HTTPAuthSessionWrapper(portal, [BasicCredentialFactory('auth')])

    # Create static web server to push initial index.html
    website = Site(resource)
    reactor.listenTCP(WEB_SERVER_PORT, website)

    reactor.run()
