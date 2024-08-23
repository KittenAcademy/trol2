import threading
import queue
from typing import Callable, Dict, List
import argparse
import paho.mqtt.client as mqtt
import time
import random
import json
from inspect import signature

from trol.shared.logger import setup_logger
log = setup_logger(__name__)

class MQTTConnectionManager:

    def __init__(self,
                 host: str = 'localhost',
                 port: int = 1883,
                 username: str = None,
                 password: str = None,
                 client_id: str = None):

        if client_id is None:
            # Generate a unique client_id
            client_id = f"{username}_{int(time.time())}_{random.randint(1000, 9999)}"

        self.client = mqtt.Client(client_id)
        self.subscriptions = {}  # type: Dict[str, Callable[..., None]] can accept 1 or 2 str params (message, topic)
        self.lock = threading.Lock()
        self.main_thread_dispatch_queue = queue.Queue()
        self.publish_event = threading.Event()
        self.publish_count = 0
        self.publish_ack_count = 0

        def on_connect(_client, _userdata, _flags, rc):
            log.debug(f"Connected with client ID {client_id}, result code {rc}")
            # We need to (re)subscribe to known subscriptions on connect.  This will cause our clients to get
            # retained messages again, which hopefully is something they're OK with, as tracking that is not something
            # I care to do.
            for topic in self.subscriptions.keys():
                self.client.subscribe(topic)

            self.main_thread_dispatch_queue.put({'type': 'connect', 'callback': lambda: self._handle_connect(rc)})

        def on_disconnect(_client, _userdata, rc):
            log.debug(f"Disconnected {client_id}, result code {rc}")
            self.main_thread_dispatch_queue.put({'type': 'disconnect', 'callback': lambda: self._handle_disconnect(rc)})

        def on_message(_client, _userdata, msg):
            #log.debug(f"Received message '{str(msg.payload)[:100]}' on topic '{msg.topic}'")
            payload = msg.payload.decode('utf-8') if isinstance(msg.payload, bytes) else msg.payload
            self.main_thread_dispatch_queue.put({'type': 'message', 'topic': msg.topic, 'callback': lambda: self._handle_message(msg, payload)})

        def on_subscribe(_client, _userdata, mid, granted_qos):
            log.debug(f"Subscription acknowledged, mid: {mid}, granted QoS: {granted_qos}")
            self.main_thread_dispatch_queue.put({'type': 'subscribe', 'callback': lambda: self._handle_subscribe(mid, granted_qos)})

        def on_publish(_client, _userdata, mid):
            log.debug(f"Message published, mid: {mid}")
            with self.lock:
                self.publish_ack_count += 1
                if self.publish_ack_count == self.publish_count:
                    self.publish_event.set()
            self.main_thread_dispatch_queue.put({'type': 'publish', 'callback': lambda: self._handle_publish(mid)})

        self.client.on_connect = on_connect
        self.client.on_disconnect = on_disconnect
        self.client.on_message = on_message
        self.client.on_subscribe = on_subscribe
        self.client.on_publish = on_publish

        # Connect to MQTT server
        if username and password:
            self.client.username_pw_set(username, password)
        self.client.connect(host, port, 60)

        # Run MQTT client in a separate thread
        self.mqtt_thread = threading.Thread(target=self.client.loop_forever, daemon=True)
        self.mqtt_thread.start()

    def _handle_connect(self, rc):
        # Handle the connect event in the main thread
        pass

    def _handle_disconnect(self, rc):
        # Handle the disconnect event in the main thread
        pass

    def _handle_message(self, msg, payload):
        # Handle the message event in the main thread
        # Because sometimes a callback will initiate new subscriptions or unsubscribe,
        # changing the number of items in the subscriptions dict during our loop, 
        # we need to do this in two steps for safety.
        callbacks = []
        for topic in self.subscriptions:
            if mqtt.topic_matches_sub(topic, msg.topic):
                callbacks.extend(self.subscriptions[topic])
        for cb in callbacks:
            # TODO: hacky
            # Allow for callbacks that want message only and ones that get message, topic:
            if len(signature(cb).parameters) >= 2:
                cb(payload, msg.topic)
            else:
                cb(payload)

    def _handle_subscribe(self, mid, granted_qos):
        # Handle the subscribe event in the main thread
        pass

    def _handle_publish(self, mid):
        # Handle the publish event in the main thread
        pass

    def subscribe(self, topic: str, callback: Callable[[str], None]):
        with self.lock:
            if topic not in self.subscriptions:
                self.subscriptions[topic] = []
                # TODO: Check how paho mqtt handles duplicate subscriptions.
                if self.client.is_connected():
                    self.client.subscribe(topic)

            if callback not in self.subscriptions[topic]:
                self.subscriptions[topic].append(callback)
            else:
                log.warning(f"Duplicate {topic} callback subscription?? This will really mess up a client at unsubscribe()")

    def unsubscribe(self, topic: str, callback: Callable[[str], None]):
        with self.lock:
            if topic in self.subscriptions:
                self.subscriptions[topic] = [cb for cb in self.subscriptions[topic] if cb != callback]
                if not self.subscriptions[topic]:
                    # last sub for this topic has been unsubbed.
                    del self.subscriptions[topic]
                    self.client.unsubscribe(topic)
            else:
                log.warning(f"Duplicate {topic} unsubscribe?? This is messed up.")

    def publish(self, topic: str, payload: str, qos: int = 1, retain: bool = True):
        log.debug(f"Attempt publish: '{payload}' on '{topic}'")
        with self.lock:
            self.publish_count += 1
            self.publish_event.clear()
        self.client.publish(topic, payload, qos, retain)

    def disconnect(self):
        self.client.disconnect()
        self.mqtt_thread.join()

    def process_callbacks(self, timeout=1):
        """ Process callbacks, only timing out if we receive no messages within timeout.  """
        # This is the "traditional" timeout style.  May never return if you recv messages
        # faster than 1/timeout.  Passing timeout=0 quits as soon as the queue is empty.
        while True:
            try:
                item = self.main_thread_dispatch_queue.get(timeout=timeout)
                # We got one, so reset the timeout
                timeout_begin = time.time()
                item['callback']()
                self.main_thread_dispatch_queue.task_done()
            except queue.Empty:
                break

    def process_callbacks_for_time(self, max_time, quit_early=False):
        """ Process callbacks.  Processes for max_time, returning even if the queue is not empty. """
        # If you pass quit_early then it will quit as soon as the queue is empty or at max_time, 
        # whichever comes first.
        start_time = time.time()
        while time.time() - start_time < max_time:
            try:
                item = self.main_thread_dispatch_queue.get(timeout=0.1)
                item['callback']()
                self.main_thread_dispatch_queue.task_done()
            except queue.Empty:
                if quit_early:
                    break # Quit as soon as there's no pending messages.
                pass # Continue processing until max_time is reached.

    def process_initialization_callbacks(self, timeout = 0.5):
        """ used mainly by MQTTVariable and derivatives for ensuring initialization from retained messages """
        # I *think* (but have not tested thoroughly) that the timeout of 0.1 we pass below will guarantee
        # that we get all the retained messages IF AND ONLY IF we do not have a lag of > 100ms to the 
        # mqtt server.

        # I also think we could quit the minute we get a message for a topic we've seen before, instead of 
        # using the timeout.  Reason being, it seems like MQTT always delivers all the retained messages first.
        # (I also have not verified this.)

        # I *think* it makes sense to count multiple calls to this function as distinct as far as counting new
        # topics, therefore:
        self.received_topics = set()

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                item = self.main_thread_dispatch_queue.get(timeout=0.1)
                item['callback']()
                if not self._is_seen_topic(item):
                    start_time = time.time()  # Reset timeout only for the first message on a new topic
                self.main_thread_dispatch_queue.task_done()
            except queue.Empty:
                pass # Continue processing until timeout is reached

    def _is_seen_topic(self, item):
        if 'topic' not in item.keys():
            return False
        if item['topic'] in self.received_topics:
            return True
        self.received_topics.add(item['topic'])
        return False


