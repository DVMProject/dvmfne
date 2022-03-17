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

import subprocess
import socket
import pickle

from binascii import b2a_hex as ahex
from binascii import a2b_hex as bhex
from random import randint
from hashlib import sha256
from time import time
from bitstring import BitArray
from csv import reader as csv_reader
from csv import DictReader as csv_dict_reader

from twisted.python import log
from twisted.internet.protocol import DatagramProtocol, Factory, Protocol
from twisted.protocols.basic import NetstringReceiver
from twisted.internet import reactor, task

from fne import fne_config
from fne import fne_log
from fne import fne_const
import json

# Global variables used whether we are a module or __main__
systems = {}
_act_log_lock = False
#TODO: fix this, but for now it's a quick little hack to get running
open_logfiles = {}

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

# ---------------------------------------------------------------------------
#   Module Routines
# ---------------------------------------------------------------------------

# Helper to perform initial FNE setup.
def setup_fne():
    import argparse
    import sys
    import os
    import signal
    import logging
    
    # Change the current directory to the location of the application
    os.chdir(os.path.dirname(os.path.realpath(sys.argv[0])))

    # CLI argument parser - handles picking up the config file from the command
    # line, and sending a "help" message
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', action = 'store', dest = 'ConfigFile', help = '/full/path/to/config.file (usually fne.cfg)')
    parser.add_argument('-l', '--logging', action = 'store', dest = 'LogLevel', help = 'Override config file logging level.')
    cli_args = parser.parse_args()

    # Ensure we have a path for the config file, if one wasn't specified, then
    # use the execution directory
    if not cli_args.ConfigFile:
        cli_args.ConfigFile = os.path.dirname(os.path.abspath(__file__)) + '/fne.cfg'

    # Call the external routine to build the configuration dictionary
    config = fne_config.build_config(cli_args.ConfigFile)
    
    # Call the external routing to start the system logger
    if cli_args.LogLevel:
        config['Log']['LogLevel'] = cli_args.LogLevel

    logger = fne_log.config_logging(config['Log'])

    logger.debug('Logging system started, anything from here on gets logged')
    logger.info('Digital Voice Modem FNE - SYSTEM STARTING...')

    observer = log.PythonLoggingObserver()
    observer.start()

    # Set up the signal handler
    def sig_handler(_signal, _frame):
        logger.info('Digital Voice Modem FNE is terminating with signal %s', str(_signal))
        fne_shutdown_handler(_signal, _frame, logger)
        logger.info('All system handlers executed - stopping reactor')
        reactor.stop()
        
    # Set signal handers so that we can gracefully exit if need be
    for sig in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(sig, sig_handler)

    # Initialize activity log
    act_log_file = setup_activity_log(config, logger)

    return config, logger, act_log_file

# Shut ourselves down gracefully by disconnecting from the masters and clients.
def fne_shutdown_handler(_signal, _frame, _logger):
    for system in systems:
        _logger.info('SHUTDOWN: DE-REGISTER SYSTEM: %s', 
                     system)
        systems[system].dereg()

# Timed loop used for reporting HBP status
# REPORT BASED ON THE TYPE SELECTED IN THE MAIN CONFIG FILE
def config_reports(_config, _logger, _factory):                 
    if _config['Reports']['Report']:
        def reporting_loop(_logger, _server):
            _logger.debug('Periodic reporting loop started')
            _server.send_config()
            _server.send_timed()
            
        _logger.info('Reporting services configured')
        
        report_server = _factory(_config, _logger)
        report_server.clients = []
        reactor.listenTCP(_config['Reports']['ReportPort'], report_server)
        
        reporting = task.LoopingCall(reporting_loop, _logger, report_server)
        reporting.start(_config['Reports']['ReportInterval'])

    else:
        def reporting_loop(_logger, server):
            return

        _logger.info('Reporting services disabled')
        report_server = _factory(_config, _logger)
   
    return report_server

# Helper to split a file.
def split_file(filePath, fin, percentage=0.50):
    foutName = filePath + '.1'
    with open(foutName, 'a+') as fout:
        content = list(fin)
        fin.seek(0)

        nLines = sum(1 for line in fin)
        fin.seek(0)

        nTrain = int(nLines * percentage)
        nValid = nLines - nTrain

        fin.truncate()

        i = 0
        for line in content:
            if (i < nTrain) or (nLines - i > nValid):
                fout.write(line)
                i += 1
            else:
                fin.write(line)

        fout.flush()
        fout.close()
        fin.flush()
        fin.seek(0, 2)

# Helper to setup the system activity logs.
def setup_activity_log(_config, _logger):
    if _config['Log']['AllowActTrans'] == False:
        return None

    act_log_file = open(_config['Log']['ActivityLogFile'], "a+")
    def act_log_split_loop(_actLogFile, _filePath):
        global _act_log_lock
        _actLogFile.seek(0)
                
        nLines = sum(1 for line in _actLogFile)
        _actLogFile.seek(0)
        if (nLines < 2048):
            _actLogFile.seek(0, 2)
        else:
            _act_log_lock = True
            split_file(_filePath, _actLogFile)
            _actLogFile.seek(0, 2)
            _act_log_lock = False
            
    _logger.info('Activity Log Transfer services configured')
        
    logsplitter = task.LoopingCall(act_log_split_loop, act_log_file, _config['Log']['ActivityLogFile'])
    logsplitter.start(3600)
    return (act_log_file)

#TODO: make this into a class
# Helpers for peer diagnostic logs.
def get_peer_diag_log_filename(_config, _peer_id):
    if _config['Log']['AllowDiagTrans'] == False:
        return None

    diag_log_filepath = _config['Log']['DiagLogPath'] + str(_peer_id) + ".log"
    return (diag_log_filepath)

def get_peer_diag_log_handler(_config, _logger, _peer_id):
    global open_logfiles
    if _config['Log']['AllowDiagTrans'] == False:
        return None

    if (_peer_id in open_logfiles):
        diag_log_file = open_logfiles[_peer_id]
        print("Type of found logfile: {}".format(type(diag_log_file)))
        
    else:
        diag_log_filepath = get_peer_diag_log_filename(_config, _peer_id)
        diag_log_file = open(diag_log_filepath, "a+")
        open_logfiles[_peer_id] = diag_log_file

    return (diag_log_file)

