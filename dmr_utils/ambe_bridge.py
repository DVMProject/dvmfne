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

# Twisted is pretty important, so I keep it separate
from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor
from twisted.internet import task

# Things we import from the core modules
from fne.fne_core import hex_str_3, hex_str_4, int_id

from dmr_utils import decode, bptc, const, golay, qr

import ambe_utils

# ---------------------------------------------------------------------------
#   Constants
# ---------------------------------------------------------------------------

DMR_DATA_SYNC_MS    =   '\xD5\xD7\xF7\x7F\xD7\x57'
DMR_VOICE_SYNC_MS   =   '0x7F7D5DD57DFD'

# TLV tag definitions
TAG_BEGIN_TX    = 0         # Begin transmission with optional metadata
TAG_AMBE        = 1         # AMBE frame to transmit (old tag now uses 49 or 72)
TAG_END_TX      = 2         # End transmission, close session
TAG_TG_TUNE     = 3         # Send blank start/end frames to network for a specific talk group
TAG_PLAY_AMBE   = 4         # Play an AMBE file
TAG_REMOTE_CMD  = 5         # SubCommand for remote configuration
TAG_AMBE_49     = 6         # AMBE frame of 49 bit samples (IPSC)
TAG_AMBE_72     = 7         # AMBE frame of 72 bit samples (HB)
TAG_SET_INFO    = 8         # Set DMR Info for slot
TAG_DMR_TEST    = 9

# Burst Data Types
BURST_DATA_TYPE = {
    'VOICE_HEAD':  '\x01',
    'VOICE_TERM':  '\x02',
    'SLOT1_VOICE': '\x0A',
    'SLOT2_VOICE': '\x8A'
}

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
header_flag     = lambda _slot: (0xA0 if (_slot == 2) else 0x20) | ord(const.DMR_SLT_VHEAD)
terminator_flag = lambda _slot: (0xA0 if (_slot == 2) else 0x20) | ord(const.DMR_SLT_VTERM)
voice_flag      = lambda _slot, _vf: (0x80 if (_slot == 2) else 0) | (0x10 if (_vf == 0) else 0) | _vf

# ---------------------------------------------------------------------------
#   Class Declaration
#
# ---------------------------------------------------------------------------

class SLOT:
    def __init__(self, _slot, _rf_src, _dst_id, _repeater_id, _cc):
        self.rf_src = hex_str_3(_rf_src)                # DMR ID of sender
        self.dst_id = hex_str_3(_dst_id)                # Talk group to send to
        self.repeater_id = hex_str_4(_repeater_id)      # Repeater ID
        self.slot = _slot                               # Slot to use
        self.cc = _cc                                   # Color code to use
        self.type = 0                                   # 1=voice header, 2=voice terminator; voice, 0=burst A ... 5=burst F
        self.stream_id = hex_str_4(0)                   # Stream id is same across a single session
        self.frame_count = 0                            # Count of frames in a session
        self.start_time = 0                             # Start of session
        self.time = 0                                   # Current time in session.  Used to calculate duration

# ---------------------------------------------------------------------------
#   Class Declaration
#
# ---------------------------------------------------------------------------

class RX_SLOT(SLOT):
    def __init__(self, _slot, _rf_src, _dst_id, _repeater_id, _cc):
        SLOT.__init__(self, _slot, _rf_src, _dst_id, _repeater_id, _cc)
        self.vf = 0                                     # Voice Frame (A-F in DMR spec)
        self.seq = 0                                    # Incrementing sequence number for each DMR frame
        self.emblc = [None] * 6                         # Storage for embedded LC

# ---------------------------------------------------------------------------
#   Class Declaration
#
# ---------------------------------------------------------------------------

class TX_SLOT(SLOT):
    def __init__(self, _slot, _rf_src, _dst_id, _repeater_id, _cc):
        SLOT.__init__(self, _slot, _rf_src, _dst_id, _repeater_id, _cc)
        self.lastSeq = 0                                # Used to look for gaps in seq numbers
        self.lostFrame = 0                              # Number of lost frames in a single session

