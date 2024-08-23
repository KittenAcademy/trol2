import obswebsocket
from obswebsocket import obsws, requests, events
import json
from time import sleep
import datetime
from urllib.parse import urlparse, urlunparse
from typing import Callable, Any

from trol.obs.functions import ObsFunctions
from trol.shared.logger import setup_logger, is_debug, DEBUG
log = setup_logger(__name__)

import sys
import argparse
ap = argparse.ArgumentParser()
ap.add_argument('--stats-log', type=str, help='Optional stats log filename')
ap.add_argument('--config', type=str, default='./config.yaml', help='Config filename (default: ./config.yaml)')
ap.add_argument('--auto-start', action='store_true', help='Auto start streaming (default: False)')
ap.add_argument('--debug', action='store_true', help='Provide debugging output (warning: extremely verbose!)')
ap.add_argument('--skip_init', action='store_true', default=False)
args = ap.parse_args()

from trol.shared.settings import get_settings
settings = get_settings()
settings.load_from_yaml_file(args.config)

from trol.shared.MQTT import MQTTConnectionManager
from trol.shared.MQTTCameras import MQTTCameras
from trol.shared.MQTTPositions import MQTTPositions
from trol.shared.MQTTVariable import MQTTVariable
from trol.shared.MQTTCommands import OBSCommands

obs = obsws(settings.obs.host, settings.obs.port, settings.obs.password)

if(args.debug):
    log.setLevel(DEBUG)
    obs.register(lambda x: log.debug(f"OBS Event Received: {x}"))

obs.connect()

mqtt = MQTTConnectionManager(settings.mqtt.host, settings.mqtt.port, settings.mqtt.username, settings.mqtt.password)
cameras = MQTTCameras(mqtt, f"{settings.mqtt_root}/cameras")
positions = MQTTPositions(mqtt, f"{settings.mqtt_root}/positions")

RTMP_SETTINGS = {'close_when_inactive': True, 
                 'ffmpeg_options': 'rtsp_transport=tcp rtsp_flags=prefer_tcp', 
                 'hw_decode': False, 
                 'input': '', 
                 'is_local_file': False, 
                 'reconnect_delay_sec': 1, 
                 'restart_on_activate': True}

AUDIO_SETTINGS = {'buffering_mb': 1, 
                  'close_when_inactive': True, 
                  'ffmpeg_options': 'rtps_transport=tcp rtsp_flags=prefer_tcp', 
                  'hw_decode': True, 
                  'input': '', 
                  'is_local_file': False}

def checked_call(request):
    foo = obs.call(request)
    if not foo.status:
        request_type = request.name
        error_code = foo.datain.get('code')
        if error_code is none:
            raise Exception(f"{request_type} failed. To debug, try using obs-websocket-py from https://github.com/KittenAcademy/obs-websocket-py")
        error_message = foo.datain.get('comment', 'Unknown reason.')
        raise Exception(f"{request_type} failed {error_code}:{error_message}")
    return foo.datain

def call_until_success(request, max_attempts = 20):
    while True:
        try:
            foo = checked_call(request)
        except Exception as e:
            log.info(f"Exception: {e}")
            max_attempts -= 1
            if max_attempts <= 0:
                raise Exception(f"Call failed after multiple attempts: {e}")
            sleep(0.01)
            continue
        return foo

def for_all_items_named(name: str, callback: Callable[[Any, Any],None]): # Honestly, I have no idea what type 'item' is, is it just a dict?
    """ 
    Execute code for each source of a given name, in all scenes.
    """
    scenes_response = checked_call(requests.GetSceneList())
    scenes = scenes_response['scenes']
    for scene in scenes:
        scene_item_list = checked_call(requests.GetSceneItemList(sceneName=scene['sceneName']))
        items = scene_item_list['sceneItems']
        for item in items:
            if item['sourceName'] == name:
                callback(scene, item)




def set_item_enabled(scenename: str, sceneuuid: str, itemid: int, enabled: bool = True):
    log.debug(f"Setting enabled: {scenename}, {sceneuuid}, {itemid}, {enabled}")
    checked_call(requests.SetSceneItemEnabled(sceneName = scenename, sceneUuid = sceneuuid, sceneItemId = itemid, sceneItemEnabled=enabled))

def set_named_items_enabled(name: str, enabled=True):
    for_all_items_named(name, lambda s,i: set_item_enabled(s['sceneName'], s['sceneUuid'], i['sceneItemId'], enabled))

def log_media_state():
    inputs = checked_call(requests.GetInputList())['inputs']
    for input in inputs:
        inputname = input['inputName']
        if inputname.startswith('TROL '):
            res = checked_call(requests.GetMediaInputStatus(inputUuid = input['inputUuid']))
            if res['mediaState'] != 'OBS_MEDIA_STATE_PLAYING':
                log.debug(f"MEDIA STATE FOR {input['inputName']} : {res}")