def close_peer_logs():
    global open_logfiles
    for _peer_id in open_logfiles:
        open_logfiles[_peer_id].close()
    return True

# ---------------------------------------------------------------------------
#   String Utility Routines
# ---------------------------------------------------------------------------

# Create a 2 byte hex string from an integer
def hex_str_2(_int_id):
    try:
        return format(_int_id,'x').rjust(4,'0')
    except TypeError:
        raise

# Create a 3 byte hex string from an integer
def hex_str_3(_int_id):
    try:
        return format(_int_id,'x').rjust(6,'0')
    except TypeError:
        raise

# Create a 4 byte hex string from an integer
def hex_str_4(_int_id):
    try:
        return format(_int_id,'x').rjust(8,'0')
    except TypeError:
        raise

# Convert a hex string to an int (peer ID, etc.)
def int_id(_hex_string):
    return int(_hex_string, 16)

def int_to_bytes(numIn):
    return numIn.to_bytes(4, "big")

def bytes_to_int(bytesIn):
    return int.from_bytes(bytesIn, "big")

# ---------------------------------------------------------------------------
#   Dictionary Routines
# ---------------------------------------------------------------------------

def mk_id_dict(_path, _file):
    dict = {}
    try:
        with open(_path + _file, 'rU') as _handle:
            ids = csv_reader(_handle, dialect='excel', delimiter=',')
            for row in ids:
                dict[int(row[0])] = (row[1])
            _handle.close
            return dict
    except IOError:
        return dict

# ---------------------------------------------------------------------------
#   Class Declaration
#     Used to parse out AMBE and send to gateway.
# ---------------------------------------------------------------------------

class AMBE:
    def __init__(self, _config, _logger):
        self._CONFIG = _config
        self._logger = _logger

        self._sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self._exp_ip = self._CONFIG['AMBE']['Address']
        self._exp_port = self._CONFIG['AMBE']['Port']

    def parse_ambe(self, _client, _data):
        _seq = int_id(_data[4:5])
        _srcID = int_id(_data[5:8])
        _dstID = int_id(_data[8:11])
        _rptID = int_id(_data[11:15])
        _bits = int_id(_data[15:16])       # SCDV NNNN (Slot|Call type|Data|Voice|Seq or Data type)
        _slot = 2 if _bits & 0x80 else 1
        _callType = 1 if (_bits & 0x40) else 0
        _frameType = (_bits & 0x30) >> 4
        _voiceSeq = (_bits & 0x0f)
        _streamID = int_id(_data[16:20])
        self._logger.debug('(%s) SEQ %d SRC_ID %d DST_ID %d PEER %d BITS %0X TS %d CALLTYPE %d FRAMETYPE %d VOICESEQ %d [STREAM ID %0X]', 
                           _client, _seq, _srcID, _dstID, _rptID, _bits, _slot, _callType, _frameType, _voiceSeq, _streamID)

        #self._logger.debug('Frame 1:(%s)', self.ByteToHex(_data))
        _dmr_frame = BitArray('0x' + ahex(_data[20:]))
        _ambe = _dmr_frame[0:108] + _dmr_frame[156:264]
        #_sock.sendto(_ambe.tobytes(), ("127.0.0.1", 31000))

        ambeBytes = _ambe.tobytes()
        self._sock.sendto(ambeBytes[0:9], (self._exp_ip, self._exp_port))
        self._sock.sendto(ambeBytes[9:18], (self._exp_ip, self._exp_port))
        self._sock.sendto(ambeBytes[18:27], (self._exp_ip, self._exp_port))

# ---------------------------------------------------------------------------
#   Class Declaration
#     Used to parse out packet data and send to gateway.
# ---------------------------------------------------------------------------

class PacketData:
    def __init__(self, _fne, _config, _logger):
        self._FNE = _fne
        self._CONFIG = _config
        self._logger = _logger

        self._sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self._gateway = self._CONFIG['PacketData']['Gateway']
        self._gateway_port = self._CONFIG['PacketData']['GatewayPort']

        self._port = self._CONFIG['PacketData']['Port']

        class UDP_IMPORT(DatagramProtocol):
            def __init__(self, callback_function):
                self.func = callback_function

            def datagramReceived(self, _data, hostInfo):    # hostInfo is tuple; converted from 2.x to 3.x syntax
                self.func(_data, hostInfo)
        
        self.udp_port = reactor.listenUDP(self._port, UDP_IMPORT(self.packet_datagramReceived))

    def send_data(self, _data):
        self._sock.sendto(_data, (self._gateway, self._gateway_port))

    # Twisted callback with data from socket
    def packet_datagramReceived(self, _data, hostInfo):   # hostInfo is tuple; converted from 2.x to 3.x syntax
        self._FNE.send_peers(_data)

# ---------------------------------------------------------------------------
#   Class Declaration
#     This implements the core network FNE logic.
# ---------------------------------------------------------------------------

