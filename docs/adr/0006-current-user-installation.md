# ADR 0006: Current-user installation

- Status: Accepted
- Date: 2026-08-24

## Context

The release wheel can be installed into a virtual environment, but that leaves its
location and `PATH` setup to every user. The installed `mojit` command must be
available from any working directory without requiring administrator privileges,
modifying the system Python installation, or introducing a network dependency into
the verified offline release.

## Considered alternatives

- document manual virtual-environment creation and `PATH` editing;
- require an external application manager such as `pipx` or `uv`;
- build a machine-wide installer that requires elevation;
- manage one isolated installation for the current Windows user.

## Evidence

- The application wheel already declares the `mojit` console entry point.
- The release wheelhouse is verified offline on 64-bit CPython 3.11-3.14.
- The runtime deliberately avoids searching or modifying `PATH`, including when it
  loads its packaged FriBiDi library.

## Decision

The release bundle contains one PowerShell lifecycle script. It installs the pinned
application and dependencies, without network access, into
`%LOCALAPPDATA%\Programs\mojit`, then prepends that environment's `Scripts` directory
to the current user's `PATH`. It does not modify the machine `PATH` or a system Python
installation.

Before installation, the script verifies the exact wheelhouse inventory and every
payload checksum. It records a private ownership marker in the installation root.
Reinstallation and recursive removal are permitted only when that marker is valid.
The installed copy of the same script owns upgrade, repair, and uninstall behavior.

## Consequences and follow-up

- Installation needs no elevation and is isolated from other Python applications.
- Existing terminal processes retain their old environment, so WezTerm must be
  restarted once after the first installation.
- A supported 64-bit CPython remains a prerequisite, but no package manager or
  network access is required during installation.
- The release verifier exercises installation from outside the source tree, repeat
  installation, command execution from another directory, and protected uninstall.
- This is a current-user installation, not an MSI or an all-users deployment.
