import argparse
import threading
import time
from onvif import ONVIFCamera
import requests
from requests.auth import HTTPDigestAuth

from trol.shared.logger import setup_logger, is_debug
log = setup_logger(__name__)

def decode_position(ptzposition):
    #print(f"decode: {ptzposition}")
    x = 0
    y = 0
    z = 0
    if ptzposition.PanTilt:
        x = ptzposition.PanTilt.x
        y = ptzposition.PanTilt.y
    if ptzposition.Zoom:
        z = ptzposition.Zoom.x
    return (x,y,z)

def encode_position(coords):
    return {'PanTilt': {'x': coords[0], 'y': coords[1]}, 'Zoom': {'x': coords[2]}}


# TODO: refactor all the thing.
def get_service_and_token(camera_ip, port, username, password):
    camera = ONVIFCamera(camera_ip, port, username, password)
    ptz_service = camera.create_ptz_service()
    media_service = camera.create_media_service()
    profiles = media_service.GetProfiles()
    token = profiles[0].token
    return ptz_service, media_service, profiles, token

def get_current_position(ptz_service, token):
    status = ptz_service.GetStatus({'ProfileToken': token})
    position = status.Position
    return decode_position(position)

def are_coords_equal(c1, c2, tolerance=0.01):
    return all(abs(a - b) <= tolerance for a, b in zip(c1, c2))

def poll_position_until_complete(ptz_service, token, target_position, callback=None, max_checks_without_change=2, sleep_interval=0.5):
    last_position = None
    current_position = None
    checks_without_change = 0

    while True:
        current_position = get_current_position(ptz_service, token)
        if are_coords_equal(current_position, target_position):
            break

        # The above is probably sufficient but we're going belt+suspenders
        # Check to make sure the camera hasn't stopped moving somewhere else
        if last_position and are_coords_equal(current_position, last_position, tolerance = 0):
            checks_without_change += 1
        else:
            checks_without_change = 0

        if checks_without_change >= max_checks_without_change:
            log.warn(f"Movement stopped without reaching target.")
            break

        last_position = current_position
        time.sleep(sleep_interval)

    if callback:
        callback(current_position)

def relative_move(ptz_service, token, vector, callback=None):
    position = get_current_position(ptz_service, token)
    destination = tuple(max(min(a+b,1),-1) for a,b in zip(position, vector))
    move_to_position(ptz_service, token, destination, callback)

def move_to_position(ptz_service, token, coords, callback=None):
    position = encode_position(coords)
    request = ptz_service.create_type('AbsoluteMove')
    request.ProfileToken = token
    request.Position = position
    ptz_service.AbsoluteMove(request)
    
    if callback:
        threading.Thread(target=poll_position_until_complete, args=(ptz_service, token, coords, callback)).start()

# Function to move to a stored position
def move_to_stored_position(ptz_service, token, position_number, callback=None):
    presets = ptz_service.GetPresets({'ProfileToken': token})
    target_preset = None
    for preset in presets:
        log.debug(f"Target preset: {preset}")
        if preset.token == str(position_number):
            target_preset = preset
            break

    if target_preset:
        ptz_service.GotoPreset({'ProfileToken': token, 'PresetToken': target_preset.token})
        
        if callback:
            threading.Thread(target=poll_position_until_complete, args=(ptz_service, token, decode_position(target_preset.PTZPosition), callback)).start()
    else:
        raise Exception(f"Preset position {position_number} not found.")

# Function to store the current position as a preset
def store_current_position_as_preset(ptz_service, token, preset_name):
    # Create a new preset with the current position
    request = ptz_service.create_type('SetPreset')
    request.ProfileToken = token
    request.PresetName = preset_name
    response = ptz_service.SetPreset(request)
    return response

# TODO: add/move this to screenshot.py in an accessable way
def get_screenshot(camera_ip, port, username, password):
    _, media_service, profiles, token = get_service_and_token(*args, **args)
    snapshot_uri = media_service.GetSnapshotUri({'ProfileToken': profiles[0].token}).Uri
    # Download the image
    response = requests.get(snapshot_uri, auth=HTTPDigestAuth(username, password),timeout=10)
    if response.status_code != 200:
        raise Exception(f"Request for screenshot {camera_ip} returned {response}")
    return response.content

