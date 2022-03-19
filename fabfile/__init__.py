# Run with: fab <task> -H <user>@<addr> --prompt-for-login-password --prompt-for-sudo-password
from invoke import Collection

from fabfile import backup, configure, install, misc, status

ns = Collection()
ns.add_collection(backup)
ns.add_collection(configure)
ns.add_collection(install)
ns.add_collection(misc)
ns.add_collection(status)
