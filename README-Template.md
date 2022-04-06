{% macro details(title) -%}

<details>
    <summary>{{ title }}</summary>
{{ caller() }}
</details>

{%- endmacro -%}

# Home Media Server

This repo contains tools to setup a home media server remotely via [docker-compose](https://docs.docker.com/compose/) and [fabric](https://www.fabfile.org/). It is meant to be a good starting point, not a comprehensive solution. 

The services currently supported are: 
{%- for service_name in service_names %}
- [{{service_name | title}}]({{ services[service_name].link }}): {{ services[service_name].description }}
{%- endfor %}


Docker-compose is used to manage containerized services and fabric is used to deploy/update and configure the remote host by running commands through SSH.

> :warning: This project was only tested on a raspberry pi 3B running headless raspi-os, but should work on other debian/ubuntu distros.

## Requirements

On local machine you'll need python (>= 3.6) and the following packages: 

```
pip install -r requirements.txt
```

The remote is assumed to be a linux machine which can be accessed via SSH. 

## TL;DR

> :warning: Only run these scripts if you trust the numerous sources they use. While most code is ran in docker (so is relatively sandboxed) and comes from well-established, trusted sources (such as [linuxserver](https://www.linuxserver.io/)), some things are installed by piping to bash (notably docker itself). You should always analyse the source for yourself!

To deploy the default services to your host just run (locally):
```
fab deploy -H <user>@<addr> --prompt-for-login-password
```

Then you should be able to simply launch the services by running (on the remote host):
```
dcp up -d
```

The above will pull in the newest images, and run all services in containers. After a few minutes (once everything is initialized), you should be able to see the homer dashboard by visiting `http://<remote-ip>`. Which should look like the following:

<p align="center"> 
  <img width="600" src="screenshots/dashboard.png">
</p>

There are a few other tasks that help you configure services (all `config-*` tasks below), but most services will require some further configuration through their webUI. 

Some useful monitoring tools can also be installed via the tasks `install-ctop/lzd`.

And of course, *everything* is customizable!

## Project Structure

### Running Tasks

The main setup script lives inside [`fabfile.py`](fabfile.py). You can view all available tasks like so:

```
> fab --list
{{ fabric.tasks }}
```

To run an above task on your remote machine you can run:

```
fab <task> [task-args] -H <user>@<addr> --prompt-for-login-password
```

Local commands, such as `render-readme`, need not the `-H` option or any other host related options.

You can also setup a `fabric.yml` config file to hold host information such as user, address and password. See [here](https://docs.fabfile.org/en/latest/concepts/configuration.html) for more information on fabric's config options.

### Service Configuration

The main configuration file is `services.yml`. Inside you'll find a list of services and associated data. If a service enabled, then it will be included in the docker-compose file. This file is templated via [jinja](https://palletsprojects.com/p/jinja/).

*Note:* A service that is marked as `true` is enabled (i.e: `service: true` is equivalent to `service: enabled: true`).

<details>
    <summary>Contents of <code>services.yml</code></summary>

```yaml
{{ services_raw }}
```

</details>

### Secret Management

To not have passwords written in plain text in any config files we use [keyring](https://keyring.readthedocs.io/en/latest/). 

On the command line you need to run:
```
> keyring set system username
```

To set any passwords/secrets you might need. You can then retreive them by using the following syntax in a template: {% raw %}`{{ keyring_get("system", "username") }}`{% endraw %}.

### Docker-compose file

All services run through docker compose. The compose file itself it jinja-templated and uses YAML anchors to reduce config duplication.

Individual services can be enabled/disabled in `services.yml`.

### Profile (bash aliases)

The `.profile` file contains a few useful bash aliases. Feel free to modify.

### Working Directories

By default, all services are configured to be in `/srv/<service name>`, and the media is located at `/mnt/mybook/srv/media/`. These defaults can be edited in `fabfile.py`. 

## Mounting an external disk

See [here](https://pimylifeup.com/raspberry-pi-mount-usb-drive/) for a more in-depth tutorial. The TL;DR is below:
```
# Find disk, get info, make mount dir
lsblk
sudo blkid /dev/sda1
sudo apt install ntfs-3g
sudo mkdir -p /mnt/mybook
```

Then, if in debian (raspi-os), in `/etc/fstab` add the following line:
```
UUID=[UUID] /mnt/mybook [TYPE] defaults,auto,users,rw,nofail,noatime 0 0
```

In ubuntu, you'll want to add the following instead:
```
UUID=<uuid> /mnt/mybook ntfs uid=<userid>,gid=<groupid>,umask=0022,sync,auto,rw 0 0
```

## Default docker-compose settings per service

Here we show the snippet of the docker compose file that is responsible for each service. 

{%- for service_name in service_names %}
{% call details('Compose for %s' % (service_name | title)) %}
```yaml
{{ services[service_name].compose }}
```
{% endcall %}
{%- endfor %}
  

## Troubleshooting & FAQ

{% call details("<i>Raspberry pi can be pinged but does not respond to ssh/http requests.</i>") %}
This is likely due to the PI running out of RAM (i.e: it can't allocate pages for new processes). This can be "fixed" by resizing the swap partition. Try rebooting and running the `resize-swap` task with a larger size (maybe 2048 MB).
{% endcall %}

{% call details("<i>If not needed wifi/bluetooth can be disabled on the PI to save power. This might be required if you have a limited power supply.</i>") %}
In `/boot/config.txt` add the following two lines and reboot:
```
dtoverlay=disable-wifi
dtoverlay=disable-bt
```
{% endcall %}

{% call details("<i>How to add a new service?</i>") %}
You'll need to create an entry in `services.yml` with all the associated fields and add an entry in the docker file and optionally in homer's config. Make sure to wrap these in a jinja if enabled conditional to be able to easily enable/disable the service. 
{% endcall %}

{% call details("<i>I can't see a service's memory consumption!</i>") %}
If `lazy-docker` or `docker stats --no-stream` doesn't show memory consumption, you'll probably need to enable the cgroup memory manager by adding `cgroup_enable=cpuset cgroup_enable=memory cgroup_memory=1` to your `/boot/cmdline.txt` file. See [here](https://github.com/docker/for-linux/issues/1112) for more info.
{% endcall %}

{% call details("<i>If running on a laptop: Closing the lid/screen shutsdown the server.</i>") %}
This will depend on which distro you use. For ubuntu, [see here](https://askubuntu.com/questions/141866/keep-ubuntu-server-running-on-a-laptop-with-the-lid-closed).
{% endcall %}

{% call details("<i>Graphics card not found!</i>") %}
This is likely a driver issue. Check if the card is accessible with `sudo lshw -c video`. If it's there, you [can try this](https://linuxconfig.org/how-to-install-the-nvidia-drivers-on-ubuntu-19-04-disco-dingo-linux).
{% endcall %}

{% call details("<i>My headless install now has a GUI</i>") %}
Installing GPU drivers on ubuntu can cause this. See [here](https://askubuntu.com/questions/1250026) for a fix. 
{% endcall %}

## Changelog

Most recent on top:

- Add Home assistant service (and mosquitto broker) as well as link to octoprint in homer.

- Tweak compose file to allow `pihole` to receive traffic. Add battery/power monitoring tasks. 

- Removed fabfile.helpers in favor of importing tasks via their namespace (i.e: `from fabfile import x` and doing `x.y` instead of `from fabfile.x import y`).

- Fix precommit hooks, split fabfile.misc into misc and status. Make `Ombi` use host networking to help it find all Arrs. Refactor install tasks.

- Refactor all fabric code into a package, tasks are spread across multiple files for easy maintenance. Add a few tasks such as speedtest (and required dockerfile).

- Add backup tasks for all services. Rename `code-server` volume.

- Fix (G)UID for transmission. Add container name field for `gluetun`, `watchtower`, and cronjob for updating containers with `watchtower`. Switch WebUI to flood for transmission (*much* better). 

- Add transmission configuration task and associated files. Now all *arrs can see the directory transmission downloads to as it's in `/media/downloads`.

- Change volumes for *arr stack to enable hardlinks. Removed all references to individual media folders, i.e:`{% raw %}{{ MEDIA_REMOTE_ROOT }}/tv:/tv{% endraw %}` for tv, movies, music, and downloads and replaced them with one volume:`{% raw %}{{ MEDIA_REMOTE_ROOT }}:/media{% endraw %}`.