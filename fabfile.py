# Run with: fab <task> -H <user>@<addr> --prompt-for-login-password
import configparser
import datetime
import inspect
import io
import itertools
import json
import posixpath
import re
import sys
import time
import xml.etree.ElementTree as ET
from functools import partial
from pathlib import Path
from stat import S_ISDIR, S_ISREG
from zipfile import ZipFile, ZipInfo

import dateutil
import dateutil.parser
import dateutil.tz
import fabric.main
import invoke.program
import keyring
import requests
from bs4 import BeautifulSoup
from fabric import task
from jinja2 import Environment, FileSystemLoader, select_autoescape
from ruamel.yaml import YAML
from tqdm.auto import tqdm

# GLOBAL DEFAULTS

SERVICES_REMOTE_ROOT = "/srv"
COMPOSE_REMOTE_ROOT = "~"
COMPOSE_FILE = "docker-compose.yml"
HOMER_REMOTE_FILE = "config.yml"
TRANSMISSION_REMOTE_FILE = "settings.json"
DCP = f"docker-compose -f {COMPOSE_REMOTE_ROOT}/{COMPOSE_FILE}"
MEDIA_REMOTE_ROOT = "/mnt/mybook/srv/media/"

LOCAL_ROOT = "."
BACKUP_DIR = "backup"
PROFILE_FILE = ".profile"
SERVICES_FILE = "services.yml"
HOMER_FILE = "homer-config.yml"
TRANSMISSION_FILE = "transmission-config.yml"

SERVICES_PATH = Path(LOCAL_ROOT) / SERVICES_FILE
COMPOSE_PATH = Path(LOCAL_ROOT) / COMPOSE_FILE
PROFILE_PATH = Path(LOCAL_ROOT) / PROFILE_FILE
HOMER_PATH = Path(LOCAL_ROOT) / HOMER_FILE
TRANSMISSION_PATH = Path(LOCAL_ROOT) / TRANSMISSION_FILE
BACKUP_PATH = Path(LOCAL_ROOT) / BACKUP_DIR


# Helper Functions


def get_hostname(c):
    ips = c.run("hostname -I", hide=True).stdout.split(" ")
    return ips[0]


def dcp_is_up(c):
    ret = c.run("docker-compose top", hide=True, warn=True)
    return ret.ok and ret.stdout


def clone_or_pull(c, addr, path):
    # Make sure git is installed
    if c.run("git --version", hide=True, warn=True).failed:
        c.sudo("apt-get install git -y")

    # Only clone repo if not present, only allow fast-forward (i.e: no merge)
    c.sudo(f"mkdir -p {path}")
    if c.sudo(f"git -C {path} pull --ff-only", warn=True).failed:
        c.sudo(f"git clone {addr} {path}")


def put_mv(c, path_or_data, target_dir, raw=False, filename=None):
    """Upload file at `path_or_data` to remote's `target_dir`.
    This operation is done as a temporary put then a move because
    we might not have permissions to upload to `target_dir`.
    If `raw` then treat `path_or_data` as a data stream/string."""
    if raw and not filename:
        raise ValueError("Argument `filename` is required when `raw`=True")
    filename = path_or_data if not raw else filename
    c.put(io.StringIO(path_or_data) if raw else path_or_data, filename)
    c.sudo(f"mkdir -p {target_dir}")
    c.sudo(f"mv ~/{filename} {target_dir}", warn=True)


def get_py_version(c):
    v = c.run(
        "python -V || python3 -V || echo 'Default 0.0.0'", hide=True, warn=True
    ).stdout.split(" ")[-1]
    return [int(i) for i in v.split(".")]


def get_jinja_env(root=None):
    # Create templating engine environment
    return Environment(
        loader=FileSystemLoader(root or LOCAL_ROOT), autoescape=select_autoescape()
    )


def load_service_config(services_config=None, root=None):
    # Preprocess services.yml, fill out any secrets with `keyring`
    env = get_jinja_env(root)
    services = env.get_template(services_config or str(SERVICES_PATH), "r")
    services = services.render(keyring_get=keyring.get_password)

    # Load services config, expand enable option
    services = YAML(typ="safe").load(services)
    services = {
        k: v if type(v) is not bool else {"enable": v} for k, v in services.items()
    }
    return {k.replace("-", "_"): v for k, v in services.items()}


