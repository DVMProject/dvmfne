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
from binascii import b2a_hex as ahex

from dmr_utils.golay_tables import *

X22     = 0x00400000   # vector representation of X^22
X18     = 0x00040000   # vector representation of X^18
X11     = 0x00000800   # vector representation of X^11
MASK12  = 0xfffff800   # auxiliary vector for testing
MASK8   = 0xfffff800   # auxiliary vector for testing
GENPOL  = 0x00000c75   # generator polinomial, g(x)

# This routine currently uses hex strings of the precalculated codes.
# This generates them from the integer table for (20,8,7) 
ENCSTR_2087 = [0 for x in range(256)]
for value in range(256):
    ENCSTR_2087[value] = hex(ENCODE_2087[value])[2:].rjust(4,'0')

def get_synd_1987(_pattern):
    aux = X18
    if _pattern >= X11:
        while _pattern & MASK8:
            while not (aux & _pattern):
                aux = aux >> 1
            _pattern = _pattern ^ ((aux / X11) * GENPOL)
    return _pattern

def get_synd_23127(_pattern):
    aux = X22
    if _pattern >= X11:
        while _pattern & MASK12:
            while not (aux & _pattern):
                aux = aux >> 1
            _pattern = _pattern ^ ((aux / X11) * GENPOL)
    return _pattern

def decode_2087(_data):
    bin_data = int(ahex(_data), 16)
    syndrome = get_synd_1987(bin_data)
    error_pattern = DECODE_1987[syndrome]
    if error_pattern != 0x00:
        bin_data = bin_data ^ error_pattern
    return bin_data >> 12

def encode_2087(_data):
    byte = ord(_data)
    cksum = ENCODE_2087[byte]
    return ( byte << 12 | (cksum & 0xFF) << 4 | cksum >> 12)