# ---------------------------------------------------------------------------
#   Class Declaration
#
# ---------------------------------------------------------------------------

class AMBE_BASE:
    def __init__(self, _parent, _name, _config, _logger, _port):
        self._parent = _parent
        self._logger = _logger
        self._config = _config
        self._system = _name
        
        self._gateways = [(self._parent._gateway, self._parent._gateway_port)]
        self._ambeRxPort = _port                                # Port to listen on for AMBE frames to transmit to all peers
        self._dmrgui = '127.0.0.1'

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self._slot = 2                                          # "current slot"
        self.rx = [0, RX_SLOT(1, 0, 0, 0, 1), RX_SLOT(2, 0, 0, 0, 1)]
        self.tx = [0, TX_SLOT(1, 0, 0, 0, 1), TX_SLOT(2, 0, 0, 0, 1)]
        
        class UDP_IMPORT(DatagramProtocol):
            def __init__(self, callback_function):
                self.func = callback_function
            def datagramReceived(self, _data, (_host, _port)):
                self.func(_data, (_host, _port))
        
        self.udp_port = reactor.listenUDP(self._ambeRxPort, UDP_IMPORT(self.import_datagramReceived))

        pass

    def stop_listening(self):
        self.udp_port.stopListening()

    def send_voice_header(self, _rx_slot):
        _rx_slot.vf = 0             # voice frame (A-F)
        _rx_slot.seq = 0            # Starts at zero for each incoming transmission, wraps back to zero when 256 is reached.
        _rx_slot.frame_count = 0    # Number of voice frames in this session (will be greater than zero of header is sent)

    def send_voice72(self, _rx_slot, _ambe):
        pass

    def send_voice49(self, _rx_slot, _ambe):
        pass

    def send_voice_term(self, _rx_slot):
        pass

    # TG selection, send a simple blank voice frame to network
    def sendBlankAmbe(self, _rx_slot, _stream_id, _frames=1):
        _rx_slot.stream_id = _stream_id
        self.send_voice_header(_rx_slot)
        sleep(0.06)
        silence = '\xAC\AA\x40\x20\x00\x44\x40\x80\x80'
        self._logger.info('(%s) Silence %d frames', self._system, _frames)
        while _frames > 0:
            self.send_voice72(_rx_slot, silence+silence+silence)
            sleep(0.06)
            _frames = _frames - 1
        self.send_voice_term(_rx_slot)
        self._logger.info('(%s) Playback done', self._system)

    # Twisted callback with data from socket
    def import_datagramReceived(self, _data, (_host, _port)):
        subscriber_ids, talkgroup_ids, peer_ids = self._parent.get_globals()

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
                    if (t == TAG_BEGIN_TX) or (t == TAG_SET_INFO):                    
                        if ord(l) > 1:
                            _slot = int_id(v[10:11])
                            _rx_slot = self.rx[_slot]
                            _rx_slot.slot = _slot
                            _rx_slot.rf_src = hex_str_3(int_id(v[0:3]))
                            _rx_slot.repeater_id = self._parent.get_repeater_id(hex_str_4(int_id(v[3:7])))
                            _rx_slot.dst_id = hex_str_3(int_id(v[7:10]))
                            _rx_slot.cc = int_id(v[11:12])

                        if t == TAG_BEGIN_TX:
                            _rx_slot.stream_id = hex_str_4(randint(0, 0xFFFFFFFF))   # Every stream has a unique ID
                            self._logger.info('(%s) Begin AMBE encode STREAM ID: %s SUB: %s REPEATER: %s TGID %s, TS %s', \
                                          self._system, int_id(_rx_slot.stream_id), int_id(_rx_slot.rf_src), int_id(_rx_slot.repeater_id), int_id(_rx_slot.dst_id), _slot)
                            self.send_voice_header(_rx_slot)
                        else:
                            self._logger.info('(%s) Set DMR Info SUB: %s REPEATER: %s TGID %s, TS %s', \
                                          self._system, int_id(_rx_slot.rf_src), int_id(_rx_slot.repeater_id), int_id(_rx_slot.dst_id), _slot)
                    elif ((t == TAG_AMBE) or (t == TAG_AMBE_72)): # generic AMBE or specific AMBE72
                        _slot = int_id(v[0])
                        _rx_slot = self.rx[_slot]
                        if _rx_slot.frame_count > 0:
                            self.send_voice72(_rx_slot, v[1:])
                    elif (t == TAG_AMBE_49): # AMBE49
                        _slot = int_id(v[0])
                        _rx_slot = self.rx[_slot]
                        if _rx_slot.frame_count > 0:
                            self.send_voice49(_rx_slot, v[1:])
                    elif (t == TAG_END_TX):
                        _slot = int_id(v[0])
                        _rx_slot = self.rx[_slot]
                        if _rx_slot.frame_count > 0:
                            self.send_voice_term(_rx_slot)
                        
                        self._logger.info('(%s) End AMBE encode STREAM ID: %d FRAMES: %d', self._system, int_id(_rx_slot.stream_id), _rx_slot.frame_count)
                        
                        # set it back to zero so any random AMBE frames are ignored.
                        _rx_slot.frame_count = 0
                    elif (t == TAG_TG_TUNE):
                        _rx_slot.dst_id = hex_str_3(int(v.split('=')[1]))
                        self._logger.info('(%s) New txTg = %d on Slot %d', self._system, int_id(_rx_slot.dst_id), _rx_slot.slot)
                        self.sendBlankAmbe(_rx_slot, hex_str_4(randint(0,0xFFFFFFFF)))
                    elif (t == TAG_DMR_TEST):
                        _rx_slot.dst_id = hex_str_3(int(v.split('=')[1]))
                        self._logger.info('(%s) New txTg = %d on Slot %d', self._system, int_id(_rx_slot.dst_id), _rx_slot.slot)
                        thread.start_new_thread(self.sendBlankAmbe, (_rx_slot, hex_str_4(randint(0,0xFFFFFFFF)), 5 * 60 * 500))
                            
                    else:
                        self._logger.info('(%s) unknown TLV t=%d, l=%d, v=%s (%s)', self._system, t, ord(l), ahex(v), v)
            else:
                self._logger.info('(%s) EOF on UDP stream', self._system)

    # Begin export call to partner                
    def begin_call(self, _slot, _src_id, _dst_id, _repeater_id, _cc, _seq, _stream_id):
        metadata = _src_id[0:3] + _repeater_id[0:4] + _dst_id[0:3] + struct.pack("b", _slot) + struct.pack("b", _cc)

        # start transmission
        self.send_tlv(TAG_BEGIN_TX, metadata)    
        self._sock.sendto('reply log2 {} {}'.format(int_id(_src_id), int_id(_dst_id)), (self._dmrgui, 34003))
        self._logger.info('Voice Transmission Start on TS {} and TG {} from {}'.format(_slot, int_id(_dst_id), int_id(_src_id)))

        _tx_slot = self.tx[_slot]
        _tx_slot.slot = _slot
        _tx_slot.rf_src = _src_id
        _tx_slot.repeater_id = _repeater_id
        _tx_slot.dst_id = _dst_id
        _tx_slot.cc = _cc
        _tx_slot.stream_id = _stream_id

        _tx_slot.start_time = time()
        _tx_slot.frame_count = 0
        _tx_slot.lostFrame = 0
        _tx_slot.lastSeq = _seq

    # End export call to partner                
    def end_call(self, _tx_slot):
        # end transmission
        self.send_tlv(TAG_END_TX, struct.pack("b", _tx_slot.slot))
        
        call_duration = time() - _tx_slot.start_time
        _lost_percentage = ((_tx_slot.lostFrame / float(_tx_slot.frame_count)) * 100.0) if _tx_slot.frame_count > 0 else 0.0
        
        self._sock.sendto("reply log" +
                          strftime(" %m/%d/%y %H:%M:%S", localtime(_tx_slot.start_time)) +
                          ' {} {} "{}"'.format(int_id(_tx_slot.rf_src), _tx_slot.slot, int_id(_tx_slot.dst_id)) +
                          ' {:.2f}%'.format(_lost_percentage) +
                          ' {:.2f}s'.format(call_duration), (self._dmrgui, 34003))
        
        self._logger.info('Voice Transmission End {:.2f} seconds loss rate: {:.2f}% ({}/{})'.format(call_duration, _lost_percentage, _tx_slot.frame_count - _tx_slot.lostFrame, _tx_slot.frame_count))

    # Export voice frame to partner (actually done in sub classes for 49 or 72 bits)               
    def export_voice(self, _tx_slot, _seq, _ambe):
        if _seq != ((_tx_slot.lastSeq + 1) & 0xff):
            _tx_slot.lostFrame += 1
        _tx_slot.lastSeq = _seq

    def send_tlv(self, _tag, _value):
        _tlv = struct.pack("bb", _tag, len(_value)) + _value
        for _gateway in self._gateways:
            self._sock.sendto(_tlv, _gateway)

