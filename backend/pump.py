"""
pump.fun token creation module.
Interacts with the pump.fun Solana program to create tokens and buy initial supply.
"""

import hashlib
import json
import os
import struct
import time as time_module
from pathlib import Path
from typing import Optional

from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.system_program import ID as SYSTEM_PROGRAM_ID
from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts

# ── Constants ────────────────────────────────────────────────────────────────

PUMP_PROGRAM_ID = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string(
    "ATokenGPvbdGVxr1b2hvZbsiqW5xr25ix9sJ5RjKjTjV"
)
METADATA_PROGRAM_ID = Pubkey.from_string(
    "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"
)
SYSVAR_RENT_ID = Pubkey.from_string(
    "SysvarRent111111111111111111111111111111111"
)

# Known pump.fun global state PDAs (constant across all tokens)
GLOBAL_ACCOUNT = Pubkey.from_string(
    "4wTV1YmiEkRvx92CwN7b7e7T4RvK5pYZJnwsJN3EEMPz"
)
FEE_RECIPIENT = Pubkey.from_string(
    "CJmtRtBqHPNk3EZnpyE6Q1NHTWgpweD9843N6xuBRiKj"
)

RPC_URL = os.getenv(
    "SOLANA_RPC_URL",
    "https://api.mainnet-beta.solana.com",
)

# Metadata storage
METADATA_DIR = Path(__file__).resolve().parent / "token_metadata"
METADATA_BASE_URL = os.getenv(
    "METADATA_BASE_URL",
    "http://localhost:8000/meme/metadata",
)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _discriminator(name: str) -> bytes:
    """Anchor instruction discriminator = sha256('global:<name>')[:8]"""
    return hashlib.sha256(f"global:{name}".encode()).digest()[:8]


def _anchor_string(value: str, max_bytes: int = 100) -> bytes:
    """Encode a UTF-8 string as an Anchor string (4-byte LE len + bytes)."""
    encoded = value.encode("utf-8")[:max_bytes]
    return struct.pack("<I", len(encoded)) + encoded


# ── Metadata helpers ─────────────────────────────────────────────────────────

def _save_metadata(
    token_id: str,
    name: str,
    symbol: str,
    description: str,
    image_url: str,
    twitter: str,
    telegram: str,
    website: str,
) -> str:
    """Persist metadata JSON and return its URI."""
    metadata = {
        "name": name,
        "symbol": symbol,
        "description": description or "",
        "image": image_url or "",
        "showName": True,
        "createdOn": "https://pump.fun",
        "twitter": twitter or "",
        "telegram": telegram or "",
        "website": website or "",
    }
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    path = METADATA_DIR / f"{token_id}.json"
    path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return f"{METADATA_BASE_URL}/{token_id}.json"


def load_metadata(token_id: str) -> Optional[dict]:
    """Load previously-saved token metadata."""
    path = METADATA_DIR / f"{token_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ── Core: create token ───────────────────────────────────────────────────────

