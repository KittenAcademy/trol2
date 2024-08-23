import json
from urllib.parse import urlparse, urlunparse
from typing import Callable, Any
import traceback

from PIL import Image
import io
import base64

from trol.shared.settings import get_settings
import argparse

from trol.shared.logger import setup_logger, is_debug, set_debug
log = setup_logger(__name__)

from trol.shared.MQTT import MQTTConnectionManager
from trol.shared.MQTTCameras import MQTTCameras
from trol.shared.MQTTCommands import CameraCommands

from .ONVIF import get_service_and_token, move_to_stored_position, move_to_position, get_current_position, relative_move, get_screenshot

ap = argparse.ArgumentParser()
ap.add_argument('--config', type=str, default='./config.yaml', help='Config filename (default: ./config.yaml)')
args = ap.parse_args()

settings = get_settings()
settings.load_from_yaml_file(args.config)

mqtt = MQTTConnectionManager(settings.mqtt.host, settings.mqtt.port, settings.mqtt.username, settings.mqtt.password)
cameras = MQTTCameras(mqtt, f"{settings.mqtt_root}/cameras")
cameraCommands = CameraCommands(mqtt, settings.mqtt_root)

# How many prior_ptz_positions to save
MAX_PTZ_HISTORY = 5

def getConnection(camera):
    url = urlparse(camera.rtspurl)
    # TODO: Don't log username/passwords!
    # log.debug(f"Connecting to {url.hostname} with username {url.username}")
    host, port, user, password = get_credentials(camera._name)
    ptz_service, media_service, profiles, token = get_service_and_token(host, port, user, password )
    return ptz_service, token

def get_credentials(camera_name: str):
    camera = cameras.getByName(camera_name)
    if camera is None:
        log.error(f"Couldn't get camera: {camera_name}")

    url = urlparse(camera.rtspurl)
    return (url.hostname, 80, url.username, url.password)

def getCurrentPosition(camera, ptz_service=None, token=None):
    url = urlparse(camera.rtspurl)
    try:
        if ptz_service is None or token is None:
            ptz_service, token = getConnection(camera)
        position = get_current_position(ptz_service, token)
    except Exception as e:
        stack_trace = traceback.format_exc()
        log.error(f"Exception getting current position for {camera._name}: {e}\n{stack_trace}")
    return position

def add_position_to_undo_stack(camera, ptz_service=None, token=None):
    coords = getCurrentPosition(camera, ptz_service, token)
    prior_ptz = camera.prior_ptz_positions
    if camera.prior_ptz_positions is None:
        camera.prior_ptz_positions = []
    camera.prior_ptz_positions.append(coords)
    camera.prior_ptz_positions = camera.prior_ptz_positions[-MAX_PTZ_HISTORY:]
    log.debug(f"Updated prior ptz for {camera._name} now {camera.prior_ptz_positions}.")

def handle_go_back(camera, negative_index):
    """ Go back to the abs negative_indexth prior coords """
    prior_ptz = camera.prior_ptz_positions
    if prior_ptz is None or len(prior_ptz) == 0:
        prior_ptz = []
        log.warn(f"Request for {camera._name} to go back but no priors stored.")
        return

    if abs(negative_index) > len(prior_ptz):
        # If the negative index is larger than the list, go to the oldest position and clear the list
        coords = prior_ptz[0]
        del prior_ptz[:]
    else:
        # Get the coords at the specified negative index
        coords = prior_ptz[negative_index]
        # Remove any skipped history
        del prior_ptz[negative_index:]

    log.info(f"Handling request for {camera._name} to go back to {coords}")
    handle_goto_coords(camera, coords)
    camera.prior_ptz_positions = prior_ptz
    log.debug(f"Updated prior ptz for {camera._name} now {prior_ptz}.")

def handle_goto_number(camera_name, position_number=None):
    log.debug(f"Request to move {camera_name} to position {position_number}")
    try:
        camera = cameras.getByName(camera_name)
        if position_number < 0:
            handle_go_back(camera, position_number)
            return
        ptz_service, token = getConnection(camera)
        add_position_to_undo_stack(camera, ptz_service=ptz_service, token=token)
        move_to_stored_position(ptz_service, token, position_number, callback = lambda coords, c=camera, s=ptz_service, t=token: report_position_arrival(c, coords, s, t))
    except Exception as e:
        stack_trace = traceback.format_exc()
        log.error(f"Exception moving {camera_name} to position {position_number}: {e}\n{stack_trace}")

def handle_goto_coords(camera_name, coords=None, ptz_service=None, token=None):
    log.debug(f"Request to move {camera_name} to coords: {coords}")
    try:
        camera = cameras.getByName(camera_name)
        if ptz_service is None or token is None:
            ptz_service, token = getConnection(camera)
        add_position_to_undo_stack(camera, ptz_service=ptz_service, token=token)
        log.debug(f"Handling request for {camera_name} to xyz {coords}")
        move_to_position(ptz_service, token, coords, callback = lambda coords, c=camera, s=ptz_service, t=token: report_position_arrival(c, coords, s, t))
    except Exception as e:
        stack_trace = traceback.format_exc()
        log.error(f"Exception moving {camera_name} to position {coords}: {e}\n{stack_trace}")

def handle_vector_move(camera_name, vector):
    log.debug(f"Got request for relative move to {vector} for {camera_name}")
    camera = cameras.getByName(camera_name)
    ptz_service, token = getConnection(camera)
    add_position_to_undo_stack(camera, ptz_service=ptz_service, token=token)
    relative_move(ptz_service, token, vector, callback = lambda coords, c=camera, s=ptz_service, t=token: report_position_arrival(c, coords, s, t))

def report_position_arrival(camera, coords, ptz_service, token):
    creds = get_credentials(camera._name)
    screenshot_data = screenshot_data_to_trol2(get_screenshot(*creds))
    topic = f"{camera.get_topic()}/ptz_arrived"
    log.debug(f"Reporting completed move on {topic}: {coords}")
    mqtt.publish(topic, json.dumps({'coords': coords, 'screenshot': screenshot_data}), retain=False)

def screenshot_data_to_trol2(data: bytes):
    # TODO: this is a common function and should be trol.shared.someplace instead of duplicated
    image = Image.open(io.BytesIO(data))
    resized_image = image.resize([settings.thumbnail_width, settings.thumbnail_height])
    thumbIO = io.BytesIO()
    resized_image.save(thumbIO, format='JPEG')
    return "data:image/jpg;base64," + str(base64.b64encode(thumbIO.getvalue()), 'utf8')



def main():
    cameraCommands.goto_relative_vector = handle_vector_move
    cameraCommands.goto_absolute_coords = handle_goto_coords
    cameraCommands.goto_ptz_position = handle_goto_number
    mqtt.process_initialization_callbacks()

    log.info(f"Startup completed.")
    try:
        while True:
            mqtt.process_callbacks(1)
    except KeyboardInterrupt:
        log.info("Shutting down by user request.")

    mqtt.disconnect()

    log.info("Program exiting.")

if __name__ == "__main__":
    main()