# ---------------------------------------------------------------------------
#   Class Declaration
#
# ---------------------------------------------------------------------------

class AMBE_FNE(AMBE_BASE):
    def __init__(self, _parent, _name, _config, _logger, _port):
        AMBE_BASE.__init__(self, _parent, _name, _config, _logger, _port)
        
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
        AMBE_BASE.send_voice_header(self, _rx_slot)
        flag = header_flag(_rx_slot.slot) # DT_VOICE_LC_HEADER
        dmr = self.encode_voice_header(_rx_slot)
        for j in range(0,2):
            self.send_frameTo_system(_rx_slot, flag, dmr)
            sleep(0.06)

    def send_voice72(self, _rx_slot, _ambe):
        flag = voice_flag(_rx_slot.slot, _rx_slot.vf) # calc flag value
        
        # Construct the dmr frame from AMBE(108 bits) + sync/CACH (48 bits) + AMBE(108 bits)
        _new_frame = self.encode_voice(BitArray('0x' + ahex(_ambe)), _rx_slot) 
        
        self.send_frameTo_system(_rx_slot, flag, _new_frame.tobytes())

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
        flag = terminator_flag(_rx_slot.slot) # DT_TERMINATOR_WITH_LC
        dmr = self.encode_voice_term( _rx_slot )
        self.send_frameTo_system(_rx_slot, flag, dmr)

    # Construct DMR frame, HB header and send result to all peers on network
    def send_frameTo_system(self, _rx_slot, _flag, _dmr_frame):
        # Make the HB frame, ready to send
        frame = self.make_dmrd(_rx_slot.seq, _rx_slot.rf_src, _rx_slot.dst_id, _rx_slot.repeater_id, _flag, _rx_slot.stream_id, _dmr_frame)         
        self.send_system(_rx_slot, frame)       # Send  the frame to all peers or master
        _rx_slot.seq += 1                       # Convienent place for this increment
        _rx_slot.frame_count += 1               # update count (used for stats and to make sure header was sent)

    # Override the super class because (1) DMO must be placed on slot 2 and (2) repeater_id must be the ID of the client (TODO)
    def send_system(self, _rx_slot, _frame):
        if hasattr(self._parent, '_peers'):
            _orig_flag = _frame[15] # Save off the flag since _frame is a reference
            for _peer in self._parent._peers:
                _peerDict = self._parent._peers[_peer]
                if _peerDict['TX_FREQ'] == _peerDict['RX_FREQ']:
                    if (self._DMOStreamID == 0) or (time() > self._DMOTimeout): # are we idle?
                        self._DMOStreamID = _rx_slot.stream_id
                        self._DMOTimeout = time() + 0.50
                        self._logger.info('(%s) DMO Transition from idle to stream %d', self._system, int_id(_rx_slot.stream_id))
                    if _rx_slot.stream_id != self._DMOStreamID: # packet is from wrong stream?
                        if (_frame[15] & 0x2F) == 0x21: # Call start?
                            self._logger.info('(%s) DMO Ignore traffic on stream %d', self._system, int_id(_rx_slot.stream_id))
                        continue
                    if (_frame[15] & 0x2F) == 0x22: # call terminator flag?
                        self._DMOStreamID = 0       # we are idle again
                        self._logger.info('(%s) DMO End of call, back to IDLE', self._system)

                    _frame[15] = (_frame[15] & 0x7f) | 0x80 # force to slot 2 if client in DMO mode
                else:
                    _frame[15] = _orig_flag # Use the origional flag value if not DMO

                _repeaterID = hex_str_4(int(_peerDict['PEER_ID']))
                for _index in range(0,4):   # Force the repeater ID to be the "destination" ID of the client (fne will not accept it otherwise)
                    _frame[_index + 11] = _repeaterID[_index]

                self._parent.send_peer(_peer, _frame)
                self._DMOTimeout = time() + 0.50
        else:
            self._parent.send_master(_frame)

    # Construct a complete HB frame from passed parameters
    def make_dmrd(self, _seq, _rf_src, _dst_id, _repeater_id, _flag, _stream_id, _dmr_frame):
        frame = bytearray('DMRD')                   # HB header type DMRD
        frame += struct.pack("i", _seq)[0]          # add sequence number
        frame += _rf_src[0:3]                       # add source ID
        frame += _dst_id[0:3]                       # add destination ID
        frame += _repeater_id[0:4]                  # add repeater ID (4 bytes)
        frame += struct.pack("i", _flag)[0:1]       # add flag to packet
        frame += _stream_id[0:4]                    # add stream ID (same for all packets in a transmission)
        frame += _dmr_frame                         # add the dmr frame
        frame += struct.pack("i", 0)[0:2]           # add in the RSSI and err count
        return frame
    
    # Private function to create a voice header or terminator DMR frame
    def __encode_voice_header(self, _rx_slot, _sync, _dtype):
        _src_id = _rx_slot.rf_src
        _dst_id = _rx_slot.dst_id
        _cc = _rx_slot.cc

        # create lc
        lc = '\x00\x00\x00' + _dst_id + _src_id         # PF + Reserved + FLCO + FID + Service Options + Group Address + Source Address

        # encode lc into info
        full_lc_encode = bptc.encode_header_lc(lc)
        _rx_slot.emblc = bptc.encode_emblc(lc)          # save off the emb lc for voice frames B-E
        _rx_slot.emblc[5] = bitarray(32)                # NULL message (F)

        # create slot_type
        slot_type = chr((_cc << 4) | (_dtype & 0x0f))   # data type is Header or Term

        # generate FEC for slot type
        slot_with_fec  = BitArray(uint=golay.encode_2087(slot_type), length=20)

        # construct final frame - info[0:98] + slot_type[0:10] + DMR_DATA_SYNC_MS + slot_type[10:20] + info[98:196]
        frame_bits = full_lc_encode[0:98] + slot_with_fec[0:10] + decode.to_bits(_sync) + slot_with_fec[10:20] + full_lc_encode[98:196]
        return decode.to_bytes(frame_bits)
    
    # Create a voice header DMR frame
    def encode_voice_header(self, _rx_slot):
        return self.__encode_voice_header(_rx_slot, DMR_DATA_SYNC_MS, 1) # data_type=Voice_LC_Header
    
    def encode_voice(self, _ambe1, _ambe2, _ambe3, _emb):
        pass
    
    # Create a voice DMR frame A-F frame type
    def encode_voice(self, _ambe, _rx_slot):
        _frame_type = _rx_slot.vf
        if _frame_type > 0:                                                 # if not a SYNC frame cccxss
            index = (_rx_slot.cc << 3) | self.lcss[_frame_type]             # index into the encode table makes this a simple lookup
            emb = bitarray(format(qr.ENCODE_1676[ index ], '016b'))         # create emb of 16 bits
            embedded = emb[8:16] + _rx_slot.emblc[_frame_type] + emb[0:8]   # Take emb and a chunk of the embedded LC and combine them into 48 bits
        else:
            embedded = BitArray(DMR_VOICE_SYNC_MS)                          # Voice SYNC (48 bits)
        _new_frame = _ambe[0:108] +  embedded + _ambe[108:216]              # Construct the dmr frame from AMBE(108 bits) + sync/emb (48 bits) + AMBE(108 bits)
        return _new_frame
    
    # Create a voice terminator DMR frame
    def encode_voice_term(self, _rx_slot):
        return self.__encode_voice_header(_rx_slot, DMR_DATA_SYNC_MS, 2)   # data_type=Voice_LC_Terminator

    def export_voice(self, _tx_slot, _seq, _ambe):
        self.send_tlv(TAG_AMBE_72, struct.pack("b", _tx_slot.slot) + _ambe)    # send AMBE
        if _seq != ((_tx_slot.lastSeq + 1) & 0xff):
            self._logger.info('(%s) Seq number not found.  got %d expected %d', self._system, _seq, _tx_slot.lastSeq+1)
            _tx_slot.lostFrame += 1
        _tx_slot.lastSeq = _seq

