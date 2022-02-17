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

# Protocol Tags
TAG_DMR_DATA = b'DMRD'
TAG_P25_DATA = b'P25D'

TAG_MASTER_WL_RID = b'MSTWRID'
TAG_MASTER_BL_RID = b'MSTBRID'
TAG_MASTER_ACTIVE_TGS = b'MSTTID'
TAG_MASTER_DEACTIVE_TGS = b'MSTDTID'
TAG_MASTER_NAK = b'MSTNAK'
TAG_MASTER_CLOSING = b'MSTCL'
TAG_MASTER_PONG = b'MSTPONG'

TAG_REPEATER_ACK = b'RPTACK'
TAG_REPEATER_CLOSING = b'RPTCL'
TAG_REPEATER_LOGIN = b'RPTL'
TAG_REPEATER_AUTH = b'RPTK'
TAG_REPEATER_OPTIONS = b'RPTO'
TAG_REPEATER_CONFIG = b'RPTC'
TAG_REPEATER_PING = b'RPTPING'
TAG_REPEATER_SLEEP = b'RPTSL'

TAG_TRANSFER_ACT_LOG = b'TRNSLOG'
TAG_TRANSFER_DIAG_LOG = b'TRNSDIAG'

# Timers
STREAM_TO = .360

# Frame Types
FT_VOICE = 0x0
FT_VOICE_SYNC = 0x1
FT_DATA_SYNC = 0x2

# DMR Data Types
DT_VOICE_PI_HEADER = 0x0
DT_VOICE_LC_HEADER = 0x1
DT_TERMINATOR_WITH_LC = 0x2
DT_CSBK = 0x3
DT_DATA_HEADER = 0x6
DT_RATE_12_DATA = 0x7
DT_RATE_34_DATA = 0x8
DT_IDLE = 0x9
DT_RATE_1_DATA = 0xA

# P25 DUID Types
P25_DUID_HDU = 0x0
P25_DUID_TDU = 0x3
P25_DUID_LDU1 = 0x5
P25_DUID_TSDU = 0x7
P25_DUID_LDU2 = 0xA
P25_DUID_PDU = 0xC
P25_DUID_TDULC = 0xF

# P25 LCF Types
P25_LC_GROUP = 0x00
P25_LC_PRIVATE = 0x03

P25_LCF_TSBK_CALL_ALERT = 0x1F
P25_LCF_TSBK_ACK_RSP_FNE = 0x20

P25_TSBK_IOSP_GRP_AFF = 0x28
P25_TSBK_OSP_U_DEREG_ACK = 0x2F
P25_TSBK_OSP_ADJ_STS_BCAST = 0x3C
