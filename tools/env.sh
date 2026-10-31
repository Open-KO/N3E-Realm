# Source from the repository root. No system or desktop settings are modified.
export CARGO_HOME="${N3E_TOOLS:-$PWD/.cache/tools}/cargo"
export RUSTUP_HOME="${N3E_TOOLS:-$PWD/.cache/tools}/rustup"
export PATH="${N3E_TOOLS:-$PWD/.cache/tools}/venv/bin:$CARGO_HOME/bin:$PATH"
export IMGUI="${N3E_TOOLS:-$PWD/.cache/tools}/imgui"
export PATH="${N3E_TOOLS:-$PWD/.cache/tools}/blender:$PATH"
