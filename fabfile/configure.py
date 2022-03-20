import json

import keyring
from fabric import task
from ruamel.yaml import YAML

from fabfile import status
from fabfile.defaults import (
    COMPOSE_FILE,
    COMPOSE_PATH,
    COMPOSE_REMOTE_ROOT,
    DCP,
    HOMER_PATH,
    HOMER_REMOTE_FILE,
    MEDIA_REMOTE_ROOT,
    SERVICES_REMOTE_ROOT,
    TRANSMISSION_PATH,
    TRANSMISSION_REMOTE_FILE,
)
from fabfile.utils import _get_hostname, _get_jinja_env, _load_service_config, _put_mv


@task
def homer(c, services_config=None, root=None):
    """Fetch and add apikey to homer dashboard for *arr apps"""
    # Get list of services
    env = _get_jinja_env(root)
    services = _load_service_config(services_config, root)

    if "homer" not in services:
        raise ValueError("Please make sure to deploy homer first!")

    # Get apikeys (if exists)
    arrs = [service for service in services if service.lower().endswith("arr")]
    arrkeys = {service: status.get_arrkey(c, service) for service in arrs}
    arrkeys = {service: key for service, key in arrkeys.items() if key}

    for service, key in arrkeys.items():
        services[service]["apikey"] = key
    if arrkeys:
        print(f"Found API keys for {', '.join(arrkeys)}.")
        print("Adding them to Homer's config... ", end="")
    else:
        print("Found no API keys! Please make sure to init services first.")
        return

    # (Re)-render homer's config and upload it
    homer_config = env.get_template(str(HOMER_PATH))
    homer_config = homer_config.render(
        **services,
        hostname=_get_hostname(c),
    )
    _put_mv(
        c,
        homer_config,
        f"/{SERVICES_REMOTE_ROOT}/homer/",
        raw=True,
        filename=HOMER_REMOTE_FILE,
    )
    print("done!")


@task
def plex(c, services_config=None, root=None):
    """Claim plex server, see: `https://www.plex.tv/claim/`"""
    # Get claim token, update docker-compose.yml and spin up
    # the plex service so it can acknowledge the claim before timeout
    # IMPORTANT: Make sure *.plex.tv is not blocked by pihole during setup

    env = _get_jinja_env(root)
    services = _load_service_config(services_config, root)

    if "plex" not in services:
        raise ValueError("Please make sure to deploy plex first!")

    print("Visit `https://www.plex.tv/claim/` to get a claim token.")
    claim = input("Plex claim number (claim-xxx..x): ")
    services["plex"]["claim"] = claim
    dcp = env.get_template(str(COMPOSE_PATH))
    dcp = dcp.render(
        **services,
        MEDIA_REMOTE_ROOT=MEDIA_REMOTE_ROOT,
        SERVICES_REMOTE_ROOT=SERVICES_REMOTE_ROOT,
    )
    _put_mv(c, dcp, COMPOSE_REMOTE_ROOT, raw=True, filename=COMPOSE_FILE)
    c.run(f"{DCP} up -d plex")
    c.run(f"{DCP} stop plex")


@task(aliases=["transm"])
def transmission(c, root=None):
    """Upload transmission's `settings.json` to host"""
    env = _get_jinja_env(root)
    temp = env.get_template(str(TRANSMISSION_PATH))
    temp = temp.render(keyring_get=keyring.get_password)
    temp = YAML(typ="safe").load(temp)
    _put_mv(
        c,
        json.dumps(temp, indent=2, sort_keys=True),
        f"/{SERVICES_REMOTE_ROOT}/transmission/",
        raw=True,
        filename=TRANSMISSION_REMOTE_FILE,
    )


@task(aliases=["wg"])
def wireguard(c, conf=None, services_config=None, root=None):
    """Upload wireguard config (i.e: wg0.conf) to host"""
    services = _load_service_config(services_config, root)
    if "wireguard" not in services:
        raise ValueError("Please make sure to deploy wireguard first!")
    _put_mv(c, conf or "./wg0.conf", f"{SERVICES_REMOTE_ROOT}/wireguard/")
