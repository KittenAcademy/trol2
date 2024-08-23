import json
import argparse
from trol.shared.MQTT import MQTTConnectionManager
from trol.shared.MQTTPositions import MQTTPositions
from trol.shared.settings import get_settings

def get_args():
    parser = argparse.ArgumentParser(description='Populate MQTT topics from JSON file')
    parser.add_argument('--config', default="./config.yaml", help='TROL2 config file')
    parser.add_argument('--positionfile', required=True, help='Position definition yaml')
    parser.add_argument('--delete', action="store_true", default=False, help='Choose destruction')
    args = parser.parse_args()
    return args;

def main():
    args = get_args()
    settings = get_settings()
    settings.load_from_yaml_file(args.config)

    position_data = get_settings("position")
    position_data.load_from_yaml_file(args.positionfile)

    mqtt = MQTTConnectionManager(**settings.mqtt)
    positions = MQTTPositions(mqtt, f"{settings.mqtt_root}/positions")
    # Initialize from MQTT:
    mqtt.process_initialization_callbacks()

    if(args.delete):
        positions.delByName(position_data.name)

        # Delete data if any: 
        for k in ['active', 'requested', 'isaudio', 'locked_until', 'lock_level', 'obs_item_default', 'nice_name']:
            mqtt.publish(f"{settings.mqtt_root}/positions/{position_data.name}/{k}", "")
        print(f"Deleted {position_data.name}")
        print(f"NOTE: Ignore any errors below regarding converting messages from MQTTVariable.")
    else:
        position = positions.addOrGetByName(position_data.name)
        position.isaudio = position_data.get('isaudio', False)
        position.nice_name = position_data.get('nice_name', None)
        position.obs_item_default = position_data.get('obs_item_default', {})
        position.locked_until = 0
        position.lock_level = 'Discord user'
        # Not set: active, requested, lock_level
        
        print(f"Created {position_data.name}")

    mqtt.process_callbacks_for_time(1, quit_early=True)
    print(f"Disconnecting.")
    mqtt.disconnect()

if __name__ == '__main__':
    main()