def read_file(c, path, encoding="utf-8", raw=False):
    """Read remote file into a memory buffer"""
    f = io.BytesIO()
    c.get(path, f)
    return f.getvalue().decode(encoding) if not raw else f.getvalue()


def total_files(c, dir):
    return int(c.run(f"find {dir} -type f | wc -l", hide=True).stdout)


def get_xml_value(c, path, key, encoding="utf-8", default=None):
    """Given a path to a remote XML file and a key, retrieve it's value."""
    try:
        content = read_file(c, path, encoding=encoding)
        return ET.fromstring(content).find(key).text
    except FileNotFoundError:
        return default


def remote_walk(c, root, exclude_dirs=None):
    """Like os.walk but for the remote host!"""
    exclude_dirs = set(exclude_dirs or [])
    root = c.sftp().normalize(root)
    for entry in c.sftp().listdir(root):
        pathname = posixpath.join(root, entry)
        mode = c.sftp().stat(pathname).st_mode
        if S_ISDIR(mode):
            # It's a directory!
            if pathname not in exclude_dirs:
                yield from remote_walk(c, pathname, exclude_dirs=exclude_dirs)
        elif S_ISREG(mode):
            # It's a file!
            yield pathname


def generic_backup(
    c, root, service, pbar=True, excluded=None, compressed=False, verbose=True
):
    if verbose:
        print(f"Downloading {service} backup from {root}...")
    pbar = partial(tqdm, total=total_files(c, root)) if pbar else lambda x: x

    if compressed:
        with ZipFile(f"{BACKUP_PATH}/{service}.zip", "w") as archive:
            for path in pbar(remote_walk(c, root, exclude_dirs=excluded)):
                archive.writestr(
                    ZipInfo(str(Path(path).relative_to(root))),
                    read_file(c, path, raw=True),
                )

    else:
        for path in pbar(remote_walk(c, root, exclude_dirs=excluded)):
            c.get(path, str(BACKUP_PATH / service / Path(path).relative_to(root)))


def get_service_compose(service, dcp_path=None):
    """Given a service name, extract it's docker compose config as text"""
    with open(dcp_path or str(COMPOSE_PATH), "r") as f:
        pattern = (
            rf"{{%-?\s+if\s+{service.lower()}\.enable\s+%}}(.*?){{%-?\s+endif\s+%}}"
        )
        matches = re.findall(pattern, f.read(), re.IGNORECASE | re.DOTALL)
        return inspect.cleandoc(matches[0]) if matches else "Compose not found!"


def print_dicts(*dicts, titles=None, sep="\t", sort_keys=True, indent=2):
    """Print dictionaries side by side"""
    if titles is not None and len(titles) != len(dicts):
        raise ValueError("Titles must be same length as dicts.")
    dicts = [json.dumps(d, sort_keys=sort_keys, indent=indent) for d in dicts]
    max_lens = [max(len(l) for l in d.splitlines()) for d in dicts]
    dicts = [d.splitlines() for d in dicts]
    for parts in itertools.chain([titles], itertools.zip_longest(*dicts, fillvalue="")):
        padded = [p + " " * (max_lens[i] - len(p)) for i, p in enumerate(parts)]
        print(sep.join(padded))


# Tasks to execute on host machine


@task
def reboot(c):
    """Reboot host machine"""
    c.sudo("reboot")


@task
def apt_update(c):
    """(apt) Update and upgrade system"""
    c.sudo("apt-get update -y")
    c.sudo("apt-get upgrade -y")


@task
def install_py3(c, force=False):
    """Install python3 (and pip!) if not present"""
    if (
        get_py_version(c)[0] < 3
        or c.run("python3 -m pip -V", hide=True, warn=True).failed
        or force
    ):
        c.sudo("apt-get install -y libffi-dev libssl-dev")
        c.sudo("apt-get install -y python3-dev")
        c.sudo("apt-get install -y python3 python3-pip ")
    else:
        print("Python3 is already installed, skipping...")