class coreFNE(DatagramProtocol):
    def __init__(self, _name, _config, _logger, _act_log_file, _report):
        # Define a few shortcuts to make the rest of the class more readable
        self._CONFIG = _config
        self._system = _name
        self._logger = _logger
        self._report = _report
        self._act_log_file = _act_log_file
        self._config = self._CONFIG['Systems'][self._system]
        
        # Define shortcuts and generic function names based on the type of
        # system we are
        if self._config['Mode'] == 'master':
            self._peers = self._CONFIG['Systems'][self._system]['PEERS']
            self.send_system = self.send_peers
            self.maintenance_loop = self.master_maintenance_loop
            self.datagramReceived = self.master_datagramReceived
            self.dereg = self.master_dereg
        
        elif self._config['Mode'] == 'peer':
            self._stats = self._config['STATS']
            self.send_system = self.send_master
            self.maintenance_loop = self.peer_maintenance_loop
            self.datagramReceived = self.peer_datagramReceived
            self.dereg = self.peer_dereg
        
        # Configure for AMBE audio export if enabled
        if self._config['ExportAMBE']:
            self._ambe = AMBE(self._CONFIG, self._logger)

        # Configure for raw packet data export if enabled
        if self._config['PacketData']:
            self._packet_data = PacketData(self, self._CONFIG, self._logger)

    def startProtocol(self):
        # Set up periodic loop for tracking pings from peers.  Run every
        # 'PING_TIME' seconds
        self._system_maintenance = task.LoopingCall(self.maintenance_loop)
        self._system_maintenance_loop = self._system_maintenance.start(self._CONFIG['Global']['PingTime'])

    def dmrd_validate(self, _peer_id, _rf_src, _dst_id, _slot, _call_type, _frame_type, _dtype_vseq, _stream_id):
        pass

    def dmrd_received(self, _peer_id, _rf_src, _dst_id, _seq, _slot, _call_type, _frame_type, _dtype_vseq, _stream_id, _data):
        pass

    def p25d_preprocess(self, _peer_id, _rf_src, _dst_id, _call_type, _duid, _dtype_vseq, _stream_id, _data):
        pass

    def p25d_validate(self, _peer_id, _rf_src, _dst_id, _call_type, _duid, _dtype_vseq, _stream_id):
        pass

    def p25d_received(self, _peer_id, _rf_src, _dst_id, _call_type, _duid, _dtype_vseq, _stream_id, _data):
        pass

    def peer_ignored(self, _peer_id, _rf_src, _dst_id, _call_type, _slot, _dtype_vseq, _stream_id, _is_source):
        pass

    def peer_connected(self, _peer_id, _peer):
        pass
    
    def send_peers(self, _packet):
        for _peer in self._peers:
            self.send_peer(_peer, _packet)

    def send_peer(self, _peer, _packet):
        _ip = self._peers[_peer]['IP']
        _port = self._peers[_peer]['PORT']
        self.transport.write(_packet, (_ip, _port))
        if self._CONFIG['Log']['RawPacketTrace']:
            self._logger.debug('(%s) PEER %s Network Transmitted (to %s:%s) -- %s', self._system, self._peers[_peer]['PEER_ID'],
                               self._peers[_peer]['IP'], self._peers[_peer]['PORT'], ahex(_packet))

    def send_master(self, _packet):
        self.transport.write(_packet.encode(), (self._config['MasterAddress'], self._config['MasterPort']))
        if self._CONFIG['Log']['RawPacketTrace']:
            self._logger.debug('(%s) Network Transmitted (to %s:%s) -- %s', self._system, 
                               self._config['MasterAddress'], self._config['MasterPort'], ahex(_packet))

    def master_dereg(self):
        for _peer in self._peers:
            self.send_peer(_peer, fne_const.TAG_MASTER_CLOSING + str(_peer).encode())
            self._logger.info('(%s) De-Registration sent to PEER %s', self._system, self._peers[_peer]['PEER_ID'])
            
    def peer_dereg(self):
        self.send_master(fne_const.TAG_REPEATER_CLOSING + self._config['PeerId'])
        self._logger.info('(%s) De-Registration sent to MASTER (%s:%s)', self._system, self._config['MasterAddress'], self._config['MasterPort'])

    def peer_trnslog(self, _message):
        self.send_master(fne_const.TAG_TRANSFER_ACT_LOG + self._config['PeerId'] + _message)
    
    def send_peer_wrids(self, _peer, _rids):
        from struct import pack
        if self._config['Mode'] == 'master':
            data = pack('>I', int(len(_rids)))
            for rid in _rids:
                data = data + pack('>I', int(rid))

            self.send_peer(_peer, fne_const.TAG_MASTER_WL_RID + data)
            self._logger.debug('(%s) Whitelist RIDs sent to PEER %s', self._system, self._peers[_peer]['PEER_ID'])

    def master_send_wrids(self, _rids):
        try:
            if self._config['Mode'] == 'master':
                for _peer in self._peers:
                    self.send_peer_wrids(_peer, _rids)
        except:
            self._logger.error('(%s) Failed to send whitelist RIDs', self._system)

    def send_peer_brids(self, _peer, _rids):
        from struct import pack
        if self._config['Mode'] == 'master':
            data = pack('>I', int(len(_rids))) 
            for rid in _rids:
                data = data + pack('>I', int(rid))

            self.send_peer(_peer, fne_const.TAG_MASTER_BL_RID + data)
            self._logger.debug('(%s) Blacklist RIDs sent to PEER %s', self._system, self._peers[_peer]['PEER_ID'])

    def master_send_brids(self, _rids):
        try:
            if self._config['Mode'] == 'master':
                for _peer in self._peers:
                    self.send_peer_brids(_peer, _rids)
        except:
            self._logger.error('(%s) Failed to send blacklist RIDs', self._system)

    def send_peer_tgids(self, _peer, _tgids):
        from struct import pack
        if self._config['Mode'] == 'master':
            data = pack('>I', int(len(_tgids)))
            for tid in _tgids:
                data = data + pack('>I', int(tid)) + pack('>B', int(_tgids[tid][1]))

            self.send_peer(_peer, fne_const.TAG_MASTER_ACTIVE_TGS + data)
            self._logger.debug('(%s) Active TGIDs sent to PEER %s', self._system, self._peers[_peer]['PEER_ID'])

    def master_send_tgids(self, _system, _tgids):
        try:
            if self._config['Mode'] == 'master':
                for _peer in self._peers:
                    if _peer['SYSTEM'] == _system:
                        self.send_peer_tgids(_peer, _tgids)
        except:
            self._logger.error('(%s) Failed to send talkgroup IDs', self._system)

    def send_peer_disabled_tgids(self, _peer, _tgids):
        from struct import pack
        if self._config['Mode'] == 'master':
            data = pack('>I', int(len(_tgids)))
            for tid in _tgids:
                data = data + pack('>I', int(tid)) + pack('>B', int(_tgids[tid][1]))

            self.send_peer(_peer, fne_const.TAG_MASTER_DEACTIVE_TGS + data)
            self._logger.debug('(%s) Deactivated TGIDs sent to PEER %s', self._system, self._peers[_peer]['PEER_ID'])

    def master_send_disabled_tgids(self, _system, _tgids):
        try:
            if self._config['Mode'] == 'master':
                for _peer in self._peers:
                    if _peer['SYSTEM'] == _system:
                        self.send_peer_disabled_tgids(_peer, _tgids)
        except:
            self._logger.error('(%s) Failed to send talkgroup IDs', self._system)
    
    # Aliased in __init__ to maintenance_loop if system is a master
    def master_maintenance_loop(self):
        for _peer in self._peers:
            _this_peer = self._peers[_peer]
            # Check to see if any of the peers have been quiet (no ping)
            # longer than allowed
            if _this_peer['LAST_PING'] + self._CONFIG['Global']['PingTime'] * self._CONFIG['Global']['MaxMissed'] < time():
                self._logger.info('(%s) PEER %s has timed out', self._system, _this_peer['PEER_ID'])
                # remove any timed out peers from the configuration
                del self._CONFIG['Systems'][self._system]['PEERS'][_peer]
    
    # Aliased in __init__ to maintenance_loop if system is a peer
    def peer_maintenance_loop(self):
        # If we're not connected, zero out the stats and send a login request
        # RPTL
        if self._stats['CONNECTION'] == 'NO' or self._stats['CONNECTION'] == 'RTPL_SENT':
            self._stats['PINGS_SENT'] = 0
            self._stats['PINGS_ACKD'] = 0
            self._stats['CONNECTION'] = 'RTPL_SENT'
            self.send_master('RPTL' + self._config['PeerId'])
            self._logger.info('(%s) Sending login request to MASTER (%s:%s)', self._system, self._config['MasterAddress'], self._config['MasterPort'])
        # If we are connected, sent a ping to the master and increment the
        # counter
        if self._stats['CONNECTION'] == 'YES':
            self.send_master('RPTPING' + self._config['PeerId'])
            self._stats['PINGS_SENT'] += 1
            self._logger.debug('(%s) RPTPING Sent to MASTER. Pings since connected: %s', self._system, self._stats['PINGS_SENT'])

    # Aliased in __init__ to datagramReceived if system is a master
    def master_datagramReceived(self, _data, hostInfo): # hostInfo is a tuple; converted from 2.x to 3.x syntax
        _host, _port = hostInfo
        global _act_log_lock
        if self._CONFIG['Log']['RawPacketTrace']:
            self._logger.debug('(%s) Network Received (from %s:%s) -- %s', self._system, _host, _port, ahex(_data))

        # process opcode from data, usually first 4 bytes but can be a varied length
        # depending on the opcode
        #print("Data packet")
        #print(_data)
        if _data[:4] == fne_const.TAG_DMR_DATA: # fne_const.TAG_DMR_DATA -- encapsulated DMR data frame
            _peer_id = int.from_bytes(_data[11:15], "big")
            if (_peer_id in self._peers and self._peers[_peer_id]['CONNECTION'] == 'YES' and 
                self._peers[_peer_id]['IP'] == _host and self._peers[_peer_id]['PORT'] == _port):
                _seq = _data[4]
                _rf_src = _data[5:8]
                _dst_id = _data[8:11]
                _bits = int_id(_data[15])
                _slot = 2 if (_bits & 0x80) else 1
                _call_type = 'unit' if (_bits & 0x40) else 'group'
                _frame_type = (_bits & 0x30) >> 4
                _dtype_vseq = (_bits & 0xF) # data, 1=voice header, 2=voice terminator; voice, 0=burst A ...  5=burst F
                _stream_id = _data[16:20]
                #self._logger.debug('(%s) DMRD - SEQ %s SRC_ID %s DST_ID %s', self._system, int_id(_seq), int_id(_rf_src), int_id(_dst_id))

                if self.dmrd_validate(_peer_id, _rf_src, _dst_id, _slot, _call_type, _frame_type, _dtype_vseq, _stream_id) == True:
                    if self.peer_ignored(_peer_id, _rf_src, _dst_id, _call_type, _slot, _dtype_vseq, _stream_id, True) == True:
                        return

                    # If AMBE audio exporting is configured...
                    if self._config['ExportAMBE']:
                        self._ambe.parse_ambe(self._system, _data)

                    # If packet data exporting is configured...
                    if self._config['PacketData']:
                        if ((_frame_type == fne_const.FT_DATA_SYNC) and ((_dtype_vseq == fne_const.DT_CSBK) or (_dtype_vseq == fne_const.DT_DATA_HEADER) or
                                                                         (_dtype_vseq == fne_const.DT_RATE_12_DATA) or (_dtype_vseq == fne_const.DT_RATE_34_DATA) or
                                                                         (_dtype_vseq == fne_const.DT_RATE_1_DATA))):
                            self._packet_data.send_data(_data)

                    # The basic purpose of a master is to repeat to the peers
                    if self._config['Repeat'] == True:
                        for _peer in self._peers:
                            if _peer != _peer_id:
                                if self.peer_ignored(_peer, _rf_src, _dst_id, _call_type, _slot, _dtype_vseq, _stream_id, False) == False:
                                    self.send_peer(_peer, _data)
                                    self._logger.debug('(%s) DMRD: Packet TS %s SRC_PEER %s DST_ID %s DST_PEER %s [STREAM ID %s]', self._system, 
                                                       _slot, _peer_id, int_id(_dst_id), int_id(_peer), int_id(_stream_id))
                                else:
                                    continue

                    # Userland actions -- typically this is the function you
                    # subclass for an application
                    self.dmrd_received(_peer_id, _rf_src, _dst_id, _seq, _slot, _call_type, _frame_type, _dtype_vseq, _stream_id, _data)

        elif _data[:4] == fne_const.TAG_P25_DATA: # fne_const.TAG_P25_DATA -- encapsulated P25 data frame
            _peer_id = int.from_bytes(_data[11:15], "big")
            if (_peer_id in self._peers and self._peers[_peer_id]['CONNECTION'] == 'YES' and
                self._peers[_peer_id]['IP'] == _host and self._peers[_peer_id]['PORT'] == _port):
                _rf_src = bytes_to_int(_data[5:8])
                _dst_id = bytes_to_int(_data[8:11])
                _call_type = 'unit' if (_data[4] == fne_const.P25_LC_PRIVATE) else 'group'
                _duid = _data[22]
                _dtype_vseq = fne_const.FT_VOICE if ((_duid != fne_const.P25_DUID_TDU) and (_duid != fne_const.P25_DUID_TDULC)) else fne_const.DT_TERMINATOR_WITH_LC
                _stream_id = bytes_to_int(_data[16:20])

                if self.p25d_validate(_peer_id, _rf_src, _dst_id, _call_type, _duid, _dtype_vseq, _stream_id) == True:
                    self.p25d_preprocess(_peer_id, _rf_src, _dst_id, _call_type, _duid, _dtype_vseq, _stream_id, _data)
                    if self.peer_ignored(_peer_id, _rf_src, _dst_id, _call_type, 1, _dtype_vseq, _stream_id, True) == True:
                        return

                    # If packet data exporting is configured...
                    if self._config['PacketData']:
                        if ((_duid == fne_const.P25_DUID_TSDU) or (_duid == fne_const.P25_DUID_PDU)):
                            self._packet_data.send_data(_data)

                    # The basic purpose of a master is to repeat to the peers
                    if self._config['Repeat'] == True:
                        for _peer in self._peers:
                            if _peer != _peer_id:
                                if self.peer_ignored(_peer, _rf_src, _dst_id, _call_type, 1, _dtype_vseq, _stream_id, False) == False:
                                    self.send_peer(_peer, _data)
                                    self._logger.debug('(%s) P25D: Packet SRC_PEER %s DST_ID %s DST_PEER %s [STREAM ID %s]', self._system,
                                                       _peer_id, _dst_id, _peer, _stream_id)
                                else:
                                    continue

                    # Userland actions -- typically this is the function you
                    # subclass for an application
                    self.p25d_received(_peer_id, _rf_src, _dst_id, _call_type, _duid, _dtype_vseq, _stream_id, _data)

        elif _data[:4] == fne_const.TAG_REPEATER_LOGIN: # fne_const.TAG_REPEATER_LOGIN -- a repeater wants to login
            #convert the incoming bytes to an int
            _peer_id = int.from_bytes(_data[4:8], "big")
            if _peer_id:
                # Build the configuration data structure for the peer
                self._peers.update({_peer_id: {
                        'CONNECTION': 'RPTL-RECEIVED',
                        'PINGS_RECEIVED': 0,
                        'LAST_PING': time(),
                        'IP': _host,
                        'PORT': _port,
                        'SALT': randint(0,0xFFFFFFFF),
                        'PEER_ID': _peer_id,

                        'IDENTITY': '',
                        'RX_FREQ': '',
                        'TX_FREQ': '',

                        'LATITUDE': '',
                        'LONGITUDE': '',
                        'HEIGHT': '',
                        'LOCATION': '',

                        'TX_OFFSET': '',
                        'CH_BW': '',
                        'CHANNEL_ID': '',
                        'CHANNEL_NO': '',
                        'TX_POWER': '',

                        'SOFTWARE_ID': '',

                        'RCON_PASSWORD': '',
                        'RCON_PORT': '',

                        'DIAG_LOG_FILE': None,
                }})

                self._logger.info('(%s) Repeater logging in with PEER %s, %s:%s', self._system, _peer_id, _host, _port)

                _salt_str = self._peers[_peer_id]['SALT'].to_bytes(4, "big")
                self.send_peer(_peer_id, fne_const.TAG_REPEATER_ACK + _salt_str)
                self._peers[_peer_id]['CONNECTION'] = 'CHALLENGE_SENT'
                self._peers[_peer_id]['SYSTEM'] = self._system
                self._logger.info('(%s) Sent Challenge Response to PEER %s for login %s', self._system, _peer_id, self._peers[_peer_id]['SALT'])

            else:
                self.transport.write(fne_const.TAG_MASTER_NAK + _peer_id, (_host, _port))
                self._logger.warning('(%s) Invalid login from PEER %s', self._system, _peer_id)

        elif _data[:4] == fne_const.TAG_REPEATER_AUTH: # fne_const.TAG_REPEATER_AUTH -- Repeater has answered our login challenge
            _peer_id = int.from_bytes(_data[4:8], "big")
            _peer_bytes = _data[4:8]
            if (_peer_id in self._peers and self._peers[_peer_id]['CONNECTION'] == 'CHALLENGE_SENT' and
                self._peers[_peer_id]['IP'] == _host and self._peers[_peer_id]['PORT'] == _port):
                _this_peer = self._peers[_peer_id]
                _this_peer['LAST_PING'] = time()
                _sent_hash = _data[8:]
                _salt_str = self._peers[_peer_id]['SALT'].to_bytes(4, "big")
                #salt_bytes = _this_peer['SALT'].to_bytes(4, byteorder="big")
                _calc_hash = sha256(_salt_str + self._config['Passphrase'].encode()).digest()
                if _sent_hash == _calc_hash:
                    _this_peer['CONNECTION'] = 'WAITING_CONFIG'
                    
                    self.send_peer(_peer_id, fne_const.TAG_REPEATER_ACK + _peer_bytes)
                    self._logger.info('(%s) PEER %s has completed the login exchange successfully', self._system, _this_peer['PEER_ID'])
                else:
                    self._logger.warning('(%s) PEER %s has FAILED the login exchange', self._system, _this_peer['PEER_ID'])
                    self.transport.write(fne_const.TAG_MASTER_NAK + _peer_bytes, (_host, _port))
                    del self._peers[_peer_id]
            else:
                self.transport.write(fne_const.TAG_MASTER_NAK + _peer_bytes, (_host, _port))
                self._logger.warning('(%s) RPTK from unauth PEER %s', self._system, _peer_id)

        elif _data[:4] == fne_const.TAG_REPEATER_CONFIG: # fne_const.TAG_REPEATER_CONFIG -- Repeater is sending it's configuration
            _peer_id = int.from_bytes(_data[4:8], "big")
            if (_peer_id in self._peers and self._peers[_peer_id]['CONNECTION'] == 'WAITING_CONFIG' and
                self._peers[_peer_id]['IP'] == _host and self._peers[_peer_id]['PORT'] == _port):
                _this_peer = self._peers[_peer_id]
                jsonBytes = _data[8:]
                peerCfg = json.loads(jsonBytes.decode())
                peerInfo = peerCfg['info']
                peerChannel = peerCfg['channel']
                peerRcon = peerCfg['rcon']

                _this_peer['CONNECTION'] = 'YES'
                _this_peer['PINGS_RECEIVED'] = 0
                _this_peer['LAST_PING'] = time()

                _this_peer['IDENTITY'] = peerCfg['identity']
                _this_peer['RX_FREQ'] = peerCfg['rxFrequency']
                _this_peer['TX_FREQ'] = peerCfg['txFrequency']

                _this_peer['LATITUDE'] = peerInfo['latitude']
                _this_peer['LONGITUDE'] = peerInfo['latitude']
                _this_peer['HEIGHT'] = peerInfo['latitude']
                _this_peer['LOCATION'] = peerInfo['latitude']
                _this_peer['TX_OFFSET'] = peerChannel['txOffsetMhz']
                _this_peer['CH_BW'] = peerChannel['chBandwidthKhz']
                _this_peer['CHANNEL_ID'] = peerChannel['channelId']
                _this_peer['CHANNEL_NO'] = peerChannel['channelNo']
                _this_peer['TX_POWER'] = peerChannel['txPower']
                _this_peer['RCON_PASSWORD'] = peerRcon['password']
                _this_peer['RCON_PORT'] = peerRcon['port']

                # setup peer diagnostics log
                if self._CONFIG['Log']['AllowDiagTrans'] == True:
                    diag_log_file = get_peer_diag_log_filename(self._CONFIG, self._logger, _peer_id)
                    _this_peer['DIAG_LOG_FILE'] = diag_log_file

                self.send_peer(_peer_id, fne_const.TAG_REPEATER_ACK + _peer_id.to_bytes(4, "big"))
                self._logger.info('(%s) PEER %s has sent configuration', self._system, _this_peer['PEER_ID'])
                self._logger.info('(%s) PEER %s Connection from PEER Completed', self._system, _this_peer['PEER_ID'])

                # Userland actions -- typically this is the function you
                # subclass for an application
                self.peer_connected(_peer_id, _this_peer)
            else:
                self.transport.write(fne_const.TAG_MASTER_NAK + _peer_id.to_bytes(4, "big"), (_host, _port))
                self._logger.warning('(%s) Configuration from unauth PEER %s', self._system, _peer_id)

        elif _data[:5] == fne_const.TAG_REPEATER_CLOSING: # fne_const.TAG_REPEATER_CLOSING -- Disconnect command
            _peer_id = int.from_bytes(_data[5:9], "big")
            if (_peer_id in self._peers and self._peers[_peer_id]['CONNECTION'] == 'YES' and
                self._peers[_peer_id]['IP'] == _host and self._peers[_peer_id]['PORT'] == _port):
                self._logger.info('(%s) PEER %s is closing down', self._system, _peer_id)
                self.transport.write(fne_const.TAG_MASTER_NAK + _peer_id.to_bytes(4, "big"), (_host, _port))

                # setup peer diagnostics log
                if self._CONFIG['Log']['AllowDiagTrans'] == True:
                    if self._peers[_peer_id]['DIAG_LOG_FILE'] != None:
                        diag_log_file = self._peers[_peer_id]['DIAG_LOG_FILE']
                        close_peer_logs()
                        _this_peer['DIAG_LOG_FILE'] = None

                del self._peers[_peer_id]

        elif _data[:7] == fne_const.TAG_REPEATER_PING: # fne_const.TAG_REPEATER_PING -- peer is pinging us
            _peer_id = int.from_bytes(_data[7:11], "big")
            if (_peer_id in self._peers and self._peers[_peer_id]['CONNECTION'] == "YES" and
                self._peers[_peer_id]['IP'] == _host and self._peers[_peer_id]['PORT'] == _port):
                self._peers[_peer_id]['PINGS_RECEIVED'] += 1
                self._peers[_peer_id]['LAST_PING'] = time()
                self.send_peer(_peer_id, fne_const.TAG_MASTER_PONG + _peer_id.to_bytes(4, "big"))
                self._logger.debug('(%s) Received and answered RPTPING from PEER %s', self._system, _peer_id)
            else:
                self.transport.write(fne_const.TAG_MASTER_NAK + _peer_id.to_bytes(4, "big"), (_host, _port))
                self._logger.warning('(%s) RPTPING from unauth PEER %s', self._system, _peer_id)

        elif _data[:7] == fne_const.TAG_TRANSFER_ACT_LOG: # fne_const.TAG_TRANSFER_ACT_LOG -- peer is transferring activity log data to us
            if self._CONFIG['Log']['AllowActTrans'] == True and _act_log_lock == False:
                _peer_id = int.from_bytes(_data[7:11], "big")
                if (_peer_id in self._peers and self._peers[_peer_id]['CONNECTION'] == "YES" and
                    self._peers[_peer_id]['IP'] == _host and self._peers[_peer_id]['PORT'] == _port):
                    _msg = _data[11:-1]
                    self._act_log_file.seek(0, 2)
                    self._act_log_file.write(str(_peer_id) + ' ' + _msg + '\n')
                    self._act_log_file.flush()

        elif _data[:8] == fne_const.TAG_TRANSFER_DIAG_LOG: # fne_const.TAG_TRANSFER_DIAG_LOG -- peer is transferring diagnostics log data to us
            if self._CONFIG['Log']['AllowDiagTrans'] == True:
                _peer_id = int.from_bytes(_data[8:12], "big")
                if (_peer_id in self._peers and self._peers[_peer_id]['CONNECTION'] == "YES" and
                    self._peers[_peer_id]['IP'] == _host and self._peers[_peer_id]['PORT'] == _port):
                    _msg = _data[12:-1]
                    diag_log_file = self._peers[_peer_id]['DIAG_LOG_FILE']
                    if diag_log_file != None:
                        diag_log_file.seek(0, 2)
                        diag_log_file.write(str(_peer_id) + ' ' + _msg + '\n')
                        diag_log_file.flush()

        else:
            try:
                self._logger.error('(%s) Unrecognized command PEER %s PACKET %s', self._system, _peer_id, ahex(_data))
            except UnboundLocalError:
                self._logger.error('(%s) Unrecognized command %s PACKET %s', self._system, _data[:9], ahex(_data))
        
    # Aliased in __init__ to datagramReceived if system is a peer
    def peer_datagramReceived(self, _data, hostInfo): # hostInfo is tuple; converted from 2.x to 3.x syntax
        _host, _port = hostInfo
        if self._CONFIG['Log']['RawPacketTrace']:
            self._logger.debug('(%s) Network Received (from %s:%s) -- %s', self._system, _host, _port, ahex(_data))

        # validate that we receveived this packet from the master - security check!
        if self._config['MasterAddress'] == _host and self._config['MasterPort'] == _port:
            # process opcode from data, usually first 4 bytes but can be a varied length
            # depending on the opcode
            if _data[:4] == fne_const.TAG_DMR_DATA: # fne_const.TAG_DMR_DATA -- encapsulated DMR data frame
                _peer_id = _data[11:15]
                if _peer_id != self._config['PeerId']:
                    #self._logger.warning('(%s) PEER %s; routed traffic, rewriting PEER %s', self._system, _peer_id, int_id(self._config['PeerId']))
                    _peer_id = self._config['PeerId']

                if _peer_id == self._config['PeerId']: # Validate the source and intended target
                    _seq = _data[4:5]
                    _rf_src = _data[5:8]
                    _dst_id = _data[8:11]
                    _bits = int_id(_data[15])
                    _slot = 2 if (_bits & 0x80) else 1
                    _call_type = 'unit' if (_bits & 0x40) else 'group'
                    _frame_type = (_bits & 0x30) >> 4
                    _dtype_vseq = (_bits & 0xF) # data, 1=voice header, 2=voice terminator; voice, 0=burst A ...  5=burst F
                    _stream_id = _data[16:20]

                    # If AMBE audio exporting is configured...
                    if self._config['ExportAMBE']:
                        self._ambe.parse_ambe(self._system, _data)

                    # Userland actions -- typically this is the function you
                    # subclass for an application
                    self.dmrd_received(_peer_id, _rf_src, _dst_id, _seq, _slot, _call_type, _frame_type, _dtype_vseq, _stream_id, _data)

            elif _data[:4] == fne_const.TAG_P25_DATA: # fne_const.TAG_P25_DATA -- encapsulated P25 data
                _peer_id = _data[11:15]
                if _peer_id != self._config['PeerId']:
                    #self._logger.warning('(%s) PEER %s; routed traffic, rewriting PEER %s', self._system, _peer_id, int_id(self._config['PeerId']))
                    _peer_id = self._config['PeerId']

                if _peer_id == self._config['PeerId']: # Validate the source and intended target
                    _rf_src = _data[5:8]
                    _dst_id = _data[8:11]
                    _call_type = 'unit' if (_data[4] == 0x03) else 'group'
                    _duid = int_id(_data[22])
                    _dtype_vseq = fne_const.FT_VOICE if ((_duid != fne_const.P25_DUID_TDU) and (_duid != fne_const.P25_DUID_TDULC)) else fne_const.DT_TERMINATOR_WITH_LC
                    _stream_id = _data[16:20]

                    # Userland actions -- typically this is the function you
                    # subclass for an application
                    self.p25d_received(_peer_id, _rf_src, _dst_id, _call_type, _duid, _dtype_vseq, _stream_id, _data)

            elif _data[:5] == fne_const.TAG_MASTER_CLOSING: # MSTCL -- notify us the master is closing down
                if _data[5:9] == self._config['PeerId']:
                    self._stats['CONNECTION'] = 'NO'
                    self._logger.info('(%s) PEER %s MSTCL recieved', self._system, int_id(self._config['PeerId']))

            elif _data[:6] == fne_const.TAG_MASTER_NAK: # fne_const.TAG_MASTER_NAK -- a NACK from the master
                _peer_id = _data[6:10]
                if _peer_id == self._config['PeerId']: # Validate the source and intended target
                    self._logger.warning('(%s) PEER %s MSTNAK received', self._system, int_id(self._config['PeerId']))
                    self._stats['CONNECTION'] = 'NO' # Disconnect ourselves and re-register

            elif _data[:6] == fne_const.TAG_REPEATER_ACK: # fne_const.TAG_REPEATER_ACK -- an ACK from the master
                # Depending on the state, an RPTACK means different things, in
                # each clause, we check
                # and/or set the state
                if self._stats['CONNECTION'] == 'RTPL_SENT': # If we've sent a login request...
                    _login_int32 = _data[6:10]
                    self._logger.info('(%s) PEER %s login ACK received with ID %s', self._system, int_id(self._config['PeerId']), int_id(_login_int32))

                    _pass_hash = sha256(_login_int32 + self._config['Passphrase']).hexdigest()
                    _pass_hash = bhex(_pass_hash)
                    self.send_master(fne_const.TAG_REPEATER_AUTH + self._config['PeerId'] + _pass_hash)
                    self._stats['CONNECTION'] = 'AUTHENTICATED'

                elif self._stats['CONNECTION'] == 'AUTHENTICATED': # If we've sent the login challenge...
                    if _data[6:10] == self._config['PeerId']:
                        self._logger.info('(%s) PEER %s authentication accepted', self._system, int_id(self._config['PeerId']))
                        _config_packet = self._config['PeerId'] + \
                                         self._config['Identity'] + \
                                         self._config['RxFrequency'] + \
                                         self._config['TxFrequency'] + \
                                         '          ' + \
                                         self._config['Latitude'] + \
                                         self._config['Longitude'] + \
                                         '  0' + \
                                         self._config['Location'] + \
                                         '          ' + \
                                         ' 0.00' + \
                                         '00.00' + \
                                         '  0' + \
                                         '   0' + \
                                         ' 0' + \
                                         self._config['SoftwareId'] + \
                                         '          ' + \
                                         '                    ' + \
                                         '    0'

                        self.send_master(fne_const.TAG_REPEATER_CONFIG + _config_packet)
                        self._stats['CONNECTION'] = 'CONFIG-SENT'
                        self._logger.info('(%s) PEER %s Configuration sent to master', self._system, int_id(self._config['PeerId']))
                    else:
                        self._stats['CONNECTION'] = 'NO'
                        self._logger.error('(%s) PEER %s Configuration master ACK Contained peer wrong ID - Connection Reset', self._system,
                                           int_id(self._config['PeerId']))

                elif self._stats['CONNECTION'] == 'CONFIG-SENT': # If we've sent out configuration to the master
                    if _data[6:10] == self._config['PeerId']:
                        self._logger.info('(%s) PEER %s Master accepted configuration', self._system, int_id(self._config['PeerId']))
                        self._stats['CONNECTION'] = 'YES'
                        self._logger.info('(%s) PEER %s Connection to MASTER Completed', self._system, int_id(self._config['PeerId']))
                    else:
                        self._stats['CONNECTION'] = 'NO'
                        self._logger.error('(%s) PEER %s Master ACK Contained wrong peer ID - Connection Reset', self._system,
                                           int_id(self._config['PeerId']))

            elif _data[:7] == fne_const.TAG_MASTER_PONG: # fne_const.TAG_MASTER_PONG -- a reply to RPTPING (send by peer)
                if _data[7:11] == self._config['PeerId']:
                    self._stats['PINGS_ACKD'] += 1
                    self._logger.debug('(%s) PEER %s MSTPONG received, pongs since connected %s', self._system,
                                       int_id(self._config['PeerId']), self._stats['PINGS_ACKD'])

            else:
                self._logger.error('(%s) Unrecognized command PEER %s PACKET %s', self._system, int_id(self._config['PeerId']), ahex(_data))