# ---------------------------------------------------------------------------
#   Class Declaration
#
# ---------------------------------------------------------------------------

class AMBE_IPSC(AMBE_BASE):
    def __init__(self, _parent, _name, _config, _logger, _port):
        AMBE_BASE.__init__(self, _parent, _name, _config, _logger, _port)
        self._tempHead = [0] * 3                         # It appears that there 3 frames of HEAD (mostly the same)
        self._tempVoice = [0] * 6
        self._tempTerm = [0]

        self._seq = 0                        # RPT Transmit frame sequence number (auto-increments for each frame). 16 bit
        self.ipsc_seq = 0                    # Same for all frames in a transmit session (sould use stream_id).  8 bit

        self.load_template()
        pass

    def send_voice_header(self, _rx_slot):
        AMBE_BASE.send_voice_header(self, _rx_slot)
        self._seq = randint(0,32767)                    # A transmission uses a random number to begin its sequence (16 bit)
        self.ipsc_seq = (self.ipsc_seq  + 1) & 0xff     # this is an 8 bit value which wraps around.

        for i in range(0, 3):                           # Output the 3 HEAD frames to our peers
            self.rewriteFrame(self._tempHead[i], _rx_slot.slot, _rx_slot.dst_id, _rx_slot.rf_src, _rx_slot.repeater_id)
            sleep(0.06)
        pass

    def send_voice72(self, _rx_slot, _ambe):
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
        _frame = self._tempVoice[_rx_slot.vf][:33] + ambe.tobytes() + self._tempVoice[_rx_slot.vf][52:]    # Insert the 3 49 bit AMBE frames
        self.rewriteFrame(_frame, _rx_slot.slot, _rx_slot.dst_id, _rx_slot.rf_src, _rx_slot.repeater_id)
        _rx_slot.vf = (_rx_slot.vf + 1) % 6                         # the voice frame counter which is always mod 6
        pass

    def send_voice49(self, _rx_slot, _ambe):
        ambe49_1 = BitArray('0x' + ahex(_ambe[0:7]))[0:50]
        ambe49_2 = BitArray('0x' + ahex(_ambe[7:14]))[0:50]
        ambe49_3 = BitArray('0x' + ahex(_ambe[14:21]))[0:50]
        ambe = ambe49_1 + ambe49_2 + ambe49_3

        _frame = self._tempVoice[_rx_slot.vf][:33] + ambe.tobytes() + self._tempVoice[_rx_slot.vf][52:]    # Insert the 3 49 bit AMBE frames
        self.rewriteFrame(_frame, _rx_slot.slot, _rx_slot.dst_id, _rx_slot.rf_src, _rx_slot.repeater_id)
        _rx_slot.vf = (_rx_slot.vf + 1) % 6                         # the voice frame counter which is always mod 6
        pass

    def send_voice_term(self, _rx_slot):
        self.rewriteFrame(self._tempTerm, _rx_slot.slot, _rx_slot.dst_id, _rx_slot.rf_src, _rx_slot.repeater_id)
        pass

    def rewriteFrame( self, _frame, _newSlot, _newGroup, _newSourceID, _newPeerID ):
        _peerId         = _frame[1:5]                 # int32 peer who is sending us a packet
        _src_sub        = _frame[6:9]                 # int32 Id of source
        _burst_data_type = _frame[30]
        _group          = _frame[9:12]

        ########################################################################
        # re-Write the peer radio ID to that of this program
        _frame = _frame.replace(_peerId, _newPeerID, 1)
        # re-Write the source subscriber ID + destination Group ID combo in the IPSC Header
        _frame = _frame.replace(_src_sub + _group, _newSourceID + _newGroup, 1)
        # Re-Write the destination Group ID + source subscriber ID combo in the decoded LCs
        _frame = _frame.replace(_group + _src_sub, _newGroup + _newSourceID, 1)

        _frame = _frame[:5] + struct.pack("i", self.ipsc_seq)[0] + _frame[6:]   # ipsc sequence number increments on each transmission (stream id)

        # Re-Write IPSC timeslot value
        _call_info = int_id(_frame[17:18])
        if _newSlot == 1:
            _call_info &= ~(1 << 5)
        elif _newSlot == 2:
            _call_info |= 1 << 5
        _call_info = chr(_call_info)
        _frame = _frame[:17] + _call_info + _frame[18:]

        _x = struct.pack("i", self._seq)
        _frame = _frame[:20] + _x[1] + _x[0] + _frame[22:]          # rtp sequence number increments for EACH frame sent out
        self._seq = self._seq + 1

        # Re-Write DMR timeslot value
        # Determine if the slot is present, so we can translate if need be
        if _burst_data_type == BURST_DATA_TYPE['SLOT1_VOICE'] or _burst_data_type == BURST_DATA_TYPE['SLOT2_VOICE']:
            # Re-Write timeslot if necessary...
            if _newSlot == 1:
                _burst_data_type = BURST_DATA_TYPE['SLOT1_VOICE']
            elif _newSlot == 2:
                _burst_data_type = BURST_DATA_TYPE['SLOT2_VOICE']
            _frame = _frame[:30] + _burst_data_type + _frame[31:]

        if (time() - self._parent._busy_slots[_newSlot]) >= 0.10 :          # slot is not busy so it is safe to transmit
            # Send the packet to all peers in the target IPSC
            self._parent.send_to_ipsc(_frame)
        else:
            self._logger.info('Slot {} is busy, will not transmit packet from gateway'.format(_newSlot))
        self.rx[_newSlot].frame_count += 1      # update count (used for stats and to make sure header was sent)

    # Read a record from the captured IPSC file looking for a payload type that matches the filter
    def readRecord(self, _file, _match_type):
        _notEOF = True
        #        _file.seek(0)
        while (_notEOF):
            _data = ""
            _bLen = _file.read(4)
            if _bLen:
                _len, = struct.unpack("i", _bLen)
                if _len > 0:
                    _data = _file.read(_len)
                    _payload_type   = _data[30]
                    if _payload_type == _match_type:
                        return _data
                else:
                    _notEOF = False
            else:
                _notEOF = False
        return _data

    def load_template(self):
        try:
            _t = open('template.bin', 'rb')             # Open the template file.  This was recorded OTA

            for i in range(0, 3):
                self._tempHead[i] = self.readRecord(_t, BURST_DATA_TYPE['VOICE_HEAD'])

            for i in range(0, 6):                       # Then there are 6 frames of AMBE.  We will just use them in order
                self._tempVoice[i] = self.readRecord(_t, BURST_DATA_TYPE['SLOT2_VOICE'])

            self._tempTerm = self.readRecord(_t, BURST_DATA_TYPE['VOICE_TERM'])
            _t.close()
        except IOError:
            self._logger.error('Can not open template.bin file')
            exit()
        self._logger.debug('IPSC templates loaded')

    def export_voice(self, _tx_slot, _seq, _ambe):
        self.send_tlv(TAG_AMBE_49, struct.pack("b", _tx_slot.slot) + _ambe)    # send AMBE
        if _seq != ((_tx_slot.lastSeq + 1) & 0xff):
            _tx_slot.lostFrame += 1
        _tx_slot.lastSeq = _seq