@task
def install_ctop(c):
    """Install top-like interface for container metrics"""
    c.sudo(
        "echo 'deb http://packages.azlux.fr/debian/ buster main' | sudo tee /etc/apt/sources.list.d/azlux.list"
    )
    c.sudo("wget -qO - https://azlux.fr/repo.gpg.key | sudo apt-key add -")
    c.sudo("apt update")
    c.sudo("apt install docker-ctop")


@task(aliases=["install_lzd"])
def install_lazydocker(c):
    """Install the lazy docker manager"""
    c.run(
        "curl https://raw.githubusercontent.com/jesseduffield/lazydocker/master/scripts/install_update_linux.sh | bash"
    )


@task
def install_docker(c, force=False):
    """Install docker if not present"""
    if c.run("docker -v", hide=True, warn=True).failed or force:
        c.run("curl -sSL https://get.docker.com | sh")
        c.sudo("usermod -aG docker ${USER}")
        c.sudo("systemctl enable docker")
    else:
        print("Docker is already installed, skipping...")


@task
def install_docker_compose(c, force=False):
    """Install docker-compose if not present"""
    # Call dependencies, this should be done via pre-tasks
    # but theres a bug on windows (https://github.com/fabric/fabric/issues/2202)
    install_py3(c, force=force)
    install_docker(c, force=force)

    if c.run("docker-compose --version", hide=True, warn=True).failed or force:
        c.sudo("python3 -m pip install docker-compose")
    else:
        print("Docker-compose is already installed, skipping...")


@task(aliases=["dcp_ls"])
def dcp_services(c, verbose=True):
    """List services in remote's compose file"""
    ret = c.run(f"{DCP} ps --services", hide=True, warn=True)
    services = ret.stdout.splitlines() if ret.ok else []
    if verbose:
        print(
            f"Services are: {', '.join(services)}" if services else "No services found!"
        )
    return services


@task(aliases=["dcp_ls_up"])
def dcp_running_services(c, verbose=True):
    """List running services on remote host"""
    running = c.run(
        f'docker-compose ps --services --filter "status=running"', hide=True
    ).stdout.splitlines()
    if verbose:
        print(
            f"Running services are: {', '.join(running)}."
            if running
            else "No services are running."
        )
    return running


@task(aliases=["resize_swap"])
def set_swap_size(c, size=None):
    """Set swap partition size on remote (in MB)"""
    if not size:
        size = input("New swap size (in MB): ")

    size = int(size)
    c.sudo("dphys-swapfile swapoff")
    content = read_file(c, "/etc/dphys-swapfile", encoding="utf-8")
    content = re.sub(r"CONF_SWAPSIZE=\d+", f"CONF_SWAPSIZE={size}", content, count=1)
    put_mv(c, content, "/etc", raw=True, filename="dphys-swapfile")
    c.sudo("dphys-swapfile setup")
    c.sudo("dphys-swapfile swapon")
    print("Please reboot host for changes to take effect.")


@task
def get_arrkey(c, service, encoding="utf-8"):
    """Retrieve API key for an *arr service"""
    # Special case for Bazarr because it's API is not compliant
    if service.lower() == "bazarr":
        conf = configparser.ConfigParser()
        conf.read_string(
            read_file(c, f"{SERVICES_REMOTE_ROOT}/{service}/config/config.ini")
        )
        return conf.get("auth", "apikey", fallback=None) or ""
    return get_xml_value(
        c,
        f"{SERVICES_REMOTE_ROOT}/{service}/config.xml",
        "ApiKey",
        encoding=encoding,
        default="",
    )


@task
def get_arrport(c, service, encoding="utf-8"):
    """Retrieve port for an *arr service"""
    # Special case for Bazarr because it's API is not compliant
    if service.lower() == "bazarr":
        conf = configparser.ConfigParser()
        conf.read_string(
            read_file(c, f"{SERVICES_REMOTE_ROOT}/{service}/config/config.ini")
        )
        return conf.get("general", "port", fallback=None) or ""
    return get_xml_value(
        c,
        f"{SERVICES_REMOTE_ROOT}/{service}/config.xml",
        "Port",
        encoding=encoding,
        default="",
    )


