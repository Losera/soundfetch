"""soundfetch agent tool adapters — pre-built wrappers for LangChain,
LlamaIndex, and Smolagents.

Each entry-point function returns a list of framework-native tool
objects wrapping the same underlying ``soundfetch`` MCP functions::

    # LangChain
    from soundfetch.adapters import langchain_tools
    tools = langchain_tools()

    # LlamaIndex
    from soundfetch.adapters import llamaindex_tools
    tools = llamaindex_tools()

    # Smolagents
    from soundfetch.adapters import smolagents_tools
    tools = smolagents_tools()

All three expose the same four tools::

    search_sounds        — search a provider, return JSON results
    download_manifest    — download sounds from a manifest
    check_provider_status — check provider configuration
    list_sources         — list available providers

Framework imports are lazy — none of ``langchain-core``, ``llama-index-core``,
or ``smolagents`` is pulled in until you call the corresponding function.
"""

__all__ = ["langchain_tools", "llamaindex_tools", "smolagents_tools"]


def langchain_tools():
    """Return soundfetch tools as LangChain StructuredTool objects.

    Requires ``pip install "soundfetch[langchain]"``.
    """
    from .langchain import build_tools
    return build_tools()


def llamaindex_tools():
    """Return soundfetch tools as LlamaIndex FunctionTool objects.

    Requires ``pip install "soundfetch[llamaindex]"``.
    """
    from .llamaindex import build_tools
    return build_tools()


def smolagents_tools():
    """Return soundfetch tools as Smolagents Tool objects.

    Requires ``pip install "soundfetch[smolagents]"``.
    """
    from .smolagents import build_tools
    return build_tools()
