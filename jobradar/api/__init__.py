"""HTTP API for the JobRadar dashboard frontend.

The pipeline (jobradar.__main__) continues to run as a CLI. This package adds a
FastAPI service on top of the same project so a UI can observe outbound sends,
inbound replies, and scheduled follow-ups, and act on them.

Launch with: python -m jobradar api
"""

from jobradar.api.app import create_app

__all__ = ["create_app"]
