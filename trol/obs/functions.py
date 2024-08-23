import obswebsocket
from obswebsocket import obsws, requests, events
from time import sleep
import yaml
from trol.shared.logger import setup_logger, set_debug
log = setup_logger(__name__)

def get_args():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', type=str, default='./config.yaml', help='Config filename (default: ./config.yaml)')
    ap.add_argument('--create', type=str, default=None, help='yaml filename of scene items to create.')
    ap.add_argument('--update', type=str, default=None, help='yaml filename of scene items to update.')
    ap.add_argument('--delete', type=str, default=None, help='yaml filename of scene items to delete.')
    ap.add_argument('--die_on_error', action='store_true', default=False, help="Error if items can't be created/deleted.")
    ap.add_argument('--debug', action='store_true', default=False, help="Output debugging information.")
#    ap.add_argument('--test', type=str, default=None, help="internal use only.")
    args = ap.parse_args()

    if args.debug:
        set_debug(log)

    return args

def load_yaml(filename):
    with open(filename, 'r') as file:
        data = yaml.safe_load(file)
    return data

def main():
    from trol.shared.settings import get_settings

    args = get_args()
    settings = get_settings()
    settings.load_from_yaml_file(args.config)

    obs_websocket = obsws(settings.obs.host, settings.obs.port, settings.obs.password)
    obs_websocket.connect()

    obs = ObsFunctions(obs_websocket)

#    if args.test:
#        original_item = obs.get_item_by_name(args.test)
#        border_item = obs.get_item_by_name('Border')
#        transform = settings.obs.fullscreen_transform.to_dict()
#        transform['name'] = args.test
#        border_item['sceneItemEnabled'] = False
#        obs.update_item(border_item)
#        obs.update_item(transform)
#        sleep(5)
#        obs.update_item(original_item)
#        border_item['sceneItemEnabled'] = True
#        obs.update_item(border_item)
#        return


    if args.create:
        items = load_yaml(args.create)
        scene = obs.get_current_scene()
        for itemname, item in items.items():
            print(f"Creating {itemname}...")
            try:
                if obs.get_item_by_name(itemname) is not None:
                    print(f"{itemname} exists, deleting...")
                    obs.delete_item_by_name(itemname)
                obs.create_item(item, scene)
            except Exception as e:
                if args.die_on_error:
                    raise e
                print(f"Error creating {itemname}, continuing.")
                log.debug(f"Error {e} creating {itemname}.")
        print("Complete.")
        return
    if args.update:
        items = load_yaml(args.update)
        scene = obs.get_current_scene()
        for itemname, item in items.items():
            print(f"Updating {itemname}...")
            try:
                obs.update_item(item, scene)
            except Exception as e:
                if args.die_on_error:
                    raise e
                print(f"Error updating {itemname}, continuing.")
                log.debug(f"Error {e} updating {itemname}.")
        print("Complete.")
        return
    if args.delete:
        items = load_yaml(args.delete)
        for itemname, item in items.items():
            print(f"Deleting {itemname}...")
            try:
                obs.delete_item(item)
            except Exception as e:
                if args.die_on_error:
                    raise e
                print(f"Error deleting {itemname}, continuing.")
                log.debug(f"Error {e} deleting {itemname}.")
        print("Complete.")
        return

    items = obs.get_full_items_data()
    print(yaml.dump(items, default_flow_style=False, sort_keys=False))

