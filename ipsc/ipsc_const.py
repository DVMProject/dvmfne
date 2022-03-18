#
# Digital Voice Modem - Fixed Network Equipment
# GPLv2 Open Source. Use is subject to license terms.
# DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
#
# @package DVM / FNE / dmrlink
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

# Known IPSC Message Types
CALL_CONFIRMATION     = b'\x05' # Confirmation FROM the recipient of a confirmed call.
TXT_MESSAGE_ACK       = b'\x54' # Doesn't seem to mean success, though. This code is sent success or failure
CALL_MON_STATUS       = b'\x61' #  |
CALL_MON_RPT          = b'\x62' #  | Exact meaning unknown
CALL_MON_NACK         = b'\x63' #  |
XCMP_XNL              = b'\x70' # XCMP/XNL control message
GROUP_VOICE           = b'\x80'
PVT_VOICE             = b'\x81'
GROUP_DATA            = b'\x83'
PVT_DATA              = b'\x84'
RPT_WAKE_UP           = b'\x85' # Similar to OTA DMR "wake up"
INTERRUPT_REQUEST     = b'\x86' 
MASTER_REG_REQ        = b'\x90' # FROM peer TO master
MASTER_REG_REPLY      = b'\x91' # FROM master TO peer
PEER_LIST_REQ         = b'\x92' # From peer TO master
PEER_LIST_REPLY       = b'\x93' # From master TO peer
PEER_REG_REQ          = b'\x94' # Peer registration request
PEER_REG_REPLY        = b'\x95' # Peer registration reply
MASTER_ALIVE_REQ      = b'\x96' # FROM peer TO master
MASTER_ALIVE_REPLY    = b'\x97' # FROM master TO peer
PEER_ALIVE_REQ        = b'\x98' # Peer keep alive request
PEER_ALIVE_REPLY      = b'\x99' # Peer keep alive reply
DE_REG_REQ            = b'\x9A' # Request de-registration from system
DE_REG_REPLY          = b'\x9B' # De-registration reply

# IPSC Version Information
IPSC_VER_14           = b'\x00'
IPSC_VER_15           = b'\x00'
IPSC_VER_15A          = b'\x00'
IPSC_VER_16           = b'\x01'
IPSC_VER_17           = b'\x02'
IPSC_VER_18           = b'\x02'
IPSC_VER_19           = b'\x03'
IPSC_VER_22           = b'\x04'

# Link Type Values - assumed that cap+, etc. are different, this is all I can confirm
LINK_TYPE_IPSC        = b'\x04'

# Burst Data Types
BURST_DATA_TYPE = {
    'PI_HEADER':        b'\x00',
    'VOICE_HEADER':     b'\x01',
    'VOICE_TERMINATOR': b'\x02',
    'CSBK':             b'\x03',
    'DATA_HEADER':      b'\x06',
    'UNCONFIRMED_DATA': b'\x07',
    'CONFIRMED_DATA':   b'\x08',
    'SLOT1_VOICE':      b'\x0A',
    'SLOT2_VOICE':      b'\x8A'   # This is really a flip of bit 7; of the SLOT1_VOICE data type
}

# IPSC Version and Link Type are Used for a 4-byte version field in registration packets
IPSC_VER              = LINK_TYPE_IPSC + IPSC_VER_17 + LINK_TYPE_IPSC + IPSC_VER_16

# Packets that must originate from a peer (or master peer)
ANY_PEER_REQUIRED = [GROUP_VOICE, PVT_VOICE, GROUP_DATA, PVT_DATA, CALL_MON_STATUS, CALL_MON_RPT, CALL_MON_NACK, XCMP_XNL, RPT_WAKE_UP, DE_REG_REQ]

# Packets that must originate from a non-master peer
PEER_REQUIRED = [PEER_ALIVE_REQ, PEER_ALIVE_REPLY, PEER_REG_REQ, PEER_REG_REPLY]

# Packets that must originate from a master peer
MASTER_REQUIRED = [PEER_LIST_REPLY, MASTER_ALIVE_REPLY]

# User-Generated Packet Types
USER_PACKETS = [GROUP_VOICE, PVT_VOICE, GROUP_DATA, PVT_DATA]

# RTP Constants (https://en.wikipedia.org/wiki/Real-time_Transport_Protocol)

RTP_VER = b'\x80'                    # Actually; this isn't just the version but Version, Padding Flag, Extension Flag and 4-bit CC

RTP_PAYLOAD_VOICE_HEADER = b'\xDD'   # Based on fuzzy analysis of Wireshark dumps of IPSC -- 0xDD seems to be used for the 1st VOICE HEADER (its just VOICE with bit 8 set)
RTP_PAYLOAD_VOICE = b'\x5D'          # Based on fuzzy analysis of Wireshark dumps of IPSC -- 0x5D seems to be used for VOICE HEADER and VOICE
RTP_PAYLOAD_TERM = b'\x5E'           # Based on fuzzy analysis of Wireshark dumps of IPSC -- 0x5E seems to be used for VOICE TERMINATOR

# RCM (Repeater Call Monitor) Constants
TS = {
    b'\x00': '1',
    b'\x01': '2'
}

NACK = {
    b'\x05': 'BSID Start',
    b'\x06': 'BSID End'
}

TYPE = {
    b'\x30': 'Private Data Set-Up',
    b'\x31': 'Group Data Set-Up',
    b'\x32': 'Private CSBK Set-Up',
    b'\x45': 'Call Alert',
    b'\x47': 'Radio Check Request',
    b'\x48': 'Radio Check Success',
    b'\x49': 'Radio Disable Request',
    b'\x4A': 'Radio Disable Received',
    b'\x4B': 'Radio Enable Request',
    b'\x4C': 'Radio Enable Received',
    b'\x4D': 'Remote Monitor Request',
    b'\x4E': 'Remote Monitor Request Received', #(doesn't mean it was successful) 
    b'\x4D': 'Remote Monitor Request',
    b'\x4F': 'Group Voice',
    b'\x50': 'Private Voice',
    b'\x51': 'Group Data',
    b'\x52': 'Private Data',
    b'\x53': 'All Call',
    b'\x54': 'Message ACK/Failure', #text message acknowledgement, but doesn't mean it was successful - it gives the same code if it worked or failed...
    b'\x84': 'ARS/GPS?' # Not yet clear, seen by a user running ARS & GPS
}

SEC = {
    b'\x00': 'None',
    b'\x01': 'Basic',
    b'\x02': 'Enhanced'
}

STATUS = {
    b'\x01': 'Active',
    b'\x02': 'End',
    b'\x05': 'TS In Use',
    b'\x08': 'RPT Disabled',
    b'\x09': 'RF Interference',
    b'\x0A': 'BSID ON',
    b'\x0B': 'Timeout',
    b'\x0C': 'TX Interrupt'
}

REPEAT = {
    b'\x01': 'Repeating',
    b'\x02': 'Idle',
    b'\x03': 'TS Disabled',
    b'\x04': 'TS Enabled'
}
