#!/bin/bash
#
#
#  Usage: make_containers.sh <docker registry> <specific system>
#    Both parameters are optional.  
#

# Check if the registry parameter is supplied
registry=$1

# Ensure the registry ends with a '/' if it is supplied
if [ -n "$registry" ] && [[ "$registry" != */ ]]; then
  registry="${registry}/"
fi

# Get the current date in YYYY-MM-DD format
current_date=$(date +%Y-%m-%d)

# Define the system names
systemnames=("obs" "screenshot" "newsrunner" "autocam" "discord" "ptzhandler" "filemover" "microformat")

# Check if a specific system name is supplied
if [ -n "$2" ]; then
  # Validate the provided system name
  if [[ " ${systemnames[@]} " =~ " $2 " ]]; then
    systemnames=("$2")
  else
    echo "Invalid system name: $2"
    echo "Valid system names are: ${systemnames[@]}"
    exit 1
  fi
fi

# Build the base image
docker build -f docker/Dockerfile-base -t trol2base:temporary .
if [ $? -ne 0 ]; then
  echo "Failed to build base image"
  exit 1
fi

# Loop through each system name and build the Docker images
for systemname in "${systemnames[@]}"; do
  docker build -f docker/Dockerfile-${systemname} -t ${registry}trol2${systemname}:latest -t ${registry}trol2${systemname}:${current_date} .
  if [ $? -ne 0 ]; then
    echo "Failed to build image for ${systemname}"
    exit 1
  fi

  # Push the images if registry is supplied
  if [ -n "$registry" ]; then
    docker push ${registry}trol2${systemname}:latest
    if [ $? -ne 0 ]; then
      echo "Failed to push latest tag for ${systemname}"
      exit 1
    fi

    docker push ${registry}trol2${systemname}:${current_date}
    if [ $? -ne 0 ]; then
      echo "Failed to push date tag for ${systemname}"
      exit 1
    fi
  fi
done

# Clean up
docker rmi trol2base:temporary

echo "Docker images built successfully."