@task
def get_arrbackup_path(c, service, port, apikey, max_staleness=48, sleep=10, retries=3):
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

    if response := list_backups():
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
    return get_arrbackup_path(
        c,
        service,
        port,
        apikey,
        max_staleness=max_staleness,
        sleep=sleep,
        retries=retries - 1,
    )


@task
def deploy(c, services_config=None, root=None, force=False, update=False):
    """Install services with docker-compose"""
    if update:
        apt_update(c)
    install_docker_compose(c, force=force)

    # Get dashboard icons, create /srv directory
    clone_or_pull(
        c,
        "https://github.com/walkxhub/dashboard-icons.git",
        f"{SERVICES_REMOTE_ROOT}/dashboard-icons/",
    )

    # Move and render docker-compose and .profile
    env = get_jinja_env(root)
    services = load_service_config(services_config, root)
    dcp = env.get_template(str(COMPOSE_PATH))
    dcp = dcp.render(
        **services,
        MEDIA_REMOTE_ROOT=MEDIA_REMOTE_ROOT,
        SERVICES_REMOTE_ROOT=SERVICES_REMOTE_ROOT,
    )
    put_mv(c, dcp, COMPOSE_REMOTE_ROOT, raw=True, filename=COMPOSE_FILE)

    # Upload and source profile script
    profile = env.get_template(str(PROFILE_PATH))
    profile = profile.render(DCP=DCP)
    put_mv(c, profile, "~", raw=True, filename=PROFILE_FILE)
    c.run(f"source {PROFILE_FILE}")

    # Render homer's config and upload it
    homer_config = env.get_template(str(HOMER_PATH))
    homer_config = homer_config.render(
        **services,
        hostname=get_hostname(c),
    )
    put_mv(
        c,
        homer_config,
        f"{SERVICES_REMOTE_ROOT}/homer/",
        raw=True,
        filename=HOMER_REMOTE_FILE,
    )

    # Install convenience packages
    if c.run("tmux -V", hide=True, warn=True).failed:
        c.sudo("apt-get install tmux -y")
    if c.run("ncdu -V", hide=True, warn=True).failed:
        c.sudo("apt-get install ncdu -y")


@task(aliases=["config_wg", "config_wireguard"])
def configure_wireguard(c, conf=None, services_config=None, root=None):
    """Upload wireguard config (i.e: wg0.conf) to host"""
    services = load_service_config(services_config, root)
    if "wireguard" not in services:
        raise ValueError("Please make sure to deploy wireguard first!")
    put_mv(c, conf or "./wg0.conf", f"{SERVICES_REMOTE_ROOT}/wireguard/")


@task(aliases=["config_plex"])
def configure_plex(c, services_config=None, root=None):
    """Claim plex server, see: `https://www.plex.tv/claim/`"""
    # Get claim token, update docker-compose.yml and spin up
    # the plex service so it can acknowledge the claim before timeout
    # IMPORTANT: Make sure *.plex.tv is not blocked by pihole during setup

    env = get_jinja_env(root)
    services = load_service_config(services_config, root)

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
    put_mv(c, dcp, COMPOSE_REMOTE_ROOT, raw=True, filename=COMPOSE_FILE)
    c.run(f"{DCP} up -d plex")
    c.run(f"{DCP} stop plex")


@task(aliases=["config_homer"])
def configure_homer(c, services_config=None, root=None):
    """Fetch and add apikey to homer dashboard for *arr apps"""
    # Get list of services
    env = get_jinja_env(root)
    services = load_service_config(services_config, root)

    if "homer" not in services:
        raise ValueError("Please make sure to deploy homer first!")

    # Get apikeys (if exists)
    arrs = [service for service in services if service.lower().endswith("arr")]
    arrkeys = {service: get_arrkey(c, service) for service in arrs}
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
        hostname=get_hostname(c),
    )
    put_mv(
        c,
        homer_config,
        f"/{SERVICES_REMOTE_ROOT}/homer/",
        raw=True,
        filename=HOMER_REMOTE_FILE,
    )
    print("done!")


@task(aliases=["config_transmission"])
def configure_transmission(c, root=None):
    """Upload transmission's `settings.json` to host"""
    env = get_jinja_env(root)
    temp = env.get_template(str(TRANSMISSION_PATH))
    temp = temp.render(keyring_get=keyring.get_password)
    temp = YAML(typ="safe").load(temp)
    put_mv(
        c,
        json.dumps(temp, indent=2, sort_keys=True),
        f"/{SERVICES_REMOTE_ROOT}/transmission/",
        raw=True,
        filename=TRANSMISSION_REMOTE_FILE,
    )