def create_token(
    name: str,
    symbol: str,
    description: str = "",
    image_url: str = "",
    twitter: str = "",
    telegram: str = "",
    website: str = "",
    secret_key: Optional[str] = None,
) -> dict:
    """
    Create a new token on pump.fun.

    Requires ``PUMP_SECRET_KEY`` (base58-encoded Solana keypair) in the
    environment or passed explicitly.  The payer must carry enough SOL to
    cover rent + tx fees (~0.1 SOL).

    Returns ``{signature, mint_address, uri, slot}``.
    """
    # ── Payer ────────────────────────────────────────────────────────────
    key_str = secret_key or os.getenv("PUMP_SECRET_KEY") or ""
    if not key_str:
        raise ValueError(
            "PUMP_SECRET_KEY is not set — provide a secret_key or set the "
            "environment variable"
        )
    payer = Keypair.from_base58_string(key_str)

    # ── New mint keypair ─────────────────────────────────────────────────
    mint_kp = Keypair()
    mint = mint_kp.pubkey()

    # ── Persist metadata & build URI ─────────────────────────────────────
    uri = _save_metadata(
        str(mint),
        name,
        symbol,
        description,
        image_url,
        twitter,
        telegram,
        website,
    )

    # ── Derive PDAs ──────────────────────────────────────────────────────
    bonding_curve, _ = Pubkey.find_program_address(
        [b"bonding-curve", bytes(mint)],
        PUMP_PROGRAM_ID,
    )
    bonding_curve_ata, _ = Pubkey.find_program_address(
        [bytes(bonding_curve), bytes(TOKEN_PROGRAM_ID), bytes(mint)],
        ASSOCIATED_TOKEN_PROGRAM_ID,
    )
    metadata_pda, _ = Pubkey.find_program_address(
        [b"metadata", bytes(METADATA_PROGRAM_ID), bytes(mint)],
        METADATA_PROGRAM_ID,
    )

    # ── Instruction data ─────────────────────────────────────────────────
    #   Anchor 8-Byte discriminator + 3 Anchor strings (name, symbol, uri)
    data = (
        _discriminator("create")
        + _anchor_string(name, 32)
        + _anchor_string(symbol, 10)
        + _anchor_string(uri, 200)
    )

    accounts = [
        AccountMeta(mint, is_signer=True, is_writable=True),
        AccountMeta(payer.pubkey(), is_signer=True, is_writable=True),
        AccountMeta(GLOBAL_ACCOUNT, is_signer=False, is_writable=True),
        AccountMeta(bonding_curve, is_signer=False, is_writable=True),
        AccountMeta(bonding_curve_ata, is_signer=False, is_writable=True),
        AccountMeta(FEE_RECIPIENT, is_signer=False, is_writable=True),
        AccountMeta(metadata_pda, is_signer=False, is_writable=True),
        AccountMeta(TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(ASSOCIATED_TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(SYSTEM_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(METADATA_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(SYSVAR_RENT_ID, is_signer=False, is_writable=False),
    ]

    ix = Instruction(PUMP_PROGRAM_ID, data, accounts)

    # ── Send transaction ─────────────────────────────────────────────────
    client = Client(RPC_URL)
    blockhash = client.get_latest_blockhash().value.blockhash

    msg = MessageV0.try_compile(
        payer=payer.pubkey(),
        instructions=[ix],
        address_lookup_table_accounts=[],
        recent_blockhash=blockhash,
    )
    tx = VersionedTransaction(msg, [payer, mint_kp])

    resp = client.send_transaction(
        tx,
        opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed),
    )
    sig = resp.value

    return {
        "signature": str(sig),
        "mint_address": str(mint),
        "uri": uri,
    }


# ── Core: buy tokens (initial purchase) ──────────────────────────────────────

def buy_tokens(
    mint_address: str,
    amount_sol: float = 0.01,
    slippage_basis_points: int = 500,
    secret_key: Optional[str] = None,
) -> dict:
    """
    Buy tokens from a pump.fun bonding curve.

    ``amount_sol`` is the amount of SOL to spend.
    Returns ``{signature, token_amount}``.
    """
    key_str = secret_key or os.getenv("PUMP_SECRET_KEY") or ""
    if not key_str:
        raise ValueError("PUMP_SECRET_KEY is not set")
    payer = Keypair.from_base58_string(key_str)
    mint = Pubkey.from_string(mint_address)

    # Derive the bonding curve PDA
    bonding_curve, _ = Pubkey.find_program_address(
        [b"bonding-curve", bytes(mint)],
        PUMP_PROGRAM_ID,
    )
    bonding_curve_ata, _ = Pubkey.find_program_address(
        [bytes(bonding_curve), bytes(TOKEN_PROGRAM_ID), bytes(mint)],
        ASSOCIATED_TOKEN_PROGRAM_ID,
    )
    user_ata, _ = Pubkey.find_program_address(
        [bytes(payer.pubkey()), bytes(TOKEN_PROGRAM_ID), bytes(mint)],
        ASSOCIATED_TOKEN_PROGRAM_ID,
    )

    data = _discriminator("buy")
    # Buy instruction data: amount (8 bytes LE), slippage (8 bytes LE)
    amount_lamports = int(amount_sol * 1_000_000_000)
    data += struct.pack("<Q", amount_lamports)
    data += struct.pack("<Q", slippage_basis_points)

    accounts = [
        AccountMeta(mint, is_signer=False, is_writable=True),
        AccountMeta(bonding_curve, is_signer=False, is_writable=True),
        AccountMeta(bonding_curve_ata, is_signer=False, is_writable=True),
        AccountMeta(GLOBAL_ACCOUNT, is_signer=False, is_writable=True),
        AccountMeta(FEE_RECIPIENT, is_signer=False, is_writable=False),
        AccountMeta(user_ata, is_signer=False, is_writable=True),
        AccountMeta(payer.pubkey(), is_signer=True, is_writable=True),
        AccountMeta(SYSTEM_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(ASSOCIATED_TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(SYSVAR_RENT_ID, is_signer=False, is_writable=False),
    ]

    ix = Instruction(PUMP_PROGRAM_ID, data, accounts)
    client = Client(RPC_URL)
    blockhash = client.get_latest_blockhash().value.blockhash

    msg = MessageV0.try_compile(
        payer=payer.pubkey(),
        instructions=[ix],
        address_lookup_table_accounts=[],
        recent_blockhash=blockhash,
    )
    tx = VersionedTransaction(msg, [payer])

    resp = client.send_transaction(
        tx,
        opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed),
    )

    return {
        "signature": str(resp.value),
        "mint_address": mint_address,
        "amount_sol": amount_sol,
    }


def get_wallet_info() -> dict:
    """Return configured wallet address, SOL balance, and created tokens."""
    key_str = os.getenv("PUMP_SECRET_KEY") or ""
    if not key_str:
        return {"address": None, "balance_sol": None, "tokens": []}

    payer = Keypair.from_base58_string(key_str)
    address = str(payer.pubkey())

    # Get SOL balance
    balance_sol = None
    try:
        client = Client(RPC_URL)
        resp = client.get_balance(payer.pubkey())
        balance_sol = resp.value / 1_000_000_000
    except Exception:
        pass

    # List created tokens from metadata directory
    tokens = []
    if METADATA_DIR.exists():
        for f in sorted(METADATA_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.suffix == ".json":
                try:
                    meta = json.loads(f.read_text(encoding="utf-8"))
                    tokens.append({
                        "mint_address": f.stem,
                        "name": meta.get("name", ""),
                        "symbol": meta.get("symbol", ""),
                    })
                except Exception:
                    pass

    return {
        "address": address,
        "balance_sol": balance_sol,
        "tokens": tokens,
    }
