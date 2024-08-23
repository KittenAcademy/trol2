import argparse
import yaml

def create_docker_compose(systemnames, cameras, registry=None, configname=None, image_version="latest"):
    services = {}
    network_name = "trol_network"

    registry_string = ""
    if registry is not None:
        registry_string = f"{registry}/"

    
    # Add camera services
    for camera in cameras:
        service_name = f"screenshot_{camera}"
        services[service_name] = {
            "command": f"--config config.yaml --camera_name {camera} --on_fail delayed",
            "image": f"{registry_string}trol2screenshot:{image_version}",
            "restart": "unless-stopped",
            "networks": [network_name]
        }
        if configname is not None:
            services[service_name]["configs"] = [{ "source": configname, "target": "/app/config.yaml"}]

    # Add system services
    for system in systemnames:
        services[system] = {
            "image": f"{registry_string}trol2{system}:{image_version}",
            "restart": "unless-stopped",
            "networks": [network_name]
        }
        if configname is not None:
            services[system]["configs"] = [{ "source": configname, "target": "/app/config.yaml"}]


    docker_compose = {
        "version": "3.9",
        "services": services,
        "networks": {
            network_name: {
                "driver": "overlay",
                "attachable": True,
                "name": network_name,
            }
        }
    }
    if configname is not None:
        docker_compose['configs'] = { configname: { "external": True }}

    print(yaml.dump(docker_compose, default_flow_style=False))
    if configname is not None:
        print("#")
        print(f"# Don't forget to: docker config create {configname} ./config.yaml")
        print("#")
    print("# create: docker stack deploy -c ./docker-compose.yml trol2")
    print("# remove: docker stack rm trol2")


def main():
    parser = argparse.ArgumentParser(description="Generate a docker-compose.yml file.")
    parser.add_argument("--registry", type=str, default=None, help="Registry name (e.g. registry.myorg.com)")
    parser.add_argument("--cameras", type=str, help="Comma-separated list of cameras (e.g. zoom1,zoom2,4k1)")
    parser.add_argument("--configname", type=str, help="Optional Docker config system name for config.yaml")
    parser.add_argument("--imageversion", type=str, default='latest', help="Image version tag, defaults to 'latest'")

    args = parser.parse_args()
    cameras = args.cameras.split(',')
    systemnames = ["obs", "newsrunner", "discord", "ptzhandler", "autocam"]

    create_docker_compose(systemnames, cameras, registry=args.registry, configname=args.configname, image_version=args.imageversion)

if __name__ == "__main__":
    main()

