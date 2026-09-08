"""FastAPI dependencies for the Artifact Hub."""

from fastapi import Request

from artifact_hub.services.artifact_hub import ArtifactHub


def get_hub(request: Request) -> ArtifactHub:
    return request.app.state.hub
