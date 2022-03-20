import io
import re
import sys
from pathlib import Path

import fabric.main
import invoke.program
import requests
from bs4 import BeautifulSoup
from fabric import task

from fabfile import install
from fabfile.defaults import (
    COMPOSE_FILE,
    COMPOSE_PATH,
    COMPOSE_REMOTE_ROOT,
    DCP,
    HOMER_PATH,
    HOMER_REMOTE_FILE,
    MAX_LINE_LENGTH,
    MEDIA_REMOTE_ROOT,
    PROFILE_FILE,
    PROFILE_PATH,
    SERVICES_PATH,
    SERVICES_REMOTE_ROOT,
)
from fabfile.utils import (
    _clone_or_pull,
    _get_hostname,
    _get_jinja_env,
    _get_service_compose,
    _load_service_config,
    _put_mv,
    _read_file,
    _run,
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
def deploy(c, services_config=None, root=None, force=False, update=False):
    """Install services with docker-compose"""
    if update:
        apt_update(c)
    install.docker_compose(c, force=force)

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
        services[service]["description"] = services[service].get("short_description") or (
            item.text.encode("ascii", "ignore").decode() if item else "Missing Description!"
        )
        services[service]["description"] = services[service]["description"].strip()
        services[service]["link"] = services[service].get("link") or services[service].get("github")

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


@task(help={"check": "Checks if source is formatted without applying changes"})
def format(c, check=False, root=None):
    """Format (python) code on local/host machine at root"""

    # Run isort
    isort_options = " --check-only --diff" if check else ""
    _run(c, f"isort {isort_options} {root or '.'} --profile black")

    # Run Black
    black_options = "--diff --check" if check else ""
    _run(c, f"black --line-length={MAX_LINE_LENGTH} {black_options} {root or '.'}")
