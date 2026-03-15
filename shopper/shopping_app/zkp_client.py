"""
Shopping App — zkp_client.py (FIXED)

Strapi ZKP HTTP client. Shopping App calls:
  - register_seller()       → POST /api/register-seller
  - generate_kyc_proof()    → POST /api/generate-kyc-proof
  - verify_balance_proof()  → POST /api/verify-balance-proof
  - get_kyc_tree_status()   → GET  /api/kyc-tree-status
  - get_latest_root()       → GET  /api/latest-root

FIX: Strapi controller uses snake_case field names in destructuring:
  const { national_id, date_of_birth, business_license, tin, business_address } = ctx.request.body;
So we must send snake_case keys, NOT camelCase.
"""

import hashlib
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def encode_to_bigint(value):
    """Convert a value to numeric BigInt string for Poseidon. BN254 field < 2^253."""
    s = str(value).strip()
    if s.isdigit():
        if int(s) < (2 ** 253):
            return s
        h = hashlib.sha256(s.encode()).hexdigest()
        return str(int(h, 16) % (2 ** 253))
    stripped = ''.join(c for c in s if c.isdigit())
    if stripped and int(stripped) < (2 ** 253):
        return stripped
    h = hashlib.sha256(s.encode()).hexdigest()
    return str(int(h, 16) % (2 ** 253))


def encode_kyc_fields(raw_kyc):
    """
    Encode raw KYC dict to numeric BigInt strings for Poseidon circuit.

    Keys: national_id, date_of_birth (YYYYMMDD), business_license, tin, business_address
    
    date_of_birth MUST be passed as 'YYYYMMDD' string (e.g., '19900115').
    The circuit expects it as an integer: birth_year = date_of_birth \ 10000.
    encode_to_bigint() passes it through as-is since it's purely numeric.
    """
    fields = ['national_id', 'date_of_birth', 'business_license', 'tin', 'business_address']
    encoded = {}
    for f in fields:
        v = raw_kyc.get(f, '')
        encoded[f] = encode_to_bigint(v) if v else '0'
    return encoded


class ZKPClient:
    def __init__(self, base_url=None):
        self.base_url = (base_url or settings.ZKP_STRAPI_URL).rstrip('/')

    def _request(self, method, path, **kwargs):
        url = f"{self.base_url}{path}"
        timeout = kwargs.pop('timeout', 120)
        try:
            resp = getattr(requests, method)(url, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            logger.error(f"ZKP API timeout: {method.upper()} {url}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"ZKP API error: {method.upper()} {url} — {e}")
            raise

    # ── Seller KYC (Shopping App registers + generates proof) ──

    def register_seller(self, national_id, date_of_birth, business_license, tin, business_address):
        """
        Register seller KYC commitment in Strapi Merkle tree.
        All fields must be pre-encoded as numeric BigInt strings.
        
        IMPORTANT: Strapi controller destructures with snake_case:
          const { national_id, date_of_birth, business_license, tin, business_address } = ctx.request.body;
        So JSON keys MUST be snake_case.
        """
        return self._request('post', '/api/register-seller', json={
            'national_id': national_id,
            'date_of_birth': date_of_birth,
            'business_license': business_license,
            'tin': tin,
            'business_address': business_address,
        }, timeout=120)  # Registration involves Poseidon hashing + Merkle tree rebuild — can take 60s+

    def generate_kyc_proof(self, national_id, date_of_birth, business_license, tin, business_address, leaf_index):
        """
        Generate PLONK KYC proof. Same encoded fields + leaf_index from registration.
        
        Strapi controller destructures with snake_case:
          const { national_id, date_of_birth, business_license, tin, business_address, leaf_index } = ctx.request.body;
        """
        return self._request('post', '/api/generate-kyc-proof', json={
            'national_id': national_id,
            'date_of_birth': date_of_birth,
            'business_license': business_license,
            'tin': tin,
            'business_address': business_address,
            'leaf_index': leaf_index,
        }, timeout=120)  # PLONK proof generation with Merkle path can take 60s+

    # ── Balance Proof (Shopping App verifies Payment App's proof) ──

    def verify_balance_proof(self, proof, public_signals):
        """Verify Groth16 balance proof. Shopping App NEVER sees actual balance."""
        return self._request('post', '/api/verify-balance-proof', json={
            'proof': proof,
            'publicSignals': public_signals,
        })

    # ── Public Tree Status ──

    def get_kyc_tree_status(self):
        return self._request('get', '/api/kyc-tree-status')

    def get_latest_root(self):
        return self._request('get', '/api/latest-root')

    def get_root_history(self):
        return self._request('get', '/api/root-history')