// Thanks for the help ChatGPT.
//    as they used to say, "dictated but not read."

class MQTTVariable {
   constructor(mqttClient, topic, valueType = 'string', initialValue = null, callback = null) {
      this._mqttClient = mqttClient;
      this._topic = topic;
      this._valueType = valueType;
      this._value = initialValue;
      this._callback = callback;

      // Subscribe to the MQTT topic
      this._mqttClient.subscribe(this._topic, (err) => {
         if (!err) {
            // console.log(`Subscribed to ${this._topic}`);
            ;
         } else {
            console.error(`Failed to subscribe to ${this._topic}: ${err}`);
         }
      });


      // Listen for messages on the topic
      this._mqttClient.on('message', (topic, message) => {
         if (topic === this._topic) {
            this._onMessage(message.toString());
         }
      });
   }

   get value() {
      return this._value;
   }

   set value(newValue) {
      this._value = newValue;
      this._publish(newValue);
   }

   _publish(value) {
      let payload;
      if (typeof value === 'object') {
         payload = JSON.stringify(value);
      } else {
         payload = String(value);
      }
      this._mqttClient.publish(this._topic, payload, {retain: true});
   }

   addCallback(callback) {
      this._callback = callback;
   }

   _onMessage(message) {
      try {
         switch (this._valueType) {
            case 'int':
               this._value = parseInt(message, 10);
               break;
            case 'float':
               this._value = parseFloat(message);
               break;
            case 'boolean':
               this._value = message.toLowerCase() === 'true' || message === '1';
               break;
            case 'object':
               this._value = JSON.parse(message);
               break;
            default:
               this._value = message;
         }
      } catch (e) {
         console.error(`Error converting message: ${e}`);
         this._value = message;
      }
      if (this._callback) {
         try {
            this._callback();
         } catch (e) {
            console.error(`Ignoring error in ${this._topic} callback: ${e}`);
         }
      }
   }
}

class MQTTObject {
   constructor(mqttClient, rootTopic, name, mqttVars) {
      this._mqttClient = mqttClient;
      this._rootTopic = rootTopic;
      this.name = name;
      this._mqttVars = mqttVars;
      this._data = {};

      for (const [key, type] of mqttVars) {
         this._data[key] = new MQTTVariable(this._mqttClient, `${this._rootTopic}/${key}`, type);
      }
      
      return new Proxy(this, {
         get: (target, prop) => {
            if (prop in target._data) {
               return target._data[prop].value;
            }
            return target[prop];
         },
         set: (target, prop, value) => {
            if (prop in target._data) {
               target._data[prop].value = value;
               return true;
            }
            target[prop] = value;
            return true;
         },
         deleteProperty: (target, prop) => {
            if (prop in target._data) {
               delete target._data[prop];
               return true;
            }
            delete target[prop];
            return true;
         },
         ownKeys: (target) => {
            return Reflect.ownKeys(target).concat(Reflect.ownKeys(target._data));
         },
         getOwnPropertyDescriptor: (target, prop) => {
            if (prop in target._data) {
               return {
                  configurable: true,
                  enumerable: true,
                  value: target._data[prop].value,
                  writable: true
               };
            }
            return Object.getOwnPropertyDescriptor(target, prop);
         }
      });

   }

   addCallback(attributeName, callback) {
      if (this._data[attributeName]) {
         this._data[attributeName].addCallback(callback);
      } else {
         throw new Error(`Attribute '${attributeName}' not found in MQTTObject`);
      }
   }

   getAttribute(name) {
      if (name in this._data) {
         return this._data[name].value;
      } else {
         throw new Error(`Attribute '${name}' not found in MQTTObject`);
      }
   }

   setAttribute(name, value) {
      if (name in this._data) {
         this._data[name].value = value;
      } else {
         throw new Error(`Attribute '${name}' not found in MQTTObject`);
      }
   }

   serialize() {
      const data = {};
      for (const [key, variable] of Object.entries(this._data)) {
         data[key] = variable.value;
      }
      return data;
   }

