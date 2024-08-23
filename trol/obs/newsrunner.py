import obswebsocket
from obswebsocket import obsws, requests, events
import json
from time import sleep
from urllib.parse import urlparse, urlunparse
from typing import Callable, Any


from trol.shared.settings import get_settings
import argparse

from trol.shared.logger import setup_logger, is_debug
log = setup_logger(__name__)

from trol.shared.MQTT import MQTTConnectionManager
from trol.shared.MQTTCameras import MQTTCameras
from trol.shared.MQTTPositions import MQTTPositions
from trol.shared.MQTTVariable import MQTTVariable

from datetime import datetime
from time import time


ap = argparse.ArgumentParser()
ap.add_argument('--config', type=str, default='./config.yaml', help='Config filename (default: ./config.yaml)')
ap.add_argument('--interval', type=int, default='900', help='Number of seconds in-between news runs.')
ap.add_argument('--displaytime', type=int, default='120', help='Number of seconds to show the news.')
args = ap.parse_args()

# Literally everything in this script needs this stuff so it's a lot less passing things around to just make it global.
settings = get_settings()
settings.load_from_yaml_file(args.config)

obs = obsws(settings.obs.host, settings.obs.port, settings.obs.password)
if(is_debug(log)):
    obs.register(lambda x: log.debug(f"OBS Event Received: {x}"))
obs.connect()

mqtt = MQTTConnectionManager(settings.mqtt.host, settings.mqtt.port, settings.mqtt.username, settings.mqtt.password)


def for_all_items_named(name: str, callback: Callable[[Any, Any],None]): # Honestly, I have no idea what type 'item' is, is it just a dict?
    """ 
    Execute code for each source of a given name, in all scenes.
    """
    scenes_response = obs.call(requests.GetSceneList())
    scenes = scenes_response.getScenes()
    for scene in scenes:
        scene_item_list = obs.call(requests.GetSceneItemList(sceneName=scene['sceneName']))
        items = scene_item_list.getSceneItems()
        for item in items:
            if item['sourceName'] == name:
                callback(scene, item)

def set_item_enabled(scenename: str, sceneuuid: str, itemid: int, enabled: bool = True):
    log.debug(f"Setting enabled: {scenename}, {sceneuuid}, {itemid}, {enabled}")
    obs.call(requests.SetSceneItemEnabled(sceneName = scenename, sceneUuid = sceneuuid, sceneItemId = itemid, sceneItemEnabled=enabled))

def set_named_items_enabled(name: str, enabled=True):
    #     log.info(f"In scene: {scene['sceneName']} ({scene['sceneUuid']}):  {item['sourceName']}")
    for_all_items_named(name, lambda s,i: set_item_enabled(s['sceneName'], s['sceneUuid'], i['sceneItemId'], enabled))

def get_next_quarter_hour():
    nt = datetime.now().replace(minute=0,second=0).timestamp()
    while(nt <= time()):
       nt += args.interval
    return nt;

# Because the parameter to process_callbacks is a timeout that resets anytime we get a message
def wait_until(timestamp):
    while time() < timestamp:
        mqtt.process_callbacks_for_time(1)
        

def main():
    scroll_active = MQTTVariable(mqtt, f"{settings.mqtt_root}/scroll/isactive", bool)
    # process messages so we can throw away any existing value of scroll/isactive and force it off.
    mqtt.process_initialization_callbacks()
    # Callback means that whatever the value of scroll/isactive is set to is what we'll do
    # so, unlike the cameras, it's currently assumed that the request (i.e. setting scroll/isactive)
    # always accomplished the action (i.e. making the scroll visible or not)
    scroll_active.add_callback(lambda: set_named_items_enabled('Scroll', scroll_active.value))
    scroll_active.value = False

    scroll_text = MQTTVariable(mqtt, f"{settings.mqtt_root}/scroll/newsticker", str, initial_value="")
    mqtt.process_initialization_callbacks()
    scroll_text.add_callback(lambda: log.info(f"News scroll changed to '{scroll_active.value}"))

    next_run = get_next_quarter_hour()

    log.info(f"Startup completed.  Current news is '{scroll_text.value}'.")
    try:
        while True:
            # Let the mqtt loop run until we are ready
            next_run_in = next_run - time()
            log.info(f"Waiting {next_run_in} seconds until {datetime.fromtimestamp(next_run).isoformat()}")
            wait_until(next_run)
            # TODO: change this to check for whitespace only
            if scroll_text.value is not None and len(scroll_text.value) > 1:
                log.info(f"Displaying news scroll: {scroll_text.value}")
                scroll_active.value = True
                wait_until(time() + args.displaytime)
                scroll_active.value = False
            else:
                log.info("No news to display.")
            next_run = get_next_quarter_hour()
    except KeyboardInterrupt:
        log.info("Shutting down by user request.")

    obs.disconnect()
    mqtt.disconnect()

    log.info("Program exiting.")

if __name__ == "__main__":
    main()


