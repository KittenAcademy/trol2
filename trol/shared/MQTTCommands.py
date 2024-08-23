from typing import Dict, Callable, Type
from trol.shared.MQTT import MQTTConnectionManager
import json
from time import time
from trol.shared.logger import setup_logger
from traceback import format_exc
log = setup_logger(__name__)

class MQTTCommands:
    def __init__(self, mqtt: MQTTConnectionManager, topic: str, command_definitions: Dict[str, Dict[str, Type]], command_handlers: Dict[str, Callable] = None):
        """ 
        Base class for command dispatch via MQTT.  

        Clients can call .command(paramname = param, paramname = param) and it will be dispatched via MQTT to a command handler.
        Servers/command handlers can use the same class, just provide handlers.

        Parameters:
        mqtt (MQTTConnectionManager):  An existing connection to the MQTT server
        topic (str): The MQTT topic we send/recv commands on
        command_definitions (dictionary of {commandname: {param1: type, param2: type}...}): Defining the known commands, typically coded in subclass.
          example: { "commandone": {"foo": str, "bar": list}, "commandtwo": {"baz": dict}, "commandthree": {}...}
        command_handlers (dict of {commandname: callback, ...}): OPTIONAL list of callbacks; can also be set directly as MQTTCommand.callbackname=callback
        """
        self.mqtt  = mqtt
        self.topic = topic
        self.handlers = command_handlers or {}
        self.definitions = command_definitions
        self.is_subscribed = False

        # Only subscribe if we have handlers, otherwise we can only send commands as a client.
        if self.handlers:
            self.subscribe()

    def subscribe(self):
        if self.is_subscribed:
            log.debug("{self.__class__.__name__} attempting to subscribe twice?")
            return
        log.debug(f"{self.__class__.__name__} subscribing to command channel: {self.topic}")
        self.mqtt.subscribe(self.topic, self.receive_command)
        self.is_subscribed = True


    def receive_command(self, message: str):
        """ MQTT callback to receive and dispatch a command from MQTT """
        
        log.debug(f"Got command from MQTT: {message}")

        payload = json.loads(message)
        command = payload.get("command")
        params = payload.get("params")

        handler = self.handlers.get(command)
        if handler:
            try:
                handler(**params)
            except TypeError as e:
                log.error(f"Error in handler signature? {command}:{e}\n{format_exc()}")
            except Exception as e:
                log.error(f"Error in command handler?  {command}:{e}\n{format_exc()}")
        else:
            log.error(f"Unknown command from mqtt: {command}")

    def send_command(self, command: str, params: dict):
        """ Send a command to MQTT for dispatch """

        if command not in self.definitions: 
            raise ValueError(f"Unknown command: {command}")

        message = {
                "command": command,
                "params": params,
                "metadata": {
                    "timestamp": time()
                }
        }
        self.mqtt.publish(self.topic, json.dumps(message), retain = False)

    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        elif name in self.definitions:
            return lambda **params: self.send_command(name, params)
        raise AttributeError(f"Attribute/Command not found: {name}")

    def __setattr__(self, name, value):
        """ Can set command callbacks """
        if 'definitions' in self.__dict__ and name in self.definitions:
            if callable(value):
                if not self.handlers:  # Subscribe to topic when we get the first handler.
                    self.subscribe()
                self.handlers[name] = value
            else:
                raise ValueError(f"Handler for {name} is not callable.")
        else:
            self.__dict__[name] = value

class OBSCommands(MQTTCommands):
    def __init__(self, mqtt: MQTTConnectionManager, topic_root: str, command_handlers: Dict[str, Callable] = None):
        """
        Commands handled by OBS interface (OBS/interface.py)

        Parameters:
        mqtt: An existing connection to the MQTT server
        topic_root: The root topic for TROL
        """

        command_definitions = {
            "start_recording": {},
            "stop_recording": {},
            "stop_streaming": {},
            "start_streaming": {},
            "make_fullscreen": { 'position_name': str },
            "restore_scene_defaults": {}
            }
        super().__init__(mqtt, f"{topic_root}/obs/command", command_definitions, command_handlers)

class CameraCommands(MQTTCommands):
    def __init__(self, mqtt: MQTTConnectionManager, topic_root: str, command_handlers: Dict[str, Callable] = None):
        command_definitions = {
                "goto_ptz_position":    { 'camera_name': str, 'position_number': int },
                "goto_absolute_coords": { 'camera_name': str, 'coords': tuple },
                "goto_relative_vector": { 'camera_name': str, 'vector': tuple }
            }
        super().__init__(mqtt, f"{topic_root}/commands/camera", command_definitions, command_handlers)

