const topic = root_topic;
const client = mqtt.connect(mqtt_url, mqtt_auth);
// EventEmitter class gives a warning if > 11 listeners are on an event, and we do one for each variable 
// in MQTTCameras and MQTTPositions, so we need to up the limit a lot. 
client.setMaxListeners(1000) // Rough estimate, increase if needed.

const cameras = new MQTTCameras(client, `${topic}/cameras`);
const positions = new MQTTPositions(client, `${topic}/positions`);
selectedCameras = [];
selectedPositions = [];
simulatorPositions = {};

single_selection_mode = true;

function sendMQTTCommand(topic, message) {
   message['metadata'] = { 'timestamp': Date.now()/1000 };
   client.publish(topic, JSON.stringify(message));
}

function cameraCommand(command_name, parameters) {
   const message = { command: command_name, params: parameters };
   sendMQTTCommand(`${root_topic}/commands/camera`, message);
}

function OBSCommand(command_name, parameters) {
   const message = { command: command_name, params: parameters };
   sendMQTTCommand(i`${root_topic}/obs/command`, message);
}

function formatTime(isoString) {
   const date = new Date(isoString);
   return date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function olderThan(isoString, seconds) {
   const date = new Date(isoString);
   const now = new Date();

   const diffInMs = now - date;
   const diffInSeconds = diffInMs / 1000;

   return diffInSeconds > seconds;
}

/////////////////////////////////////////////////////////////////////
// UI SELECTIONS
//
function executeSelection() {
   // If there's a camera and a position both selected that means put the camera in the position.
   if ((selectedCameras.length == 1) && (selectedPositions.length == 1)) {
      requestCameraInPosition(selectedCameras[0], selectedPositions[0]);
      clearAllSelections();
   }
}

function clearAllSelections() {
   clearSelections(cameras, selectedCameras);
   clearSelections(positions, selectedPositions);
   clearSimulatorSelections();
}

function clearSimulatorSelections() {
   Object.values(simulatorPositions).forEach(s => {
      s.removeOverlay('selected');
   });
}

function clearSelections(objects, selectedList) {
   for (name of selectedList) {
      objects.getByName(name).rotator.removeOverlay('selected');
   }
   selectedList.length = 0;
}

function toggleSelected(objects, selectedList, name) {
   // console.log(`Toggle selection for ${name}`);

   const idx = selectedList.indexOf(name);
   if (idx !== -1) {
      objects.getByName(name).rotator.removeOverlay('selected');
      selectedList.splice(idx, 1);
   } else {
      if(single_selection_mode) clearSelections(objects, selectedList);
      objects.getByName(name).rotator.addOverlay('selected', 'img/selected.png');
      selectedList.push(name);
   }
   executeSelection();
   updateAllUI();
   updateSimulatorSelection();
}

function updateSimulatorSelection() {
   Object.entries(simulatorPositions).forEach(([name, rotator]) => {
      if(selectedPositions.includes(name)) {
         rotator.addOverlay('selected', 'img/selected.png');
      } else {
         rotator.removeOverlay('selected');
      }
   });
}

function updateAllUI() {
   updatePositionActionButtons();
   updateCameraActionButtons();
   updatePTZUI();
}

///////////////////////////////////////////////////////////////////////////
// PTZ UI
//
function updatePTZUI() {
   label = document.getElementById('ptz-controls');
   label.innerHTML = 'PTZ:';
   label.classList.add('ptz-controls');

   if(selectedCameras.length != 1) {
      label.style.display = 'none';
      return
   }
   
   camera_name = camera_name;
   camera = cameras.getByName(camera_name);

   if(camera.prior_ptz_positions === null) {
      camera.prior_ptz_positions = [];
   }
   if(camera.known_ptz_positions == null) {
      camera.known_ptz_positions = {};
   }
   if ((!camera.prior_ptz_positions.length) && (Object.keys(camera.known_ptz_positions).length === 0)) {
    label.style.display = 'none';
    return;
   }

   label.style.display='block';

   // Create position buttons
   const ptzGroup = document.createElement('div');
   ptzGroup.classList.add("ptz-positions-container");
   for (const [ptzname, coords] of Object.entries(camera.known_ptz_positions)) {
      const ptzButton = document.createElement('button');
      ptzButton.classList.add('button');
      ptzButton.textContent = ptzname;
      ptzButton.onclick = () => gotoPTZName(camera_name, ptzname);
      ptzGroup.appendChild(ptzButton);

   }

   // Create "BACK" button
   if (camera.prior_ptz_positions.length > 0) {
      const backButton = document.createElement('button');
      backButton.classList.add('button');
      backButton.textContent = 'go back';
      backButton.onclick = () => gotoPTZBack(camera_name);
      ptzGroup.appendChild(backButton);
   }
   label.appendChild(ptzGroup);
}

function get_coords_by_name(camera_name, position_name) {
   return cameras.getByName(camera_name).known_ptz_positions[position_name]
}

function gotoPTZName(camera_name, position_name) {
   cameraCommand('goto_absolute_coords', { 'camera_name': camera_name, 'coords': get_coords_by_name(camera_name, position_name) })
}

function gotoPTZBack(camera_name) {
   camera = cameras.getByName(camera_name)
   coords = camera.prior_ptz_positions.pop();
   camera.prior_ptz_positions = camera.prior_ptz_positions; // Force a publish
   cameraCommand('goto_absolute_coords', { 'camera_name': camera_name, 'coords': coords });
   updatePTZUI();
}



///////////////////////////////////////////////////////////////////////////////
// POSITION UI
//
function updatePositionActionButtons() {
   const buttonContainer = document.getElementById('position-controls');
   if(selectedPositions.length == 0) {
      buttonContainer.style.display = 'none';
      return;
   }
   buttonContainer.style.display = 'block';

   const position_name = selectedPositions[0];
   const label = document.getElementById('position-label');
   label.innerText = position_name;

   const lockPositionButton = document.getElementById('lockPosition');
   position = positions.getByName(position_name);
   lockPositionButton.innerText = positions.positionIsLocked(position_name) ? `${position['lock_level'].toUpperCase()} LOCKED` : 'UNLOCKED';
}

function togglePositionLock() {
   if(selectedPositions.length != 1) {
      console.log(`But that's unpossible!`);
      return
   }
   position_name = selectedPositions[0];
   position = positions.getByName(position_name);
   if(positions.positionIsLocked(position_name)) {
      position['locked_until'] = 0; // Super unlocked
   } else {
      position['locked_until'] = -1; // Locked forever
   }
   updatePositionActionButtons();
}

function updateLockedPositionUI(position) {
   console.log(`Updating lock UI for ${position['name']}.`);
   let unixTimeNow = Date.now() / 1000;
      simposition = simulatorPositions[position['name']];
   if(positions.positionIsLocked(position['name'])) {
      position.rotator.addOverlay('locked', 'img/lock.png');
      simposition.addOverlay('locked', 'img/lock.png');
      // We don't get notified when the unlock time is passed, so we want to
      // handle it ourselves. 
      if (position['locked_until'] > unixTimeNow) {
         let timeout = position['locked_until'] - unixTimeNow;
         console.log(`${position['name']} locked for ${timeout} seconds`);
         position.locktimeout = setTimeout(() => {
            position.rotator.removeOverlay('locked');
            simposition.removeOverlay('locked');
            console.log(`${position['name']} unlocked`);
            updatePositionActionButtons();
         }, timeout * 1000);
      }
      updatePositionActionButtons();
   } else {
      if(position.locktimeout) {
         clearTimeout(position.locktimeout);
         position.locktimeout = null;
      }
      position.rotator.removeOverlay('locked');
      simposition.removeOverlay('locked');
      updatePositionActionButtons();
   }
}

function updatePositionLabels() {
   cams_to_update = {};
   for (position of positions) {
      // console.log(`Labeling ${position['active']} in ${position['name']}.`);
      if(position['active'] in cams_to_update) {
         cams_to_update[position['active']].push(position['name']);
      } else {
         cams_to_update[position['active']] = [position['name']];
      }
      position.rotator.updateLabel(2, position['active']);
   }
   for (camera of cameras) {
      if (camera['name'] in cams_to_update) {
         camera.rotator.updateLabel(2, cams_to_update[camera['name']].join(','));
         camera.rotator.addOverlay('active', 'img/active.png');
      } else {
         camera.rotator.updateLabel(2, '');
         camera.rotator.removeOverlay('active');
      }
   }
}


////////////////////////////////////////////////////////////////////////////
// CAMERA UI
//
function updateCameraActionButtons() {
   const buttonContainer = document.getElementById('camera-controls');
   if(selectedCameras.length == 0) {
      buttonContainer.style.display = 'none';
      return;
   } else if (selectedCameras.length > 1) {
      console.log('Too many cameras selected for UI assumptions.');
      buttonContainer.style.display = 'none';
      return;
   }
   buttonContainer.style.display = 'block';
   buttonContainer.innerHTML = '';

   camera_name = selectedCameras[0];
   camera = cameras.getByName(camera_name);

   let label = document.createElement('div');
   label.classList.add('action-label');
   label.innerText = camera_name;
   buttonContainer.append(label);

   // Private/Public
   let button = document.createElement('button');
   button.classList.add('button')
   button.textContent = camera.ispublic ? 'PUBLIC' : 'PRIVATE';
   button.onclick = () => toggleCameraPublic(camera_name);
   buttonContainer.append(button);

   // Hidden/Visible
   button = document.createElement('button');
   button.classList.add('button')
   button.textContent = camera.ishidden ? 'HIDDEN' : 'VISIBLE';
   button.onclick = () => toggleCameraHidden(camera_name);
   buttonContainer.append(button);

   // Audio/None
   button = document.createElement('button');
   button.classList.add('button')
   button.textContent = camera.noaudio ? 'NO AUDIO' : 'AUDIO OK';
   button.onclick = () => toggleCameraAudio(camera_name);
   buttonContainer.append(button);

   // PTZ Lock
   button = document.createElement('button');
   button.classList.add('button');
   button.textContent = (camera.ptz_locked == 'root') ? 'PTZ Locked' : 'PTZ Unlocked';
   button.onclick = () => toggleCameraPTZLocked(camera_name);
   buttonContainer.append(button);

}

function toggleCameraPublic(camera_name) {
   camera = cameras.getByName(camera_name);
   camera.ispublic = !camera.ispublic;
   updateCameraActionButtons();
}

function toggleCameraHidden(camera_name) {
   camera = cameras.getByName(camera_name);
   camera.ishidden = !camera.ishidden;
   updateCameraActionButtons();
}

function toggleCameraAudio(camera_name) {
   camera = cameras.getByName(camera_name);
   camera.noaudio = !camera.noaudio;
   updateCameraActionButtons();
}

function toggleCameraPTZLocked(camera_name) {
   camera = cameras.getByName(camera_name);
   if(camera.ptz_locked) {
      camera.ptz_locked = ''
   } else {
      camera.ptz_locked = 'root'
   }
   updateCameraActionButtons();
}


////////////////////////////////////////////////////////////////////
// MOBILE
//
//   
// TODO: Change this to detect whether we're running inside the WebView/app
function isMobile() {
   return /Mobi|Android/i.test(navigator.userAgent);
}

function updateMobileButtons() {
   if(! isMobile()) {
      document.getElementById('mobile-buttons').style.display = 'none';
      // console.log("Not mobile.");
      return;
   }
   document.getElementById('mobile-buttons').style.display = 'block';
}


function openTinyCamButtonClicked() {
   if(selectedCameras.length == 1) {
      launchTinyCam(selectedCameras[0]);
   } else {
      console.log(`Can't do tinycam, onyl one camera needs to be selected.`);
   }
}

function launchTinyCam(camname) {
   AndroidInterface.setCameraName(camname);
   console.log(`Opening TinyCam for ${camname}`);
   window.location.href = "myapp://launch";
}

/////////////////////////////////////////////////////////////////////
// TROL ACTIONS
//
function requestCameraInPosition(camera_name, position_name) {
   console.log(`Requesting ${camera_name} in ${position_name}`);
   position = positions.getByName(position_name);
   position['requested'] = camera_name;
   // Lock the position for root_camlock seconds so admins/voters don't step on changes.
   let unixTimeNow = Date.now() / 1000;
   let unlock_time = unixTimeNow + 20.0;
   // TODO: Should be from settings config.yaml "root_camlock_duration"
   positions.lockPosition(position_name, 'root', 20.0);
   updateLockedPositionUI(position);
}


/////////////////////////////////////////////////////////////////////
// CAMERA UI
//
function updateVisibilityLabel(camera) { 
   let label = '';
   if(camera.ispublic) {
      if(camera.ishidden) {
         label = 'HIDDEN';
      } else {
         label = 'PUBLIC';
      }
   } else {
      label = 'PRIVATE';
   }
   camera.rotator.updateLabel(3, label);
}


////////////////////////////////////////////////////////////////////
// INITIALIZATION
//
function initializeSimulator(viewElementID,audioElementID) {
   // Init simulator
   // TODO: This should be set by scene... once we implement those.
   // TODO: In the same vein, these shouldn't be hardcoded.
   console.log("Initialize Simulator");
   for (let position_name of ['TROL TR', 'TROL TL', 'TROL B']) {
      if(simulatorPositions[position_name]) {
         console.log(`Simulator position ${position_name} already exists, skipping...`);
         continue
      }
      const streamviewContainer = document.getElementById(viewElementID);
      const rotator = new ImageRotator(
         ['img/static.jpg'], // Screenshots
         ['','','',''], // Labels
         {},         // Overlays
         1000,       // switchInterval
         5,          // maxImages
         240, 135,   // resolution
         () => toggleSelected(positions, selectedPositions, position_name)
      );
      rotator.container.className = 'streamview-image-container';
      rotator.container.classList.add(`streamview-${position_name.replace(' ', '-').toLowerCase()}`);
      simulatorPositions[position_name] = rotator;
      streamviewContainer.appendChild(rotator.container);
      //console.log(`Created simulator position ${position_name}`);
   }
   for (let position_name of ['TROL A1', 'TROL A2']) {
      if(simulatorPositions[position_name]) {
         console.log(`Simulator position ${position_name} already exists, skipping...`);
         continue
      }
      const streamaudioContainer = document.getElementById(audioElementID);
      const rotator = new ImageRotator(
         ['img/static.jpg'], // Screenshots
         ['','','',''], // Labels
         {'audioicon': 'img/audio.png'},  // Overlays
         1000,       // switchInterval
         5,          // maxImages
         240, 135,   // resolution
         () => toggleSelected(positions, selectedPositions, position_name)
      );
      rotator.container.className = 'streamaudio-image-container';
      rotator.container.classList.add(`streamaudio-${position_name.replace(' ', '-').toLowerCase()}`);
      simulatorPositions[position_name] = rotator;
      streamaudioContainer.appendChild(rotator.container);
      //console.log(`Created simulator position ${position_name}`);
   }

}


function initializeCameras(elementID) {
   // Init Cameras
   cameras.addListChangedCallback( () => { 
      console.log('Camera list changed, re-initialize cameras.');
      const imageGallery = document.getElementById(elementID);
      // Clear existing contents
      while (imageGallery.firstChild) {
         imageGallery.removeChild(imageGallery.firstChild);
      }
      for (let camera of cameras) {
         const rotator = new ImageRotator(
            ['img/static.jpg'], // Screenshots
            [camera['name'],'','',camera['ispublic']?'PUBLIC':''], // Labels
            {},         // Overlays
            1000,       // switchInterval
            5,          // maxImages
            240, 135,   // resolution
            () => toggleSelected(cameras, selectedCameras, camera['name']) // clickHandler
         );
         camera.rotator = rotator;
         camera.addCallback('screenshot', () => {
            screenshot = camera.getAttribute('screenshot');
            if(screenshot.trim() === '') {
               console.log(`Got blank (error) screenshot for ${camera['name']}.`);
            } else {
               if(rotator.imageArray[0] == 'img/static.jpg') {
                  // We have a real screenshot so let's remove the static default.
                  rotator.removeAllImages();
               }
               rotator.addImage(camera.getAttribute('screenshot')); 
            }
         });
         camera.addCallback('noaudio', () => {
            updateCameraActionButtons();
         });
         camera.addCallback('last_screenshot_timestamp', () => {
            // console.log(`screenshot timestamp for ${camera.name} is {camera.last_screenshot_timestamp}`);
            camera.rotator.updateLabel(1, formatTime(camera.last_screenshot_timestamp));
            if(camera.unresponsiveTimeout) {
               //console.log("Clearing timeout")
               clearTimeout(camera.unresponsiveTimeout);
            }
            if(olderThan(camera.getAttribute('last_screenshot_timestamp'), 30)) {
               console.log(`${camera['name']} unresponsive.`)
               camera.rotator.addOverlay('unresponsive', 'img/unresponsive.png');
            } else {
               camera.rotator.removeOverlay('unresponsive');
               camera.unresponsiveTimeout = setTimeout(() => {
                  console.log(`${camera['name']} unresponsive.`)
                  camera.rotator.addOverlay('unresponsive', 'img/unresponsive.png');
               }, 30 * 1000);
            }
         });
         camera.unresponsiveTimeout = setTimeout(() => {
            // We check here instead of not even setting the timeout because
            // the value of nothumb doesn't exist during init.
            if(!camera.nothumb) {
               console.log(`${camera['name']} unresponsive.`)
               camera.rotator.addOverlay('unresponsive', 'img/unresponsive.png');
            }
         }, 30 * 1000);

         camera.addCallback('ispublic', () => { updateVisibilityLabel(camera); updateCameraActionButtons(); });
         camera.addCallback('ishidden', () => { updateVisibilityLabel(camera); updateCameraActionButtons(); });
         camera.addCallback('prior_ptz_positions', () => { updatePTZUI(); });
         camera.addCallback('known_ptz_positions', () => { updatePTZUI(); });
         camera.addCallback('ptz_locked', () => { updatePTZUI(); });

         imageGallery.appendChild(rotator.container);
         console.log(`Initialized camera ${camera['name']}`);

      }
   });
}

function initializePositions(elementID) {
   // Init Positions
   positions.addListChangedCallback( () => {
      const positionGallery = document.getElementById(elementID);
      console.log(`Position list changed, re-initialize positions.`);
      while (positionGallery.firstChild) {
         positionGallery.removeChild(positionGallery.firstChild); 
      }
      for (let position of positions) {
         const rotator = new ImageRotator(
            ['img/static.jpg'],
            [position['name'],'','',''], 
            {}, 
            1000, 
            5, 
            240, 135, 
            () => toggleSelected(positions, selectedPositions, position['name'])
         );
         position.rotator = rotator;
         // Callback for when a new camera is placed in a position.
         position.addCallback('active', () => {
            // console.log(`Active camera in position ${position['name']} changed to ${position['active']}`);
            // Point the position's imageArray at the camera's imageArray so we share the same images.
            active_camera = cameras.getByName(position['active']);
            if(active_camera === null) {
               console.log(`Attempting to set active camera to a camera we don't know: ${position['active']}`);
            } else {
               // updateImages takes a reference so now they will have the same images in perpetuity.
               position.rotator.updateImages(active_camera.rotator.imageArray);
            }
            updatePositionLabels();
            // Point the simulation's imageArray at the camera's.
            if(position['name'] in simulatorPositions) {
               // console.log(`Updating simulator position ${position['name']}`);
               simulatorPositions[position['name']].updateImages(active_camera.rotator.imageArray);
            } else {
               console.log(`Not updating simulator position ${position['name']} not in ${simulatorPositions}`);
            }
         });
         // Callback for when a position is locked, preventing changes from voting or (sometimes) admins
         position.addCallback('locked_until', () => {
            console.log(`Got changed lock for ${position['name']}`);
            updateLockedPositionUI(position);
         });

         positionGallery.appendChild(rotator.container);
         console.log(`Initialized position ${position['name']}`);
      }
   });
}

async function initialize() {
   initializeSimulator('streamview-container', 'streamaudio-container');
   initializeCameras('camera-list');
   initializePositions('position-list');
   await waitForInitialMessages(client);

   // Defined in another script, called from here for responsiveness.
   scaleImages();

   // Create the initial UI state
   clearAllSelections();
   updateAllUI();
   // updateMobileButtons only called at startup right now.
   updateMobileButtons();

   console.log("Initialization completed.");
}

async function deleteAllScreenshots() {
   // For testing purposes
   for(c of cameras)
      c.rotator.removeAllImages();
   // positions and simulator only hold references to camera image arrays.  So in theory the below is no logner needed.
   /* for(p of positions)
      p.rotator.updateImages([]);
   Object.values(simulatorPositions).forEach(value => {
      value.updateImages([]) 
   }); */
}
//document.addEventListener('click', deleteAllScreenshots);


client.on('connect', async function() {
   console.log("Connected.")
   initialize();
});

client.on('error', function(err) {
   console.error('Connection error:', err);
});

