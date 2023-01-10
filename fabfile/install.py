from fabric import task

from fabfile.utils import _check_run, _get_py_version, _put_mv


@task(default=True, aliases=["install"])
def all(c, force=False):
    """Run all Install sub-tasks"""
    croc(c, force=force)
    ctop(c, force=force)
    docker(c, force=force)
    docker_compose(c, force=force)
    lazydocker(c, force=force)
    python3(c, force=force)
    speedtest(c, force=force)


@task
def ctop(c, force=False):
    """Install top-like interface for container metrics"""
    _check_run(
        c,
        "ctop -v",
        [
            "echo 'deb http://packages.azlux.fr/debian/ buster main' | sudo tee /etc/apt/sources.list.d/azlux.list",
            "wget -qO - https://azlux.fr/repo.gpg.key | sudo apt-key add -",
            "sudo apt update",
            "sudo apt install docker-ctop",
        ],
        on_fail="CTOP is already installed, skipping...",
        sudo=False,
        force=force,
    )


@task
def docker(c, force=False):
    """Install docker if not present"""
    _check_run(
        c,
        "docker -v",
        [
            # "curl -sSL https://get.docker.com | sh"
            "curl -fsSL https://get.docker.com -o get-docker.sh",
            "sh get-docker.sh",
            "usermod -aG docker ${USER}",
            "chmod 666 /var/run/docker.sock" "systemctl enable docker",
            "rm -f get-docker.sh",
        ],
        on_fail="Docker is already installed, skipping...",
        sudo=True,
        force=force,
    )


@task(aliases=["dcp"])
def docker_compose(c, force=False):
    """Install docker-compose if not present"""
    # Call dependencies, this should be done via pre-tasks
    # but theres a bug on windows (https://github.com/fabric/fabric/issues/2202)
    python3(c, force=force)
    docker(c, force=force)
    _check_run(
        c,
        "docker-compose --version",
        "python3 -m pip install docker-compose",
        on_fail="Docker-compose is already installed, skipping...",
        sudo=True,
        force=force,
    )


@task
def elodie(c, force=False):
    """An EXIF-based photo assistant, organizer, manager and workflow automation tool"""
    if c.run("elodie --help", hide=True, warn=True).failed:
        # Install elodie in it's own venv
        python3(c, force=force)
        c.sudo("apt-get install -y python3-venv")
        c.run("python3 -m venv ~/.elodie/venv")

        c.sudo("apt-get install -y libimage-exiftool-perl")
        c.run("git clone https://github.com/jmathai/elodie.git ~/.elodie/src")
        with c.cd(".elodie/src"):
            c.run("~/.elodie/venv/bin/python3 -m pip install -r requirements.txt")

        # Copy over default config used by elodie
        c.run("cp .elodie/src/config.ini-sample .elodie/config.ini")

        # Add elodie executable to path
        _put_mv(
            c,
            '~/.elodie/venv/bin/python3 ~/.elodie/src/elodie.py "$@"\n',
            ".local/bin",
            filename="elodie",
            raw=True,
        )
        c.sudo("chmod +x .local/bin/elodie")
        print("Make sure to edit `~/.elodie/config.ini` for elodie to find location info!")
    else:
        print("Elodie is already installed, skipping...")


@task(aliases=["lzd"])
def lazydocker(c, force=False):
    """Install the lazy docker manager"""
    _check_run(
        c,
        "test -f ~/.local/bin/lazydocker",  # not sure why `lazydocker --version` doesn't work...
        [
            "curl https://raw.githubusercontent.com/jesseduffield/lazydocker/master/scripts/install_update_linux.sh | bash",
            "rm lazydocker",  # Don't worry it's in ~/.local/bin still
        ],
        on_fail="Lazy-docker is already installed, skipping...",
        sudo=True,
        force=force,
    )


@task(aliases=["py3"])
def python3(c, force=False):
    """Install python3 (and pip!) if not present"""
    _check_run(
        c,
        "python3 -m pip -V",
        [
            "apt-get install -y libffi-dev libssl-dev",
            "apt-get install -y python3-dev",
            "apt-get install -y python3 python3-pip ",
        ],
        on_fail="Python3 is already installed, skipping...",
        sudo=True,
        force=force or _get_py_version(c)[0] < 3,
    )


@task
def speedtest(c, force=False):
    """Install Ookla's speedtest client on host"""
    _check_run(
        c,
        "speedtest --version",
        "apt install speedtest-cli",
        on_fail="Speedtest is already installed, skipping...",
        sudo=True,
        force=force,
    )


@task
def croc(c, force=False):
    """Install croc: a tool to send and receive files"""
    _check_run(
        c,
        "croc -v",
        "curl https://getcroc.schollz.com | bash",
        on_fail="Croc is already installed, skipping...",
        sudo=False,
        force=force,
    )


@task
def jc(c, force=False):
    """Install jc, a cli parser for common tools"""
    python3(c, force=force)
    _check_run(
        c,
        "~/.local/bin/jc -v",
        "python3 -m pip install jc",
        on_fail="JC is already installed, skipping...",
        force=force,
    )
