# Classes for importing and merging yaml files specified either from an environment variable, or from a command-line parameter or
# wherever else.
# Imported data hierarchy allows access to elements in either attribute-style (e.g settings.foo.bar) or dictionary style (e.g. settings['foo']['bar'])
# or mixed as you like (e.g. settings['foo'].bar) because I probably am insane.
#
import os
import yaml
import json
import argparse
import argcomplete
from traceback import format_exc

from trol.shared.logger import setup_logger, set_debug
from collections.abc import MutableMapping
from trol.shared.MQTT import MQTTConnectionManager 
from trol.shared.MQTTVariable import MQTTVariable

log = setup_logger(__name__)
#set_debug(log)

class ConfigNode(MutableMapping):
    def __init__(self, data = None, on_change = None):
        self._on_change_callback = on_change
        self._load_data(data)

    def _load_data(self, data=None):
        if data is None:
            data = {}
        self._data = {}
        for key, value in data.items():
            if isinstance(value, dict):
                self._data[key] = ConfigNode(value, on_change=self._on_change_callback)
            else:
                self._data[key] = value

    def set_on_change(self, on_change):
        self._on_change_callback = on_change
        # Propagate to all sub-nodes
        for value in self._data.values():
            if isinstance(value, ConfigNode):
                value.set_on_change(on_change)
    
    def isempty(self):
        return not bool(self._data)

    def __getattr__(self, item):
        if item.startswith('_'):
            if item in self.__dict__:
                return self.__dict__[item]
            else:
                raise AttributeError(f"'ConfigNode' object has no attribute '{item}'")
        else:
            try:
                return self._data[item]
            except KeyError:
                raise AttributeError(f"'ConfigNode' object has no attribute '{item}'")

    def __getitem__(self, item):
        return self._data[item]

    def get(self, item, default=None):
        return self._data.get(item, default)

    def __setattr__(self, key, value):
        if key.startswith('_'):
            super().__setattr__(key, value)
        else:
            if isinstance(value, dict):
                self._data[key] = ConfigNode(value, on_change=self._on_change_callback)
            else:
                self._data[key] = value
            if self._on_change_callback:
                try:
                    self._on_change_callback(key, value)
                except Exception as e:
                    log.warn(f"Ignored exception in on_change callback: {e}: {format_exc()}")

    def __setitem__(self, key, value):
        if key.startswith('_'):
            super().__setattr__(key, value)
        else:
            if isinstance(value, dict):
                self._data[key] = ConfigNode(value, on_change=self._on_change_callback)
            else:
                self._data[key] = value
            if self._on_change_callback:
                try:
                    self._on_change_callback(key, value)
                except Exception as e:
                    log.warn(f"Ignored exception in on_change callback: {e}: {format_exc()}")

    def __delattr__(self, key):
        try:
            del self._data[key]
            try:
                self._on_change_callback(key, value)
            except Exception as e:
                log.warn(f"Ignored exception in on_change callback: {e}: {format_exc()}")
        except KeyError:
            raise AttributeError(f"'ConfigNode' object has no attribute '{key}'")

    def __delitem__(self, key):
        del self._data[key]
        try:
            self._on_change_callback(key, value)
        except Exception as e:
            log.warn(f"Ignored exception in on_change callback: {e}: {format_exc()}")


    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def to_dict(self):
        result = {}
        for key, value in self._data.items():
            if isinstance(value, ConfigNode):
                result[key] = value.to_dict()
            else:
                result[key] = value
        return result

    def to_yaml(self):
        return yaml.dump(self.to_dict(), default_flow_style=False)

    def to_json(self, pretty = False):
        if pretty:
            return json.dumps(self.to_dict(), indent=4)
        else:
            return json.dumps(self.to_dict(), separators=(',', ':'))

    def __repr__(self):
        return self.to_json()

    def merge(self, other):
        if isinstance(other, dict):
            other = ConfigNode(other)
        elif not isinstance(other, ConfigNode):
            raise TypeError(f"Can only merge with a dict or another ConfigNode instance.  {other}")

        for key, value in other.items():
            log.debug(f"merge {key} = {value}")
            if key in self._data and isinstance(self._data[key], ConfigNode) and isinstance(value, ConfigNode):
                self._data[key].merge(value)
            else:
                self._data[key] = value

class Settings(ConfigNode):
    def __init__(self, *args, singleton_name = None, **kwargs):
        self._singleton_name = singleton_name
        self._mqtt = None
        self._mqtt_topic = None
        self._mqtt_var = None
        super().__init__(*args, **kwargs)

    def save_to_yaml_file(self, file_path):
        with open(file_path, 'w') as file:
            yaml.safe_dump(self.to_dict(), file)

    def load_from_yaml_file(self, file_path):
        with open(file_path, 'r') as file:
            config = yaml.safe_load(file)
        self._load_data(config)

    def load_from_environment(self, environment_variable = 'CONFIG_FILE_PATH'):
        config_file_path = os.getenv(environment_variable)
        if config_file_path:
            self.load_from_yaml_file(config_file_path)

    def load_from_command_line(self):
        """ For executables that don't otherwise care about the CLI """
        parser = argparse.ArgumentParser(description='Settings module')
        parser.add_argument('--config', type=str, help='Path to the config file', default='config.yaml')
        args, unknown = parser.parse_known_args()
        self.load_from_yaml_file(args.config)

    def sync_via_mqtt(self, mqtt: MQTTConnectionManager, topic: str):
        """ Create a MQTTVariable to copy ourselves into and read updates from other processes """
        self._mqtt = mqtt
        self._topic = topic
        self._mqtt_var = MQTTVariable(self._mqtt, topic)
        self._mqtt_var.add_callback(lambda: self.update_from_mqtt())
        self.set_on_change(lambda _key, _value: self.perform_sync())

    def perform_sync(self):
        """ Send our current state into the MQTT """
        self._mqtt_var.value = self.to_dict()

    def update_from_mqtt(self):
        """ Update our current state from MQTT """
        # NOTE: Merging does not trigger on_change and that's how we want it to be.
        log.debug(f"{self._singleton_name} merging from MQTT...")
        self.merge(json.loads(self._mqtt_var.value))

