# MB230 hello-world helper aliases
# Add to your shell rc (e.g. ~/.zshrc or ~/.bashrc):
#   source /media/dorin/more_data/work/mb230-vestel/hello-world/shell-aliases.sh
# or copy the alias lines you want.

MB230_HELLO_WORLD_DIR="/media/dorin/more_data/work/mb230-vestel/hello-world"

# Always build the hello-world ARM binary via Docker
alias mb230-hello-build='(cd "$MB230_HELLO_WORLD_DIR" && ./build-docker.sh)'

# Serve hello-world over HTTP for TV wget upload (default port 8000)
alias mb230-hello-serve='(cd "$MB230_HELLO_WORLD_DIR" && python3 -m http.server 8000)'
