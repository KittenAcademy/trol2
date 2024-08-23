import argparse
import json
import time
import threading
from datetime import datetime
import requests
from requests.auth import HTTPDigestAuth
import io
from PIL import Image
import base64
import numpy as np
from urllib.parse import urlparse
import ffmpeg
import tempfile
import os

from trol.shared.settings import get_settings

from trol.shared.MQTT import MQTTConnectionManager
from trol.shared.MQTTVariable import MQTTVariable

from trol.shared.logger import setup_logger, is_debug
log = setup_logger(__name__)

failure_count = None
last_error = None

def make_static(thumb_width, thumb_height):
    random_data = np.random.randint(100, 150, (thumb_height, thumb_width), dtype=np.uint8)
    image = Image.fromarray(random_data, 'L')
    thumbIO = io.BytesIO()
    image.save(thumbIO, format='JPEG')
    return "data:image/jpg;base64," + str(base64.b64encode(thumbIO.getvalue()), 'utf8')

def process_screenshot(c, thumb_width = 240, thumb_height = 135):
    ### Convert response content into resized image represented as b64 string
    image = Image.open(io.BytesIO(c))
    # TODO: get resolution from config
    resized_image = image.resize([thumb_width, thumb_height])
    thumbIO = io.BytesIO()
    resized_image.save(thumbIO, format='JPEG')
    return "data:image/jpg;base64," + str(base64.b64encode(thumbIO.getvalue()), 'utf8')

def get_screenshot_http(screenshot_address, camera_user = None, camera_pass = None, timeout=5):
    # If no creds supplied, see if they're embedded in URL
    if not camera_user:
        purl = urlparse(screenshot_address)
        if purl.username:
            camera_user = purl.username
            camera_pass = purl.password

    if camera_user:
        r = requests.get(screenshot_address,auth=HTTPDigestAuth(camera_user, camera_pass),timeout=timeout)
    else:
        r = requests.get(screenshot_address,timeout=timeout)
    sc = r.status_code
    if sc == 200:
        return r.content
    else:
        raise Exception(f"Request for {screenshot_address} returned {sc}")

def get_screenshot_stream(screenshot_address, _camera_user, _camera_pass):
    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmpfile:
        try:
            # Capture frame and write to the temporary file
            (
                ffmpeg
                .input(screenshot_address)
                .output(tmpfile.name, vframes=1, update=1)
                .overwrite_output()
                .global_args('-loglevel', 'error')
                .run()
            )
            with open(tmpfile.name, 'rb') as file:
                file_data = file.read()
        finally:
            os.remove(tmpfile.name)
    return file_data

def is_rtsp(url):
    parsed_url = urlparse(url)
    return parsed_url.scheme.lower() == 'rtsp'

def get_camera_screenshot(screenshot_address, camera_user, camera_pass, thumb_width, thumb_height, timeout=5):
    global last_error
    try:
        if is_rtsp(screenshot_address):
            return process_screenshot(get_screenshot_stream(screenshot_address, camera_user, camera_pass), thumb_width, thumb_height)
        else:
            return process_screenshot(get_screenshot_http(screenshot_address, camera_user, camera_pass, timeout), thumb_width, thumb_height)
    except Exception as e:
        # Take a note.
        last_error = f"{datetime.now().isoformat()} -- {e}";
    return None


