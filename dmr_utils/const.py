#!/usr/bin/env python
#
# Digital Voice Modem - Fixed Network Equipment
# GPLv2 Open Source. Use is subject to license terms.
# DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
#
# @package DVM / FNE
#
###############################################################################
#   Copyright (C) 2016  Cortney T. Buffington, N0MJS <n0mjs@me.com>
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
from bitarray import bitarray

# DMR Data Types
DT_VOICE_PI_HEADER = '\x00'
DT_VOICE_LC_HEADER = '\x01'
DT_TERMINATOR_WITH_LC = '\x02'
DT_CSBK = '\x03'
DT_DATA_HEADER = '\x06'
DT_RATE_12_DATA = '\x07'
DT_RATE_34_DATA = '\x08'

# Sync patterns used for LC and Voice Burst A packets
BS_VOICE_SYNC = bitarray()
BS_DATA_SYNC  = bitarray()
BS_VOICE_SYNC.frombytes(b'\x75\x5F\xD7\xDF\x75\xF7')
BS_DATA_SYNC.frombytes(b'\xDF\xF5\x7D\x75\xDF\x5D')

MS_VOICE_SYNC = bitarray()
MS_DATA_SYNC = bitarray()
MS_VOICE_SYNC.frombytes(b'\x7F\x7D\x5D\xD5\x7D\xFD')
MS_DATA_SYNC.frombytes(b'\xD5\xD7\xF7\x7F\xD7\x57')

SYNC_TYPE_NONE = 0x00
SYNC_TYPE_VOICE = 0x01
SYNC_TYPE_DATA = 0x02

# Feature Set
FID_ETSI = '\x00'
FID_DMRA = '\x10'

# LC Options - Use for Group Voice
LC_OPT = '\x00\x00\x20'

LC_GROUP_VOICE = '\x00'
LC_PRIVATE_VOICE = '\x01'

LC_SVC_OPT_EMERGENCY = '\x80'
LC_SVC_OPT_PRIVACY = '\x40'
LC_SVC_OPT_BCAST = '\x08'
LC_SVC_OPT_OVCM = '\x04'

CALL_PRIORITY_NONE = '\x00'
CALL_PRIORITY_1 = '\x01'
CALL_PRIORITY_2 = '\x02'    # Default Priority
CALL_PRIORITY_3 = '\x03'

# Voice Control
VC_EMBEDDED_LC_BITS = 0x02
VC_EMB = 0x04
VC_EMBEDDED_LC = 0x10
VC_SYNC = 0x40

# Precomputed EMB values, where CC always = 1, and PI always = 0
EMB = {
    'BURST_B': bitarray('0001001110010001'),
    'BURST_C': bitarray('0001011101110100'),
    'BURST_D': bitarray('0001011101110100'),
    'BURST_E': bitarray('0001010100000111'),
    'BURST_F': bitarray('0001000111100010')
}

# Precomputed Slot Type values where CC always = 1
SLOT_TYPE = {
    'PI_HEAD':       bitarray('00010000001101100111'),
    'VOICE_LC_HEAD': bitarray('00010001101110001100'),
    'VOICE_LC_TERM': bitarray('00010010101001011001'),
    'CSBK':          bitarray('00010011001010110010'),
    'MBC_HEAD':      bitarray('00010100100111110000'),
    'MBC_CONT':      bitarray('00010101000100011011'),
    'DATA_HEAD':     bitarray('00010110000011001110'),
    '1/2_DATA':      bitarray('00010111100000100101'),
    '3/4_DATA':      bitarray('00011000111010100001'),
    'IDLE':          bitarray('00011001011001001010'),
    '1/1_DATA':      bitarray('00011010011110011111'),
    'RES_1':         bitarray('00011011111101110100'),
    'RES_2':         bitarray('00011100010000110110'),
    'RES_3':         bitarray('00011101110011011101'),
    'RES_4':         bitarray('00011110110100001000'),
    'RES_5':         bitarray('00011111010111100011')
}

# LC infor for first 3 Bytes:
# Byte 1: PF (1),Res(1),FLCO(6) -- Byte 2: FID(8) -- Byte 3: Service Options(8)
LC_VOICE = {
    'FLCO-GRP': bitarray('00000000'),
    'FLCO-USR': bitarray('00000011'),
    'FID-GENC': bitarray('00000000'),
    'FID-MOTO': bitarray('00010000'),
    'SVC-OVCM': bitarray('00100000'),
    'SVC-NONE': bitarray('00000000')
}

'''
EMB: CC(4b), PI(1b), LCSS(2b), EMB Parity(9b - QR 16,7,5)
Slot Type: CC(4b), DataType(4), Slot Type Parity(12b - )
'''
