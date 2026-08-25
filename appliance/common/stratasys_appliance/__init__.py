"""stratasys_appliance — code shared by the factory side (serial/image
service, provisioning tool, license tool) and the device side
(security service).

Sub-modules:
    crypto      canonical JSON + Ed25519 sign / verify + key files
    serials     SC000001 serial-number format and sequencing rules
    license     signed license payload build / verify
    manifests   signed image-catalog manifest verify + policy
    identity    device ID derivation + hardware fingerprint
    audit       hash-chained audit log
"""

__version__ = "0.1.0"
