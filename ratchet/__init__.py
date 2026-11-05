"""ratchet: PREREG ratchet_v1 (silicyte-0119). Importing the package installs the sealed-read audit hook first."""
from . import guard as _guard

_guard.install_audit_hook()

__all__ = ['guard']