def verify_active():
    # To be called on startup to verify that the cameras we think are active actually are and 
    # also to process any pending cam change requests.
    inputs = checked_call(requests.GetInputList())['inputs']

    positionlist = []
    for input in inputs:
        log.debug(f"Verifying: {input}")
        inputname = input['inputName']
        input_settings = checked_call(requests.GetInputSettings(inputName=inputname))['inputSettings']
        #log.debug(f"Input: {input}\n  Settings: {input_settings}\n")
        # TODO: Only verify positions known to MQTTPositions, don't look for 'TROL '
        if inputname.startswith('TROL '):
            position = positions.getByName(inputname)
            if position is None:
                raise Exception(f"Unknown position {inputname}")
            url = input_settings.get('input', 'Missing URL')
            camera_name = cameras.getNameByUrl(url)
            if camera_name is None:
                log.info(f"Can't find camera in position {inputname} using url {url}.")
                camera_name = 'unknown'
            if camera_name == position.active and camera_name == position.requested:
                log.info(f"Position {inputname} checks out OK.")
                continue
            
            # active does not equal requested or what's actually active so let's fix that.
            url = get_camera_url_for_position(inputname, position.requested)
            log.info(f"{inputname} has actual {camera_name}, active {position.active}, requested {position.requested}.  Setting to {position.requested} ({url}).")
            set_input_url(inputname, url)
            position.active = position.requested


def reset_position(position_name, input_url = None):
    obsfun = ObsFunctions(obs)
    obsfun.delete_item_by_name(position_name)
    item = positions.getByName(position_name).obs_item_default.copy()
    if input_url is not None:
        item['inputSettings']['input'] = input_url
    obsfun.create_item(item)


def set_input_url(input_name, new_url):
    reset_position(input_name, new_url)
    #input_settings = checked_call(requests.GetInputSettings(inputName=input_name))['inputSettings']
    #input_settings['input'] = new_url
    #checked_call(requests.SetInputSettings(inputName=input_name, inputSettings=input_settings, overlay=True))
    log.info(f"Set new URL for source '{input_name}' to '{new_url}'")
    

def get_camera_url_for_position(posname, camname):
    try:
        if positions[posname].isaudio:
            if cameras[camname].noaudio:
                log.error(f"Request for {camname} in {posname} denied because {camname} is no audio.")
                return None
            return cameras[camname].audiourl
        else:
            return cameras[camname].rtspurl
    except Exception as e:
        log.error(f"Cannot get url for {posname}, {camname} because {e}")
    return None

def is_recording():
    status = checked_call(requests.GetRecordStatus())
    return status.getOutputActive()

def start_recording():
    checked_call(requests.StartRecord())

def stop_recording():
    filename = checked_call(requests.StopRecord())['outputPath']
    return filename

def is_streaming():
    status = checked_call(requests.GetStreamStatus())
    return status['outputActive']

def start_streaming():
    checked_call(requests.StartStream())

def stop_streaming():
    checked_call(requests.StopStream())

def make_fullscreen(position_name):
    obscene = ObsFunctions(obs)
    border_item = obscene.get_item_by_name('Border')
    transform = settings.obs.fullscreen_transform.to_dict()
    transform['name'] = position_name
    border_item['sceneItemEnabled'] = False
    obscene.update_item(border_item)
    obscene.update_item(transform)

def restore_scene_defaults():
    obscene = ObsFunctions(obs)
    obscene.update_from_yaml(settings.obs.scene_yaml_file)

# This is called when an input HAS BEEN CHANGED and we need to inform everyone that it has.
# See handle_cam_change_request for the code that initiates a camera change.
def handle_input_changed(message):
    message = message.datain
    inputname = message['inputName']
    position = positions.getByName(inputname)
    if position is None:
        log.error(f"Unknown position changed: {inputname}")
        return

    camera_url = message['inputSettings'].get('input', 'missing URL')
    camera_name = cameras.getNameByUrl(camera_url)
    if camera_name is None:
        camera_name = "unknown"
        log.error(f"{inputname} switch to unknown camera at '{camera_url}'")
    position.active = camera_name
    log.info(f"Position {inputname} changed to camera {camera_name}.")

