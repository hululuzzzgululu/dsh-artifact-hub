# Artifact Hub

Artifact Hub turns mutable Session Files into immutable, shareable Artifact Versions without coupling their lifetime to the original session.

## Language

**Session File**:
A file generated inside a session workspace. It remains mutable and is not an Artifact until a user explicitly shares it.
_Avoid_: artifact file, shared file

**Artifact**:
The stable logical identity created from a Session File when sharing starts. It identifies the product, not a particular file snapshot.
_Avoid_: session file

**Artifact Version**:
An immutable snapshot of an Artifact's content. Each version has its own checksum and storage location.
_Avoid_: mutable artifact, live file

**Business ID**:
A stable identifier for an Artifact Hub entity outside its database row. APIs and relationships use it so storage-specific row identity never leaks across the repository boundary.
_Avoid_: database row ID, auto-increment ID

**Share**:
The current access state for one Artifact Version, providing a revocable, optionally expiring public link with view-and-download access. An Artifact Version has at most one Share; sharing it again replaces the previous link and options rather than recording another Share.
_Avoid_: share link as the whole model

**Share Grant**:
An explicit recipient authorization for a Share. It belongs to recipient-oriented views and is not part of the first hub slice.
_Avoid_: recipient, shared-with-me record

**Storage Mode**:
The filesystem placement contract used to materialize an Artifact Version: Local or NAS.
_Avoid_: object storage provider

**Local**:
The hub reads a Session File that is visible on the hub machine and copies it into Artifact storage.

**NAS**:
The DSH side copies a Session File into a shared filesystem path prepared by the hub; the hub validates and commits that path.
