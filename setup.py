import os
import subprocess
from setuptools import setup, find_packages
from setuptools.command.install import install
from setuptools.command.develop import develop

def install_completion_script(target_dir):
    """Install the bash completion script in the target directory."""
    try:
        completion_script = subprocess.check_output(
            ['register-python-argcomplete', 'trol-settings']
        ).decode('utf-8')
    except subprocess.CalledProcessError:
        print("Error generating bash completion script.")
        return

    completion_file = os.path.join(target_dir, 'trol-settings')
    with open(completion_file, 'w') as f:
        f.write(completion_script)

    print(f"Bash completion script installed at {completion_file}.")

class CustomInstallCommand(install):
    def run(self):
        super().run()
        # Determine target directory
        target_dir = os.path.expanduser('~/.local/share/bash-completion/completions/')
        os.makedirs(target_dir, exist_ok=True)
        install_completion_script(target_dir)

class CustomDevelopCommand(develop):
    def run(self):
        super().run()
        # Determine target directory
        target_dir = os.path.expanduser('~/.local/share/bash-completion/completions/')
        os.makedirs(target_dir, exist_ok=True)
        install_completion_script(target_dir)

setup(
    name='trol',
    version='2.1',
    packages=find_packages(),
    install_requires=[
        'argcomplete',
    ],
    entry_points={
        'console_scripts': [
            'trol-obs-interface = trol.obs.interface:main',
            'trol-screenshot = trol.cameras.screenshot:main',
            'trol-handleptz = trol.cameras.handlePTZ:main',
            'trol-autocam = trol.cameras.autocam:main',
            'trol-bot = trol.discord.bot:main',
            'trol-filemover = trol.filemover.filemover:main',
            'trol-microformat = trol.microformat.microformat:main',
            'trol-newsrunner = trol.obs.newsrunner:main',
            'trol-settings = trol.shared.settings:main',
            'trol-mqtt = trol.shared.MQTT:main',
            'trol-setup-camera = initialize.camera:main',
            'trol-setup-position = initialize.position:main',
            'trol-setup-obs = trol.obs.functions:main', 
            'trol-onvif = trol.cameras.ONVIF:main',
        ]
    },
    cmdclass={
        'install': CustomInstallCommand,
        'develop': CustomDevelopCommand,
    },
)

