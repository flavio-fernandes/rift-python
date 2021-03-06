# TODO: Replace from...import... with import...

import enum
import os
import socket
import random

import constants
import fsm
import mcast_receive_handler
import mcast_send_handler
import neighbor
import offer
import utils
import timer
from packet_common import create_packet_header, encode_protocol_packet, decode_protocol_packet

import common.constants
import common.ttypes
from encoding.ttypes import NodeCapabilities, LIEPacket
import encoding.ttypes

# TODO: LIEs arriving with a TTL larger than 1 MUST be ignored.

# TODO: Currently, adjacencies are tied to interfaces, so I don't have a separate class for Adjacencies.
#       That may change if multipoint interfaces are supported

# TODO: Implement configuration of POD numbers

# TODO: Send LIE packets with network control precedence.

# TODO: Add IPv6 support

# TODO: Have a mechanism to detect that an interface comes into / goes out of existence

# TODO: Have a mechanism to detect IPv4 or IPv6 address changes on an interface

class Interface:

    UNDEFINED_OR_ANY_POD = 0

    def generate_advertised_name(self):
        return self._node.name + '-' + self._interface_name

    def get_mtu(self):
        # TODO: Find a portable (or even non-portable) way to get the interface MTU
        # TODO: Find a way to be informed whenever the interface MTU changes
        mtu = 1500
        return mtu

    @staticmethod
    def generate_nonce():
        # 63 bits instead of 64 because nonce field is a signed i64
        nonce = random.getrandbits(63)
        return nonce

    class State(enum.Enum):
        ONE_WAY = 1
        TWO_WAY = 2
        THREE_WAY = 3

    class Event(enum.Enum):
        TIMER_TICK = 1
        LEVEL_CHANGED = 2
        HAL_CHANGED = 3
        HAT_CHANGED = 4
        HALS_CHANGED = 5
        LIE_RECEIVED = 6
        NEW_NEIGHBOR = 7
        VALID_REFLECTION = 8
        NEIGHBOR_DROPPED_REFLECTION = 9
        NEIGHBOR_CHANGED_LEVEL = 10
        NEIGHBOR_CHANGED_ADDRESS = 11
        NEIGHBOR_CHANGED_MINOR_FIELDS = 12     # Draft uses this in PROCESS_LIE step 3.4 but does not define it
        UNACCEPTABLE_HEADER = 13
        HOLD_TIME_EXPIRED = 14
        MULTIPLE_NEIGHBORS = 15
        LIE_CORRUPT = 16
        SEND_LIE = 17
        # UPDATE_ZTP_OFFER = 18      Removed. See deviation DEV-2 in doc/deviations.md. TODO: remove line completely.

    def action_store_hal(self):
        # TODO: Need to implement ZTP state machine first
        pass

    def action_store_hat(self):
        # TODO: Need to implement ZTP state machine first
        pass

    def action_store_hals(self):
        # TODO: Need to implement ZTP state machine first
        pass

    def action_update_level(self):
        # TODO: Need to implement ZTP state machine and/or configuration first
        pass

    def action_send_lie(self):
        packet_header = create_packet_header(self._node)
        capabilities = NodeCapabilities(
            flood_reduction = True,
            leaf_indications = common.ttypes.LeafIndications.leaf_only_and_leaf_2_leaf_procedures)
        if self._neighbor:
            neighbor_system_id = self._neighbor.system_id
            neighbor_link_id = self._neighbor.local_id
            lie_neighbor = encoding.ttypes.Neighbor(neighbor_system_id, neighbor_link_id)
        else:
            lie_neighbor = None
        lie_packet = LIEPacket(
            name = self._advertised_name,
            local_id = self._local_id,
            flood_port = self._node._rx_tie_port,
            link_mtu_size = self._mtu,
            neighbor = lie_neighbor,
            pod = self._pod,
            nonce = Interface.generate_nonce(),
            capabilities = capabilities,
            holdtime = 3,
            not_a_ztp_offer = False,                # TODO: Set not_a_ztp_offer
            you_are_not_flood_repeater = False,     # TODO: Set you_are_not_flood_repeater
            label = None)
        packet_content = encoding.ttypes.PacketContent(lie = lie_packet)
        protocol_packet = encoding.ttypes.ProtocolPacket(packet_header, packet_content)
        encoded_protocol_packet = encode_protocol_packet(protocol_packet)
        self._mcast_send_handler.send_message(encoded_protocol_packet)
        self.info(self._tx_log, "Send LIE {}".format(protocol_packet))

    def action_cleanup(self):
        self._neighbor = None

    def check_reflection(self):
        # Does the received LIE packet (which is now stored in _neighbor) report us as the neighbor?
        if self._neighbor.neighbor_system_id != self._node.system_id:
            self.info(self._log, "Neighbor does not report us as neighbor (system-id {:16x} instead of {:16x}"
                .format(self._neighbor.neighbor_system_id, self._node.system_id))
            return False
        if self._neighbor.neighbor_link_id != self._local_id:
            self.info(self._log, "Neighbor does not report us as neighbor (link-id {} instead of {}"
                .format(self._neighbor.neighbor_link_id, self._local_id))
            return False
        return True

    def check_three_way(self):
        # Section B.1.5
        # CHANGE: This is a little bit different from the specificaiton (see comment [CheckThreeWay])
        if self._fsm._state == self.State.ONE_WAY:
            pass 
        elif self._fsm._state == self.State.TWO_WAY:
            if self._neighbor.neighbor_system_id == None:
                pass
            elif self.check_reflection():
                self._fsm.push_event(self.Event.VALID_REFLECTION)
            else:
                self._fsm.push_event(self.Event.MULTIPLE_NEIGHBORS)
        else: # state is THREE_WAY
            if self._neighbor.neighbor_system_id == None:
                self._fsm.push_event(self.Event.NEIGHBOR_DROPPED_REFLECTION)
            elif self.check_reflection():
                pass
            else:
                self._fsm.push_event(self.Event.MULTIPLE_NEIGHBORS)

    def check_header(self, header):
        if not header:
            self.warning(self._rx_log, "Received packet without header")
            return False
        if header.major_version != constants.RIFT_MAJOR_VERSION:
            self.warning(self._rx_log, "Received packet with wrong major version (expected {} but got {})".format(
                constants.RIFT_MAJOR_VERSION, header.major_version))
            return False
        if not self.is_valid_received_system_id(header.sender):
            self.warning(self._rx_log, "Received packet with invalid system id")
            return False
        return True

    def check_minor_change(self, new_neighbor):
        # TODO: what if link_mtu_size changes?
        # TODO: what if pod changes?
        # TODO: what if capabilities changes?
        # TODO: what if holdtime changes?
        # TODO: what if not_a_ztp_offer changes?
        # TODO: what if you_are_not_flood_repeater changes?
        # TODO: what if label changes?
        minor_change = False
        if new_neighbor.flood_port != self._neighbor.flood_port:
            msg = "Neighbor flood-port changed from {} to {}".format(self._neighbor.flood_port, new_neighbor.flood_port)
            minor_change = True
        elif new_neighbor.name != self._neighbor.name:
            msg = "Neighbor name changed from {} to {}".format(self._neighbor.name, new_neighbor.name)
            minor_change = True
        elif new_neighbor.local_id != self._neighbor.local_id:
            msg = "Neighbor local-id changed from {} to {}".format(self._neighbor.local_id, new_neighbor.local_id)
            minor_change = True
        if minor_change:
            self.info(self._log, msg)
        return minor_change
        
    def send_offer_to_ztp_fsm(self, neighbor):
        offer_for_ztp = offer.Offer(neighbor.level, neighbor.not_a_ztp_offer, neighbor.system_id, self._fsm._state)  # TODO: _state is private
        self._node._fsm.push_event(self._node.Event.NEIGHBOR_OFFER, offer_for_ztp)

    def this_node_is_leaf(self):
        return self._node.level_value() == common.constants.leaf_level

    def remote_level_lower_than_hat(self, remote_level):
        return

    def difference_from_my_level(self, remote_level):
        assert self._node.level_value() != None
        assert remote_level != None
        return abs(remote_level - self._node.level_value())

    # TODO: Add counters for each of these conditions
    def received_header_unacceptable(self, remote_level):
        # Received level is unacceptable as defined in section B.1.4.3.2
        if remote_level == None:
            self._remote_header_unacceptable = True
            self._remote_header_unacceptable_reason = "LIE has undefined level"
        elif self._node.level_value() == None:
            self._remote_header_unacceptable = True
            self._remote_header_unacceptable_reason = "My level is undefined"
        elif self.this_node_is_leaf() and self.remote_level_lower_than_hat(remote_level):
            self._remote_header_unacceptable = True
            self._remote_header_unacceptable_reason = "This node is leaf and remote level lower than HAT"
        elif (remote_level != common.constants.leaf_level) and (self.difference_from_my_level(remote_level) > 1):
            self._remote_header_unacceptable = True
            self._remote_header_unacceptable_reason = "LIE's level is not leaf AND its difference is more than one from my level"
        else:
            self._remote_header_unacceptable = False
            self._remote_header_unacceptable_reason = ""
        return self._remote_header_unacceptable

    def action_process_lie(self, event_data):
        (protocol_packet, (from_address, from_port)) = event_data
        # Section B.1.4.1
        if not self.check_header(protocol_packet.header):
            self.action_cleanup()     # TODO: Don't need this since transition to state one-way will do this
            self._fsm.push_event(self.Event.UNACCEPTABLE_HEADER)   # TODO: Draft doesn't have this; need something to transition to state OneWay
            return
        # TODO: This is a simplistic way of implementing the hold timer. Use a real timer instead.
        self._time_ticks_since_lie_received = 0
        # Section B.1.4.3.2
        new_neighbor = neighbor.Neighbor(protocol_packet, from_address, from_port)
        if self.received_header_unacceptable(protocol_packet.header.level):
            self.action_cleanup()     # TODO: Don't need this since transition to state one-way will do this
            # Note: We send an offer to the ZTP state machine directly from here instead of pushing an UDPATE_ZTP_OFFER 
            # event (see deviation DEV-2 in doc/deviations)
            self.send_offer_to_ztp_fsm(new_neighbor)
            self._fsm.push_event(self.Event.UNACCEPTABLE_HEADER)   # TODO: Draft doesn't have this; need something to transition to state OneWay
            return
        # Section B.1.4.3
        # Note: We send an offer to the ZTP state machine directly from here instead of pushing an UDPATE_ZTP_OFFER 
        # event (see deviation DEV-2 in doc/deviations)
        self.send_offer_to_ztp_fsm(new_neighbor)
        if not self._neighbor:
            self.info(self._log, "New neighbor detected with system-id {:16x}".format(protocol_packet.header.sender))
            self._neighbor = new_neighbor
            self._fsm.push_event(self.Event.NEW_NEIGHBOR)
            self.check_three_way()
            return
        # Section B.1.4.3.1
        if new_neighbor.system_id != self._neighbor.system_id:
            self.info(self._log, "Neighbor system-id changed from {:16x} to {:16x}"
                .format(self._neighbor.system_id, new_neighbor.system_id))
            self._fsm.push_event(self.Event.MULTIPLE_NEIGHBORS)
            return
        # Section B.1.4.3.2
        if new_neighbor.level != self._neighbor.level:
            self.info(self._log, "Neighbor level changed from {} to {}"
                .format(self._neighbor.level, new_neighbor.level))
            self._fsm.push_event(self.Event.NEIGHBOR_CHANGED_LEVEL)
            return
        # Section B.1.4.3.3
        if new_neighbor.address != self._neighbor.address:
            self.info(self._log, "Neighbor address changed from {} to {}"
                .format(self._neighbor.address, new_neighbor.address))
            self._fsm.push_event(self.Event.NEIGHBOR_CHANGED_ADDRESS)
            return
        # Section B.1.4.3.4
        if self.check_minor_change(new_neighbor): 
            self._fsm.push_event(self.Event.NEIGHBOR_CHANGED_MINOR_FIELDS)
        self._neighbor = new_neighbor      # TODO: The draft does not specify this, but it is needed
        # Section B.1.4.3.5
        self.check_three_way()

    def action_check_hold_time_expired(self):
        # TODO: This is a (too) simplistic way of managing timers in the draft; use an explicit timer
        # If time_ticks_since_lie_received is None, it means the timer is not running
        self.info(self._log, "_time_ticks_since_lie_received = {}")
        if self._time_ticks_since_lie_received == None:
            return False
        self._time_ticks_since_lie_received += 1
        if self._neighbor and self._neighbor.holdtime:
            holdtime = self._neighbor.holdtime
        else:
            holdtime = common.constants.default_holdtime
        if self._time_ticks_since_lie_received >= holdtime:
            self._fsm.push_event(self.Event.HOLD_TIME_EXPIRED)

    _state_one_way_transitions = {
        Event.TIMER_TICK: (None, [], [Event.SEND_LIE]),
        Event.LEVEL_CHANGED: (State.ONE_WAY, [action_update_level], [Event.SEND_LIE]),
        Event.HAL_CHANGED: (None, [action_store_hal]),
        Event.HAT_CHANGED: (None, [action_store_hat]),
        Event.HALS_CHANGED: (None, [action_store_hals]),
        Event.LIE_RECEIVED: (None, [action_process_lie]),
        Event.NEW_NEIGHBOR: (State.TWO_WAY, [], [Event.SEND_LIE]),
        Event.UNACCEPTABLE_HEADER: (State.ONE_WAY, []),
        Event.HOLD_TIME_EXPIRED: (None, []),
        Event.SEND_LIE: (None, [action_send_lie]),
        # Removed. See deviation DEV-2 in doc/deviations.md. TODO: remove line completely.
        # Event.UPDATE_ZTP_OFFER: (None, [action_send_offer_to_ztp_fsm])
    }

    _state_two_way_transitions = {
        Event.TIMER_TICK: (None, [action_check_hold_time_expired], [Event.SEND_LIE]),
        Event.LEVEL_CHANGED: (State.ONE_WAY, [action_update_level]),
        Event.HAL_CHANGED: (None, [action_store_hal]),
        Event.HAT_CHANGED: (None, [action_store_hat]),
        Event.HALS_CHANGED: (None, [action_store_hals]),
        Event.HALS_CHANGED: (None, [action_store_hals]),
        Event.LIE_RECEIVED: (None, [action_process_lie]),
        Event.VALID_REFLECTION: (State.THREE_WAY, []),
        Event.NEIGHBOR_CHANGED_LEVEL: (State.ONE_WAY, []),
        Event.NEIGHBOR_CHANGED_ADDRESS: (State.ONE_WAY, []),
        Event.UNACCEPTABLE_HEADER: (State.ONE_WAY, []),
        Event.HOLD_TIME_EXPIRED: (State.ONE_WAY, []),
        Event.MULTIPLE_NEIGHBORS: (State.ONE_WAY, []),
        Event.LIE_CORRUPT: (State.ONE_WAY, []),             # This transition is not in draft
        Event.SEND_LIE: (None, [action_send_lie]),
        # Removed. See deviation DEV-2 in doc/deviations.md. TODO: remove line completely.
        # Event.UPDATE_ZTP_OFFER: (None, [action_send_offer_to_ztp_fsm]),
     }
     
    _state_three_way_transitions = {
        Event.TIMER_TICK: (None, [action_check_hold_time_expired], [Event.SEND_LIE]),
        Event.LEVEL_CHANGED: (State.ONE_WAY, [action_update_level]),
        Event.HAL_CHANGED: (None, [action_store_hal]),
        Event.HAT_CHANGED: (None, [action_store_hat]),
        Event.HALS_CHANGED: (None, [action_store_hals]),
        Event.LIE_RECEIVED: (None, [action_process_lie]),
        Event.NEIGHBOR_DROPPED_REFLECTION: (State.TWO_WAY, []),
        Event.NEIGHBOR_CHANGED_LEVEL: (State.ONE_WAY, []),
        Event.NEIGHBOR_CHANGED_ADDRESS: (State.ONE_WAY, []),
        Event.UNACCEPTABLE_HEADER: (State.ONE_WAY, []),
        Event.HOLD_TIME_EXPIRED: (State.ONE_WAY, []),
        Event.MULTIPLE_NEIGHBORS: (State.ONE_WAY, []),
        Event.LIE_CORRUPT: (State.ONE_WAY, []),             # This transition is not in draft
        Event.SEND_LIE: (None, [action_send_lie]),
        # Removed. See deviation DEV-2 in doc/deviations.md. TODO: remove line completely.
        # Event.UPDATE_ZTP_OFFER: (None, [action_send_offer_to_ztp_fsm])
    }

    _transitions = {
        State.ONE_WAY: _state_one_way_transitions,
        State.TWO_WAY: _state_two_way_transitions,
        State.THREE_WAY: _state_three_way_transitions
    }

    _state_entry_actions = {
        State.ONE_WAY: [action_cleanup]
    }

    fsm_definition = fsm.FsmDefinition(
        state_enum = State, 
        event_enum = Event, 
        transitions = _transitions, 
        state_entry_actions = _state_entry_actions,
        initial_state = State.ONE_WAY)

    def info(self, logger, msg):
        logger.info("[{}] {}".format(self._log_id, msg))

    def warning(self, logger, msg):
        logger.warning("[{}] {}".format(self._log_id, msg))

    def __init__(self, node, config):
        # TODO: process bandwidth field in config
        self._node = node
        self._interface_name = config['name']
        # TODO: Make the default metric/bandwidth depend on the speed of the interface
        self._metric  = self.get_config_attribute(config, 'metric', common.constants.default_bandwidth)
        self._advertised_name = self.generate_advertised_name()
        self._log_id = node._log_id + "-{}".format(self._interface_name)
        self._ipv4_address = utils.interface_ipv4_address(self._interface_name)
        self._rx_lie_ipv4_mcast_address = self.get_config_attribute(
            config, 'rx_lie_mcast_address', constants.DEFAULT_LIE_IPV4_MCAST_ADDRESS)
        self._tx_lie_ipv4_mcast_address = self.get_config_attribute(
            config, 'tx_lie_mcast_address', constants.DEFAULT_LIE_IPV4_MCAST_ADDRESS)
        self._rx_lie_ipv6_mcast_address = self.get_config_attribute(
            config, 'rx_lie_v6_mcast_address', constants.DEFAULT_LIE_IPV6_MCAST_ADDRESS)
        self._tx_lie_ipv6_mcast_address = self.get_config_attribute(
            config, 'tx_lie_v6_mcast_address', constants.DEFAULT_LIE_IPV6_MCAST_ADDRESS)
        self._rx_lie_port = self.get_config_attribute(config, 'rx_lie_port', constants.DEFAULT_LIE_PORT)
        self._tx_lie_port = self.get_config_attribute(config, 'tx_lie_port', constants.DEFAULT_LIE_PORT)
        self._rx_tie_port = self.get_config_attribute(config, 'rx_tie_port', constants.DEFAULT_TIE_PORT)
        self._log = node._log.getChild("if")
        self.info(self._log, "Create interface")
        self._rx_log = self._log.getChild("rx")
        self._tx_log = self._log.getChild("tx")
        self._fsm_log = self._log.getChild("fsm")
        self._local_id = node.allocate_interface_id()
        self._mtu = self.get_mtu()
        self._pod = self.UNDEFINED_OR_ANY_POD
        self._remote_header_unacceptable = False
        self._remote_header_unacceptable_reason = ""
        self._neighbor = None
        self._time_ticks_since_lie_received = None
        self._fsm = fsm.Fsm(
            definition = self.fsm_definition,
            action_handler = self,
            log = self._fsm_log,
            log_id = self._log_id)
        if self._node.running:
            self.run()

    def run(self):
        self._mcast_send_handler = mcast_send_handler.McastSendHandler(
            self._interface_name,
            self._tx_lie_ipv4_mcast_address, 
            self._tx_lie_port)
        (source_address, source_port) = self._mcast_send_handler.source_address_and_port()
        self._lie_udp_source_port = source_port
        self._mcast_receive_handler = mcast_receive_handler.McastReceiveHandler(
            self._interface_name,
            self._rx_lie_ipv4_mcast_address, 
            self._rx_lie_port,
            self._node.mcast_loop,
            self.receive_mcast_message)
        self._one_second_timer = timer.Timer(1.0, lambda: self._fsm.push_event(self.Event.TIMER_TICK))

    def get_config_attribute(self, config, attribute, default):
        if attribute in config:
            return config[attribute]
        else:
            return default
            
    def is_valid_received_system_id(self, system_id):
        if system_id == 0:
            return False
        return True
        
    def receive_mcast_message(self, message, from_address_and_port):
        # TODO: Handle decoding errors (does decode_protocol_packet throw an exception in that case? Try it...)
        protocol_packet = decode_protocol_packet(message)
        self.info(self._rx_log, "Receive {}".format(protocol_packet))
        if not protocol_packet.content:
            self.warning(self._rx_log, "Received packet without content")
            return
        if protocol_packet.content.lie:
            if self._node.mcast_loop and (self._node.system_id == protocol_packet.header.sender):
                self.info(self._log, "Ignore looped back LIE packet")
            else:
                event_data = (protocol_packet, from_address_and_port)
                self._fsm.push_event(self.Event.LIE_RECEIVED, event_data)
        if protocol_packet.content.tide:
            # TODO: process TIDE
            pass
        if protocol_packet.content.tire:
            # TODO: process TIDE
            pass
        if protocol_packet.content.tie:
            # TODO: process TIDE
            pass

    @staticmethod
    def cli_summary_headers():
        return [
            ["Interface", "Name"],
            ["Neighbor", "Name"],
            ["Neighbor", "System ID"],
            ["Neighbor", "State"]]

    def cli_summary_attributes(self):
        if self._neighbor:
            return [
                self._interface_name,
                self._neighbor.name,
                utils.system_id_str(self._neighbor.system_id),
                self._fsm._state.name]
        else:
            return [
                self._interface_name,
                "",
                "",
                self._fsm._state.name]

    def cli_detailed_attributes(self):
        return [
            ["Interface Name", self._interface_name],
            ["Advertised Name", self._advertised_name],
            ["Interface IPv4 Address", self._ipv4_address],
            ["Metric", self._metric],
            ["Receive LIE IPv4 Multicast Address", self._rx_lie_ipv4_mcast_address],
            ["Transmit LIE IPv4 Multicast Address", self._tx_lie_ipv4_mcast_address],
            ["Receive LIE IPv6 Multicast Address", self._rx_lie_ipv6_mcast_address],
            ["Transmit LIE IPv6 Multicast Address", self._tx_lie_ipv6_mcast_address],
            ["Receive LIE Port", self._rx_lie_port],
            ["Transmit LIE Port", self._tx_lie_port],
            ["Receive TIE Port", self._rx_tie_port],
            ["System ID", utils.system_id_str(self._node._system_id)],
            ["Local ID", self._local_id],
            ["MTU", self._mtu],
            ["POD", self._pod],
            ["State", self._fsm._state.name],
            ["Received Header Unacceptable", self._remote_header_unacceptable],
            ["Received Header Unacceptable Reason", self._remote_header_unacceptable_reason],
            ["Neighbor", "True" if self._neighbor else "False"]
        ]

    def cli_detailed_neighbor_attributes(self):
        if self._neighbor:
            return self._neighbor.cli_detailed_attributes()
        else:
            return None
