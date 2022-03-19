# This file contains the core of some tasks that are reused by others,
# We put them here mainly to avoid circular imports

import configparser

from fabfile.defaults import SERVICES_REMOTE_ROOT
from fabfile.utils import _get_py_version, _get_xml_value, _read_file


def _install_docker(c, force=False):
    """Install docker if not present"""
    if c.run("docker -v", hide=True, warn=True).failed or force:
        # c.sudo("curl -sSL https://get.docker.com | sh")
        c.run("curl -fsSL https://get.docker.com -o get-docker.sh")
        c.sudo("sh get-docker.sh")
        c.sudo("usermod -aG docker ${USER}")
        c.sudo("systemctl enable docker")
        c.run("rm get-docker.sh")
    else:
        print("Docker is already installed, skipping...")


def _install_docker_compose(c, force=False):
    """Install docker-compose if not present"""
    # Call dependencies, this should be done via pre-tasks
    # but theres a bug on windows (https://github.com/fabric/fabric/issues/2202)
    _install_python3(c, force=force)
    _install_docker(c, force=force)

    if c.run("docker-compose --version", hide=True, warn=True).failed or force:
        c.sudo("python3 -m pip install docker-compose")
    else:
        print("Docker-compose is already installed, skipping...")


def _install_python3(c, force=False):
    """Install python3 (and pip!) if not present"""
    if _get_py_version(c)[0] < 3 or c.run("python3 -m pip -V", hide=True, warn=True).failed or force:
        c.sudo("apt-get install -y libffi-dev libssl-dev")
        c.sudo("apt-get install -y python3-dev")
        c.sudo("apt-get install -y python3 python3-pip ")
    else:
        print("Python3 is already installed, skipping...")


def _status_dcp_running_services(c):
    """List running services on remote host"""
    return c.run(f'docker-compose ps --services --filter "status=running"', hide=True).stdout.splitlines()


def _status_get_arrkey(c, service, encoding="utf-8"):
    """Retrieve API key for an *arr service"""
    # Special case for Bazarr because it's API is not compliant
    if service.lower() == "bazarr":
        conf = configparser.ConfigParser()
        conf.read_string(_read_file(c, f"{SERVICES_REMOTE_ROOT}/{service}/config/config.ini"))
        return conf.get("auth", "apikey", fallback=None) or ""
    return _get_xml_value(
        c,
        f"{SERVICES_REMOTE_ROOT}/{service}/config.xml",
        "ApiKey",
        encoding=encoding,
        default="",
    )


def _status_get_arrport(c, service, encoding="utf-8"):
    """Retrieve port for an *arr service"""
    # Special case for Bazarr because it's API is not compliant
    if service.lower() == "bazarr":
        conf = configparser.ConfigParser()
        conf.read_string(_read_file(c, f"{SERVICES_REMOTE_ROOT}/{service}/config/config.ini"))
        return conf.get("general", "port", fallback=None) or ""
    return _get_xml_value(
        c,
        f"{SERVICES_REMOTE_ROOT}/{service}/config.xml",
        "Port",
        encoding=encoding,
        default="",
    )
