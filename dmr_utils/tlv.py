#!/usr/bin/env python
#
# Digital Voice Modem - Fixed Network Equipment
# GPLv2 Open Source. Use is subject to license terms.
# DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
#
# @package DVM / FNE
#
###############################################################################
#   Copyright (C) 2017 Mike Zingman N4IRR
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

from __future__ import print_function

# Python modules we need
import sys
from bitarray import bitarray
from bitstring import BitArray
from bitstring import BitString
import struct
from time import time, sleep
from importlib import import_module
from binascii import b2a_hex as ahex
from random import randint
import sys, socket, ConfigParser, thread, traceback
from threading import Lock
from time import time, sleep, clock, localtime, strftime
from pprint import pprint

# Twisted is pretty important, so I keep it separate
from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor
from twisted.internet import task

# Things we import from the core modules
from fne.fne_core import hex_str_3, hex_str_4, int_id

from dmr_utils import lc, bptc, const, golay, qr, rs129

from ipsc.ipsc_const import *
from dmr_utils.const import *

import ambe_utils

# ---------------------------------------------------------------------------
#   Constants
# ---------------------------------------------------------------------------

# TLV tag definitions
TAG_BEGIN_TX    = 0x00      # Begin transmission with optional metadata
TAG_PI_INFO     = 0x01      # Set DMR PI data for slot
TAG_END_TX      = 0x02      # End transmission, close session

TAG_AMBE_49     = 0x0A      # AMBE frame of 49 bit samples (IPSC)
TAG_AMBE_72     = 0x0B      # AMBE frame of 72 bit samples (FNE)

TAG_DMR_TEST    = 0xFF

# ---------------------------------------------------------------------------
#   Globals
# ---------------------------------------------------------------------------

'''
    Flag bits
    SGTT NNNN       S = Slot (0 = slot 1, 1 = slot 2)
                    G = Group call = 0, Private = 1
                    T = Type (Voice = 00, Data Sync = 10, ,Voice Sync = 01, Unused = 11)
                    NNNN = Sequence Number or data type (from slot type)
'''
lc_header_flag     = lambda _slot: (0xA0 if (_slot == 2) else 0x20) | ord(const.DT_VOICE_LC_HEADER)
pi_header_flag     = lambda _slot: (0xA0 if (_slot == 2) else 0x20) | ord(const.DT_VOICE_PI_HEADER)
terminator_flag = lambda _slot: (0xA0 if (_slot == 2) else 0x20) | ord(const.DT_TERMINATOR_WITH_LC)
voice_flag      = lambda _slot, _vf: (0x80 if (_slot == 2) else 0) | (0x10 if (_vf == 0) else 0) | _vf

# ---------------------------------------------------------------------------
#   Class Declaration
#
# ---------------------------------------------------------------------------

class SLOT:
    def __init__(self, _slot, _src_id, _dst_id, _peer_id, _cc):
        self.src_id = hex_str_3(_src_id)                    # Source ID
        self.dst_id = hex_str_3(_dst_id)                    # Destination ID (TG)
        self.peer_id = hex_str_4(_peer_id)                  # Peer ID
        self.slot = _slot                                   # Slot to use
        self.cc = _cc                                       # Color code to use
        self.type = 0                                       # 1=voice header, 2=voice terminator; voice, 0=burst A ... 5=burst F
        self.stream_id = hex_str_4(0)                       # Stream id is same across a single session
        self.frame_count = 0                                # Count of frames in a session
        self.start_time = 0                                 # Start of session
        self.time = 0                                       # Current time in session.  Used to calculate duration
        self.group = True                                   #

        self.secure = False                                 #
        self.alg_id = 0                                     # Algorithm ID
        self.key_id = 0                                     # Key ID
        self.mi = ''                                        # Message Indicator

# ---------------------------------------------------------------------------
#   Class Declaration
#
# ---------------------------------------------------------------------------

class RX_SLOT(SLOT):
    def __init__(self, _slot, _src_id, _dst_id, _peer_id, _cc):
        SLOT.__init__(self, _slot, _src_id, _dst_id, _peer_id, _cc)
        self.vf = 0                                         # Voice Frame (A-F in DMR spec)
        self.seq = 0                                        # Incrementing sequence number for each DMR frame
        self.emblc = [None] * 6                             # Storage for embedded LC

# ---------------------------------------------------------------------------
#   Class Declaration
#
# ---------------------------------------------------------------------------

class TX_SLOT(SLOT):
    def __init__(self, _slot, _src_id, _dst_id, _peer_id, _cc):
        SLOT.__init__(self, _slot, _src_id, _dst_id, _peer_id, _cc)
        self.lastSeq = 0                                    # Used to look for gaps in seq numbers
        self.lostFrame = 0                                  # Number of lost frames in a single session

