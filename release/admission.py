from release.codec import decode_v1
from release.inventory import AcceptedPiece, AdmissionInventory


def admit_station_piece(inventory: AdmissionInventory, original_bytes: bytes) -> str:
    piece = decode_v1(original_bytes)
    return inventory.claim(piece.issuance_id, original_bytes)


def get_accepted_piece(inventory: AdmissionInventory, acceptance_id: str) -> AcceptedPiece:
    return inventory.get(acceptance_id)