# ---------------------------------------------------------------------------
#   Class Declaration
#     This implements the socket-based reporting logic.
# ---------------------------------------------------------------------------

class report(NetstringReceiver):
    def __init__(self, factory):
        self._factory = factory

    def connectionMade(self):
        self._factory.clients.append(self)
        self._factory._logger.info('Reporting client connected: %s', self.transport.getPeer())

    def connectionLost(self, reason):
        self._factory._logger.info('Reporting client disconnected: %s', self.transport.getPeer())
        self._factory.clients.remove(self)

    def stringReceived(self, data):
        self.process_message(data)

    def process_message(self, _message):
        global systems
        opcode = _message[:1]
        if opcode == REPORT_OPCODES['CONFIG_REQ']:
            self._factory._logger.info('Reporting client sent \'CONFIG_REQ\': %s', self.transport.getPeer())
            self.send_config()
        elif opcode == REPORT_OPCODES['RCON_REQ']:
            _arguments = _message.split(',')
            if (len(_arguments) < 6):
                self._factory._logger.error('RCON request contained an invalid number of arguments; RCON_REQ from %s', self.transport.getPeer())
                return  

            try:
                _peer_id = int(_arguments[1])
                _dmr_slot = int(_arguments[4])
            except:
                self._factory._logger.error('RCON request contained invalid arguments; RCON_REQ from %s', self.transport.getPeer())
                return

            _command = _arguments[2]
            _command_arg = _arguments[3]
            _mot_mfid = _arguments[5]

            _peer_id = hex_str_4(_peer_id)
            _peer = {}

            # find peer 
            for system in systems:
                if systems[system]._CONFIG['Systems'][system]['Mode'] == 'master':
                    _peers = systems[system]._CONFIG['Systems'][system]['PEERS']
                    if (_peer_id in _peers and _peers[_peer_id]['CONNECTION'] == 'YES'):
                        _peer = _peers[_peer_id]
                        break

            if not _peer:
                self._factory._logger.error('RCON request contained invalid PEER ID; RCON_REQ from %s, PEER ID %s', self.transport.getPeer(), _peer_id)
                return

            _peer_ip = _peer['IP']
            _rcon_password = _peer['RCON_PASSWORD']
            _rcon_port = _peer['RCON_PORT']

            if self._factory._config['Global']['RconTool'] != '':
                self._factory._logger.info('RCON_REQ from %s: PEER ID %s COMMAND %s DMR SLOT %s ARGUMENT %s MOT MFID %s', 
                             self.transport.getPeer(), _peer_id, _command, _dmr_slot, _command_arg, _mot_mfid)

                _root_cmd = [self._factory._config['Global']['RconTool'], '-a', str(_peer_ip), '-p', str(_rcon_port), '-P', str(_rcon_password)]

                # handle P25 commands with mot mfid
                if _mot_mfid == 'true':
                    _cmd = list(_root_cmd)
                    _cmd.append('p25-set-mfid')
                    _cmd.append('144')
                    subprocess.call(_cmd)

                _cmd = list(_root_cmd)
                if _dmr_slot == 0:
                    _cmd.append(str(_command).strip())
                    _cmd.append(str(_command_arg).strip())
                else:
                    _cmd.append(str(_command).strip())
                    _cmd.append(str(_dmr_slot))
                    _cmd.append(str(_command_arg).strip())
                subprocess.call(_cmd)

                if _mot_mfid == 'true':
                    _cmd = list(_root_cmd)
                    _cmd.append('p25-set-mfid')
                    _cmd.append('0')
                    subprocess.call(_cmd)
        else:
            self._factory._logger.error('Report unrecognized opcode %s PACKET %s', int_id(opcode), ahex(_message))

# ---------------------------------------------------------------------------
#   Class Declaration
#     This implements the report service factory.
# ---------------------------------------------------------------------------

class reportFactory(Factory):
    def __init__(self, config, logger):
        self._config = config
        self._logger = logger
        
    def buildProtocol(self, addr):
        if (addr.host) in self._config['Reports']['ReportClients'] or '*' in self._config['Reports']['ReportClients']:
            self._logger.debug('Permitting report server connection attempt from: %s:%s', addr.host, addr.port)
            return report(self)
        else:
            self._logger.error('Invalid report server connection attempt from: %s:%s', addr.host, addr.port)
            return None

    def send_timed(self):
        pass
            
    def send_clients(self, _message):
        if self._config['Reports']['Report']:
            for client in self.clients:
                client.sendString(_message)
            
    def send_config(self):
        print(self._config['Systems'])
        serialized = pickle.dumps(self._config['Systems'], protocol = pickle.HIGHEST_PROTOCOL)
        self.send_clients(REPORT_OPCODES['CONFIG_RSP'] + serialized)