# ---------------------------------------------------------------------------
#   Class Declaration
#
# ---------------------------------------------------------------------------

class tlvBase:
    def __init__(self, _parent, _name, _config, _logger, _port):
        self._parent = _parent
        self._logger = _logger
        self._config = _config
        self._system = _name
        
        self._gateways = [(self._parent._gateway, self._parent._gateway_port)]
        self._tlvPort = _port                               # Port to listen on for TLV frames to transmit to all peers

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self._slot = 2                                      # "current slot"
        self.rx = [0, RX_SLOT(1, 0, 0, 0, 1), RX_SLOT(2, 0, 0, 0, 1)]
        self.tx = [0, TX_SLOT(1, 0, 0, 0, 1), TX_SLOT(2, 0, 0, 0, 1)]
        
        class UDP_IMPORT(DatagramProtocol):
            def __init__(self, callback_function):
                self.func = callback_function
            def datagramReceived(self, _data, (_host, _port)):
                self.func(_data, (_host, _port))
        
        self.udp_port = reactor.listenUDP(self._tlvPort, UDP_IMPORT(self.import_datagramReceived))
        pass

    def send_voice_header(self, _rx_slot):
        _rx_slot.vf = 0                                     # voice frame (A-F)
        _rx_slot.seq = 0                                    # Starts at zero for each incoming transmission, wraps back to zero when 256 is reached.
        _rx_slot.frame_count = 0                            # Number of voice frames in this session (will be greater than zero of header is sent)

    def send_pi_header(self, _rx_slot):
        pass

    def send_voice72(self, _rx_slot, _ambe):
        pass

    def send_voice49(self, _rx_slot, _ambe):
        pass

    def send_voice_term(self, _rx_slot):
        pass

    # Export voice frame to partner (actually done in sub classes for 49 or 72 bits)               
    def export_voice(self, _tx_slot, _seq, _ambe):
        if _seq != ((_tx_slot.lastSeq + 1) & 0xff):
            _tx_slot.lostFrame += 1
        _tx_slot.lastSeq = _seq

    # Twisted callback with data from socket
    def import_datagramReceived(self, _data, (_host, _port)):
        #self._logger.debug('(%s) Network Received TLV (from %s:%s) -- %s', self._system, _host, _port, ahex(_data))
        _slot = self._slot
        _rx_slot = self.rx[_slot]

        # Parse out the TLV
        t = _data[0]
        if (t):
            l = _data[1]
            if (l):
                v = _data[2:]
                if (v):
                    t = ord(t)
                    if (t == TAG_BEGIN_TX):
                        if ord(l) > 1:
                            _slot = int_id(v[10:11])
                            _rx_slot = self.rx[_slot]
                            _rx_slot.slot = _slot
                            _rx_slot.src_id = hex_str_3(int_id(v[0:3]))
                            _rx_slot.peer_id = self._parent.get_peer_id(hex_str_4(int_id(v[3:7])))
                            _rx_slot.dst_id = hex_str_3(int_id(v[7:10]))
                            _rx_slot.cc = int_id(v[11:12])

                            group = int_id(v[12])
                            if (group == 0):
                                _rx_slot.group = False
                            else:
                                _rx_slot.group = True

                        _rx_slot.stream_id = hex_str_4(randint(0, 0xFFFFFFFF))   # Every stream has a unique ID
                        self._logger.info('(%s) TLV BEGIN_TX, STREAM ID %s SRC_ID %s PEER %s GROUP %s TGID %s TS %s', \
                                        self._system, int_id(_rx_slot.stream_id), int_id(_rx_slot.src_id), int_id(_rx_slot.peer_id), group, int_id(_rx_slot.dst_id), _slot)
                        self.send_voice_header(_rx_slot)
                    elif (t == TAG_PI_INFO):
                        if ord(l) > 1:
                            _slot = int_id(v[9:10])
                            _rx_slot = self.rx[_slot]
                            _rx_slot.secure = True
                            _rx_slot.dst_id = hex_str_3(int_id(v[0:3]))
                            _rx_slot.alg_id = v[3:4]
                            _rx_slot.key_id = v[4:5]
                            _rx_slot.mi = v[5:9]
                        self._logger.info('(%s) TLV PI_INFO, STREAM ID %s SRC_ID %s PEER %s TS %s ALG %s KID %s', \
                                        self._system, int_id(_rx_slot.stream_id), int_id(_rx_slot.src_id), int_id(_rx_slot.peer_id), _slot, int_id(_rx_slot.alg_id), int_id(_rx_slot.key_id))
                        self.send_pi_header(_rx_slot)
                    elif (t == TAG_END_TX):
                        _slot = int_id(v[0])
                        _rx_slot = self.rx[_slot]
                        if _rx_slot.frame_count > 0:
                            self.send_voice_term(_rx_slot)
                        
                        self._logger.info('(%s) TLV END_TX, STREAM ID %d FRAMES %d', self._system, int_id(_rx_slot.stream_id), _rx_slot.frame_count)
                        
                        # set it back to zero so any random AMBE frames are ignored.
                        _rx_slot.frame_count = 0

                    elif (t == TAG_AMBE_72): # generic AMBE or specific AMBE72
                        _slot = int_id(v[0])
                        _rx_slot = self.rx[_slot]
                        if _rx_slot.frame_count > 0:
                            self.send_voice72(_rx_slot, v[1:])
                    elif (t == TAG_AMBE_49): # AMBE49
                        _slot = int_id(v[0])
                        _rx_slot = self.rx[_slot]
                        if _rx_slot.frame_count > 0:
                            self.send_voice49(_rx_slot, v[1:])

                    elif (t == TAG_DMR_TEST):
                        _rx_slot.dst_id = hex_str_3(int(v.split('=')[1]))
                        self._logger.info('(%s) TLV DMR_TEST, TGID %d TS %d', self._system, int_id(_rx_slot.dst_id), _rx_slot.slot)
                        thread.start_new_thread(self.sendBlankAmbe, (_rx_slot, hex_str_4(randint(0,0xFFFFFFFF)), 5 * 60 * 500))
                            
                    else:
                        self._logger.info('(%s) TLV unknown, T %d L %d, V %s', self._system, t, ord(l), ahex(v))
            else:
                self._logger.info('(%s) EOF on UDP stream', self._system)

    def stop_listening(self):
        self.udp_port.stopListening()

    def send_tlv(self, _tag, _value):
        _tlv = struct.pack("bb", _tag, len(_value)) + _value
        for _gateway in self._gateways:
            self._sock.sendto(_tlv, _gateway)

    # TG selection, send a simple blank voice frame to network
    def sendBlankAmbe(self, _rx_slot, _stream_id, _frames=1):
        _rx_slot.stream_id = _stream_id
        self.send_voice_header(_rx_slot)
        sleep(0.06)
        silence = '\xAC\AA\x40\x20\x00\x44\x40\x80\x80'
        self._logger.info('(%s) Silence %d frames', self._system, _frames)
        while _frames > 0:
            self.send_voice72(_rx_slot, silence + silence + silence)
            sleep(0.06)
            _frames = _frames - 1
        self.send_voice_term(_rx_slot)

    # Begin export call to partner                
    def begin_call(self, _slot, _group_call, _src_id, _dst_id, _peer_id, _cc, _seq, _stream_id):
        group = '\x01'
        if (_group_call == False):
            group = '\x00'

        metadata = _src_id[0:3] + _peer_id[0:4] + _dst_id[0:3] + struct.pack('B', _slot) + struct.pack('B', _cc) + group

        # start transmission
        self.send_tlv(TAG_BEGIN_TX, metadata)    

        self._logger.info('Voice Transmission Start; slot = {}, dstId = {}, srcId = {}'.format(_slot, int_id(_dst_id), int_id(_src_id)))

        _tx_slot = self.tx[_slot]
        _tx_slot.slot = _slot
        _tx_slot.src_id = _src_id
        _tx_slot.peer_id = _peer_id
        _tx_slot.dst_id = _dst_id
        _tx_slot.cc = _cc
        _tx_slot.stream_id = _stream_id

        _tx_slot.start_time = time()
        _tx_slot.frame_count = 0
        _tx_slot.lostFrame = 0
        _tx_slot.lastSeq = _seq

    # Send PI call parameters to partner                
    def pi_params(self, _slot, _dst_id, _alg_id, _key_id, _mi):
        metadata = _dst_id[0:3] + _alg_id + _key_id + _mi[0:4] + struct.pack('B', _slot)

        sleep(0.06)

        # start transmission
        self.send_tlv(TAG_PI_INFO, metadata)    

        self._logger.info('PI parameters; slot = {}, dstId = {}, algId = {}, kId = {}'.format(_slot, int_id(_dst_id), int_id(_alg_id), int_id(_key_id)))

        _tx_slot = self.tx[_slot]
        _tx_slot.secure = True
        _tx_slot.alg_id = _alg_id
        _tx_slot.key_id = _key_id
        _tx_slot.mi = _mi

    # End export call to partner                
    def end_call(self, _tx_slot):
        # end transmission
        self.send_tlv(TAG_END_TX, struct.pack('B', _tx_slot.slot))
        
        call_duration = time() - _tx_slot.start_time
        _lost_percentage = ((_tx_slot.lostFrame / float(_tx_slot.frame_count)) * 100.0) if _tx_slot.frame_count > 0 else 0.0
        
        self._logger.info('Voice Transmission End; {:.2f} seconds loss rate: {:.2f}% ({}/{})'.format(call_duration, _lost_percentage, _tx_slot.frame_count - _tx_slot.lostFrame, _tx_slot.frame_count))