def publish_camera_status(mqtt_manager, camera_root, jpgurl, camera_user = None, camera_pass = None, thumb_width = None, thumb_height = None, timeout = None, on_fail = 'delayed'):
    global failure_count
    screenshot_topic = f"{camera_root}/screenshot"
    timestamp_topic  = f"{camera_root}/last_screenshot_timestamp"
    error_topic      = f"{camera_root}/error_message"

    log.debug(f"Getting screenshot for {camera_root} from {jpgurl}")
    screenshot = get_camera_screenshot(jpgurl, camera_user, camera_pass, thumb_width, thumb_height, timeout)
    if screenshot:
        failure_count.value = 0
        mqtt_manager.publish(timestamp_topic, datetime.now().isoformat())
    else:
        failure_count.value += 1
        mqtt_manager.publish(error_topic, last_error)
        log.info(f"{camera_root} screenshot {failure_count.value} error(s): {last_error}")
        # TODO: Have an option to do nothing until X failures/X time since last success, then send clear.
        # Or just make that how it always works.
        # TODO: Make this an option:
        if failure_count.value > 50:
            raise Exception("Failure count reached 50, dying so Docker can restart us.")
        if on_fail == 'static':
            screenshot = make_static(thumb_width, thumb_height)
        elif on_fail == 'clear':
            screenshot = ''
        elif on_fail == 'delayed':
            if failure_count.value > 20:
                screenshot = ''
        else:
            # don't publish any screenshot data.
            return
    mqtt_manager.publish(screenshot_topic, screenshot)

def get_args():
    parser = argparse.ArgumentParser(description='Camera Screenshot Publisher')
    parser.add_argument('--config', type=str, required=True, help='Config filename (default: ./config.yaml)')

    parser.add_argument('--camera_name', type=str, required=True, help='Name of the camera')
    parser.add_argument('--camera_user', type=str, help='Camera username')
    parser.add_argument('--camera_pass', type=str, help='Camera password')

    parser.add_argument('--on_fail', type=str, choices=['static', 'clear', 'nothing', 'delayed'], default='nothing', help='What to do on camera fail')
    parser.add_argument('--interval', type=int, default=5, help='Interval in seconds between screenshots')
    parser.add_argument('--timeout', type=int, default=10, help='Timeout waiting for screenshot')
    
    args = parser.parse_args()


    return args


def main():
    global args
    global failure_count

    args = get_args()

    settings = None
    if args.config:
        settings = get_settings()
        settings.load_from_yaml_file(args.config)

    if settings is not None:
        if not args.camera_user:
            args.camera_user = settings.camera_user
        if not args.camera_pass:
            args.camera_pass = settings.camera_pass
        
    mqtt_manager = MQTTConnectionManager(**settings.mqtt)
    camera_root  = f"{settings.mqtt_root}/cameras/{args.camera_name}"
    jpg_address  = MQTTVariable(mqtt_manager, f"{camera_root}/jpgurl")
    nothumb      = MQTTVariable(mqtt_manager, f"{camera_root}/nothumb", value_type = bool, initial_value=False)
    failure_count = MQTTVariable(mqtt_manager, f"{camera_root}/failure_count", value_type = int, initial_value=0)

    mqtt_manager.process_callbacks(timeout=1)

    # MAIN LOOP
    try:
        while True:
            # Get screenshot
            if jpg_address.value is None:
                log.error(f"No screenshot URL for {args.camera_name}")
                # We don't die here because someone could provide a screenshot address while we're running via mqtt
            if nothumb.value:
                log.debug(f"Not retrieving thumbnail for {args.camera_name} because nothumb is set.")
                # We don't die here because this could change and dying/restarting is probably more strain than just looping.
            else:
                # Reload these at every loop in case they change in settings.
                camera_user = args.camera_user or settings.camera_user
                camera_pass = args.camera_pass or settings.camera_pass
                # TODO: Refactor, and get timeout from settings
                publish_camera_status(mqtt_manager, camera_root, jpg_address.value, 
                                      camera_user = camera_user, 
                                      camera_pass = camera_pass, 
                                      thumb_width = settings.thumbnail_width, 
                                      thumb_height = settings.thumbnail_height, 
                                      timeout = args.timeout, 
                                      on_fail = args.on_fail)

            mqtt_manager.process_callbacks_for_time(args.interval)
    
    except KeyboardInterrupt:
        mqtt_manager.disconnect()
        log.debug("Disconnected from MQTT broker")

if __name__ == '__main__':
    main()

