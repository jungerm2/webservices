from fabric import task

from fabfile.helpers import _install_docker, _install_docker_compose, _install_python3


@task(default=True, aliases=["install"])
def all(c, force=False):
    ctop(c, force=force)
    docker(c, force=force)
    docker_compose(c, force=force)
    lazydocker(c, force=force)
    python3(c, force=force)


@task
def ctop(c, force=False):
    """Install top-like interface for container metrics"""
    if c.run("ctop -v", hide=True, warn=True).failed or force:
        c.sudo(
            "echo 'deb http://packages.azlux.fr/debian/ buster main' | sudo tee /etc/apt/sources.list.d/azlux.list"
        )
        c.sudo("wget -qO - https://azlux.fr/repo.gpg.key | sudo apt-key add -")
        c.sudo("apt update")
        c.sudo("apt install docker-ctop")
    else:
        print("CTOP is already installed, skipping...")


@task
def docker(c, force=False):
    """Install docker if not present"""
    _install_docker(c, force=force)


@task(aliases=["dcp"])
def docker_compose(c, force=False):
    """Install docker-compose if not present"""
    _install_docker_compose(c, force=force)


@task(aliases=["lzd"])
def lazydocker(c, force=False):
    """Install the lazy docker manager"""
    if c.run("lazydocker --version", hide=True, warn=True).failed or force:
        c.run(
            "curl https://raw.githubusercontent.com/jesseduffield/lazydocker/master/scripts/install_update_linux.sh | bash"
        )
        c.run("rm lazydocker")  # Don't worry it's in ~/.local/bin still
    else:
        print("Lazy-docker is already installed, skipping...")


@task(aliases=["py3"])
def python3(c, force=False):
    """Install python3 (and pip!) if not present"""
    _install_python3(c, force=force)