# ---------------------------------------------------------------------------
#   Class Declaration
#
# ---------------------------------------------------------------------------

class tlvFNE(tlvBase):
    def __init__(self, _parent, _name, _config, _logger, _port):
        tlvBase.__init__(self, _parent, _name, _config, _logger, _port)

        self.lcss = [
                     0b11111111, # not used (place holder)
                     0b01,       # First fragment
                     0b11,       # Continuation fragment
                     0b11,       # Continuation fragment
                     0b10,       # Last fragment
                     0b00        # Null message
        ]
        self._DMOStreamID = 0
        self._DMOTimeout = 0
    
    def send_voice_header(self, _rx_slot):
        tlvBase.send_voice_header(self, _rx_slot)
        flag = lc_header_flag(_rx_slot.slot)
        dmr = self.encode_voice_header(_rx_slot)
        for j in range(0,2):
            self.send_fne_frame(_rx_slot, flag, dmr)
            sleep(0.06)

    def send_pi_header(self, _rx_slot):
        flag = pi_header_flag(_rx_slot.slot)
        dmr = self.encode_pi_header(_rx_slot)
        self.send_fne_frame(_rx_slot, flag, dmr)
        pass

    def send_voice72(self, _rx_slot, _ambe):
        flag = voice_flag(_rx_slot.slot, _rx_slot.vf) # calc flag value
        
        # Construct the dmr frame from AMBE(108 bits) + sync/CACH (48 bits) + AMBE(108 bits)
        _new_frame = self.encode_voice(BitArray('0x' + ahex(_ambe)), _rx_slot) 
        
        self.send_fne_frame(_rx_slot, flag, _new_frame.tobytes())

        # the voice frame counter which is always mod 6
        _rx_slot.vf = (_rx_slot.vf + 1) % 6                         

    def send_voice49(self, _rx_slot, _ambe):
        ambe49_1 = BitArray('0x' + ahex(_ambe[0:7]))[0:49]
        ambe49_2 = BitArray('0x' + ahex(_ambe[7:14]))[0:49]
        ambe49_3 = BitArray('0x' + ahex(_ambe[14:21]))[0:49]

        ambe72_1 = ambe_utils.convert49BitTo72BitAMBE(ambe49_1)
        ambe72_2 = ambe_utils.convert49BitTo72BitAMBE(ambe49_2)
        ambe72_3 = ambe_utils.convert49BitTo72BitAMBE(ambe49_3)

        v = ambe72_1 + ambe72_2 + ambe72_3
        self.send_voice72(_rx_slot, v)

    def send_voice_term(self, _rx_slot):
        flag = terminator_flag(_rx_slot.slot)
        dmr = self.encode_voice_term(_rx_slot)
        self.send_fne_frame(_rx_slot, flag, dmr)

    # Export voice frame to partner (actually done in sub classes for 49 or 72 bits)               
    def export_voice(self, _tx_slot, _seq, _ambe):
        self.send_tlv(TAG_AMBE_72, struct.pack('B', _tx_slot.slot) + _ambe) # send AMBE
        if _seq != ((_tx_slot.lastSeq + 1) & 0xff):
            self._logger.info('(%s) Seq number not found.  got %d expected %d', self._system, _seq, _tx_slot.lastSeq + 1)
            _tx_slot.lostFrame += 1
        _tx_slot.lastSeq = _seq

    # Construct DMR frame, FNE header and send result to all peers on network
    def send_fne_frame(self, _rx_slot, _flag, _dmr_frame):
        # Make the HB frame, ready to send
        frame = self.make_dmrd(_rx_slot.seq, _rx_slot.src_id, _rx_slot.dst_id, _rx_slot.peer_id, _flag, _rx_slot.stream_id, _dmr_frame)         
        self.send_system(_rx_slot, frame)                   # Send  the frame to all peers or master
        _rx_slot.seq += 1                                   # Convienent place for this increment
        _rx_slot.frame_count += 1                           # update count (used for stats and to make sure header was sent)

    # Override the super class because (1) DMO must be placed on slot 2 and (2) peer_id must be the ID of the client (TODO)
    def send_system(self, _rx_slot, _frame):
        if hasattr(self._parent, '_peers'):
            _orig_flag = _frame[15]                         # Save off the flag since _frame is a reference
            for _peer in self._parent._peers:
                _peerDict = self._parent._peers[_peer]
                if _peerDict['TX_FREQ'] == _peerDict['RX_FREQ']:
                    if (self._DMOStreamID == 0) or (time() > self._DMOTimeout): # are we idle?
                        self._DMOStreamID = _rx_slot.stream_id
                        self._DMOTimeout = time() + 0.50
                        self._logger.info('(%s) DMO Transition from idle to stream %d', self._system, int_id(_rx_slot.stream_id))
                    if _rx_slot.stream_id != self._DMOStreamID: # packet is from wrong stream?
                        if (_frame[15] & 0x2F) == 0x21:     # Call start?
                            self._logger.info('(%s) DMO Ignore traffic on stream %d', self._system, int_id(_rx_slot.stream_id))
                        continue
                    if (_frame[15] & 0x2F) == 0x22:         # call terminator flag?
                        self._DMOStreamID = 0               # we are idle again
                        self._logger.info('(%s) DMO End of call, back to IDLE', self._system)

                    _frame[15] = (_frame[15] & 0x7f) | 0x80 # force to slot 2 if client in DMO mode
                else:
                    _frame[15] = _orig_flag                 # Use the origional flag value if not DMO

                _repeaterID = hex_str_4(int(_peerDict['PEER_ID']))
                for _index in range(0,4):                   # Force the repeater ID to be the "destination" ID of the client (fne will not accept it otherwise)
                    _frame[_index + 11] = _repeaterID[_index]

                self._parent.send_peer(_peer, _frame)
                self._DMOTimeout = time() + 0.50
        else:
            self._parent.send_master(_frame)

    # Construct a complete HB frame from passed parameters
    def make_dmrd(self, _seq, _src_id, _dst_id, _peer_id, _flag, _stream_id, _dmr_frame):
        frame = bytearray('DMRD')                           # Header type DMRD
        frame += struct.pack('I', _seq)[0]                  # Sequence number
        frame += _src_id[0:3]                               # Source ID
        frame += _dst_id[0:3]                               # Destination ID
        frame += _peer_id[0:4]                              # Peer ID (4 bytes)
        frame += struct.pack('I', _flag)[0:1]               # Flag to packet
        frame += _stream_id[0:4]                            # Stream ID (same for all packets in a transmission)
        frame += _dmr_frame                                 # DMR frame
        frame += struct.pack('I', 0)[0:2]                   # RSSI and err count
        return frame
    
    # Private function to create a voice header or terminator DMR frame
    def encode_lc(self, _rx_slot, _dtype):
        _src_id = _rx_slot.src_id
        _dst_id = _rx_slot.dst_id
        _cc = _rx_slot.cc

        _fid = FID_ETSI
        if (_rx_slot.secure == True):
            _fid = FID_DMRA

        # create lc
        lcHeader = '\x00' + _fid + '\x00' + _dst_id + _src_id     # PF + Reserved + FLCO + FID + Service Options + Destination Address + Source Address

        _rx_slot.emblc = bptc.encode_emblc(lcHeader)        # save off the emb lc for voice frames B-E
        _rx_slot.emblc[5] = bitarray(32)                    # NULL message (F)

        return lc.encode_lc_header(lcHeader, _cc, _dtype, MS_DATA_SYNC)
    
    # Create a voice header DMR frame
    def encode_voice_header(self, _rx_slot):
        return self.encode_lc(_rx_slot, DT_VOICE_LC_HEADER)

    # Create a voice PI header DMR frame
    def encode_pi_header(self, _rx_slot):
        _dst_id = _rx_slot.dst_id
        _alg_id = _rx_slot.alg_id
        _key_id = _rx_slot.key_id
        _mi = _rx_slot.mi
        _cc = _rx_slot.cc

        _dtype = DT_VOICE_PI_HEADER

        _fid = FID_ETSI
        if (_rx_slot.secure == True):
            _fid = FID_DMRA

        # create lc
        lcHeader = _alg_id + _fid + _key_id  + _mi + _dst_id + '\x00\x00' # AlgID + FID + KeyID + MI + Destination Address + CRC-CCITT16

        return lc.encode_pi_header(lcHeader, _cc, _dtype, MS_DATA_SYNC)
    
    # Create a voice DMR frame A-F frame type
    def encode_voice(self, _ambe, _rx_slot):
        _frame_type = _rx_slot.vf
        if _frame_type > 0:                                 # if not a SYNC frame cccxss
            index = (_rx_slot.cc << 3) | self.lcss[_frame_type] # index into the encode table makes this a simple lookup
            emb = bitarray(format(qr.ENCODE_1676[ index ], '016b')) # create emb of 16 bits
            embedded = emb[8:16] + _rx_slot.emblc[_frame_type] + emb[0:8] # Take emb and a chunk of the embedded LC and combine them into 48 bits
        else:
            embedded = MS_VOICE_SYNC                        # Voice SYNC (48 bits)
        _new_frame = _ambe[0:108] + embedded + _ambe[108:216] # Construct the dmr frame from AMBE(108 bits) + sync/emb (48 bits) + AMBE(108 bits)
        return _new_frame
    
    # Create a voice terminator DMR frame
    def encode_voice_term(self, _rx_slot):
        return self.encode_lc(_rx_slot, DT_TERMINATOR_WITH_LC)

