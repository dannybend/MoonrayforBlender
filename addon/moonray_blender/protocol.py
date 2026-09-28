# SPDX-License-Identifier: GPL-3.0-or-later
#
# Binary protocol spoken with moonray_bridge.
# Keep in sync with bridge/src/Protocol.h

import struct

MAGIC = 0x3142524D  # "MRB1"
PROTOCOL_VERSION = 1

# client -> bridge
HELLO = 1
RDLA = 2
MESH = 3
START = 4
STOP = 5
CLEAR = 6
ACK = 7
BYE = 9

# bridge -> client
WELCOME = 100
FRAME = 101
LOG = 102
ERROR = 104
COMPLETE = 105

HEADER = struct.Struct("<IIQ")          # magic, type, size
FRAME_HEADER = struct.Struct("<IIIIfI")  # width, height, channels, flags, progress, reserved

FRAME_FLAG_COMPLETE = 1
