# Abstract database persistence behind repository adapters

Artifact Hub application services depend on an `ArtifactRepository` interface instead of a concrete database implementation. SQLite remains the default local adapter, while MySQL uses a SQLAlchemy adapter selected by the repository factory and runtime storage configuration. The runtime configuration follows DataMind's `config_objects.py` organization: `HubConfig.config` is the top-level configuration object, and its `storage` settings own `mode`, `sqlite`, and `server`. This follows the existing DataMind pattern and keeps changing database technology local to the repository layer.

Physical table names use the `dsh_` namespace prefix in both adapters: `dsh_artifacts`, `dsh_artifact_versions`, `dsh_shares`, and `dsh_uploads`. Repository initialization renames the corresponding legacy unprefixed tables in place; it fails instead of guessing when both a legacy name and its prefixed replacement already exist.
