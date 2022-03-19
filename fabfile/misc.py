import glob
import io
import json
import re
import sys
from pathlib import Path

import fabric.main
import humanize
import invoke.program
import requests
from bs4 import BeautifulSoup
from fabric import task

from fabfile.defaults import (
    COMPOSE_FILE,
    COMPOSE_PATH,
    COMPOSE_REMOTE_ROOT,
    DCP,
    DOCKERFILE_PATH,
    HOMER_PATH,
    HOMER_REMOTE_FILE,
    MEDIA_REMOTE_ROOT,
    PROFILE_FILE,
    PROFILE_PATH,
    SERVICES_PATH,
    SERVICES_REMOTE_ROOT,
)
from fabfile.helpers import (
    _install_docker_compose,
    _misc_dcp_running_services,
    _misc_get_arrkey,
    _misc_get_arrport,
)
from fabfile.utils import (
    _clone_or_pull,
    _get_hostname,
    _get_jinja_env,
    _get_service_compose,
    _load_service_config,
    _print_dicts,
    _put_mv,
    _read_file,
)


@task
def reboot(c):
    """Reboot host machine"""
    c.sudo("reboot")


@task
def apt_update(c):
    """(apt) Update and upgrade system"""
    c.sudo("apt-get update -y")
    c.sudo("apt-get upgrade -y")


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
    running = _misc_dcp_running_services(c)
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
    content = _read_file(c, "/etc/dphys-swapfile", encoding="utf-8")
    content = re.sub(r"CONF_SWAPSIZE=\d+", f"CONF_SWAPSIZE={size}", content, count=1)
    _put_mv(c, content, "/etc", raw=True, filename="dphys-swapfile")
    c.sudo("dphys-swapfile setup")
    c.sudo("dphys-swapfile swapon")
    print("Please reboot host for changes to take effect.")


@task
def get_arrkey(c, service, encoding="utf-8"):
    """Retrieve API key for an *arr service"""
    return _misc_get_arrkey(c, service, encoding=encoding)


@task
def get_arrport(c, service, encoding="utf-8"):
    """Retrieve port for an *arr service"""
    return _misc_get_arrport(c, service, encoding=encoding)


@task
def deploy(c, services_config=None, root=None, force=False, update=False):
    """Install services with docker-compose"""
    if update:
        apt_update(c)
    _install_docker_compose(c, force=force)

    # Get dashboard icons, create /srv directory
    _clone_or_pull(
        c,
        "https://github.com/walkxhub/dashboard-icons.git",
        f"{SERVICES_REMOTE_ROOT}/dashboard-icons/",
    )

    # Move and render docker-compose and .profile
    env = _get_jinja_env(root)
    services = _load_service_config(services_config, root)
    dcp = env.get_template(str(COMPOSE_PATH))
    dcp = dcp.render(
        **services,
        MEDIA_REMOTE_ROOT=MEDIA_REMOTE_ROOT,
        SERVICES_REMOTE_ROOT=SERVICES_REMOTE_ROOT,
    )
    _put_mv(c, dcp, COMPOSE_REMOTE_ROOT, raw=True, filename=COMPOSE_FILE)

    # Upload and source profile script
    profile = env.get_template(str(PROFILE_PATH))
    profile = profile.render(DCP=DCP)
    _put_mv(c, profile, "~", raw=True, filename=PROFILE_FILE)
    c.run(f"source {PROFILE_FILE}")

    # Render homer's config and upload it
    homer_config = env.get_template(str(HOMER_PATH))
    homer_config = homer_config.render(
        **services,
        hostname=_get_hostname(c),
    )
    _put_mv(
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


@task
def render_readme(_, services_config=None, root=None, dcp_path=None):
    """Update code segments in the README file (runs on local)"""
    # Get list of services (raw as well), and dcp conf
    env = _get_jinja_env(root)
    services = _load_service_config(services_config, root)
    service_names = list(services.keys())
    with open(Path(root or "./") / (services_config or str(SERVICES_PATH)), "r") as f:
        services_raw = f.read()

    # Get compose args for each service
    for service in services:
        services[service]["compose"] = _get_service_compose(service, dcp_path=dcp_path)

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
def speedtest(c, container="gluetun", verbose=0):
    """Run speedtest in given container, or host if empty"""
    print("Running speedtest", f"through {container}..." if container else "on host...")

    # Make sure all dockerfiles are on remote host
    for path in glob.glob(f"{DOCKERFILE_PATH}/**/*", recursive=True):
        _put_mv(c, path, Path(path).parent)

    # Make sure the image is built, get image hash
    img_hash = c.run(
        f"docker build -q -t speedtest -f dockerfiles/speedtest.Dockerfile .", hide=True
    ).stdout
    net = f"--net=container:{container}" if container else "--net=host"
    out = json.loads(c.run(f"docker run --rm {net} speedtest", hide=True).stdout)

    if verbose:
        print(json.dumps(out, sort_keys=True, indent=2))

    up = humanize.naturalsize(out["upload"])
    dw = humanize.naturalsize(out["download"])
    print(f"Download {dw}/s, Upload {up}/s")


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
        _print_dicts(local, vpn, titles=["Local:", "VPN:"])

    if full or verbose > 1:
        services = _load_service_config(services_config, root)
        usevpn = [
            service
            for service, v in services.items()
            if v["enable"]
            and "usevpn" in _get_service_compose(service, dcp_path=dcp_path)
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
            _print_dicts(
                local,
                vpn,
                *present_services.values(),
                titles=["Local:", "VPN:"] + [s.title() + ":" for s in present_services],
            )
        elif verbose == 1:
            _print_dicts(local, vpn, titles=["Local:", "VPN:"])

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