def get_main_args():
    from trol.shared.settings import get_settings

    parser = argparse.ArgumentParser(description='MQTT CLI interface')
    parser.add_argument('--host', help='MQTT broker host')
    parser.add_argument('--port', type=int, default=1883, help='MQTT broker port')
    parser.add_argument('--username', help='MQTT username')
    parser.add_argument('--password', help='MQTT password')
    parser.add_argument('--client_id', help='MQTT client ID')
    parser.add_argument('--config', help='Load all the above from a trol2 config file.')
    parser.add_argument('--action', required=True, choices=['subscribe', 'publish', 'clear', 'dump'], help='Action to perform')
    parser.add_argument('--topic', required=True, help='MQTT topic')
    parser.add_argument('--message', help='Message to publish')
    parser.add_argument('--notrunc', action='store_true', default=False, help='Do not truncate subscribed messages')
    parser.add_argument('--noretain', action='store_true', default=False, help='Do not retain published messages')

    args = parser.parse_args()

    if args.config:
        settings = get_settings()
        settings.load_from_yaml_file(args.config)
        args.host = settings.mqtt.host
        args.port = settings.mqtt.port
        args.username = settings.mqtt.username
        args.password = settings.mqtt.password

    return args

def dump_hierarchy(topic_value_pairs):
    # Sort by descending length of the topic string
    topic_value_pairs.sort(key=lambda x: len(x[0]), reverse=True)
    root = {}

    for topic, value in topic_value_pairs:
        parts = topic.split('/')
        current_level = root

        # Traverse or create nested dictionaries
        for part in parts[:-1]:
            if part not in current_level:
                current_level[part] = {}
            current_level = current_level[part]

        # Convert and assign the final value
        final_value = convert_mqttvar(value)

        # if the final part/key already exists it's because we have one of our funky lists of subkeys 
        # e.g. cameras or positions.  Let's treat it the way we oughta.
        if parts[-1] in current_level:
            # print(f"encountered existing key: {parts[-1]}")
            if isinstance(final_value, list):
                # I believe the correct action is to prune any branches from here that aren't listed; they would be 
                # old data that isn't accessable to trol.
                current_level[parts[-1]] = {key: value for key, value in current_level[parts[-1]].items() if key in final_value}
            else:
                #print(f"Unexpected!  Existing key is NOT a list? {final_value}")
                pass
        else:
            current_level[parts[-1]] = final_value
    return root

