from typing import Tuple, Type
from time import time

from trol.shared.MQTT import MQTTConnectionManager
from trol.shared.MQTTObject import MQTTObjectList, MQTTObject
from trol.shared.logger import setup_logger
log = setup_logger(__name__)

from trol.shared.settings import get_settings

_POSITION_ATTRIBUTES_: Tuple[Tuple[str, Type]] = (
    ('active', str),
    ('requested', str),
    ('isaudio', bool),
    ('locked_until', float),
    ('lock_level', str),
    ('nice_name', str),
    ('obs_item_default', dict),
)

class MQTTPosition(MQTTObject):
    def __init__(self, mqtt_manager: MQTTConnectionManager, mqtt_topic: str, name: str):
        super().__init__(mqtt_manager, mqtt_topic, name, _POSITION_ATTRIBUTES_)

    def isLocked(self, access_level='Discord user'):
        log.debug(f"Evaluating lock status for {self._name} LU: {self.locked_until:.0f}:{self.lock_level}.")
        #if self.locked_until is None or self.locked_until == 0:
        #    log.debug("Position not locked.")
        #    return False
        if access_level == 'root':
            log.debug(f"You are root.")
            return False
        if self.locked_until < 0:
            log.debug("Position locked indefinitely.")
            return True

        timenow = time()
        seconds_until_unlock = timenow - self.locked_until
        log.debug(f"Unlock at: {self.locked_until:.0f}.  Time now: {timenow:.0f}.  Time remaining: {seconds_until_unlock:.0f}.")

        if seconds_until_unlock >= 0:
            log.debug(f"Position unlocked {seconds_until_unlock}s ago.")
            return False
        else:
            log.debug(f"Position unlocks in {abs(seconds_until_unlock)}s.")
            if access_level == 'admin' and self.lock_level == 'admin':
                log.debug(f"Position locked by admin and you are admin.")
                return False
            return True

        log.debug("This should be unreachable.")
        return True

    def lock(self, access_level='Discord user', lock_time=None):
        settings = get_settings()
        if lock_time is None:
            if access_level == 'admin':
                lock_time = settings.admin_camlock_duration
            if access_level == 'root':
                lock_time = settings.root_camlock_duration
        if lock_time is None or access_level not in ['admin', 'root']:
            log.debug(f"Not locking {self._name} because no access at level: {access_level}.")
            return

        lock_until = time() + lock_time
        if lock_time <= 0: 
            log.debug(f"Unlocking {self._name}")
            lock_until = 0
        elif self.locked_until > lock_until:
            log.debug(f"Not locking {self._name} because it's already locked for a longer duration.");
            return
        elif self.locked_until < 0:
            log.debug(f"Not locking {self._name} because it's already locked forever.");
            return
        if self.isLocked(access_level=access_level):
            # This is only True if the lock is from a higher access level.
            log.debug(f"Not locking {self._name} because it's locked for {access_level}.")
            return

        # Everything checks out, let's lock it.
        self.locked_until = lock_until
        self.lock_level = access_level
        log.debug(f"{access_level} locked {self._name} until {self.locked_until:.0f}.")

class MQTTPositions(MQTTObjectList):
    def __init__(self, mqtt_manager: MQTTConnectionManager, mqtt_topic: str):
        super().__init__(mqtt_manager, mqtt_topic, 'Positions', MQTTPosition)

    # TODO: deprecated
    def positionIsLocked(self, position_name, access_level='Discord user'):
        return self.getByName(position_name).isLocked(access_level)
    def lockPosition(self, position_name, access_level='Discord user', lock_time=None):
        return self.getByName(position_name).lock(access_level, lock_time)

