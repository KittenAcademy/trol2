from typing import Tuple, Type
from trol.shared.MQTT import MQTTConnectionManager
from trol.shared.MQTTObject import MQTTObjectList, MQTTObject
from trol.shared.logger import setup_logger
log = setup_logger(__name__)

_CAMERA_ATTRIBUTES_: Tuple[Tuple[str, Type]] = (
            ("type", str),
            ("nice_name", str),
            ("address", str),
            ("rtspurl", str),
            ("jpgurl", str),
            ("pingurl", str),
            ("audiourl", str),
            ("ispublic", bool),
            ("nothumb", bool),
            ("noaudio", bool),
            ("ishidden", bool),
            ("failure_count", int),
            ("last_screenshot_timestamp", str),
            ("ptz_locked", str),
            ("ptz_arrived", dict),
            ("prior_ptz_positions", list),
            ("known_ptz_positions", list)
        )

class MQTTCamera(MQTTObject):
    def __init__(self, mqtt_manager: MQTTConnectionManager, topic: str, name: str):
        super().__init__(mqtt_manager, topic, name, _CAMERA_ATTRIBUTES_)

    def lockPTZ(self, lock_level='Discord user'):
        """ Really the only lock_level with any meaning here is 'root' """
        if self.isPTZLocked(lock_level):
            log.debug(f"Camera already locked.")
            return
        if lock_level == 'Discord user':
            log.debug(f"Discord user can't lock.")
            raise ValueError("'Discord user' cannot apply a lock.")
        self.ptz_locked = lock_level

    def isPTZLocked(self, lock_level='Discord user'):
        """ 
        Discord user can't PTZ, so our only possibility is it's locked by root and we're an admin, really.  
        If we are root, anything goes, if we are admin and it's locked by anyone other than root it doesn't apply to us.
        """
        if self.ptz_locked:
            if lock_level == 'root':
                log.debug(f"Camera locked by {self.ptz_locked} but you are root.")
                return False
            if lock_level == self.ptz_locked:
                return False
            if lock_level == 'admin' and self.ptz_locked == 'root':
                log.debug(f"Camera locked by root, you are admin.")
                return True
            log.debug(f"How did we get here?  locked by: {self.ptz_locked} our permission: {lock_level}")
            return True
        return False

class MQTTCameras(MQTTObjectList):
    def __init__(self, mqtt_manager: MQTTConnectionManager, mqtt_topic: str):
        super().__init__(mqtt_manager, mqtt_topic, 'Cameras', MQTTCamera)

    def getNameByUrl(self, search_url: str):
        for camera_name, camera in self.objects.items():
            for url in ['rtspurl', 'audiourl', 'jpgurl', 'pingurl']:
                if(camera.get(url, None) == search_url):
                    return camera_name
        return None

    # TODO: deprecated
    def lockCameraPTZ(self, camera_name, lock_level='Discord user'):
        return self.getByName(camera_name).lockPTZ(lock_level)
    def isCameraPTZLocked(self, camera_name, lock_level='Discord user'):
        return self.getByName(camera_name).isPTZLocked(lock_level)