@task
def render_readme(_, services_config=None, root=None, dcp_path=None):
    """Update code segments in the README file (runs on local)"""
    # Get list of services (raw as well), and dcp conf
    env = get_jinja_env(root)
    services = load_service_config(services_config, root)
    service_names = list(services.keys())
    with open(Path(root or "./") / (services_config or str(SERVICES_PATH)), "r") as f:
        services_raw = f.read()

    # Get compose args for each service
    for service in services:
        services[service]["compose"] = get_service_compose(service, dcp_path=dcp_path)

    # Get description for each service
    for service in services:
        if github_url := services[service].get("github"):
            response = requests.get(github_url)
            soup = BeautifulSoup(response.content, "lxml")
            item = soup.find("p", {"class": "f4 my-3"})
        else:
            item = None
        services[service]["description"] = services[service].get(
            "short_description"
        ) or (
            item.text.encode("ascii", "ignore").decode()
            if item
            else "Missing Description!"
        )
        services[service]["description"] = services[service]["description"].strip()
        services[service]["link"] = services[service].get("link") or services[
            service
        ].get("github")

    # Get list of invoke tasks.
    # NOTE: This should be run as c.local but there's a bug on windows that affects this.
    #       See: https://github.com/fabric/fabric/issues/2142
    #       We can't use subprocess either as it assumes a small terminal width (i.e: 80).
    #       Instead we import fabric as a module and monkey-patch both print and invoke's pty_size
    invoke.program.pty_size = lambda: (132, 0)
    sys.stdout = out = io.StringIO()
    fabric.main.Fab(
        name="Fabric",
        executor_class=fabric.main.Executor,
        config_class=fabric.main.Config,
    ).run([f"-f {Path(__file__).name}", "-l"], False)
    sys.stdout = sys.__stdout__
    services["fabric"] = {"tasks": out.getvalue()}

    # Render README and save it
    readme = env.get_template("README-Template.md")
    readme = readme.render(
        **services,
        services=services,
        service_names=service_names,
        services_raw=services_raw,
    )
    with open("README.md", "w") as f:
        f.write(readme)


@task
def backup_arrs(c, services_config=None, root=None):
    """Copy remote *arr backup directories to `backup/`"""
    services = load_service_config(services_config, root)

    # Get api keys and ports
    arrs = set(service for service in services if service.lower().endswith("arr"))
    running_arrs = set(
        service
        for service in dcp_running_services(c, verbose=False)
        if service.lower().endswith("arr")
    )

    if missing_arrs := arrs - running_arrs:
        print(f"WARNING: Skipping {missing_arrs} as they are not running!")

    running_arrs = {
        service: (
            get_arrkey(c, service),
            get_arrport(c, service),
        )
        for service in running_arrs
    }

    for service, (apikey, port) in running_arrs.items():
        backup = Path(
            get_arrbackup_path(
                c,
                service,
                port,
                apikey,
                max_staleness=48,
                sleep=10,
                retries=3,
            )
        ).name

        for path in remote_walk(c, f"{SERVICES_REMOTE_ROOT}/{service}"):
            if path.endswith(backup):
                print(f"Downloading {service} backup from {path}...")
                c.get(path, str(BACKUP_PATH / backup))
                break
        else:
            print(f"No backup found for {service}!!")


@task
def backup_plex(c):
    """Make a backup of plex data while skipping cache data"""
    generic_backup(
        c,
        f"{SERVICES_REMOTE_ROOT}/plex",
        "plex",
        excluded=["/srv/plex/Library/Application Support/Plex Media Server/Cache/"],
        compressed=True,
    )


@task
def backup_transmission(c):
    """Make a backup of transmission data"""
    generic_backup(
        c, f"{SERVICES_REMOTE_ROOT}/transmission", "transmission", compressed=True
    )


@task
def backup_tautulli(c):
    """Make a backup of tautulli data"""
    generic_backup(c, f"{SERVICES_REMOTE_ROOT}/tautulli", "tautulli", compressed=True)