class SettingsSingletons():
    _instances = {}

    @classmethod
    def get_instance(cls, name = 'default'):
        if name is None:
            name = 'default'
        if name not in cls._instances:
            cls._instances[name] = Settings(singleton_name = name)  
            log.debug(f"Returing {name} singleton")
        return cls._instances[name]

    @classmethod
    def set_instance(cls, name, settings):
        cls._instances[name] = settings

    @classmethod
    def reset_instance(cls, name):
        if name in cls._instances:
            del cls._instances[name]

    @classmethod
    def clear_all(cls):
        cls._instances.clear()

def get_settings(name = None):
    if name is None:
        name = 'default'
    return SettingsSingletons.get_instance(name)

class OrderedActions(argparse.Action):
    """ Use argparse to collect ordered operations that can occur multiple times (like say, ffmpeg does) """
    def __call__(self, parser, namespace, values, option_string=None):
        if not hasattr(namespace, 'ordered_operations'):
            setattr(namespace, 'ordered_operations', [])
        operations = getattr(namespace, 'ordered_operations')
        operations.append((self.dest, values))

def get_main_args():
    parser = argparse.ArgumentParser(description='CLI Settings Interface for Trol')
    parser.add_argument('--mqtt-config', '-C', type=str, help="Config file to use for MQTT connection etc")
    parser.add_argument('--load-from-yaml-file', type=str, action=OrderedActions, help="Filename of settings file to manipulate")
    parser.add_argument('--load-from-json-file', type=str, action=OrderedActions, help="Filename of settings file to manipulate")
    parser.add_argument('--load-from-mqtt-topic', type=str, action=OrderedActions, help="MQTT Topic, if provided manipulated config will be taken from the retained message.")
    parser.add_argument('--merge-yaml-file', type=str, action=OrderedActions, help="File to merge with manipulated config, options in this file override ones in manipulated.")
    parser.add_argument('--merge-json-file', type=str, action=OrderedActions, help="File to merge with manipulated config, options in this file override ones in manipulated.")
    parser.add_argument('--merge-mqtt-topic', type=str, action=OrderedActions, help="MQTT Topic, if provided manipulated config will be merged with the retained message.")
    parser.add_argument('--use-slice', type=str, action=OrderedActions, help="String in the format 'foo.bar.baz', take only this key and toss out the rest.")
    parser.add_argument('--write-to-mqtt-topic', type=str, action=OrderedActions, help="MQTT Topic, if provided config-file will be placed in a retained message.")
    parser.add_argument('--print-as', type=str, action=OrderedActions, help="Print the manipulated config, options are 'yaml' or 'json'")

    argcomplete.autocomplete(parser)

    args = parser.parse_args()

    needs_mqtt_config = any(
        operation in ['load_from_mqtt_topic', 'merge_mqtt_topic', 'write_to_mqtt_topic']
        for operation, _ in getattr(args, 'ordered_operations', [])
    )

    if needs_mqtt_config and not args.mqtt_config:
        parser.error(f"--mqtt-config required to use mqtt functions")

    return args

def slice_dict(data, path):
    keys = path.split('.')
    value = data
    for key in keys:
        if isinstance(value, ConfigNode):
            value = value.get(key)
        else:
            raise ValueError(f"Path '{path}' does not exist in the data structure.")
    return value

def main():
    args = get_main_args()

    mqtt = None

    if args.mqtt_config:
        settings = get_settings()
        settings.load_from_yaml_file(args.mqtt_config)

        if settings.isempty():
            print(f"ERROR: No configuration in {args.mqtt_config}")
            return

        mqtt = MQTTConnectionManager(**settings.mqtt.to_dict())

    manipulated_config = get_settings('manipulated')

    # Process operations in the order they were specified
    for operation, value in args.ordered_operations:
        # NOTE: sync_via_mqtt currently works like a merge, if that changes this will break/need changing.
        if operation in ['load_from_mqtt_topic', 'merge_mqtt_topic']:
            manipulated_config.sync_via_mqtt(mqtt, value)
            mqtt.process_initialization_callbacks()

        elif operation == 'load_from_yaml_file':
            manipulated_config.load_from_yaml_file(value)

        elif operation == 'load_from_json_file':
            manipulated_config.load_from_json_file(value)

        elif operation == 'merge_yaml_file':
            merge_config = get_settings(value)
            merge_config.load_from_yaml_file(value)
            manipulated_config.merge(merge_config)

        elif operation == 'merge_json_file':
            merge_config = get_settings(value)
            merge_config.load_from_json_file(value)
            manipulated_config.merge(merge_config)

        elif operation == 'use_slice':
            manipulated_config = slice_dict(manipulated_config, value)

        elif operation == 'write_to_mqtt_topic':
            mqtt.publish(value, manipulated_config.to_json())

        elif operation == 'print_as':
            if value == 'yaml':
                print(manipulated_config.to_yaml())
            elif value == 'json':
                print(manipulated_config.to_json(pretty=True))

if __name__ == "__main__":
    main()

