import datetime
import time
from functools import partial
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import dateutil
import dateutil.parser
import dateutil.tz
import requests
from fabric import task
from tqdm.auto import tqdm

from fabfile.defaults import BACKUP_PATH, SERVICES_REMOTE_ROOT
from fabfile.helpers import (
    _misc_dcp_running_services,
    _misc_get_arrkey,
    _misc_get_arrport,
)
from fabfile.utils import _load_service_config, _read_file, _remote_walk, _total_files


def _generic_backup(
    c, root, service, pbar=True, excluded=None, compressed=False, verbose=True
):
    if verbose:
        print(f"Downloading {service} backup from {root}...")
    pbar = partial(tqdm, total=_total_files(c, root)) if pbar else lambda x: x

    if compressed:
        with ZipFile(f"{BACKUP_PATH}/{service}.zip", "w") as archive:
            for path in pbar(_remote_walk(c, root, exclude_dirs=excluded)):
                archive.writestr(
                    ZipInfo(str(Path(path).relative_to(root))),
                    _read_file(c, path, raw=True),
                )

    else:
        for path in pbar(_remote_walk(c, root, exclude_dirs=excluded)):
            c.get(path, str(BACKUP_PATH / service / Path(path).relative_to(root)))


@task
def arr_path(
    c, service, port, apikey, max_staleness=48, sleep=10, retries=3, force=False
):
    """Return path of a recent *arr backup, create a new one if needed"""
    # The path returned is a URL path, except for bazarr when it's just a filename...
    urls = {
        "default": {
            "list": f"http://{c.host}:{port}/api/v1/system/backup",
            "create": f"http://{c.host}:{port}/api/v1/command",
        },
        "radarr": {
            "list": f"http://{c.host}:{port}/api/v3/system/backup",
            "create": f"http://{c.host}:{port}/api/v3/command",
        },
        "sonarr": {
            "list": f"http://{c.host}:{port}/api/v3/system/backup",
            "create": f"http://{c.host}:{port}/api/v3/command",
        },
        "bazarr": {
            "list": f"http://{c.host}:{port}/api/system/backups",
            "create": f"http://{c.host}:{port}/api/system/backups",
        },
    }
    urls = urls.get(service.lower(), urls["default"])

    def list_backups():
        """Call *arr API, get list of backups (most recent first)"""
        response = requests.get(urls["list"], headers={"X-Api-Key": apikey}, json={})
        response.raise_for_status()
        return response.json()

    def create_backup():
        """Call *arr API, trigger backup creation"""
        print(f"Creating backup for {service}...")
        response = requests.post(
            urls["create"], headers={"X-Api-Key": apikey}, json={"name": "Backup"}
        )
        response.raise_for_status()
        return response.json() if response.content else {}  # bazaar again...

    if retries <= 0:
        raise RuntimeError("Cannot create or find suitable backup!")

    if (response := list_backups()) and not force:
        # Again, Bazarr plays weird. It's response is not a list but a dict with key data
        if type(response) is list:
            stale = False
            timestamp = response[0].get("time")
            timestamp = dateutil.parser.parse(timestamp)
        else:
            if response["data"]:
                stale = False
                timestamp = response["data"][0].get("date")
                timestamp = dateutil.parser.parse(timestamp).replace(
                    tzinfo=dateutil.tz.UTC
                )
            else:
                stale = True
                timestamp = datetime.datetime(1970, 1, 1, 0, 0, tzinfo=dateutil.tz.UTC)

        now = datetime.datetime.now(dateutil.tz.UTC)
        if stale or now - timestamp > datetime.timedelta(hours=max_staleness):
            # If they are all stale, create one
            create_backup()
            time.sleep(sleep)
        else:
            return (
                response[0]["path"]
                if type(response) is list
                else response["data"][0]["filename"]
            )
    else:
        # If none exist, create one
        create_backup()
        time.sleep(sleep)
    return arr_path(
        c,
        service,
        port,
        apikey,
        max_staleness=max_staleness,
        sleep=sleep,
        retries=retries - 1,
        force=False,
    )


@task
def arrs(
    c,
    services_config=None,
    root=None,
    max_staleness=48,
    retries=3,
    sleep=10,
    force=False,
):
    """Copy remote *arr backup directories to `backup/`"""
    services = _load_service_config(services_config, root)

    # Get api keys and ports
    arrs = set(service for service in services if service.lower().endswith("arr"))
    running_arrs = set(
        service
        for service in _misc_dcp_running_services(c)
        if service.lower().endswith("arr")
    )

    if missing_arrs := arrs - running_arrs:
        print(f"WARNING: Skipping {missing_arrs} as they are not running!")

    running_arrs = {
        service: (
            _misc_get_arrkey(c, service),
            _misc_get_arrport(c, service),
        )
        for service in running_arrs
    }

    for service, (apikey, port) in running_arrs.items():
        backup = Path(
            arr_path(
                c,
                service,
                port,
                apikey,
                max_staleness=max_staleness,
                sleep=sleep,
                retries=retries,
                force=force,
            )
        ).name

        for path in _remote_walk(c, f"{SERVICES_REMOTE_ROOT}/{service}"):
            if path.endswith(backup):
                print(f"Downloading {service} backup from {path}...")
                c.get(path, str(BACKUP_PATH / backup))
                break
        else:
            print(f"No backup found for {service}!!")


@task
def code_server(c):
    """Make a backup of code-server data"""
    _generic_backup(
        c, f"{SERVICES_REMOTE_ROOT}/code-server", "code-server", compressed=True
    )


@task
def gluetun(c):
    """Make a backup of gluetun data"""
    _generic_backup(c, f"{SERVICES_REMOTE_ROOT}/gluetun", "gluetun", compressed=True)


@task
def homer(c):
    """Make a backup of homer data"""
    _generic_backup(c, f"{SERVICES_REMOTE_ROOT}/homer", "homer", compressed=True)


@task
def ombi(c):
    """Make a backup of ombi data"""
    _generic_backup(c, f"{SERVICES_REMOTE_ROOT}/ombi", "ombi", compressed=True)


@task
def pihole(c):
    """Make a backup of pihole data"""
    _generic_backup(c, f"{SERVICES_REMOTE_ROOT}/pihole", "pihole", compressed=True)


@task
def plex(c):
    """Make a backup of plex data while skipping cache data"""
    _generic_backup(
        c,
        f"{SERVICES_REMOTE_ROOT}/plex",
        "plex",
        excluded=["/srv/plex/Library/Application Support/Plex Media Server/Cache/"],
        compressed=True,
    )


@task
def tautulli(c):
    """Make a backup of tautulli data"""
    _generic_backup(c, f"{SERVICES_REMOTE_ROOT}/tautulli", "tautulli", compressed=True)


@task
def transmission(c):
    """Make a backup of transmission data"""
    _generic_backup(
        c, f"{SERVICES_REMOTE_ROOT}/transmission", "transmission", compressed=True
    )


@task
def wireguard(c):
    """Make a backup of wireguard data"""
    _generic_backup(
        c, f"{SERVICES_REMOTE_ROOT}/wireguard", "wireguard", compressed=True
    )


@task(aliases=["backup"], default=True)
def all(c, services_config=None, root=None, force=False):
    """Run all backup subtasks"""
    # Call dependencies, this should be done via pre-tasks
    # but theres a bug on windows (https://github.com/fabric/fabric/issues/2202)
    arrs(c, services_config, root, force=force)
    code_server(c)
    gluetun(c)
    homer(c)
    ombi(c)
    pihole(c)
    plex(c)
    tautulli(c)
    transmission(c)
    wireguard(c)