   entries() {
      return Object.entries(this._data);
   }
}

class MQTTObjList {
   constructor(mqttClient, mqttTopic, name, objectDefinition) {
      this._mqttClient = mqttClient;
      this._mqttTopic = mqttTopic;
      this.name = name;
      this._objectDefinition = objectDefinition;
      this._objects = {};
      // TODO: I guess we have a reason now to make the callbacks a list since we use it here for update
      // and we use it externally to trigger screen update.  But for now, we just have 1 client callback and 1
      // for ourselves. 
      this.client_callback = null;

      this._objlist = new MQTTVariable(this._mqttClient, this._mqttTopic, 'object', [], () => this.update());
   }

   update() {
      console.log(`${this.name} updated list: ${this._objlist.value}`);
      for (const obj of this._objlist.value) {
         if (!this.getByName(obj)) {
            this._objects[obj] = new MQTTObject(this._mqttClient, `${this._mqttTopic}/${obj}`, obj, this._objectDefinition);
         }
      }
      if (this.client_callback) {
         try {
            this.client_callback();
         } catch (e) {
            console.error(`Ignoring error in ${this._topic} callback: ${e}`);
         }
      }


   }

   addListChangedCallback(callback) {
      this.client_callback = callback;
   }

   getByName(objname) {
      return this._objects[objname] || null;
   }

   addOrGetByName(obj) {
      if (this._objects[obj]) {
         return this._objects[obj];
      }
      this._objects[obj] = new MQTTObject(this._mqttClient, `${this._mqttTopic}/${obj}`, obj, this._objectDefinition);
      this._objlist.value.push(obj);
      this._objlist._publish(this._objlist.value); // Because using push() it's not recognized as changed
      return this._objects[obj];
   }

   delByName(obj) {
      if (this._objects[obj]) {
         delete this._objects[obj];
      }
      const index = this._objlist.value.indexOf(obj);
      if (index > -1) {
         this._objlist.value.splice(index, 1);
         this._objlist._publish(this._objlist.value);  // Because using splice() it's not recognized as changed
      }
   }

   getNameByAttr(attr, attrval) {
      for (const [name, obj] of this._objects.entries()) {
         if (obj._data[attr] && obj._data[attr].value === attrval) {
            return name;
         }
      }
      return null;
   }

   getNamesByAttr(attr, attrval) {
      const names = [];
      for (const [name, obj] of this._objects.entries()) {
         if (obj._data[attr] && obj._data[attr].value === attrval) {
            names.push(name);
         }
      }
      return names;
   }

   *[Symbol.iterator]() {
      yield* Object.values(this._objects);
   }

   get items() {
      return Object.entries(this._objects);
   }

   get keys() {
      return Object.keys(this._objects);
   }

   get values() {
      return Object.values(this._objects);
   }

   get length() {
      return Object.keys(this._objects).length;
   }

   get(objname) {
      return this._objects[objname] || null;
   }

   serialize() {
      const data = {};
      for (const [name, obj] of Object.entries(this._objects)) {
         data[name] = obj.serialize();
      }
      return data;
   }
}

class MQTTCameras extends MQTTObjList {
   constructor(mqttClient, mqttTopic) {
      const cameraParams = [
         ['type', 'string'],
         ['address', 'string'],
         ['rtspurl', 'string'],
         ['jpgurl', 'string'],
         ['pingurl', 'string'],
         ['audiourl', 'string'],
         ['ispublic', 'boolean'],
         ['ishidden', 'boolean'],
         ['nothumb', 'boolean'],
         ['noaudio', 'boolean'],
         ['screenshot', 'string'],
         ['last_screenshot_timestamp', 'string'],
         ['error_message', 'string'],
         ['prior_ptz_positions', 'object'],
         ['known_ptz_positions', 'object'],
         ['ptz_locked', 'string'],
         ['ptz_arrived', 'object']
      ];
      super(mqttClient, mqttTopic, 'Cameras', cameraParams);
   }

