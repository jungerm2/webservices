# ~/.profile: executed by the command interpreter for login shells.
# This file is not read by bash(1), if ~/.bash_profile or ~/.bash_login
# exists.
# see /usr/share/doc/bash/examples/startup-files for examples.
# the files are located in the bash-doc package.

# if running bash
if [ -n "$BASH_VERSION" ]; then
    # include .bashrc if it exists
    if [ -f "$HOME/.bashrc" ]; then
        . "$HOME/.bashrc"
    fi
fi

# set PATH so it includes user's private bin if it exists
if [ -d "$HOME/bin" ] ; then
    PATH="$HOME/bin:$PATH"
fi

# set PATH so it includes user's private bin if it exists
if [ -d "$HOME/.local/bin" ] ; then
    PATH="$HOME/.local/bin:$PATH"
fi

# Add cargo to path
. "$HOME/.cargo/env"

# Compute checksum of all files in directory
# $1 is the directory to archive
function hashdirtree () {
    find $1 -type f -exec sha256sum {} \; | sort -k 2 | sha256sum
}


# Add docker-compose and others to path
export PATH="$HOME/.local/bin:$PATH"
export DOCKER_USER="$(id -u):$(id -g)"
export PUID="$(id -u)"
export PGID="$(id -g)"

# Custom convenience aliases
alias lzd='lazydocker'
alias gits='git status'

# Check battery level (only tested on ubuntu), see: https://askubuntu.com/questions/69556
alias battery-lvl='upower -i $(upower -e | grep BAT) | grep --color=never -E "state|to\ full|to\ empty|percentage"'

# Taken from https://perfectmediaserver.com/index.html
# Tail last 50 lines of docker logs
alias dtail='docker logs -tf --tail='50' '

# This alias prints the IP, network and listening ports for each container
alias dcips={% raw %}$'docker inspect -f \'{{.Name}}-{{range  $k, $v := .NetworkSettings.Networks}}{{$k}}-{{.IPAddress}} {{end}}-{{range $k, $v := .NetworkSettings.Ports}}{{ if not $v }}{{$k}} {{end}}{{end}} -{{range $k, $v := .NetworkSettings.Ports}}{{ if $v }}{{$k}} => {{range . }}{{ .HostIp}}:{{.HostPort}}{{end}}{{end}} {{end}}\' $(docker ps -aq) | column -t -s-'{% endraw %}

# Shorthand, customise docker-compose.yaml location as needed
alias dcp='{{ DCP }} '

# Remove unused images (useful after an upgrade)
alias dprune='docker image prune'

# Remove unused images, unused networks *and data* (use with care)
alias dprunesys='docker system prune --all'

alias dcp-refresh='dcp down && dprune -f && dcp up -d'
alias dcp-refresh-sys='dcp down && dprunesys -f && dcp up -d'