def convert_mqttvar(value):
    """Convert a string to its appropriate type: bool, int, float, list, dict, or str."""
    # Handle booleans
    if value == 'True':
        return True
    elif value == 'False':
        return False
    # Handle integers
    try:
        return int(value)
    except ValueError:
        pass
    # Handle floats
    try:
        return float(value)
    except ValueError:
        pass
    # Handle JSON (dict or list)
    try:
        return json.loads(value)
    except (ValueError, json.JSONDecodeError):
        pass
    # Default to string
    return value


def main():
    args = get_main_args()
    mqtt_manager = MQTTConnectionManager(args.host, args.port, args.username, args.password, args.client_id)

    if args.action == 'publish':
        if args.message is None:
            print(f"Missing --message")
            return
        mqtt_manager.publish(args.topic, args.message, retain=not args.noretain)
        mqtt_manager.process_callbacks(timeout=1)
        mqtt_manager.disconnect()
        return

    if args.action in ['subscribe','clear','dump'] and args.topic:
        seen_topics = []
        def print_message(msg, topic):
            seen_topics.append((topic, msg))
            if args.action != 'dump':
                if not args.notrunc:
                    msg = msg[:100]
                print(f"Received message ({topic}): '{msg}'")

        mqtt_manager.subscribe(args.topic, print_message)

        # Get (at least) all retained messages
        mqtt_manager.process_initialization_callbacks()

        if args.action == 'dump':
            mqtt_manager.unsubscribe(args.topic, print_message)
            mqtt_manager.disconnect()
            data = dump_hierarchy(seen_topics)
            print(json.dumps(data, indent=2))
            return

        # NOTE: This may catch some topics that do not have retained messages and sending '' may not be 
        # good for whoever is listening -- but I can't be bothered.
        if args.action == 'clear':
            mqtt_manager.unsubscribe(args.topic, print_message)
            for (topic, _payload) in seen_topics:
                mqtt_manager.publish(topic, None)
                print(f"Cleared {topic}")
            mqtt_manager.process_initialization_callbacks()
            mqtt_manager.disconnect()
            return

        print("Entering loop. (CTRL-C to exit)")
        # Main loop to process callbacks
        try:
            while True:
                # timeout = 0 to not block at all
                mqtt_manager.process_callbacks(timeout=1)
                # Do stuff here
        except KeyboardInterrupt:
            mqtt_manager.disconnect()
            # newline to not print on same line as ^C in console
            print("\nDisconnected from MQTT broker")
        return
    print(f"Invalid --action: {args.action}")

if __name__ == '__main__':
    main()