# ---------------------------------------------------------------------------
#   Class Declaration
#
# ---------------------------------------------------------------------------

class tlvIPSC(tlvBase):
    def __init__(self, _parent, _name, _config, _logger, _port):
        tlvBase.__init__(self, _parent, _name, _config, _logger, _port)

        self.emb_lc = ''

        self._tempHead = [0] * 3                            # It appears that there 3 frames of HEAD (mostly the same)
        self._tempVoice = [0] * 6
        self._tempTerm = [0]

        self._rtp_ts = 0                                    # RTP timestamp 32-bit
        self._rtp_seq = 0                                   # RTP Transmit frame sequence number (auto-increments for each frame). 16 bit

        self.ipsc_seq = 0                                   # Same for all frames in a transmit session (sould use stream_id).  8 bit
        pass

    def send_voice_header(self, _rx_slot):
        tlvBase.send_voice_header(self, _rx_slot)
        self._seq = randint(0, 32767)                       # A transmission uses a random number to begin its sequence (16 bit)
        self.ipsc_seq = (self.ipsc_seq + 1) & 0xff          # this is an 8 bit value which wraps around.
        self.emb_lc = ''

        for i in range(0, 3):                               # Output the 3 HEAD frames to our peers
            voiceHeader = self.generate_voice_header(_rx_slot, BURST_DATA_TYPE['VOICE_HEADER'])
            rtpHeader = self.generate_rtp_header(_rx_slot, RTP_PAYLOAD_VOICE_HEADER, 0)
            ipscHeader = self.generate_ipsc_voice_header(_rx_slot)

            frame = ipscHeader + rtpHeader + voiceHeader

            self.send_ipsc(_rx_slot.slot, frame)
            sleep(0.06)
        pass
    
    def send_pi_header(self, _rx_slot):
        if (_rx_slot.secure == True):
            voiceHeader = self.generate_voice_header(_rx_slot, BURST_DATA_TYPE['PI_HEADER'])
            rtpHeader = self.generate_rtp_header(_rx_slot, RTP_PAYLOAD_VOICE, 0)
            ipscHeader = self.generate_ipsc_voice_header(_rx_slot)

            frame = ipscHeader + rtpHeader + voiceHeader
            self.send_ipsc(_rx_slot.slot, frame)
        pass

    def send_voice72(self, _rx_slot, _ambe):
        rtpHeader = self.generate_rtp_header(_rx_slot, RTP_PAYLOAD_VOICE, 0)
        ipscHeader = self.generate_ipsc_voice_header(_rx_slot)

        ambe72_1 = BitArray('0x' + ahex(_ambe[0:9]))[0:72]
        ambe72_2 = BitArray('0x' + ahex(_ambe[9:18]))[0:72]
        ambe72_3 = BitArray('0x' + ahex(_ambe[18:27]))[0:72]

        ambe49_1 = ambe_utils.convert72BitTo49BitAMBE(ambe72_1)
        ambe49_2 = ambe_utils.convert72BitTo49BitAMBE(ambe72_2)
        ambe49_3 = ambe_utils.convert72BitTo49BitAMBE(ambe72_3)

        ambe49_1.append(False)
        ambe49_2.append(False)
        ambe49_3.append(False)

        ambe = ambe49_1 + ambe49_2 + ambe49_3

        # this will change to SLOT2_VOICE if _rx_slot.slot is 2
        burst = self.generate_ipsc_voice_burst(_rx_slot, BURST_DATA_TYPE['SLOT1_VOICE'], _ambe) 

        frame = ipscHeader + rtpHeader + burst
        self.send_ipsc(_rx_slot.slot, frame)
        _rx_slot.vf = (_rx_slot.vf + 1) % 6                 # the voice frame counter which is always mod 6
        pass

    def send_voice49(self, _rx_slot, _ambe):
        rtpHeader = self.generate_rtp_header(_rx_slot, RTP_PAYLOAD_VOICE, 0)
        ipscHeader = self.generate_ipsc_voice_header(_rx_slot)

        ambe49_1 = BitArray('0x' + ahex(_ambe[0:7]))[0:50]
        ambe49_2 = BitArray('0x' + ahex(_ambe[7:14]))[0:50]
        ambe49_3 = BitArray('0x' + ahex(_ambe[14:21]))[0:50]
        
        ambe = ambe49_1 + ambe49_2 + ambe49_3

        # this will change to SLOT2_VOICE if _rx_slot.slot is 2
        burst = self.generate_ipsc_voice_burst(_rx_slot, BURST_DATA_TYPE['SLOT1_VOICE'], _ambe) 

        frame = ipscHeader + rtpHeader + burst
        self.send_ipsc(_rx_slot.slot, frame)
        _rx_slot.vf = (_rx_slot.vf + 1) % 6                 # the voice frame counter which is always mod 6
        pass

    def send_voice_term(self, _rx_slot):
        voiceHeader = self.generate_voice_header(_rx_slot, BURST_DATA_TYPE['VOICE_TERMINATOR'])
        rtpHeader = self.generate_rtp_header(_rx_slot, RTP_PAYLOAD_TERM, 0)
        ipscHeader = self.generate_ipsc_voice_header(_rx_slot)

        frame = ipscHeader + rtpHeader + voiceHeader
        self.send_ipsc(_rx_slot.slot, frame)
        pass

    # Export voice frame to partner (actually done in sub classes for 49 or 72 bits)               
    def export_voice(self, _tx_slot, _seq, _ambe):
        self.send_tlv(TAG_AMBE_49, struct.pack('B', _tx_slot.slot) + _ambe)    # send AMBE
        if _seq != ((_tx_slot.lastSeq + 1) & 0xff):
            _tx_slot.lostFrame += 1
        _tx_slot.lastSeq = _seq

    def send_ipsc(self, _slot, _frame):
        if (time() - self._parent._busy_slots[_slot]) >= 0.10 : # slot is not busy so it is safe to transmit
            # Send the packet to all peers in the target IPSC
            self._parent.send_to_ipsc(_frame)
        else:
            self._logger.info('Slot {} is busy, will not transmit packet from gateway'.format(_slot))
        self.rx[_slot].frame_count += 1      # update count (used for stats and to make sure header was sent)

    def generate_ipsc_voice_header(self, _rx_slot):
        src_id = struct.pack('>I', int_id(_rx_slot.src_id))
        dst_id = struct.pack('>I', int_id(_rx_slot.dst_id))

        frameType = GROUP_VOICE
        if not _rx_slot.group:
            frameType = PVT_VOICE

        control = 0x00
        if _rx_slot.slot == 1:
            control &= ~(1 << 5)
        elif _rx_slot.slot == 2:
            control |= 1 << 5
        if _rx_slot.secure:
            control &= ~(1 << 7)
        control = chr(control)

        frame = frameType + struct.pack('>I', int_id(_rx_slot.peer_id)) + struct.pack("i", self.ipsc_seq)[0] + \
            src_id[1] + src_id[2] + src_id[3] + dst_id[1] + dst_id[2] + dst_id[3] + \
            CALL_PRIORITY_2 + struct.pack('>I', int_id(_rx_slot.stream_id)) + control

        return frame

    def generate_rtp_header(self, _rx_slot, _payload_type, _ssrc):
        rtpSeq = struct.pack("i", self._rtp_seq)
        if self._rtp_seq >= 1 and _payload_type == RTP_PAYLOAD_VOICE_HEADER:
            _payload_type = RTP_PAYLOAD_VOICE

        self._rtp_seq = self._rtp_seq + 1

        rtpHeader = RTP_VER + _payload_type + rtpSeq[1] + rtpSeq[0] + struct.pack('>I', self._rtp_ts) + \
            struct.pack('>I', _ssrc)
        
        self._rtp_ts = self._rtp_ts + 480
        return rtpHeader

    def generate_ipsc_burst(self, _rx_slot, _burst_type):
        _unk = '\x00'

        length = 0
        bitLength = 0
        if _burst_type == BURST_DATA_TYPE['VOICE_HEADER'] or _burst_type == BURST_DATA_TYPE['VOICE_TERMINATOR']:
            length = 10
