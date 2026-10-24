"""Use the required Bash runtime and the host's available zsh runtime."""

from pathlib import Path

SHELLS = ("/bin/bash",) + (("/bin/zsh",) if Path("/bin/zsh").is_file() else ())
