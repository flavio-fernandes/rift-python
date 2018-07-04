import sys
sys.path.append('gen-py')

# TODO: Add IPv6 support
# TODO: Handle receiving malformed packets

from thrift.protocol import TBinaryProtocol
from thrift.transport import TTransport
from encoding.ttypes import PacketHeader, LIEPacket, ProtocolPacket

def create_lie_protocol_packet(config):
    # TODO use information in config to create packet header
    packet_header = PacketHeader(
        major_version = 11,
        minor_version = 0,
        sender = None,
        level = None
    )
    # TODO use information in config to create LIE Packet
    lie_packet = LIEPacket(
        name = '',
        local_id = None,
        flood_port = 912,        # TODO: Is this the right default?
        link_mtu_size = 1400,
        neighbor = None,
        pod = 0,
        nonce = None,
        capabilities = None,
        holdtime = 3,            # TODO: Should this be hold_time?
        not_a_ztp_offer = False,
        you_are_not_flood_repeater = False,
        label = None)
    protocol_packet = ProtocolPacket(packet_header, lie_packet)
    return protocol_packet

def encode_protocol_packet(protocol_packet):
    transport_out = TTransport.TMemoryBuffer()
    protocol_out = TBinaryProtocol.TBinaryProtocol(transport_out)
    protocol_packet.write(protocol_out)
    encoded_protocol_packet = transport_out.getvalue()
    return encoded_protocol_packet

def decode_lie_packet(encoded_lie_packet):
    transport_in = TTransport.TMemoryBuffer(encoded_lie_packet)
    protocol_in = TBinaryProtocol.TBinaryProtocol(transport_in)
    lie_packet = LIEPacket()
    lie_packet.read(protocol_in)
    return lie_packet


