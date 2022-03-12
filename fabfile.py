# Run with: fab <task> -H <user>@<addr> --prompt-for-login-password
import itertools
import re
import io
import sys
import json
import inspect
import xml.etree.ElementTree as ET
from pathlib import Path

import keyring
import requests
import fabric.main
import invoke.program
from fabric import task
from ruamel.yaml import YAML
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape


# GLOBAL DEFAULTS

SERVICES_REMOTE_ROOT = "/srv"
COMPOSE_REMOTE_ROOT = "~"
COMPOSE_FILE = "docker-compose.yml"
HOMER_REMOTE_FILE = "config.yml"
DCP = f"docker-compose -f {COMPOSE_REMOTE_ROOT}/{COMPOSE_FILE}"

LOCAL_ROOT = "."
PROFILE_FILE = ".profile"
SERVICES_FILE = "services.yml"
HOMER_FILE = "homer-config.yml"
SERVICES_PATH = Path(LOCAL_ROOT) / SERVICES_FILE
COMPOSE_PATH = Path(LOCAL_ROOT) / COMPOSE_FILE
PROFILE_PATH = Path(LOCAL_ROOT) / PROFILE_FILE
HOMER_PATH = Path(LOCAL_ROOT) / HOMER_FILE

MEDIA_REMOTE_ROOT = "/mnt/mybook/srv/media/"


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


def read_file(c, path, encoding="utf-8"):
    """Read remote file into a memory buffer"""
    f = io.BytesIO()
    c.get(path, f)
    return f.getvalue().decode(encoding)


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
    running = [
        service
        for service in dcp_services(c, verbose=False)
        if c.run(f"docker-compose top {service}", hide=True).stdout
    ]
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


@task
def get_arrkey(c, service_path, encoding="utf-8"):
    """Retrieve API key for a *arr service"""
    try:
        content = read_file(c, f"{service_path}/config.xml", encoding=encoding)
        return ET.fromstring(content).find("ApiKey").text
    except FileNotFoundError:
        return ""


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
    arrkeys = {
        service: get_arrkey(c, f"/{SERVICES_REMOTE_ROOT}/{service}") for service in arrs
    }
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