   getNameByUrl(url) {
      for (const [camname, camera] of Object.entries(this._objects)) {
         if (camera.getAttribute('rtspurl') === url || camera.getAttribute('audiourl') === url) {
            return camname;
         }
      }
      return null;
   }

   gotoPTZNumber(camname, number) {
      this._mqttClient.publish(`${this._mqttTopic}/${camname}/goto_ptz_number`, number, {retain: false})
   }
   gotoPTZCoords(camname, x,y,z) {
      this._mqttClient.publish(`${this._mqttTopic}/${camname}/goto_ptz_coords`, `[${x},${y},${z}]`, {retain: false})
   }


}

class MQTTPositions extends MQTTObjList {
   constructor(mqttClient, mqttTopic) {
      const positionParams = [
         ['active', 'string'],
         ['requested', 'string'],
         ['isaudio', 'boolean'],
         ['locked_until', 'float'],
         ['lock_level', 'string']
      ];
      super(mqttClient, mqttTopic, 'Positions', positionParams);
   }

   positionIsLocked(position_name, access_level='Discord user') {
      const position = this.getByName(position_name);
      if (position.locked_until === null || position.locked_until === 0) {
         console.log("Position not locked.");
         return false;
      }
      if (access_level === 'root') {
         console.log("You are root.");
         return false;
      }
      if (position.locked_until < 0) {
         console.log("Position locked indefinitely.");
         return true;
      }

      const timenow = Date.now() / 1000;
      const seconds_until_unlock = timenow - position.locked_until;
      console.log(`Unlock at: ${position.locked_until.toFixed(0)}.  Time now: ${timenow.toFixed(0)}.  Time remaining: ${seconds_until_unlock.toFixed(0)}.`);

      if (seconds_until_unlock >= 0) {
         console.log(`Position unlocked ${seconds_until_unlock}s ago.`);
         return false;
      } else {
         console.log(`Position unlocks in ${Math.abs(seconds_until_unlock)}s.`);
         if (access_level === 'admin' && position.lock_level === 'admin') {
            console.log("Position locked by admin and you are admin.");
            return false;
         }
         return true;
      }

      console.log("This should be unreachable.");
      return true;
   }

   lockPosition(position_name, access_level='Discord user', lock_time=null) {
      if (lock_time === null) {
         if (access_level === 'admin') {
            lock_time = settings.admin_camlock_duration;
         }
         if (access_level === 'root') {
            lock_time = settings.root_camlock_duration;
         }
      }
      if (lock_time === null || !['admin', 'root'].includes(access_level)) {
         console.log(`Not locking ${position_name} because no access at level: ${access_level}.`);
         return;
      }

      const position = this.getByName(position_name);
      const lock_until = Date.now() / 1000 + lock_time;
      if (position.locked_until > lock_until) {
         console.log(`Not locking ${position_name} because it's already locked for a longer duration.`);
         return;
      }
      if (position.locked_until < 0) {
         console.log(`Not locking ${position_name} because it's already locked forever.`);
         return;
      }
      if (this.positionIsLocked(position_name, access_level=access_level)) {
         // This is only True if the lock is from a higher access level.
         console.log(`Not locking ${position_name} because it's already locked for ${access_level}.`);
         return;
      }

      // Everything checks out, let's lock it.
      position.locked_until = lock_until;
      position.lock_level = access_level;
      console.log(`${access_level} locked ${position_name} until ${position.locked_until.toFixed(0)}.`);
   }
}


/* Problem: we may receive a lot of messages and never reach timeout -- especially with the screenshots. 
 * Solution: only count the first message from each given topic, subsequent messages for a topic do not reset the counter.
 */
const waitForInitialMessages = (client, timeout = 500) => {
   return new Promise((resolve) => {
      const receivedTopics = new Set();
      let timer = setTimeout(() => {
         resolve();
      }, timeout);

      client.on('message', (topic) => {
         if (!receivedTopics.has(topic)) {
            receivedTopics.add(topic);
            clearTimeout(timer);
            timer = setTimeout(() => {
               resolve();
            }, timeout);
         }
      });
   });
};