@task
def backup_pihole(c):
    """Make a backup of pihole data"""
    generic_backup(c, f"{SERVICES_REMOTE_ROOT}/pihole", "pihole", compressed=True)


@task
def backup_ombi(c):
    """Make a backup of ombi data"""
    generic_backup(c, f"{SERVICES_REMOTE_ROOT}/ombi", "ombi", compressed=True)


@task
def backup_gluetun(c):
    """Make a backup of gluetun data"""
    generic_backup(c, f"{SERVICES_REMOTE_ROOT}/gluetun", "gluetun", compressed=True)


@task
def backup_homer(c):
    """Make a backup of homer data"""
    generic_backup(c, f"{SERVICES_REMOTE_ROOT}/homer", "homer", compressed=True)


@task
def backup_code_server(c):
    """Make a backup of code-server data"""
    generic_backup(
        c, f"{SERVICES_REMOTE_ROOT}/code-server", "code-server", compressed=True
    )


@task
def backup_wireguard(c):
    """Make a backup of wireguard data"""
    generic_backup(c, f"{SERVICES_REMOTE_ROOT}/wireguard", "wireguard", compressed=True)


@task
def backup(c, services_config=None, root=None):
    """Run all backup subtasks"""
    # Call dependencies, this should be done via pre-tasks
    # but theres a bug on windows (https://github.com/fabric/fabric/issues/2202)
    backup_arrs(c, services_config, root)
    backup_code_server(c)
    backup_gluetun(c)
    backup_homer(c)
    backup_ombi(c)
    backup_pihole(c)
    backup_plex(c)
    backup_tautulli(c)
    backup_transmission(c)
    backup_wireguard(c)


@task(incrementable=["verbose"])
def verify_vpn(
    c, verbose=0, full=False, services_config=None, root=None, dcp_path=None
):
    """Test that the VPN is connected and it's IP isn't local"""
    running_services = set(dcp_running_services(c, verbose=False))
    if "gluetun" not in running_services:
        raise ValueError(
            "VPN service must be running. Please first run `dcp up -d gluetun`."
        )

    # The `-T` in dcp exec is needed. See: https://stackoverflow.com/questions/43099116
    c.run(f"{DCP} exec -T gluetun sh -c 'apk add curl'", hide=True)
    vpn = json.loads(
        c.run(
            f"{DCP} exec -T gluetun sh -c 'curl https://ipleak.net/json/'", hide=True
        ).stdout
    )
    local = json.loads(c.run("curl https://ipleak.net/json/", hide=True).stdout)

    if verbose == 1:
        print_dicts(local, vpn, titles=["Local:", "VPN:"])

    if full or verbose > 1:
        services = load_service_config(services_config, root)
        usevpn = [
            service
            for service, v in services.items()
            if v["enable"]
            and "usevpn" in get_service_compose(service, dcp_path=dcp_path)
        ]
        missing_services = [
            service for service in usevpn if service not in running_services
        ]
        present_services = [
            service for service in usevpn if service in running_services
        ]

        present_services = {
            service: json.loads(
                c.run(
                    f"{DCP} exec -T {service} sh -c 'curl https://ipleak.net/json/'",
                    hide=True,
                ).stdout
            )
            for service in present_services
        }

        if verbose > 1:
            print_dicts(
                local,
                vpn,
                *present_services.values(),
                titles=["Local:", "VPN:"] + [s.title() + ":" for s in present_services],
            )
        elif verbose == 1:
            print_dicts(local, vpn, titles=["Local:", "VPN:"])

        present_services = {
            service: local != vpn and s_vpn["ip"] == vpn["ip"]
            for service, s_vpn in present_services.items()
        }

        if any(present_services.values()):
            print(
                f"Services that use VPN: {', '.join(s for s, v in present_services.items() if v)}"
            )
        if not all(present_services.values()):
            print(
                f"WARNING: services not using VPN: {', '.join(s for s, v in present_services.items() if not v)}"
            )
        if missing_services:
            print(
                "WARNING: The following services were not running, so were not checked:"
            )
            print(", ".join(missing_services))
    print("VPN working correctly." if local != vpn else "VPN not connected!!")