def get_snapshot_url(media_service, token):
    return  media_service.GetSnapshotUri({'ProfileToken': token}).Uri

def get_rtsp_url(media_service, token):
    url = media_service.GetStreamUri({
        'StreamSetup': {
            'Stream': 'RTP-Unicast',
            'Transport': {'Protocol': 'TCP'}
        },
        'ProfileToken': token
    })

    return url.Uri


def reboot_camera(camera_ip, port, username, password):
    camera = ONVIFCamera(camera_ip, port, username, password)
    device_service = camera.create_device_service()
    device_service.SystemReboot()
    log.warn("Camera is rebooting...")

# Function to return all stored positions as (number, coords)
def get_all_stored_positions(ptz_service, token):
    presets = ptz_service.GetPresets({'ProfileToken': token})
    # Seems like the cameras use (0,1.0,0) as code for "Position not set."
    positions = [(preset.token, decode_position(preset.PTZPosition)) for preset in presets 
                 if not are_coords_equal(decode_position(preset.PTZPosition), (0,1.0,0), tolerance=0)]
    return positions

def main():
    parser = argparse.ArgumentParser(description="PTZ Camera Control")
    parser.add_argument('--camera_ip', type=str, required=True, help='IP address of the camera')
    parser.add_argument('--port', type=int, default=80, help='Port of the camera')
    parser.add_argument('--username', type=str, required=True, help='Username for the camera')
    parser.add_argument('--password', type=str, required=True, help='Password for the camera')

    parser.add_argument('--print_position', action='store_true', help='Print the current position')
    parser.add_argument('--move_to_position', type=str, help='Move to the given position (x,y,z)')
    parser.add_argument('--store_position', type=str, help='Store the current position with the given preset name')
    parser.add_argument('--move_to_stored_position', type=int, help='Move to the stored position with the given position number')
    parser.add_argument('--relative_move', type=str, help='Move to position relative to this one')
    parser.add_argument('--screenshot', type=str, help='Filename for screenshot')
    parser.add_argument('--reboot', action='store_true', default=False, help='Reboot camera')
    parser.add_argument('--get_rtsp_url', action='store_true', default=False, help='Print the RTSP URL')
    parser.add_argument('--get_stored_positions', action='store_true', default=False, help='Print the positions stored in camera')

    args = parser.parse_args()


    # Get PTZ service and profile token
    ptz_service, media_service, profiles, token = get_service_and_token(args.camera_ip, args.port, args.username, args.password)

    if args.print_position:
        position = get_current_position(ptz_service, token)
        print(f"Starting position: {position}")

    if args.get_stored_positions:
        print(f"All positions: \n{get_all_stored_positions(ptz_service, token)}")

    if args.move_to_position:
        x, y, z = map(float, args.move_to_position.split(','))
        move_to_position(ptz_service, token, (x, y, z), callback=lambda: print("Move to specified position completed."))

   
    if args.move_to_stored_position:
        move_to_stored_position(ptz_service, token, args.move_to_stored_position, callback=lambda: print(f"Camera moved to position {args.move_to_stored_position} successfully."))

    if args.relative_move:
        x, y, z = map(float, args.relative_move.split(','))
        relative_move(ptz_service, token, (x,y,z), callback=lambda: print(f"Move completed, arrived at {get_current_position(ptz_service, token)}."))

    if args.store_position:
        preset_token = store_current_position_as_preset(ptz_service, token, args.store_position)
        print(f"Stored position as preset with token: {preset_token}")

    if args.screenshot:
        data = get_screenshot(args.camera_ip, args.port, args.username, args.password)
        with open(args.screenshot, 'wb') as file:
            file.write(data)
        print(f"Screenshot saved as {args.screenshot}")

    if args.get_rtsp_url:
        print(f"URL: {get_rtsp_url(media_service, token)}")

    if args.reboot:
        reboot_camera(args.camera_ip, args.port, args.username, args.password)
        print(f"Camera is rebooting...")


if __name__ == "__main__":
    main()

