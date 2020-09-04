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
import bptc

def to_bits(_string):
    _bits = bitarray(endian='big')
    _bits.frombytes(_string)
    return _bits


def voice_head_term(_string):
    burst = to_bits(_string)
    info = burst[0:98] + burst[166:264]
    slot_type = burst[98:108] + burst[156:166]
    sync = burst[108:156]
    lc = bptc.decode_full_lc(info).tobytes()
    cc = to_bytes(slot_type[0:4])
    dtype = to_bytes(slot_type[4:8])
    return {'LC': lc, 'CC': cc, 'DTYPE': dtype, 'SYNC': sync}


def voice_sync(_string):
    burst = to_bits(_string)
    ambe = [0,0,0]
    ambe[0] = burst[0:72]
    ambe[1] = burst[72:108] + burst[156:192]
    ambe[2] = burst[192:264]
    sync = burst[108:156]
    return {'AMBE': ambe, 'SYNC': sync}
    
    
def voice(_string):
    burst = to_bits(_string)
    ambe = [0,0,0]
    ambe[0] = burst[0:72]
    ambe[1] = burst[72:108] + burst[156:192]
    ambe[2] = burst[192:264]
    emb = burst[108:116] + burst[148:156]
    embed = burst[116:148]
    cc = (to_bytes(emb[0:4]))
    lcss = (to_bytes(emb[5:7]))
    return {'AMBE': ambe, 'CC': cc, 'LCSS': lcss, 'EMBED': embed}


def to_bytes(_bits):
    add_bits = 8 - (len(_bits) % 8)
    if add_bits < 8:
        for bit in xrange(add_bits):
            _bits.insert(0,0)
    _string =  _bits.tobytes()
    return _string
