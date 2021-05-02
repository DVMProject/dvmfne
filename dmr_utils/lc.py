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
from bitstring import BitArray

from const import *
import bptc
import golay

def to_bits(_string):
    _bits = bitarray(endian = 'big')
    _bits.frombytes(_string)
    return _bits

def to_bytes(_bits):
    add_bits = 8 - (len(_bits) % 8)
    if add_bits < 8:
        for bit in xrange(add_bits):
            _bits.insert(0,0)
    _string =  _bits.tobytes()
    return _string

def encode_lc_header(_lc, _cc, _dtype, _sync):
    full_lc_encode = bptc.encode_header_lc(_lc)
    slot_type = chr((_cc << 4) | (ord(_dtype) & 0x0f))
    slot_with_fec = BitArray(uint = golay.encode_2087(slot_type), length = 20)
    frame_bits = full_lc_encode[0:98] + slot_with_fec[0:10] + _sync + slot_with_fec[10:20] + full_lc_encode[98:196]
    return to_bytes(frame_bits)

def encode_pi_header(_lc, _cc, _dtype, _sync):
    full_lc_encode = bptc.encode_header_pi(_lc)
    slot_type = chr((_cc << 4) | (ord(_dtype) & 0x0f))
    slot_with_fec = BitArray(uint = golay.encode_2087(slot_type), length = 20)
    frame_bits = full_lc_encode[0:98] + slot_with_fec[0:10] + _sync + slot_with_fec[10:20] + full_lc_encode[98:196]
    return to_bytes(frame_bits)

def decode_lc_header(_string):
    burst = to_bits(_string)
    info = burst[0:98] + burst[166:264]
    slot_type = burst[98:108] + burst[156:166]
    _sync = burst[108:156]
    _lc = bptc.decode_full_lc(info).tobytes()
    _cc = to_bytes(slot_type[0:4])
    _dtype = to_bytes(slot_type[4:8])
    return {'LC': _lc, 'CC': _cc, 'DTYPE': _dtype, 'SYNC': _sync}
