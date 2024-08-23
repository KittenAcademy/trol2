# TROL v2
A complete rewrite of the KA-control system for managing a live stream consisting of multiple IP camera feeds.  

## Features

- A "control-room" display of a large number of webcams
- Ability to select which camera(s) are live on the stream in real-time
- Separate cameras/microphones for audio and video (i.e. you don't need to be hearing what the camera you're seeing or seeing the ones you're hearing)
- Access control - allow some users to only know about some subset of the cameras
- Full PTZ control -- go beyond just choosing cameras, you can reposition them as well
- Recording and transcoding the entire stream or only certain cameras
- Automatically cut in to the live stream from a phone camera or other device for easily streaming things happening right in front of you
- On-stream scrolling news feed
- Selecting cameras from discord polls; crowdsource your streaming controls
- Android Client
- Javascript/Web Client
- Discord Bot
- CLI interface(s)
- Full support for containerizing components with Docker

## Prerequisites

### Required
- An MQTT server (we use [Mosquitto MQTT](https://github.com/eclipse/mosquitto))
- [OBS Studio ](https://github.com/obsproject/obs-studio)

### Optional

- HTTP Server to serve the JS client (we use [nginx](https://hg.nginx.org/nginx/))
- [Discord bot token](https://discord.com/developers/docs/topics/oauth2#bot-users) to use the Discord comoponent[^1]
- Docker or other container-type-thing (we use [Docker Swarm](https://docs.docker.com/engine/swarm/))

[^1]: TODO: put in a better link
 

## Configuration and Installation
### Notes
Throughout the provided configuration examples you will find many references to /home/chris/KA/src/trol2/.  This is the 
root directory of this repository in our test system, so replace that with wherever you have this code.  (We plan to clean this
up in due time:tm:)

### Install OBS-Studio:
```
# Install
flatpak update && flatpak install com.obsproject.Studio
# Run it
flatpak run com.obsproject.Studio
```
- Configure the streaming options under File->Settings, keeping in mind that there are places in the trol code/sample config that 
assume a Video->Canvas Resolution of 3840x2160.
- Configure the OBS Websocket interface Tools->Websocket Server Settings.  This needs to be enabled and accessable for trol.
- == IF YOU ALREADY USE OBS BACK UP YOUR SCENES; TROL MAY OVERWRITE THEM ==

### Install and configure your MQTT server:
This is beyond the scope of this document, but some hints:
- We use the [Eclipse Mosquitto Docker Image](https://hub.docker.com/_/eclipse-mosquitto)
- In the Mosquitto config, make sure you set `use_username_as_clientid false`
- You will want to configure the MQTT instance to support MQTT Websockets as well as the standard API

### Install trol locally so you can use the CLI for configuation of components:
```
# Create a Python virtual environment so we don't pollute your system
python -m venv venv
# Activate it (do this every time you want to run a trol command)
source venv/bin/activate
# Install python requirements
pip install -r ./requirements.txt
# (optional, useful for debugging) Install our version of [obs-websocket-py](https://github.com/KittenAcademy/obs-websocket-py)
pip uninstall obs-websocket-py
git clone https://github.com/KittenAcademy/obs-websocket-py
pip install ./obs-websocket-py
# Install trol (-e for 'editable' so changes you make to source code are immediately accessable to you)
pip install -e .
```

### Configure trol for your use:
Most of the executables in trol all use the same configuration file; it's critical that you have this set up or almost nothing will work.
You can put it where you like but the default throughout is ./config.yaml
```
# Copy the sample config and edit it as needed:
# the path ./config.yaml is the default in many places
cp ./config/sample-config.yaml ./config.yaml
```
There are comments in the default config to explain the options as well as we can.

### Create the initial cameras and positions:
Cameras are just what you think, IP-based webcameras.  "Positions" are basically the same as "Sources" in OBS; it's a place in OBS where we can put a camera feed.

To setup your cameras, make copies of config/sample-camera.yaml and edit to suit, then "load" them into MQTT using `trol-setup-camera --config=./config.yaml --camerafile=sample_camera.yaml` and if you need to delete a camera the command is: `trol-setup-camera --config=./config.yaml --camerafile=sample_camera.yaml --delete`

You can also use trol-setup-camera to update an existing camera; the setting sin the yaml will overwrite the settings on an existing camera.

To setup your positions, you have options:

#### Option 1 -- Use the Kitten Academy setup:

- Edit config/obs-scene.yaml, specifically find the instances of "/home/chris/KA/src" and replace them with the appropriate
locations for your setup.  Make sure you have obs.scene_yaml_file set to config/obs-scene.yaml in your config.
- "Load" the position data into mqtt as for the cameras:  `trol-setup-position --config=./config.yaml --positionfile="config/positions/TROL A1.yaml"` and repeat 
for each position.  As for cameras, the --delete flag will reverse the operation.  As for cameras, you can use the same command to update an existing position.
- The obs.scene_yaml_file data is largely redundant with the individual position files, and will overwrite anything you have in OBS when you start the trol-obs-interface (see below)
- (optional) Import the scene into your OBS: `trol-setup-obs --config ./config.yaml --create config/obs-scene.yaml`

#### Option 2 -- DIY:

1. Set up your scene in OBS.
2. You may want to include web sources for obs/clock.html and obs/scroll/scroll.html which provide the clock and news scroll respectively.  These are not 'positions'
for trol's purposes, but should be included in the obs-scene.yaml below.
3. Export your scene to a yaml file using: `trol-setup-obs --config=./config.yaml > obs-scene.yaml`
4. Edit the resulting yaml and remove all keys named "inputUuid" and "sceneItemId".  If you have URLs for your cameras in inputSettings.input, delete the input keys
or else trol will end up putting those cameras in place every time the file is used instead of putting in the cameras that should be there.
5. Make sure obs.scene_yaml_file points at this file in your config.
6. Using the format of the files in config/positions as a guide, create your own individual position.yaml files and load them into mqtt: `trol-setup-position --config=./config.yaml --positionfile="config/positions/position.yaml`

### Javascript/Android client

Copy the sample config and edit it to suit:  
```
cp jsclient/sample-mqtt-auth.js jsclient/mqtt-auth.js
```

### News scroll
Similarly, the news scroll uses its own copy of mqtt-auth.js:
``` 
cp obs/scroll/sample-mqtt-auth.js obs/scroll/mqtt-auth.js
```
Edit to suit.

## Running trol

### Notes: 
All the executables expect your configuration to be ./config.yaml and can take a --config parameter to specify otherwise.

### trol-obs-interface
This executable connects to your running OBS instance and does all the work of controlling it.  Without this part running, nothing will work.  
A useful option is --auto-start which will immediately start streaming if you aren't already.

### trol-bot
This executable runs the Discord bot.  You'll need to have configured your bot token by creating a bot in Discord and getting a token there.  That process is 
beyond the scope of this document.  

### trol-screenshot
Trol will expect you to run one instance of this for each camera; it's what monitors the camera feed and provides regular snapshots of what the camera sees, 
used throughout the trol system.  You will need to specify --camera $CAMERA_NAME for each instance, the rest is optional.  

### trol-newsrunner
Used to display the scrolling news on the stream.  

### trol-handleptz
This is used to (you guessed it) handle all the PTZ commands for cameras.  In order to function, it requires ONVIF be enable and accessable on the 
camera, using the same username and password configured elsewhere.

### trol-autocam
Entirely optional system for automatically putting a camera on the stream whenever the camera is online.  We use this with 
[IP Webcam Pro](https://play.google.com/store/apps/details?id=com.pas.webcam.pro) to automatically stream "micro close-ups" whenever the app's server is active.

### Javascript Client
The functions of trol which are reserved for 'root' such as setting the cameras public/private are only accessable from the commandline or the js client/android client.
You can load jsclient/trol2.html in a browser as a local file, or you can set up your own webserver to make it accessable to yourself.  ==DO NOT== allow public access
to the javascript, as the trol system assumes anyone who sues the javascript is internal and has 'root' access.  

The jsclient has its own settings you must supply, mqtt-auth.js contains the credentials for reaching your mqtt server and must be configured.  See above.

### Android Client
The Android client is just a few extra things on top of a WebView that uses the jsclient, so everything that applies to the jsclient applies to Android.  This means
that if you allow anyone access to the android client, they will have full 'root' control of your trol system.  So don't do that.  You may want to install 
[tinyCam Monitor Pro](https://play.google.com/store/apps/details?id=com.alexvas.dvr.pro) since the Android client will automatically launch it to control cameras, but it's optional.

### Other useful stuff:

#### More Command-line utilities:

* trol-setup-camera for importing/updating/deleting camera configuration.
* trol-setup-position for importing/updating/deleting position configuration.
* trol-onvif for some useful camera commands (e.g. --get-rtsp-url if you don't know your camera's RTSP stream URL.)
* trol-mqtt provides useful utilities for managing MQTT topics directly, in case you want to see what messages are being passed around, or to manually set/delete a 
topic.  Especially useful is --action=dump to print YAML containing all the retained messages under a given topic, so if you have an existing trol setup but are worried your config files are out-of-date you can pull the current data from MQTT.  
* trol-settings contains useful utilities for manipulating settings files in yaml and json generally.  The Discord bot can currently take live updates to 
its settings while it is running if the config.yaml or a subset thereof is published to mqtt_root/settings, which is useful as the only way to modify
some options without changing the settings file and restarting the bot.
* trol-filemover is just a utility for taking files from one place and putting them in another -- many such utilities exist elsewhere and are probably better.
* trol-microformat uses ffmpeg to assemble a "micro close-up" video for upload to YouTube.  It works by being given the same quadrant used by the autocam system
and being pointed at the directory where OBS dumps its video recordings.

#### Further documentation:

* mqtt-topics.txt provides a list of all the MQTT topics trol uses.

## Compiling the Android Client:

If you have the Android SDK appropriately set up in your environment, then android/quickinstall.sh should do the job of compiling the Android client and, if you
have your phone connected via adb before running quickinstall.sh, it will also install the apk automatically.  See the warning above about sharing the Android Client.

NOTE: There's a few URLs and paths hardcoded in the android client that you may want to change. Check `android/app/src/main/res/xml/network_security_config.xml` for
the settings that allow some domains to be used for insecure websockets.  You'll want to put your MQTT server in here, unless you have set up TLS.

## Using Docker:

### Making the containers:
You can build all of the trol Docker containers using the make_containers.sh script in the root project directory.  It takes parameters for your local
Docker registry (if any) and which container to build (defaults to building all of them):
```
# This will build containers for everything, named "registry.myorg.com/trol_obs:YYYY-MM-DD" and also tagged 'latest':
./make_containers.sh registry.myorg.com
```
== SUPER IMPORTANT== If you supply a registry the containers will be pushed there by the script.  ==DO NOT SHARE THESE CONTAINERS PUBLICALLY== they will contain
everything under the project root, including (most likely) your precious configuration and private stuff.  So keep them private.

### Running the containers:
Each container is basically just an installed copr of the trol project and the ENTRYPOINT is the respective command-line utility as above.  So running them 
is simple.  However, we've also provided a utility to create a docker-compose.yaml suitable for deploying the entire thing as a set of services or a stack:

```
# Make the docker-compose.yaml
python docker/create_services.py --registry registry.myorg.com \
                                 --cameras "cam1,cam2,cam3" \
                                 --imageversion "YYYY-MM-DD" \
                                 --configname "trol2config-YYYY-MM-DD"
# Note: The config file must be created by you seperately:
docker config create trol2config-YYYY-MM-DD ./config.yaml
# Deploy as stack:
docker stack deploy -c ./docker-compose.yaml trol2
# Remove stack:
# docker stack rm trol2
# Run services in current shell for testing
# docker compose up
# Or detached
# docker compose up -d
```

## Contributing:
I'm as bad about logging into my github as everything else, but I do appreciate help, so... send me a pull request as you like.  It's assumed if you do you're
OK with me publishing your contributions under the same terms as the rest.

