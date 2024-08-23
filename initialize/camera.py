import json
import argparse
from trol.shared.MQTT import MQTTConnectionManager
from trol.shared.MQTTCameras import MQTTCameras
from trol.shared.settings import get_settings

def make_rtsp_url(camera_type, address, user, password):
    if camera_type == 'ANPVIZ':
        return f"rtsp://{user}:{password}@{address}/Streaming/Channels/101"
    if camera_type == 'MOTO':
        return f"rtsp://{user}:{password}@{address}/stream0"
    if camera_type in ['AMCREST', 'LOREX', 'GENERIC']:
        return f"rtsp://{user}:{password}@{address}/cam/realmonitor?channel=1&subtype=0"
    return f"rtsp://{user}:{password}@{address}/" # no clue.

def make_audio_url(camera_type, address, user, password):
    if camera_type == 'ANPVIZ':
        return f"rtsp://{user}:{password}@{address}/Streaming/Channels/101"
    if camera_type == 'MOTO':
        return f"rtsp://{user}:{password}@{address}/stream0"
    if camera_type in ['AMCREST', 'LOREX', 'GENERIC']:
        return f"rtsp://{user}:{password}@{address}/cam/realmonitor?channel=1&subtype=0"
    return f"rtsp://{user}:{password}@{address}/" # no clue.

def make_jpg_url(camera_type, address, user, password):
    if camera_type == 'ANPVIZ':
        return f"http://{user}:{password}@{address}/ISAPI/Streaming/channels/102/picture"
    if camera_type == 'MOTO':
        return f"http://{user}:{password}@{address}/cgi-bin/snapshot.cgi?stream=1&username={user}&password={password}"
    if camera_type in ['AMCREST', 'LOREX', 'GENERIC']:
        return f"http://{user}:{password}@{address}/cgi-bin/snapshot.cgi?1"
    return f"rtsp://{user}:{password}@{address}/" # no clue.

def get_args():
    parser = argparse.ArgumentParser(description='Populate MQTT topics from JSON file')
    parser.add_argument('--config', default="./config.yaml", help='TROL2 config file')
    parser.add_argument('--camerafile', required=True, help='Camera definition yaml')
    parser.add_argument('--delete', action="store_true", default=False, help='Choose destruction')
    args = parser.parse_args()
    return args;

def main():
    args = get_args()
    settings = get_settings()
    settings.load_from_yaml_file(args.config)

    camera_data = get_settings("camera")
    camera_data.load_from_yaml_file(args.camerafile)

    mqtt = MQTTConnectionManager(settings.mqtt.host, settings.mqtt.port, settings.mqtt.username, settings.mqtt.password)
    cameras = MQTTCameras(mqtt, f"{settings.mqtt_root}/cameras")
    # Initialize the cameras from MQTT:
    mqtt.process_initialization_callbacks()

    if(args.delete):
        # Delete the camera first so other users will remove it and not see all the blank strings
        # we're about to send as bad data.
        cameras.delByName(camera_data.name)

        # Delete camera data if any: 
        for k in ['type', 'address', 'rtspurl', 'jpgurl', 'audiourl', 'noaudio', 'ispublic', 'ishidden', 'nice_name', 'nothumb', 
                  'failure_count', 'last_screenshot_timestamp', 'screenshot', 'error_message',
                  'prior_ptz_positions', 'known_ptz_positions', 'ptz_locked', 'ptz_arrived'
                  ]:
            mqtt.publish(f"{settings.mqtt_root}/cameras/{camera_data.name}/{k}", "")
        print(f"Deleted {camera_data.name}")
        print(f"NOTE: Ignore any errors below regarding converting messages from MQTTVariable.")
    else:
        camera = cameras.addOrGetByName(camera_data.name)
        camera.type = camera_data.type
        camera.address = camera_data.address
        camera.rtspurl = camera_data.get('rtspurl', make_rtsp_url(camera.type, camera.address, settings.camera_user, settings.camera_pass))
        camera.audiourl = camera_data.get('audiourl', make_audio_url(camera.type, camera.address, settings.camera_user, settings.camera_pass))
        camera.jpgurl = camera_data.get('jpgurl', make_jpg_url(camera.type, camera.address, settings.camera_user, settings.camera_pass))
        camera.noaudio = camera_data.get('noaudio', False)
        camera.ispublic = camera_data.get('ispublic', False)
        camera.ishidden = camera_data.get('ishidden', False)
        camera.nice_name = camera_data.get('nice_name', None)
        camera.nothumb = camera_data.get('nothumb', False)
        
        print(f"Created {camera_data.name}")

    mqtt.process_callbacks_for_time(1, quit_early=True)
    print(f"Disconnecting.")
    mqtt.disconnect()

if __name__ == '__main__':
    main()

