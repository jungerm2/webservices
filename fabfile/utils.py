import inspect
import io
import itertools
import json
import posixpath
import re
from pathlib import Path
from stat import S_ISDIR, S_ISREG
from xml.etree import ElementTree as ET

import keyring
from jinja2 import Environment, FileSystemLoader, select_autoescape
from ruamel.yaml import YAML

from fabfile.defaults import COMPOSE_PATH, LOCAL_ROOT, SERVICES_PATH


def _get_hostname(c):
    ips = c.run("hostname -I", hide=True).stdout.split(" ")
    return ips[0]


def _dcp_is_up(c):
    ret = c.run("docker-compose top", hide=True, warn=True)
    return ret.ok and ret.stdout


def _clone_or_pull(c, addr, path):
    # Make sure git is installed
    if c.run("git --version", hide=True, warn=True).failed:
        c.sudo("apt-get install git -y")

    # Only clone repo if not present, only allow fast-forward (i.e: no merge)
    c.sudo(f"mkdir -p {path}")
    if c.sudo(f"git -C {path} pull --ff-only", warn=True).failed:
        c.sudo(f"git clone {addr} {path}")


def _put_mv(c, path_or_data, target_dir, raw=False, filename=None):
    """Upload file at `path_or_data` to remote's `target_dir`.
    This operation is done as a temporary put then a move because
    we might not have permissions to upload to `target_dir`.
    If `raw` then treat `path_or_data` as a data stream/string."""
    if raw and not filename:
        raise ValueError("Argument `filename` is required when `raw`=True")
    filename = Path(path_or_data).name if not raw else filename
    c.put(io.StringIO(path_or_data) if raw else path_or_data, str(filename))
    c.sudo(f"mkdir -p {target_dir}")
    c.sudo(f"mv ~/{filename} {target_dir}", warn=True)


def _get_py_version(c):
    v = c.run(
        "python -V || python3 -V || echo 'Default 0.0.0'", hide=True, warn=True
    ).stdout.split(" ")[-1]
    return [int(i) for i in v.split(".")]


def _get_jinja_env(root=None):
    # Create templating engine environment
    return Environment(
        loader=FileSystemLoader(root or LOCAL_ROOT), autoescape=select_autoescape()
    )


def _load_service_config(services_config=None, root=None):
    # Preprocess services.yml, fill out any secrets with `keyring`
    env = _get_jinja_env(root)
    services = env.get_template(services_config or str(SERVICES_PATH), "r")
    services = services.render(keyring_get=keyring.get_password)

    # Load services config, expand enable option
    services = YAML(typ="safe").load(services)
    services = {
        k: v if type(v) is not bool else {"enable": v} for k, v in services.items()
    }
    return {k.replace("-", "_"): v for k, v in services.items()}


def _read_file(c, path, encoding="utf-8", raw=False):
    """Read remote file into a memory buffer"""
    f = io.BytesIO()
    c.get(path, f)
    return f.getvalue().decode(encoding) if not raw else f.getvalue()


def _total_files(c, dir):
    return int(c.run(f"find {dir} -type f | wc -l", hide=True).stdout)


def _get_xml_value(c, path, key, encoding="utf-8", default=None):
    """Given a path to a remote XML file and a key, retrieve it's value."""
    try:
        content = _read_file(c, path, encoding=encoding)
        return ET.fromstring(content).find(key).text
    except FileNotFoundError:
        return default


def _remote_walk(c, root, exclude_dirs=None):
    """Like os.walk but for the remote host!"""
    exclude_dirs = set(exclude_dirs or [])
    root = c.sftp().normalize(root)
    for entry in c.sftp().listdir(root):
        pathname = posixpath.join(root, entry)
        mode = c.sftp().stat(pathname).st_mode
        if S_ISDIR(mode):
            # It's a directory!
            if pathname not in exclude_dirs:
                yield from _remote_walk(c, pathname, exclude_dirs=exclude_dirs)
        elif S_ISREG(mode):
            # It's a file!
            yield pathname


def _get_service_compose(service, dcp_path=None):
    """Given a service name, extract it's docker compose config as text"""
    with open(dcp_path or str(COMPOSE_PATH), "r") as f:
        pattern = (
            rf"{{%-?\s+if\s+{service.lower()}\.enable\s+%}}(.*?){{%-?\s+endif\s+%}}"
        )
        matches = re.findall(pattern, f.read(), re.IGNORECASE | re.DOTALL)
        return inspect.cleandoc(matches[0]) if matches else "Compose not found!"


def _print_dicts(*dicts, titles=None, sep="\t", sort_keys=True, indent=2):
    """Print dictionaries side by side"""
    if titles is not None and len(titles) != len(dicts):
        raise ValueError("Titles must be same length as dicts.")
    dicts = [json.dumps(d, sort_keys=sort_keys, indent=indent) for d in dicts]
    max_lens = [max(len(l) for l in d.splitlines()) for d in dicts]
    dicts = [d.splitlines() for d in dicts]
    for parts in itertools.chain([titles], itertools.zip_longest(*dicts, fillvalue="")):
        padded = [p + " " * (max_lens[i] - len(p)) for i, p in enumerate(parts)]
        print(sep.join(padded))