#            bitLength = (length + 2) * 8
        elif _burst_type == BURST_DATA_TYPE['PI_HEADER']:
            length = 9
#            bitLength = (length) * 8

        # HACK: OTA shows the bitLength always 96-bits -- oddly
        bitLength = 0x60

        syncType = 0x08
        if _burst_type == BURST_DATA_TYPE['VOICE_HEADER'] or _burst_type == BURST_DATA_TYPE['VOICE_TERMINATOR']:
            syncType = syncType | SYNC_TYPE_DATA
        elif _burst_type == BURST_DATA_TYPE['SLOT1_VOICE']:
            syncType = syncType | SYNC_TYPE_VOICE

        if _burst_type == BURST_DATA_TYPE['SLOT1_VOICE'] and _rx_slot.slot == 2:
            _burst_type = BURST_DATA_TYPE['SLOT2_VOICE']

        burst = _burst_type + struct.pack('B', (_rx_slot.slot - 1) << 7) + struct.pack('>H', length) + _unk + \
            struct.pack('B', syncType) + _unk + struct.pack('B', bitLength)
        return burst

    def generate_ipsc_voice_burst(self, _rx_slot, _burst_type, _ambe):
        if _burst_type == BURST_DATA_TYPE['SLOT1_VOICE'] and _rx_slot.slot == 2:
            _burst_type = BURST_DATA_TYPE['SLOT2_VOICE']

        length = 20
        control = 0x00
        controlData = ''
        if _rx_slot.vf == 0:
            control = VC_SYNC

        elif _rx_slot.vf == 1 or _rx_slot.vf == 2 or _rx_slot.vf == 3 or _rx_slot.vf == 5:
            control = VC_EMB | VC_EMBEDDED_LC_BITS
            length += 5

            emb = bptc.encode_emblc(self.emb_lc)
            if _rx_slot.vf == 1: 
                controlData = emb[1].tobytes()
            elif _rx_slot.vf == 2:
                controlData = emb[2].tobytes()
            elif _rx_slot.vf == 3:
                controlData = emb[3].tobytes()
            elif _rx_slot.vf == 5:
                controlData = struct.pack('>I', 0)

            controlData += '\x00'

        elif _rx_slot.vf == 4:
            control = VC_EMB | VC_EMBEDDED_LC_BITS | VC_EMBEDDED_LC
            length += 14

            emb = bptc.encode_emblc(self.emb_lc)
            controlData = emb[4].tobytes()
            controlData += self.emb_lc[1:]

            controlData += '\x00'

        burst = _burst_type + struct.pack('B', length) + struct.pack('B', control) + _ambe + controlData
        return burst;

    def generate_voice_header(self, _rx_slot, _burst_type):
        src_id = struct.pack('>I', int_id(_rx_slot.src_id))
        dst_id = struct.pack('>I', int_id(_rx_slot.dst_id))

        headerType = ord(LC_GROUP_VOICE)
        if not _rx_slot.group:
            headerType = ord(LC_PRIVATE_VOICE)
        if _rx_slot.secure:
            headerType &= ~(1 << 7)

        featureSet = FID_ETSI
        svcOptions = 0x00
        if _rx_slot.secure:
            featureSet = FID_DMRA
            svcOptions &= ~(1 << 6)

        header = struct.pack('B', headerType) + featureSet + struct.pack('B', svcOptions) + \
            dst_id[1] + dst_id[2] + dst_id[3] + src_id[1] + src_id[2] + src_id[3]
        self.emb_lc = header

        fec = ''
        if _burst_type == BURST_DATA_TYPE['VOICE_HEADER']:
            fec = rs129.lc_header_encode(header)
        else:
            fec = rs129.lc_terminator_encode(header)

        ipsc_burst = self.generate_ipsc_burst(_rx_slot, _burst_type)

        burst_type = map(ord, _burst_type)[0]
        burst_type = burst_type + (_rx_slot.cc << 4)
        burst_type = struct.pack('>H', burst_type)
        rssi = struct.pack('>H', 0) # fake RSSI

        return ipsc_burst + header + fec + burst_type + rssi

    def generate_pi_header(self, _rx_slot, _burst_type):
        _unk = '\x00'

        dst_id = struct.pack('>I', int_id(_rx_slot.dst_id))

        featureSet = FID_DMRA

        header = struct.pack('B', _rx_slot.alg_id) + featureSet + struct.pack('B', _rx_slot.key_id) + \
            mi[0] + mi[1] + mi[2] + mi[3] + dst_id[1] + dst_id[2] + dst_id[3] + _unk + _unk

        ipsc_burst = self.generate_ipsc_burst(_rx_slot, _burst_type)

        burst_type = map(ord, _burst_type)[0]
        burst_type = burst_type + (_rx_slot.cc << 4)
        burst_type = struct.pack('>H', burst_type)
        rssi = struct.pack('>H', 0) # fake RSSI

        return ipsc_burst + header + fec + burst_type + rssi