# This is the code that INITIATES a camera change when we get a request from MQTT.
# See handle_input_changed above for the code that "responds" to MQTT.
def handle_cam_change_request(posname: str):
    requestedcamname = positions[posname].requested
    url = get_camera_url_for_position(posname, requestedcamname)
    if url is None:
        log.error(f"No URL returned for {posname}, {requestedcamname}")
        return
    log.debug(f"Got request to change {posname} to {requestedcamname}")
    set_input_url(posname, url)
    # We have to do this here because new version of set_input_url doesn't actually /change/ inputs, it makes new ones.
    positions[posname].active = requestedcamname

# Temporary function to log stream stats to file so we can get a handle on when we should restart 
# or switch to backup.
def log_stats():
    s = checked_call(requests.GetStreamStatus())
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Log to MQTT:
    mqtt.publish(f"{settings.mqtt_root}/obs/stats", json.dumps({**s, 'timestamp': timestamp}))
    # Log to log:
    # TODO: debug maybe?
    log.info(f"{s}")
    # (optional) Log to file:
    log_media_state()
    if args.stats_log is None:
        return
    with open(args.stats_log, 'a') as file:
        file.write(f"{timestamp} - {s}\n")

def main():
    # process pending mqtt messages so the global objects have data.
    mqtt.process_initialization_callbacks()

    # Similarly, let's set the scroll disabled whether it is or not. 
    scroll_active = MQTTVariable(mqtt, f"{settings.mqtt_root}/scroll/isactive", bool)
    # process messages so we can throw away the value of scroll_requested and force it off.
    mqtt.process_initialization_callbacks()
    scroll_active.add_callback(lambda: set_named_items_enabled('Scroll', scroll_active.value))
    scroll_active.value = False
    # todo: starting the scroll should be by MQTTCommands

    # Setup MQTT callbacks.
    for posname, pos in positions.items():
        pos.add_callback('requested', lambda x=posname: handle_cam_change_request(x))

    # Setup OBS callbacks.
    obs.register(handle_input_changed, events.InputSettingsChanged)
    werewelive = True
    def on_stream_state(message):
        message = message.datain
        nonlocal werewelive
        arewelive = message['outputActive']
        if arewelive == werewelive:
            return
        if arewelive:
            log.info("Are We Live?!   YEAH!")
        else:
            log.warning("Stream is NOT active.")
        mqtt.publish(f"{settings.mqtt_root}/obs/arewelive", json.dumps(arewelive))
        werewelive = arewelive
    was_recording = False
    def on_recording_state(message):
        message = message.datain
        nonlocal was_recording
        is_recording = message['outputActive']
        if is_recording == was_recording:
            return
        if is_recording:
            log.info("Recording started.")
        else:
            log.info(f"Recording ended, located at {message['outputPath']}.")
        mqtt.publish(f"{settings.mqtt_root}/obs/is_recording", json.dumps(is_recording))
        mqtt.publish(f"{settings.mqtt_root}/obs/last_recording_filename", json.dumps(message['outputPath']))
        was_recording = is_recording
    obs.register(on_stream_state, events.StreamStateChanged)
    obs.register(on_recording_state, events.RecordStateChanged)
    # TODO: once we start using scenes...
    #obs.register(callback, events.CurrentProgramSceneChanged)

    # For cameras, having a retained "requested" topic makes sense because we could reboot and we want to be sure things are
    # in a good state. For everything else, there's commands.
    usercommands = OBSCommands(mqtt, settings.mqtt_root)
    usercommands.start_recording = start_recording
    usercommands.stop_recording = stop_recording
    usercommands.start_streaming = start_streaming
    usercommands.stop_streaming = stop_streaming
    usercommands.make_fullscreen = make_fullscreen
    usercommands.restore_scene_defaults = restore_scene_defaults

    mqtt.process_initialization_callbacks()

    # At startup we always want to check to be sure we're displaying what we think we're displaying.
    if not args.skip_init:
        restore_scene_defaults()
        verify_active()

    ###################
    # Automatically begin streaming on startup if we aren't
    if not is_streaming():
        log.warning("Stream is NOT active at startup.")
        if args.auto_start:
            log.info("Starting stream.")
            start_streaming()
   
    ############
    ## TESTING
    ############
    # log_media_state()

    ##################
    # Set up stats logging
    stats_log_interval = settings.obs.get('stats_log_interval',0)
    if stats_log_interval == 0 and args.stats_log:
        # Pick a reasonable default
        stats_log_interval = 60
    loop_time = max(stats_log_interval, 1)
    #####################
    # Loop forever!
    log.info("Startup completed.  Waiting for events...")
    try:
        while True:
            mqtt.process_callbacks_for_time(loop_time)
            if stats_log_interval: 
               log_stats()
    except KeyboardInterrupt:
        log.info("Shutting down by user request.")

    obs.disconnect()
    mqtt.disconnect()

    log.info("Program exiting.")

if __name__ == "__main__":
    main()


