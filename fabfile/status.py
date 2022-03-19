import glob
import json
from pathlib import Path

import humanize
from fabric import task

from fabfile.defaults import DCP, DOCKERFILE_PATH
from fabfile.helpers import (
    _status_dcp_running_services,
    _status_get_arrkey,
    _status_get_arrport,
)
from fabfile.utils import (
    _get_service_compose,
    _load_service_config,
    _print_dicts,
    _put_mv,
)


@task(aliases=["bat"])
def battery(c, verbose=False):
    if verbose:
        c.run("upower -i $(upower -e | grep BAT)")
    else:
        c.run('upower -i $(upower -e | grep BAT) | grep --color=never -E "state|to\ full|to\ empty|percentage"')


@task(aliases=["dcp_ls_up"])
def dcp_running_services(c, verbose=True):
    """List running services on remote host"""
    running = _status_dcp_running_services(c)
    if verbose:
        print(f"Running services are: {', '.join(running)}." if running else "No services are running.")
    return running


@task(aliases=["dcp_ls"])
def dcp_services(c, verbose=True):
    """List services in remote's compose file"""
    ret = c.run(f"{DCP} ps --services", hide=True, warn=True)
    services = ret.stdout.splitlines() if ret.ok else []
    if verbose:
        print(f"Services are: {', '.join(services)}" if services else "No services found!")
    return services


@task
def get_arrkey(c, service, encoding="utf-8"):
    """Retrieve API key for an *arr service"""
    return _status_get_arrkey(c, service, encoding=encoding)


@task
def get_arrport(c, service, encoding="utf-8"):
    """Retrieve port for an *arr service"""
    return _status_get_arrport(c, service, encoding=encoding)


@task(incrementable=["verbose"])
def speedtest(c, container="gluetun", verbose=0):
    """Run speedtest in given container, or host if empty"""
    print("Running speedtest", f"through {container}..." if container else "on host...")

    # Make sure all dockerfiles are on remote host
    for path in glob.glob(f"{DOCKERFILE_PATH}/**/*", recursive=True):
        _put_mv(c, path, Path(path).parent)

    # Make sure the image is built, get image hash
    img_hash = c.run(f"docker build -q -t speedtest -f dockerfiles/speedtest.Dockerfile .", hide=True).stdout
    net = f"--net=container:{container}" if container else "--net=host"
    out = json.loads(c.run(f"docker run --rm {net} speedtest", hide=True).stdout)

    if verbose:
        print(json.dumps(out, sort_keys=True, indent=2))

    up = humanize.naturalsize(out["upload"])
    dw = humanize.naturalsize(out["download"])
    print(f"Download {dw}/s, Upload {up}/s")


@task(incrementable=["verbose"])
def verify_vpn(c, verbose=0, full=False, services_config=None, root=None, dcp_path=None):
    """Test that the VPN is connected and it's IP isn't local"""
    running_services = set(dcp_running_services(c, verbose=False))
    if "gluetun" not in running_services:
        raise ValueError("VPN service must be running. Please first run `dcp up -d gluetun`.")

    # The `-T` in dcp exec is needed. See: https://stackoverflow.com/questions/43099116
    c.run(f"{DCP} exec -T gluetun sh -c 'apk add curl'", hide=True)
    vpn = json.loads(c.run(f"{DCP} exec -T gluetun sh -c 'curl https://ipleak.net/json/'", hide=True).stdout)
    local = json.loads(c.run("curl https://ipleak.net/json/", hide=True).stdout)

    if verbose == 1:
        _print_dicts(local, vpn, titles=["Local:", "VPN:"])

    if full or verbose > 1:
        services = _load_service_config(services_config, root)
        usevpn = [
            service
            for service, v in services.items()
            if v["enable"] and "usevpn" in _get_service_compose(service, dcp_path=dcp_path)
        ]
        missing_services = [service for service in usevpn if service not in running_services]
        present_services = [service for service in usevpn if service in running_services]

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
            service: local != vpn and s_vpn["ip"] == vpn["ip"] for service, s_vpn in present_services.items()
        }

        if any(present_services.values()):
            print(f"Services that use VPN: {', '.join(s for s, v in present_services.items() if v)}")
        if not all(present_services.values()):
            print(f"WARNING: services not using VPN: {', '.join(s for s, v in present_services.items() if not v)}")
        if missing_services:
            print("WARNING: The following services were not running, so were not checked:")
            print(", ".join(missing_services))
    print("VPN working correctly." if local != vpn else "VPN not connected!!")
