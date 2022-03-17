# Execute bashrc first
if [ -f ~/.bashrc ]; then
	. ~/.bashrc
fi

# Add docker-compose and others to path
export PATH="$HOME/.local/bin:$PATH"
export DOCKER_USER="$(id -u):$(id -g)"
export PUID="$(id -u)"
export PGID="$(id -g)"

# Custom convenience aliases
alias lzd='lazydocker'
alias gits='git status'

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
