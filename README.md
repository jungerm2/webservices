# Home Media Server

This repo contains tools to setup a home media server remotely via [docker-compose](https://docs.docker.com/compose/) and [fabric](https://www.fabfile.org/). It is meant to be a good starting point, not a comprehensive solution. 

The services currently supported are:
- [Homer](https://github.com/bastienwirtz/homer): A very simple static homepage for your server.
- [Mcserver](None): Missing Description!
- [Pihole](https://github.com/pi-hole/pi-hole): A black hole for Internet advertisements
- [Mealie](https://github.com/mealie-recipes/mealie): Mealie is a self hosted recipe manager and meal planner with a RestAPI backend and a reactive frontend application built in Vue for a pleasant user experience for the whole family. Easily add recipes into your database by providing the url and mealie will automatically import the relevant data or add a family recipe with the UI editor
- [Duckdns](https://www.duckdns.org/): Missing Description!
- [Code_server](https://github.com/coder/code-server): VS Code in the browser
- [Homeassistant](https://github.com/home-assistant/core): Open source home automation that puts local control and privacy first.
- [Filebrowser](https://github.com/filebrowser/filebrowser): Web File Browser
- [Plex](https://www.plex.tv/): Plex organizes all of your personal media so you can enjoy it no matter where you are.
- [Jellyfin](https://github.com/jellyfin/jellyfin): The Free Software Media System
- [Ombi](https://github.com/Ombi-app/Ombi): Want a Movie or TV Show on Plex/Emby/Jellyfin? Use Ombi!
- [Prowlarr](https://github.com/Prowlarr/Prowlarr): Indexer manager/proxy built on the popular *arr stack
- [Radarr](https://github.com/Radarr/Radarr): Movie organizer/manager for usenet and torrent users.
- [Sonarr](https://github.com/Sonarr/Sonarr): Smart PVR for newsgroup and bittorrent users.
- [Lidarr](https://github.com/Lidarr/Lidarr): Looks and smells like Sonarr but made for music.
- [Bazarr](https://github.com/morpheus65535/bazarr): Bazarr is a companion application to Sonarr and Radarr. It manages and downloads subtitles based on your requirements. You define your preferences by TV show or movie and Bazarr takes care of everything for you.
- [Wireguard](https://github.com/linuxserver/docker-wireguard): An extremely simple yet fast and modern VPN that utilizes state-of-the-art cryptography.
- [Gluetun](https://github.com/qdm12/gluetun): VPN client in a thin Docker container for multiple VPN providers, written in Go, and using OpenVPN or Wireguard, DNS over TLS, with a few proxy servers built-in.
- [Transmission](https://github.com/transmission/transmission): A fast, easy, and free BitTorrent client.
- [Wgeasy](https://github.com/WeeJeWel/wg-easy): The easiest way to run WireGuard VPN + Web-based Admin UI.
- [Watchtower](https://github.com/containrrr/watchtower): A process for automating Docker container base image updates.
- [Glances](https://github.com/nicolargo/glances): Glances an Eye on your system. A top/htop alternative for GNU/Linux, BSD, Mac OS and Windows operating systems.
- [Tautulli](https://github.com/Tautulli/Tautulli): A Python based monitoring and tracking tool for Plex Media Server.


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
fab misc.deploy -H <user>@<addr> --prompt-for-login-password
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
Available tasks:

  backup.all (backup, backup.backup)               Run all backup subtasks
  backup.arr-path                                  Return path of a recent *arr backup, create a new one if needed
  backup.arrs                                      Copy remote *arr backup directories to `backup/`
  backup.code-server                               Make a backup of code-server data
  backup.gluetun                                   Make a backup of gluetun data
  backup.homer                                     Make a backup of homer data
  backup.ombi                                      Make a backup of ombi data
  backup.pihole                                    Make a backup of pihole data
  backup.plex                                      Make a backup of plex data while skipping cache data
  backup.restore-simple                            Upload and unzip all not arr backups
  backup.tautulli                                  Make a backup of tautulli data
  backup.transmission                              Make a backup of transmission data
  backup.wgeasy                                    Make a backup of wgeasy data
  backup.wireguard                                 Make a backup of wireguard data
  configure.homer                                  Fetch and add apikey to homer dashboard for *arr apps
  configure.mosquitto
  configure.plex                                   Claim plex server, see: `https://www.plex.tv/claim/`
  configure.transmission (configure.transm)        Upload transmission's `settings.json` to host
  configure.wireguard (configure.wg)               Upload wireguard config (i.e: wg0.conf) to host
  install.all (install, install.install)           Run all Install sub-tasks
  install.croc                                     Install croc: a tool to send and receive files
  install.docker                                   Install docker if not present
  install.docker-compose (install.dcp)             Install docker-compose if not present
  install.elodie                                   An EXIF-based photo assistant, organizer, manager and workflow automation tool
  install.jc                                       Install jc, a cli parser for common tools
  install.lazydocker (install.lzd)                 Install the lazy docker manager
  install.python3 (install.py3)                    Install python3 (and pip!) if not present
  install.speedtest                                Install Ookla's speedtest client on host
  misc.apt-update                                  (apt) Update and upgrade system
  misc.clear-metadata
  misc.deploy                                      Install services with docker-compose
  misc.format                                      Format (python) code on local/host machine at root
  misc.reboot                                      Reboot host machine
  misc.render-readme                               Update code segments in the README file (runs on local)
  misc.set-swap-size (misc.resize-swap)            Set swap partition size on remote (in MB)
  status.bat-power                                 Get instantaneous power draw from/to battery.
  status.battery (status.bat)                      Show battery level and status (if available)
  status.dcp-running-services (status.dcp-ls-up)   List running services on remote host
  status.dcp-services (status.dcp-ls)              List services in remote's compose file
  status.get-arrkey                                Retrieve API key for an *arr service
  status.get-arrport                               Retrieve port for an *arr service
  status.speedtest                                 Run speedtest in given container, or host if empty
  status.vpn                                       Test that the VPN is connected and it's IP isn't local


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
# HOMEPAGE
homer:
  enable: true
  github: https://github.com/bastienwirtz/homer

# MINECRAFT
mcserver:
  enable: true

# QoL SERVICES
pihole:
  enable: true
  webpassword: {{ keyring_get("webserver", "pihole") }}
  github: https://github.com/pi-hole/pi-hole
mealie:
  enable: true
  github: https://github.com/mealie-recipes/mealie
duckdns:
  enable: true
  link: https://www.duckdns.org/
  token: {{ keyring_get("webserver", "duckdns-token") }}
  subdomains: {{ keyring_get("webserver", "duckdns-subdomains") }}
code-server:
  enable: false
  github: https://github.com/coder/code-server
homeassistant:
  enable: true
  github: https://github.com/home-assistant/core
filebrowser:
  enable: true
  github: https://github.com/filebrowser/filebrowser

# MEDIA SERVERS
plex:
  enable: true
  short_description: "Plex organizes all of your personal media so you can enjoy it no matter where you are."
  link: https://www.plex.tv/
  claim: ""
jellyfin:
  enable: true
  github: https://github.com/jellyfin/jellyfin
ombi:
  enable: false
  github: https://github.com/Ombi-app/Ombi

# TRACKERS
prowlarr:
  enable: true
  github: https://github.com/Prowlarr/Prowlarr
  short_description: "Indexer manager/proxy built on the popular *arr stack"
  apikey: {{ keyring_get("webserver", "prowlarr-apikey") }}
radarr:
  enable: true
  github: https://github.com/Radarr/Radarr
  apikey: {{ keyring_get("webserver", "radarr-apikey") }}
sonarr:
  enable: true
  github: https://github.com/Sonarr/Sonarr
  apikey: {{ keyring_get("webserver", "sonarr-apikey") }}
lidarr:
  enable: false
  github: https://github.com/Lidarr/Lidarr
  apikey: {{ keyring_get("webserver", "lidarr-apikey") }}
bazarr:
  enable: true
  github: https://github.com/morpheus65535/bazarr
  apikey: {{ keyring_get("webserver", "bazarr-apikey") }}

# DOWNLOADERS & VPNs
wireguard:
  enable: false
  github: https://github.com/linuxserver/docker-wireguard
  short_description: "An extremely simple yet fast and modern VPN that utilizes state-of-the-art cryptography."
gluetun:
  enable: true
  provider: {{ keyring_get("webserver", "vpn-provider") }}
  user: {{ keyring_get("webserver", "vpn-usr") }}
  password: {{ keyring_get("webserver", "vpn-pass") }}
  github: https://github.com/qdm12/gluetun
transmission:
  enable: true
  user: {{ keyring_get("webserver", "transmission-usr") }}
  password: {{ keyring_get("webserver", "transmission-pass") }}
  github: https://github.com/transmission/transmission
  short_description: "A fast, easy, and free BitTorrent client."
wgeasy:
  enable: true
  password: {{ keyring_get("webserver", "wg-easy-pass") }}
  wanip: {{ keyring_get("webserver", "duckdns-subdomains") }}.duckdns.org
  github: https://github.com/WeeJeWel/wg-easy

# MAINTENANCE & MONITORING
watchtower:
  enable: true
  github: https://github.com/containrrr/watchtower
glances:
  enable: true
  github: https://github.com/nicolargo/glances
tautulli:
  enable: false
  github: https://github.com/Tautulli/Tautulli

```

</details>

### Secret Management

To not have passwords written in plain text in any config files we use [keyring](https://keyring.readthedocs.io/en/latest/). 

On the command line you need to run:
```
> keyring set system username
```

To set any passwords/secrets you might need. You can then retreive them by using the following syntax in a template: `{{ keyring_get("system", "username") }}`.

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
<details>
    <summary>Compose for Homer</summary>

```yaml
homer:
  image: b4bz/homer
  container_name: homer
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/homer:/www/assets
    - {{ SERVICES_REMOTE_ROOT }}/dashboard-icons:/www/assets/dashboard-icons
  ports:
    - 80:8080
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Mcserver</summary>

```yaml
mcserver:
  image: marctv/minecraft-papermc-server:latest
  container_name: mcserver
  stdin_open: true
  tty: true
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/mcserver:/data:rw
  ports:
    - 25565:25565
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
    - MEMORYSIZE=6G
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Pihole</summary>

```yaml
pihole:
  container_name: pihole
  image: pihole/pihole:latest
  hostname: piholevm
  ports:
    - "53:53/tcp"
    - "53:53/udp"
    - "8081:80/tcp"
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
    - WEBPASSWORD={{ pihole.webpassword }}
    - DNSMASQ_LISTENING=all  # Very important! Otherwise no requests get processed!
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/pihole/etc/pihole:/etc/pihole
    - {{ SERVICES_REMOTE_ROOT }}/pihole/etc/dnsmasq.d:/etc/dnsmasq.d
    - {{ SERVICES_REMOTE_ROOT }}/pihole/backups:/backups
  cap_add:
    - NET_ADMIN
  dns:
    - 127.0.0.1
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Mealie</summary>

```yaml
mealie:
  container_name: mealie
  image: hkotel/mealie:latest
  ports:
    - 9925:80
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/mealie:/app/data
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Duckdns</summary>

```yaml
duckdns:
  image: lscr.io/linuxserver/duckdns:latest
  container_name: duckdns
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
    - SUBDOMAINS={{ duckdns.subdomains }}
    - TOKEN={{ duckdns.token }}
    - LOG_FILE=true
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/duckdns:/config
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Code_server</summary>

```yaml
code-server:
  image: lscr.io/linuxserver/code-server
  container_name: code-server
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
    - DEFAULT_WORKSPACE=/home
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/code-server:/config
    - ~/workspace:/home
    - {{ SERVICES_REMOTE_ROOT }}/homer/:/home/homer
  ports:
    - 8443:8443
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Homeassistant</summary>

```yaml
homeassistant:
  container_name: homeassistant
  image: "ghcr.io/home-assistant/home-assistant:stable"
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/homeassistant:/config
    - /etc/localtime:/etc/localtime:ro
  restart: unless-stopped
  privileged: true
  network_mode: host
  depends_on: [ "mosquitto", ]
mosquitto:
  container_name: mosquitto
  image: eclipse-mosquitto
  network_mode: host
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/homeassistant/addons/mosquitto:/mosquitto
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Filebrowser</summary>

```yaml
filebrowser:
  image: filebrowser/filebrowser
  container_name: filebrowser
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
  ports:
    - 8080:80
  volumes:
    - {{ MEDIA_REMOTE_ROOT }}:/srv
    - {{ SERVICES_REMOTE_ROOT }}/filebrowser/config:/config
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Plex</summary>

```yaml
plex:
  image: lscr.io/linuxserver/plex
  container_name: plex
  network_mode: host
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
    - VERSION=docker
    {% if plex.claim %}
    - PLEX_CLAIM={{ plex.claim }}
    
```

</details>
<details>
    <summary>Compose for Jellyfin</summary>

```yaml
jellyfin:
  image: lscr.io/linuxserver/jellyfin:latest
  container_name: jellyfin
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
    # - JELLYFIN_PublishedServerUrl=192.168.0.5 #optional
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/jellyfin:/config
    - {{ MEDIA_REMOTE_ROOT }}/movies:/data/movies
    - {{ MEDIA_REMOTE_ROOT }}/tv:/data/tvshows
  ports:
    - 8096:8096
    - 8920:8920 #optional
    - 7359:7359/udp #optional
    - 1900:1900/udp #optional
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Ombi</summary>

```yaml
ombi:
  image: lscr.io/linuxserver/ombi
  container_name: ombi
  # Use host mode so it can easily find *arrs
  network_mode: host
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/ombi:/config
  # ports:
  #   - 3579:3579
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Prowlarr</summary>

```yaml
prowlarr:
  # Note: use dev branch as there is no master branch atm
  image: lscr.io/linuxserver/prowlarr:develop
  container_name: prowlarr
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/prowlarr:/config
  <<: *usevpn
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Radarr</summary>

```yaml
radarr:
  image: lscr.io/linuxserver/radarr
  container_name: radarr
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/radarr:/config
    - {{ MEDIA_REMOTE_ROOT }}:/media
  <<: *usevpn
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Sonarr</summary>

```yaml
sonarr:
  image: lscr.io/linuxserver/sonarr
  container_name: sonarr
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/sonarr:/config
    - {{ MEDIA_REMOTE_ROOT }}:/media
  <<: *usevpn
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Lidarr</summary>

```yaml
lidarr:
  image: lscr.io/linuxserver/lidarr
  container_name: lidarr
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/lidarr:/config
    - {{ MEDIA_REMOTE_ROOT }}:/media
  <<: *usevpn
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Bazarr</summary>

```yaml
bazarr:
  image: lscr.io/linuxserver/bazarr
  container_name: bazarr
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/bazarr:/config
    - {{ MEDIA_REMOTE_ROOT }}:/media
  <<: *usevpn
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Wireguard</summary>

```yaml
network_mode: "service:wireguard"
depends_on: [ "wireguard", ]
{%- elif gluetun.enable %}
network_mode: "service:gluetun"
depends_on: [ "gluetun", ]
```

</details>
<details>
    <summary>Compose for Gluetun</summary>

```yaml
gluetun:
  image: qmcgaw/gluetun
  container_name: gluetun
  cap_add:
    - NET_ADMIN
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/gluetun:/gluetun
  environment:
    - VPN_SERVICE_PROVIDER={{ gluetun.provider }}
    - OPENVPN_USER={{ gluetun.user }}
    - OPENVPN_PASSWORD={{ gluetun.password }}
  <<: *vpnports
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Transmission</summary>

```yaml
transmission:
  image: ghcr.io/linuxserver/transmission
  container_name: transmission
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
    - TRANSMISSION_WEB_HOME=/flood-for-transmission
    - USER={{ transmission.user }}
    - PASS={{ transmission.password }}
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/transmission:/config
    - {{ SERVICES_REMOTE_ROOT }}/flood-for-transmission:/flood-for-transmission
    - {{ MEDIA_REMOTE_ROOT }}/downloads:/media/downloads
  <<: *usevpn
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Wgeasy</summary>

```yaml
wg-easy:
  environment:
    - WG_HOST={{ wgeasy.wanip }}
    - PASSWORD={{ wgeasy.password }}
    - WG_DEFAULT_DNS=1.1.1.1
  image: weejewel/wg-easy
  container_name: wg-easy
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/wgeasy:/etc/wireguard
  ports:
    - "51820:51820/udp"
    - "51821:51821/tcp"
  restart: always
  cap_add:
    - NET_ADMIN
    - SYS_MODULE
  sysctls:
    - net.ipv4.ip_forward=1
    - net.ipv4.conf.all.src_valid_mark=1
```

</details>
<details>
    <summary>Compose for Watchtower</summary>

```yaml
watchtower:
  image: containrrr/watchtower
  container_name: watchtower
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
  environment:
    # This cron expression needs to be 6 fields long, not the default 5
    # "At 04:00 AM, only on Monday", see: https://crontab.cronhub.io/
    - WATCHTOWER_SCHEDULE=0 0 4 * * 1
    - WATCHTOWER_CLEANUP="true"
    - TZ=America/Chicago
```

</details>
<details>
    <summary>Compose for Glances</summary>

```yaml
glances:
  image: nicolargo/glances:latest
  container_name: glances
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock:ro
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
    - GLANCES_OPT=-w
  ports:
    - 61208:61208
    - 61209:61209
  restart: unless-stopped
```

</details>
<details>
    <summary>Compose for Tautulli</summary>

```yaml
tautulli:
  image: ghcr.io/tautulli/tautulli
  container_name: tautulli
  volumes:
    - {{ SERVICES_REMOTE_ROOT }}/tautulli:/config
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=America/Chicago
  ports:
    - 8181:8181
  restart: unless-stopped
```

</details>
  

## Troubleshooting & FAQ

<details>
    <summary><i>PiHole not working on Ubuntu/Fedora.</i></summary>

See [here](https://github.com/pi-hole/docker-pi-hole#installing-on-ubuntu-or-fedora).

</details>

<details>
    <summary><i>Conected to wgeasy but no internet.</i></summary>

Make sure to open the correct port on your network. By default you need to port-forward port 51820. 

</details>

<details>
    <summary><i>Raspberry pi can be pinged but does not respond to ssh/http requests.</i></summary>

This is likely due to the PI running out of RAM (i.e: it can't allocate pages for new processes). This can be "fixed" by resizing the swap partition. Try rebooting and running the `resize-swap` task with a larger size (maybe 2048 MB).

</details>

<details>
    <summary><i>If not needed wifi/bluetooth can be disabled on the PI to save power. This might be required if you have a limited power supply.</i></summary>

In `/boot/config.txt` add the following two lines and reboot:
```
dtoverlay=disable-wifi
dtoverlay=disable-bt
```

</details>

<details>
    <summary><i>How to add a new service?</i></summary>

You'll need to create an entry in `services.yml` with all the associated fields and add an entry in the docker file and optionally in homer's config. Make sure to wrap these in a jinja if enabled conditional to be able to easily enable/disable the service. 

</details>

<details>
    <summary><i>I can't see a service's memory consumption!</i></summary>

If `lazy-docker` or `docker stats --no-stream` doesn't show memory consumption, you'll probably need to enable the cgroup memory manager by adding `cgroup_enable=cpuset cgroup_enable=memory cgroup_memory=1` to your `/boot/cmdline.txt` file. See [here](https://github.com/docker/for-linux/issues/1112) for more info.

</details>

<details>
    <summary><i>If running on a laptop: Closing the lid/screen shutsdown the server.</i></summary>

This will depend on which distro you use. For ubuntu, [see here](https://askubuntu.com/questions/141866/keep-ubuntu-server-running-on-a-laptop-with-the-lid-closed).

</details>

<details>
    <summary><i>Graphics card not found!</i></summary>

This is likely a driver issue. Check if the card is accessible with `sudo lshw -c video`. If it's there, you [can try this](https://linuxconfig.org/how-to-install-the-nvidia-drivers-on-ubuntu-19-04-disco-dingo-linux).

</details>

<details>
    <summary><i>My headless install now has a GUI</i></summary>

Installing GPU drivers on ubuntu can cause this. See [here](https://askubuntu.com/questions/1250026) for a fix. 

</details>

## Changelog

Most recent on top:

- Add wgeasy vpn service.

- Add Home assistant service (and mosquitto broker) as well as link to octoprint in homer.

- Tweak compose file to allow `pihole` to receive traffic. Add battery/power monitoring tasks. 

- Removed fabfile.helpers in favor of importing tasks via their namespace (i.e: `from fabfile import x` and doing `x.y` instead of `from fabfile.x import y`).

- Fix precommit hooks, split fabfile.misc into misc and status. Make `Ombi` use host networking to help it find all Arrs. Refactor install tasks.

- Refactor all fabric code into a package, tasks are spread across multiple files for easy maintenance. Add a few tasks such as speedtest (and required dockerfile).

- Add backup tasks for all services. Rename `code-server` volume.

- Fix (G)UID for transmission. Add container name field for `gluetun`, `watchtower`, and cronjob for updating containers with `watchtower`. Switch WebUI to flood for transmission (*much* better). 

- Add transmission configuration task and associated files. Now all *arrs can see the directory transmission downloads to as it's in `/media/downloads`.

- Change volumes for *arr stack to enable hardlinks. Removed all references to individual media folders, i.e:`{{ MEDIA_REMOTE_ROOT }}/tv:/tv` for tv, movies, music, and downloads and replaced them with one volume:`{{ MEDIA_REMOTE_ROOT }}:/media`.