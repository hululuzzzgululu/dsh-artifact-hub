# Use filesystem adapters for Local and NAS storage

The first hub implementation treats both Local and NAS as filesystem storage and keeps the storage key relative to the configured artifact root. Local snapshots are copied by the hub; NAS snapshots use a prepare/commit protocol because the hub may not be able to read the DSH machine's session workspace. This keeps the domain independent of absolute machine paths and leaves object storage for a later adapter.
