from typing import Callable, Any

import requests as requests
from requests.auth import HTTPDigestAuth

from trol.shared.settings import get_settings
settings = get_settings()
settings.load_from_command_line()

from trol.shared.logger import setup_logger, set_debug
log = setup_logger(__name__)

from trol.shared.MQTT import MQTTConnectionManager
from trol.shared.MQTTVariable import MQTTVariable
from trol.shared.MQTTPositions import MQTTPositions, MQTTPosition
from trol.shared.MQTTCameras import MQTTCameras, MQTTCamera
from trol.shared.MQTTCommands import OBSCommands

mqtt = None
cameras = None
positions = None
obs = None
is_recording = False

class CameraMonitor:
    def __init__(self, camera: MQTTCamera, position: MQTTPosition, autorecord: bool = True):
        self.camera = camera
        self.position = position
        self.autorecord = autorecord
        self.we_control_recording = False
        self.prior = None
        self.prior_audio = []
        self.state = 'offline'
        log.debug(f"Autocamera for {self.camera._name} in position {self.position._name} initialized.")


    def on_online(self):
        log.debug(f"{self.camera._name} is online. Executing online code.")
        if self.position.active != self.position.requested:
            log.error(f"Warning, {self.position._name} active does not match requested: {self.position.active} != {self.position.requested}")
            # Returning here should safely leave us in the offline mode
            return
        if self.position.requested == self.camera._name or self.position.active == self.camera._name:
            log.error(f"Error, {self.position._name} already has {self.camera._name} in either active or requested: {self.position.active},{self.position.requested}")
            # Returning here should safely leave us in the offline mode
            return
        self.state = 'online'
        self.prior = self.position.requested # save the requested camera to avoid timing issues.
        log.debug(f"Setting {self.camera._name} in position {self.position._name}, replacing {self.position.requested}")
        self.position.requested = self.camera._name
        if (not self.camera.noaudio) and settings.autocam_audio_position:
            for position_name, position in positions.items():
                if(position.isaudio):
                    self.prior_audio.append((position, position.requested))
                    if position_name == settings.autocam_audio_position:
                        log.debug(f"Setting {self.camera._name} in position {position_name}, replacing {position.requested}")
                        position.requested = self.camera._name
                    else:
                        log.debug(f"Setting {settings.null_camera_name} in position {position_name}, replacing {position.requested}")
                        position.requested = settings.null_camera_name
        if is_recording == False:
            self.we_control_recording = True
            obs.start_recording()
        else:
            self.we_control_recording = False
            log.debug(f"Not starting recording because recording already active.")
        log.debug(f"Camera {self.camera._name} activated.")

    def on_offline(self):
        log.debug(f"{self.camera._name} is offline. Executing offline code.")
        self.state = 'offline'
        log.debug(f"Setting {self.prior} in position {self.position._name} replacing {self.position.requested}")
        self.position.requested = self.prior
        self.prior = None
        if self.prior_audio:
            for position, priorcam in self.prior_audio:
                log.debug(f"Setting {priorcam} in position {position._name} replacing {position.requested}")
                position.requested = priorcam
            self.prior_audio = []
        if self.we_control_recording:
            if not is_recording:
                log.error(F"We control recording but recording already stopped!")
            obs.stop_recording()
        log.debug(f"Autocam {self.camera._name} deactivated.")

    def check_camera(self):
        try:
            url = self.camera.pingurl or self.camera.rtspurl
            # log.debug(f"Checking for connection to {url}")
            response = requests.get(url, timeout=2)
            # log.debug(f"response is: {response}")
            if response.status_code == 200:
                if self.state == 'offline':
                    self.on_online()
            else:
                if self.state == 'online':
                    self.on_offline()
        except requests.exceptions.RequestException:
            # log.debug(f"RequestException; we are offline.")
            if self.state == 'online':
                self.on_offline()


def handle_recording_toggled(active: bool):
    global is_recording

    if active:
        is_recording = True
        log.debug("RECORDING")
    else:
        is_recording = False
        log.debug("NOT RECORDING")

def main():

    global mqtt
    global cameras
    global positions
    global obs

    mqtt = MQTTConnectionManager(settings.mqtt.host, settings.mqtt.port, settings.mqtt.username, settings.mqtt.password)
    cameras = MQTTCameras(mqtt, f"{settings.mqtt_root}/cameras")
    positions = MQTTPositions(mqtt, f"{settings.mqtt_root}/positions")
    obs = OBSCommands(mqtt, settings.mqtt_root)
    recording = MQTTVariable(mqtt, f"{settings.mqtt_root}/obs/is_recording", value_type = bool, initial_value = False)
    recording.add_callback(lambda: handle_recording_toggled(recording.value))
    mqtt.process_initialization_callbacks()

    autocameras = []
    for autocam_name, autocam_settings in settings.get('autocam_dict', {}).items():
        autocameras.append(CameraMonitor(cameras.getByName(autocam_name), positions.getByName(autocam_settings.position)))

    if not autocameras:
        log.warning("No cameras set to autocam in config.")
        return

    log.info(f"Startup completed.  Monitoring {len(autocameras)} camera(s).")
    try:
        while True:
            mqtt.process_callbacks_for_time(1)
            for autocam in autocameras:
                autocam.check_camera()
    except KeyboardInterrupt:
        log.info("Shutting down by user request.")

    mqtt.disconnect()

    log.info("Program exiting.")

if __name__ == "__main__":
    main()


