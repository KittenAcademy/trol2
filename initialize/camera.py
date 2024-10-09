import json
import yaml
import argparse
from trol.shared.MQTT import MQTTConnectionManager
from trol.shared.MQTTCameras import MQTTCameras
from trol.shared.settings import get_settings

# TODO: When creating a camera populate a screenshot with static and include a timestamp, etc so our total lack of checking whether data exists
# in trol doesn't cause a failure.
KNOWN_CAMERA_KEYS = [
                'type', 'address', 'rtspurl', 'jpgurl', 'audiourl', 'noaudio', 'ispublic', 'ishidden', 'nice_name', 'nothumb',
                'failure_count', 'last_screenshot_timestamp', 'screenshot', 'error_message',
                'prior_ptz_positions', 'known_ptz_positions', 'ptz_locked', 'ptz_arrived'
            ]

def make_rtsp_url(camera_type, address, user, password):
    if camera_type == 'ANPVIZ':
        return f"rtsp://{user}:{password}@{address}/Streaming/Channels/101"
    if camera_type == 'MOTO':
        return f"rtsp://{user}:{password}@{address}/stream0"
    if camera_type in ['AMCREST', 'LOREX', 'GENERIC']:
        return f"rtsp://{user}:{password}@{address}/cam/realmonitor?channel=1&subtype=0"
    return f"rtsp://{user}:{password}@{address}/"  # no clue.

def make_audio_url(camera_type, address, user, password):
    if camera_type == 'ANPVIZ':
        return f"rtsp://{user}:{password}@{address}/Streaming/Channels/101"
    if camera_type == 'MOTO':
        return f"rtsp://{user}:{password}@{address}/stream0"
    if camera_type in ['AMCREST', 'LOREX', 'GENERIC']:
        return f"rtsp://{user}:{password}@{address}/cam/realmonitor?channel=1&subtype=0"
    return f"rtsp://{user}:{password}@{address}/"  # no clue.

def make_jpg_url(camera_type, address, user, password):
    if camera_type == 'ANPVIZ':
        return f"http://{user}:{password}@{address}/ISAPI/Streaming/channels/102/picture"
    if camera_type == 'MOTO':
        return f"http://{user}:{password}@{address}/cgi-bin/snapshot.cgi?stream=1&username={user}&password={password}"
    if camera_type in ['AMCREST', 'LOREX', 'GENERIC']:
        return f"http://{user}:{password}@{address}/cgi-bin/snapshot.cgi?1"
    return f"rtsp://{user}:{password}@{address}/"  # no clue.

def get_args():
    parser = argparse.ArgumentParser(description='Populate MQTT topics from JSON or YAML file')
    parser.add_argument('--config', default="./config.yaml", help='TROL2 config file')
    parser.add_argument('--camerafile', required=True, help='Camera definition YAML or JSON')
    parser.add_argument('--keypath', help='Dot-separated path to cameras (e.g., trol.cameras)', default='')
    parser.add_argument('--delete', action="store_true", default=False, help='Choose destruction')
    args = parser.parse_args()
    return args

def load_camera_data(file_path):
    with open(file_path, 'r') as f:
        if file_path.endswith('.yaml') or file_path.endswith('.yml'):
            return yaml.safe_load(f)
        else:
            return json.load(f)

def get_camera_data_by_keypath(data, keypath):
    keys = keypath.split('.')
    for key in keys:
        data = data.get(key, {})
    return data

def main():
    args = get_args()
    settings = get_settings()
    settings.load_from_yaml_file(args.config)

    camera_data = load_camera_data(args.camerafile)

    # Handle both single-camera and multi-camera cases
    # I think it should work like so:  If provided a keypath, we load the data from there.  If the keypath contains any of the known
    # camera data keys then we treat it as a single camera.  If it does not, we treat it as multiple cameras.  If it is a single camera
    # but does not have the key 'name' then we get the last part of the path as the name.  This allows us to easily import multiple or
    # single cameras straight back from a dump created via MQTT.py
    cameras_data = get_camera_data_by_keypath(camera_data, args.keypath) if args.keypath else camera_data
    if any(key in cameras_data for key in KNOWN_CAMERA_KEYS):
        # Single camera case
        camera_name = camera_data.get('name', args.keypath.split('.')[-1])
        if not camera_name:
            raise Exception("Can't determine camera name from provided data.")
        cameras_data = {camera_name: cameras_data}

    mqtt = MQTTConnectionManager(settings.mqtt.host, settings.mqtt.port, settings.mqtt.username, settings.mqtt.password)
    cameras = MQTTCameras(mqtt, f"{settings.mqtt_root}/cameras")
    # Initialize the cameras from MQTT:
    mqtt.process_initialization_callbacks()

    for camera_name, camera_info in cameras_data.items():
        if args.delete:
            cameras.delByName(camera_name)
            # Delete camera data
            for k in KNOWN_CAMERA_KEYS:
                mqtt.publish(f"{settings.mqtt_root}/cameras/{camera_name}/{k}", "")
            print(f"Deleted {camera_name}")
        else:
            camera = cameras.addOrGetByName(camera_name)
            camera.type = camera_info.get('type', 'GENERIC')
            camera.address = camera_info.get('address', '')
            camera.rtspurl = camera_info.get('rtspurl', make_rtsp_url(camera.type, camera.address, settings.camera_user, settings.camera_pass))
            camera.audiourl = camera_info.get('audiourl', make_audio_url(camera.type, camera.address, settings.camera_user, settings.camera_pass))
            camera.jpgurl = camera_info.get('jpgurl', make_jpg_url(camera.type, camera.address, settings.camera_user, settings.camera_pass))
            camera.noaudio = camera_info.get('noaudio', False)
            camera.ispublic = camera_info.get('ispublic', False)
            camera.ishidden = camera_info.get('ishidden', False)
            camera.nice_name = camera_info.get('nice_name', None)
            camera.nothumb = camera_info.get('nothumb', False)

            print(f"Created {camera_name}")

    mqtt.process_callbacks_for_time(1, quit_early=True)
    print(f"Disconnecting.")
    mqtt.disconnect()

if __name__ == '__main__':
    main()