class ObsFunctions():
    def __init__(self, obs_websocket):
        self.obs = obs_websocket

    def checked_call(self, request):
        foo = self.obs.call(request)
        if not foo.status:
            request_type = request.name
            error_code = foo.datain.get('code')
            if error_code is none:
                raise Exception(f"{request_type} failed. To debug, try using obs-websocket-py from https://github.com/KittenAcademy/obs-websocket-py")
            error_message = foo.datain.get('comment', 'Unknown reason.')
            raise Exception(f"{request_type} failed {error_code}:{error_message}")
        return foo.datain

    def call_until_success(self, request, max_attempts = 20):
        """ OBS websockets have a few race conditions, such as when deleting a source then renaming a new source to the deleted name. """
        while True:
            try:
                foo = self.checked_call(request)
            except Exception as e:
                log.debug(f"Exception: {e}")
                max_attempts -= 1
                if max_attempts <= 0:
                    raise Exception(f"Call failed after multiple attempts: {e}")
                sleep(0.01) # TODO: maybe don't block the caller for a long time?
                continue
            return foo

    # Allows callers to pass in either the entire scene data, or just the uuid.
    def _handle_sceneUuid_param(self, uuid_or_scene):
        if uuid_or_scene is None:
            return self.get_current_scene()['sceneUuid']
        if isinstance(uuid_or_scene, dict):
            return uuid_or_scene['sceneUuid']
        return uuid_or_scene
    
    # Allows callers to pass in either the entire item data or just the uuid,
    # also accounts for the fact that OBS uses 'inputUuid' and 'scourceUuid' for the same thing.
    def _handle_itemUuid_param(self, uuid_or_item):
        if isinstance(uuid_or_item, dict):
            return uuid_or_item.get('inputUuid', uuid_or_item.get('sourceUuid', None))
        return uuid_or_item

    # OBS returns the bounds if OBS_BOUNDS_NONE is set, but then it dies if we try to 
    # pass it back in the same way on creation, so we delete it to help prevent that.
    def _strip_bounds(self, item):
        if item['sceneItemTransform'].get('boundsType') == 'OBS_BOUNDS_NONE':
            item['sceneItemTransform'].pop('boundsType', None)
            item['sceneItemTransform'].pop('boundsAlignment', None)
            item['sceneItemTransform'].pop('boundsHeight', None)
            item['sceneItemTransform'].pop('boundsWidth', None)

    def get_current_scene(self):
        return self.checked_call(requests.GetCurrentProgramScene())

    def get_scene_items(self, sceneUuid = None):
        sceneUuid = self._handle_sceneUuid_param(sceneUuid)
        return self.checked_call(requests.GetSceneItemList(sceneUuid = sceneUuid))['sceneItems']

    def get_input_settings(self, itemUuid):
        itemUuid = self._handle_itemUuid_param(itemUuid)
        return self.checked_call(requests.GetInputSettings(inputUuid = itemUuid))['inputSettings']

    def get_input_mute(self, itemUuid):
        itemUuid = self._handle_itemUuid_param(itemUuid)
        return self.checked_call(requests.GetInputMute(inputUuid = itemUuid))['inputMuted']

    def get_input_volume(self, itemUuid):
        itemUuid = self._handle_itemUuid_param(itemUuid)
        return self.checked_call(requests.GetInputVolume(inputUuid = itemUuid))['inputVolumeMul']

    def get_input_audio_sync_offset(self, itemUuid):
        itemUuid = self._handle_itemUuid_param(itemUuid)
        return self.checked_call(requests.GetInputAudioSyncOffset(inputUuid = itemUuid))['inputAudioSyncOffset']

    def get_full_item_data(self, item):
        item['inputUuid'] = item['sourceUuid']
        item['inputName'] = item['sourceName']
        item['inputSettings'] = self.get_input_settings(item)
        if item['inputKind'] == 'ffmpeg_source':
            item['inputMuted'] = self.get_input_mute(item)
            item['inputVolumeMul'] = self.get_input_volume(item)
            item['inputAudioSyncOffset'] = self.get_input_audio_sync_offset(item)
        self._strip_bounds(item)
        return item

    def get_full_items_data(self, sceneUuid=None):
        sceneUuid = self._handle_sceneUuid_param(sceneUuid)

        items = self.get_scene_items(sceneUuid)
        itemdict = {}
        for item in items:
            itemdict[self.get_item_name(item)] = self.get_full_item_data(item)
        return itemdict

    def get_item_by_uuid(self, itemUuid, sceneUuid=None):
        sceneUuid = self._handle_sceneUuid_param(sceneUuid)
        itemUuid = self._handle_itemUuid_param(itemUuid)

        items = self.get_full_items_data(sceneUuid)
        for name, item in items.items():
            if self._handle_itemUuid_param(item) == itemUuid:
                return item
        return None

    def get_item_by_name(self, itemName, sceneUuid = None):
        sceneUuid = self._handle_sceneUuid_param(sceneUuid)
        if isinstance(itemName, dict):
            itemName = self.get_item_name(itemName)
        items = self.get_full_items_data(sceneUuid)
        for name, item in items.items():
            if name == itemName:
                return item
        return None

    def create_item(self, item, sceneUuid = None):
        sceneUuid = self._handle_sceneUuid_param(sceneUuid)

        # see comment on call_until_success function for reason why
        newids = self.call_until_success(requests.CreateInput(sceneUuid = sceneUuid, **item))

        # After creating, update the passed-in item with the new IDs.
        item['inputUuid'] = newids['inputUuid']
        item['sceneItemId'] = newids['sceneItemId']
        # Because OBS uses these terms interchangably
        item['sourceUuid'] = item['inputUuid']
        item['sourceName'] = item['inputName']
        return self.update_item(item, sceneUuid)

    def rename_item(self, item, sceneUuid = None):
        sceneUuid = self._handle_sceneUuid_param(sceneUuid)
        
        if 'inputName' in item.keys():
            # call_until_success because if we just deleted an item with this name OBS may still have name collision
            self.call_until_success(requests.SetInputName(inputUuid = self._handle_itemUuid_param(item), newInputName = item['inputName']))

    def delete_item(self, item):
        item_uuid = self._handle_itemUuid_param(item)
        if item_uuid is None:
            return self.delete_item_by_name(self.get_item_name(item))
        self.checked_call(requests.RemoveInput(inputUuid = item_uuid))

    def get_item_name(self, item_or_name):
        if isinstance(item_or_name, dict):
            return (
                   item_or_name.get('inputName') or
                   item_or_name.get('sourceName') or
                   item_or_name.get('name', None)
            )
        return item_or_name

    def delete_item_by_name(self, item_name):
        item = self.get_item_by_name(item_name)
        # Must send uuid and not entire dict to avoid possible infinite loop:
        uuid = self._handle_itemUuid_param(item) 
        self.delete_item(uuid)

    def update_from_yaml(self, filename):
        items = load_yaml(filename)
        scene = self.get_current_scene()
        for itemname, item in items.items():
            try:
                self.update_item(item, scene)
            except Exception as e:
                log.debug(f"Error {e} updating {itemname}.")
        return

    def update_item(self, item, sceneUuid = None):
        sceneUuid = self._handle_sceneUuid_param(sceneUuid)
        
        # Needed but not necessarily passed in.
        actual_item = None
        item_uuid = self._handle_itemUuid_param(item)
        if item_uuid is None:
            actual_item = self.get_item_by_name(self.get_item_name(item))
            item_uuid = self._handle_itemUuid_param(actual_item)
            item['sourceUuid'] = item_uuid
            item['inputUuid'] = item_uuid
        if actual_item is None:
            actual_item = self.get_item_by_uuid(item)
        if 'sceneItemId' not in item.keys():
            item['sceneItemId'] = actual_item['sceneItemId']

        # Input stuff
        if 'inputSettings' in item.keys() and not self._are_dicts_equal(item['inputSettings'], actual_item.get('inputSettings', {})):
            self.checked_call(requests.SetInputSettings(**item))
        if 'inputVolumeMul' in item.keys() and item['inputVolumeMul'] != actual_item.get('inputVolumeMul'): 
            self.checked_call(requests.SetInputVolume(**item))
        if 'inputMuted' in item.keys() and item['inputMuted'] != actual_item.get('inputMuted'):
            self.checked_call(requests.SetInputMute(**item))
        if 'inputAudioSyncOffset' in item.keys() and item['inputAudioSyncOffset'] != actual_item.get('inputAudioSyncOffset'):
            self.checked_call(requests.SetInputAudioSyncOffset(**item))

        # Item stuff
        if 'sceneItemTransform' in item.keys() and not self._are_dicts_equal(item['sceneItemTransform'], actual_item.get('sceneItemTransform', {})):
            self.checked_call(requests.SetSceneItemTransform(sceneUuid = sceneUuid, **item))
        if 'sceneItemEnabled' in item.keys() and item['sceneItemEnabled'] != actual_item.get('sceneItemEnabled'):
            self.checked_call(requests.SetSceneItemEnabled(sceneUuid = sceneUuid, **item))
        if 'sceneItemLocked' in item.keys() and item['sceneItemLocked'] != actual_item.get('sceneItemLocked'):
            self.checked_call(requests.SetSceneItemLocked(sceneUuid = sceneUuid, **item))
        if 'sceneItemIndex' in item.keys() and item['sceneItemIndex'] != actual_item.get('sceneItemIndex'):
            self.checked_call(requests.SetSceneItemIndex(sceneUuid = sceneUuid, **item))
        if 'sceneItemBlendMode' in item.keys() and item['sceneItemBlendMode'] != actual_item.get('sceneItemBlendMode'):
            self.checked_call(requests.SetSceneItemBlendMode(sceneUuid = sceneUuid, **item))

        item = self.get_item_by_uuid(item, sceneUuid)
        return item

    def _are_dicts_equal(self, dictA, dictB):
        """ 
        Compare two instances of OBS data to determine if they are functionally equivalent

        We consider 0, 0.0 and strings that evaluate to 0 to be equivalent.
        TODO: decide whether a missing value in the new item (dictA) can be considered equivalent to any value in 
        the old item (dictB) because not including it will not overwrite the old value.  I think the answer is yes.
        So I'm coding it as yes.  For now.
        """
        def normalize_value(value):
            if value is None:
                return None
            if isinstance(value, str):
                try:
                    # Try converting string to int or float
                    return int(value) if '.' not in value else float(value)
                except ValueError:
                    pass
            return value

        # Collect all unique keys from both dictionaries
        all_keys = set(dictA.keys()).union(set(dictB.keys()))

        for key in all_keys:
            valueA = dictA.get(key, None)
            valueB = dictB.get(key, None)
            # Consider a missing value in dictA to be equivalent to /any/ value in dictB
            # (see comment above)
            if valueA is None:
                continue

            # Normalize values for comparison
            normA = normalize_value(valueA)
            normB = normalize_value(valueB)

            if normA != normB:
                return False

        return True
if __name__=='__main__':
    main()
