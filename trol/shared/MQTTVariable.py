import json
from trol.shared.MQTT import MQTTConnectionManager
import time
import argparse
from typing import Any, Type, Union, Callable

from trol.shared.logger import setup_logger
log = setup_logger(__name__)

def make_observable(value, callback):
    """ Makes a potentially nested data structure into all ObservableList and ObservableDict and scalars. """
    if isinstance(value, dict):
        return ObservableDict(callback, {k: make_observable(v, callback) for k, v in value.items()})
    elif isinstance(value, list):
        return ObservableList(callback, [make_observable(v, callback) for v in value])
    else:
        return value

class ObservableDict(dict):
    """ Like it says on the tin, is a dict that calls callback when modified in-place """
    def __init__(self, callback, *args, **kwargs):
        self._callback = callback
        super().__init__(*args, **kwargs)

    def _trigger_callback(self):
        if self._callback:
            self._callback()

    def __setitem__(self, key, value):
        super().__setitem__(key, make_observable(value, self._callback))
        self._trigger_callback()

    def __delitem__(self, key):
        super().__delitem__(key)
        self._trigger_callback()

    def update(self, *args, **kwargs):
        super().update({k: make_observable(v, self._callback) for k, v in dict(*args, **kwargs).items()})
        self._trigger_callback()

    def clear(self):
        super().clear()
        self._trigger_callback()

class ObservableList(list):
    """ Like it says on the tin, is a list that calls callback when modified in-place """
    def __init__(self, callback, *args):
        self._callback = callback
        super().__init__([make_observable(v, self._callback) for v in args[0]])

    def _trigger_callback(self):
        if self._callback:
            self._callback()

    def append(self, item):
        super().append(make_observable(item, self._callback))
        self._trigger_callback()

    def extend(self, iterable):
        super().extend(make_observable(v, self._callback) for v in iterable)
        self._trigger_callback()

    def insert(self, index, item):
        super().insert(index, make_observable(item, self._callback))
        self._trigger_callback()

    def remove(self, item):
        super().remove(item)
        self._trigger_callback()

    def pop(self, index=-1):
        item = super().pop(index)
        self._trigger_callback()
        return item

    def clear(self):
        super().clear()
        self._trigger_callback()

    def __setitem__(self, index, value):
        super().__setitem__(index, make_observable(value, self._callback))
        self._trigger_callback()

    def __delitem__(self, index):
        super().__delitem__(index)
        self._trigger_callback()

class MQTTVariable:
    def __init__(self, mqtt_manager: MQTTConnectionManager, topic: str, value_type: Type = str, initial_value=None, callback: Callable[[None],None] = None):
        self._mqtt_manager = mqtt_manager
        self._topic = topic
        self._value_type = value_type
        self._callback = callback
        self._value = make_observable(initial_value, self.force_publish)

        # Subscribe to the MQTT topic
        self._mqtt_manager.subscribe(self._topic, self._on_message)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        self._value = make_observable(new_value, self.force_publish)
        self._publish(new_value)

    def _publish(self, value):
        if isinstance(value, (dict, list)):
            payload = json.dumps(value)
        else:
            payload = str(value)
        self._mqtt_manager.publish(self._topic, payload)

    def force_publish(self):
        self._publish(self._value)

    def add_callback(self, callback: Callable[[None],None] = None):
        self._callback = callback

    def _on_message(self, message):
        try:
            if self._value_type == int:
                self._value = int(message)
            elif self._value_type == float:
                self._value = float(message)
            elif self._value_type == bool:
                self._value = message.lower() in ('true', '1')
            elif self._value_type in [dict, list]:
                self._value = make_observable(json.loads(message), self.force_publish)
            else:
                self._value = message
        except (ValueError, json.JSONDecodeError) as e:
            log.error(f"Error converting message: {e}")
            self._value = message
        if self._callback is not None:
            try:
                self._callback()
            except Exception as e:
                log.error(f"Ignoring error in {self._topic} callback: {e}")

    def __del__(self):
        pass
        log.debug(f"Cleaning up subscription to {self._topic}")
        self._mqtt_manager.unsubscribe(self._topic, self._on_message)

def main():
    parser = argparse.ArgumentParser(description='MQTT Variable Example')
    parser.add_argument('--host', required=True, help='MQTT broker host')
    parser.add_argument('--port', type=int, default=1883, help='MQTT broker port')
    parser.add_argument('--username', help='MQTT username')
    parser.add_argument('--password', help='MQTT password')
    parser.add_argument('--client_id', help='MQTT client ID')
    parser.add_argument('--root_topic', required=True, help='Root MQTT topic')

    args = parser.parse_args()

    mqtt_manager = MQTTConnectionManager(args.host, args.port, args.username, args.password, args.client_id)

    # Create an MQTT variable
    update_var = MQTTVariable(mqtt_manager, f"{args.root_topic}/testing", initial_value="foo")

    # Process callbacks to ensure any incoming messages are handled
    mqtt_manager.process_callbacks(timeout=1)

    # Print the initial value
    print(f"Initial value: {update_var.value}")

    # Simulate updating the variable
    update_var.value = "bar"
    mqtt_manager.process_callbacks(timeout=1)
    print(f"Value after setting locally: {update_var.value}")

    
    # Simulate update from some other process
    mqtt_manager.publish(f"{args.root_topic}/testing", "baz")
    mqtt_manager.process_callbacks(timeout=1)
    print(f"Value after setting 'remotely': {update_var.value}")


if __name__ == '__main__':
    main()

