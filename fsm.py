from collections import deque
from table import Table

# TODO: Check completeness of FSM
# TODO: Report superfluous transitions (same effect in every state)
# TODO: Report could-be-implicit transitions (no effect: no actions, no pushed events, back to same state)
# TODO: Report implicit transitions

class FiniteStateMachine:

    _event_queue = deque()

    def info(self, msg):
        self._log.info("[{}] {}".format(self._log_id, msg))

    def warning(self, msg):
        self._log.warning("[{}] {}".format(self._log_id, msg))

    def __init__(self, state_enum, event_enum, transitions, initial_state, action_handler, log, log_id):
        self._log = log
        self._log_id = log_id
        self._state_enum = state_enum
        self._event_enum = event_enum
        self._transitions = transitions
        self._state = initial_state
        self._action_handler = action_handler
        self.info("Create FSM, state={}".format(self._state.name))

    def push_event(self, event, event_data = None):
        fsm = self
        event_tuple = (fsm, event, event_data)
        self._event_queue.append(event_tuple)

    @staticmethod 
    def process_queued_events():
        while FiniteStateMachine._event_queue:
            event_tuple = FiniteStateMachine._event_queue.popleft()
            fsm = event_tuple[0]
            event = event_tuple[1]
            event_data = event_tuple[2]
            fsm.process_event(event, event_data)

    def process_event(self, event, event_data):
        if event_data:
            self.info("FSM process event, state={} event={} event_data={}".format(
                self._state.name, event.name, event_data))
        else:
            self.info("FSM process event, state={} event={}".format(self._state.name, event.name))
        from_state = self._state
        if from_state in self._transitions:
            from_state_transitions = self._transitions[from_state]
        else:
            from_state_transitions = []
        if event in from_state_transitions:
            transition = from_state_transitions[event]
            to_state = transition[0]
            actions = transition[1]
            if len(transition) > 2:
                push_events = transition[2]
            else:
                push_events = []
            for action in actions:
                self.info("FSM invoke action, action={}".format(self._action_to_name(action)))
                action(self=self._action_handler)
            for push_event in push_events:
                self.info("FSM push event, event={}".format(push_event.name))
                self.push_event(push_event)
            if to_state != None:
                print("FSM transition, from_state={} to_state={}".format(_self._state.name, to_state.name))
                self._state = to_state
        else:
            self.warning("FSM missing transition, state={} event={}".format(self._state.name, event.name))

    def make_transition_table(self, report_missing = False):
        table = Table()
        table.add_row(['From state', 'Event', 'To state', 'Actions', 'Push events'])
        for from_state in self._state_enum:
            if from_state in self._transitions:
                from_state_transitions = self._transitions[from_state]
            else:
                from_state_transitions = []
            self._add_from_transitions_to_table(table, from_state, from_state_transitions, report_missing)
        return table

    def print_transition_table(self, report_missing = False):
        table = self.make_transition_table(report_missing)
        table.print()

    def _add_from_transitions_to_table(self, table, from_state, from_state_transitions, report_missing):
        for event in self._event_enum:
            if event in from_state_transitions:
                transition = from_state_transitions[event]
                self._add_transition_to_table(table, from_state, event, transition)
            else:
                if report_missing:
                    self._add_missing_transition_to_table(table, from_state, event)

    def _action_to_name(self, action):
        action_name = action.__name__
        if action_name.startswith("action_"):
            action_name = action_name[len("action_"):]
        return action_name

    def _event_to_name(self, event):
        return event.name

    def _add_transition_to_table(self, table, from_state, event, transition):
        from_state_name = from_state.name
        event_name = event.name
        to_state = transition[0]
        if to_state == None:
            to_state_name = "-"
        else:
            to_state_name = to_state.name
        actions = transition[1]
        action_names = list(map(self._action_to_name, actions))
        if action_names == []:
            action_names = '-'
        if len(transition) > 2:
            push_events = transition[2]
        else:
            push_events = []
        push_event_names = list(map(self._event_to_name, push_events))
        if push_event_names == []:
            push_event_names = '-'
        table.add_row([from_state_name, event_name, to_state_name, action_names, push_event_names])

    def _add_missing_transition_to_table(self, table, from_state, event):
        from_state_name = from_state.name
        event_name = event.name
        table.add_row([from_state_name, event_name, '* MISSING *', 
            Table.Format.EXTEND_LEFT_CELL, Table.Format.EXTEND_LEFT_CELL])

    def _transition_to_state(self, state):
        print("Transition from state {} to state {}".format(state_to_string(self._state), state_to_string(state)))
        self._state = state
