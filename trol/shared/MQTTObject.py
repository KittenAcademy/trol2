import argparse
from typing import Tuple, Type, Any, Callable
from trol.shared.MQTT import MQTTConnectionManager
from trol.shared.MQTTVariable import MQTTVariable
from trol.shared.logger import setup_logger
log = setup_logger(__name__)


class MQTTObject:
    def __init__(self, mqtt_manager: MQTTConnectionManager, topic: str, name: str, mqtt_attribute_definitions: Tuple[Tuple[str, Type]]):
        """ Holds a collection of MQTTVariables and treats them like attributes of an object. """
        self._mqtt = mqtt_manager
        self._topic = topic
        self._name = name
        self._mqtt_attribute_definitions = mqtt_attribute_definitions
        self._mqtt_attributes = {}
        for attr_def in self._mqtt_attribute_definitions:
            self._mqtt_attributes[attr_def[0]] = MQTTVariable(self._mqtt, f"{self._topic}/{attr_def[0]}", value_type = attr_def[1])

    def add_callback(self, attribute_name: str, callback: Callable[[None],None]):
        self._mqtt_attributes[attribute_name].add_callback(callback)

    def get_underlying_MQTTVariable(self, attribute_name):
        if attribute_name in self._mqtt_attributes:
            return self._mqtt_attributes[attribute_name]
        else:
            raise AttributeError(f"{self.__class__.__name__} object has no attribute '{attribute_name}'")
    def get_topic(self):
        return self._topic

    def __getattr__(self, name):
        if name.startswith('_'):
            super().__getattr__(name)
        elif name in self._mqtt_attributes:
            return self._mqtt_attributes[name].value
        else:
            raise AttributeError(f"{self.__class__.__name__} object has no attribute '{name}'")

    def __setattr__(self, name, value):
        if name.startswith('_'):
            super().__setattr__(name, value)
        elif name in self._mqtt_attributes:
            self._mqtt_attributes[name].value = value
        else:
            raise AttributeError(f"{self.__class__.__name__} object has no attribute '{name}'")

    def __delattr__(self, name):
        log.debug(f"Deleting {name}")
        if name.startswith('_'):
            super().__delattr__(name)
        elif name in self._mqtt_attributes:
            del self._mqtt_attributes[name]  # This is probably a bad idea.
        else:
            raise AttributeError(f"{self.__class__.__name__} object has no attribute '{name}'")

    def items(self):
        return self.mqtt_attributes.items()
    def keys(self):
        return self._mqtt_attributes.keys()
    def __getitem__(self, key):
        return self._mqtt_attributes[key].value
    def __setitem__(self, key, value):
        self._mqtt_attributes[key].value = value
    def __delitem__(self, key):
        del self._mqtt_attributes[key] # this is probably a bad idea
    def __contains__(self, key):
        return key in self._mqtt_attributes.keys()
    def get(self, key, default=None):
        if(key in self._mqtt_attributes.keys()):
            return self._mqtt_attributes[key].value
        return default

    def __repr__(self):
        items = (f"{key}={value.value!r}" for key, value in self._mqtt_attributes.items())
        return f"{self.__class__.__name__}=(_name={self._name}, _topic={self._topic}, {', '.join(items)})"

class MQTTObjectList:
    def __init__(self, mqtt_manager: MQTTConnectionManager, mqtt_topic: str, name: str, object_class: Type[MQTTObject] = MQTTObject):
        self.mqtt = mqtt_manager
        self.mqtt_topic = mqtt_topic
        self.name = name
        self.object_class = object_class
        self.objects = {}
        self.callback = None

        self.mqtt_name_list = MQTTVariable(self.mqtt, self.mqtt_topic, value_type=list, callback=lambda:self.update(), initial_value=[])

    def add_callback(self, callback: Callable[[None],None]):
        self.callback = callback

    def get_topic(self):
        return self.mqtt_topic

    def update(self):
        log.debug(f"{self.name} updated list: {self.mqtt_name_list.value}")
        for object_name in self.mqtt_name_list.value:
            if self.getByName(object_name) is None:
                self.objects[object_name] = self.object_class(self.mqtt, f"{self.mqtt_topic}/{object_name}", object_name)
        if self.callback is not None:
            self.callback()

    def getByName(self, object_name: str):
        if object_name in self.objects:
            return self.objects[object_name]
        return None

    def addOrGetByName(self, object_name: str):
        if object_name in self.objects:
            return self.objects[object_name]
        self.objects[object_name] = self.object_class(self.mqtt, f"{self.mqtt_topic}/{object_name}", object_name)
        self.mqtt_name_list.value.append(object_name)
        return self.objects[object_name]

    def delByName(self, object_name: str):
        log.debug(f"Deleting {object_name}")
        if object_name in self.objects:
            del self.objects[object_name]
        if object_name in self.mqtt_name_list.value:
            self.mqtt_name_list.value.remove(object_name)

    def getNameByAttr(self, attr: str, attrval: Any):
        for name, object_name in self.objects.items():
            if attr in object_name._data and attrval == obj._data[attr].value:
                return name
        return None

    def getNamesByAttr(self, attr: str, attrval: Any):
        names = []
        for name, obj in self.objects.items():
            if attr in obj._data and attrval == obj._data[attr].value:
                names.append(name)
        return names

    def __iter__(self):
        return iter(self.objects)
    def items(self):
        return self.objects.items()
    def keys(self):
        return self.objects.keys()
    def values(self):
        return self.objects.values()
    def __getitem__(self, key):
        return self.objects[key]
    def __setitem__(self, key, value):
        #self.objects[key] = value  # this is probably a bad idea
        raise Exception(f"Can't change the value of a {self.__class__.__name__} directly.")
    def __len__(self):
        return len(self.objects)
    def __delitem__(self, key):
        del self.objects[key] # this is probably a bad idea
    def get(self, key, default=None):
        return self.objects.get(key, default)
    def __contains__(self, key):
        return key in self.objects
    def __repr__(self):
        return f"{self.__class__.__name__}=(_name={self.name}, mqtt_topic={self.mqtt_topic}, {', '.join(self.mqtt_name_list.value)})"

