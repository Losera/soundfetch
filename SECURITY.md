# Security policy

## Supported versions

Security fixes are provided for the latest published beta. Until the first PyPI
publication, the current tagged release candidate is the only supported line.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repository. Do not open a
public issue containing credentials, exploitable paths, private URLs, or a
working proof of concept. Include the affected version, impact, reproduction,
and any suggested mitigation. The maintainer will acknowledge a complete report
within seven days and coordinate disclosure after a fix is available.

## Security boundaries

Soundfetch processes remote metadata and media and can write downloaded files.
MCP deployments should set `SOUNDFETCH_MCP_ROOT` to a dedicated workspace and
provide only the credentials required by the selected providers. License
metadata is preserved for review but is not independently certified.
