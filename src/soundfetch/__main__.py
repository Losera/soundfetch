"""Module entry point: `python -m soundfetch`.

Added so a consumer can resolve soundfetch through an interpreter it already
knows how to launch, without depending on the `soundfetch` console script
being on PATH. PluginForge's SampleBrowserPanel is the motivating case: the
console script is only ever installed inside a venv, never on PATH, which
made `soundfetch` (the bare executable name) unresolvable to
juce::ChildProcess. `<python> -m soundfetch` needs only a working interpreter
path, which a caller can point at the venv directly.
"""

from soundfetch.cli import main

if __name__ == "__main__":
    main()
