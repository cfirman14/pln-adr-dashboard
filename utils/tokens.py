"""
PART 8 — Token unik untuk link respons pelanggan.
Token ini berfungsi sebagai "kunci" satu-satunya cara pelanggan mengakses
halaman respons mereka — tidak perlu login, cukup lewat link email.
"""

import secrets


def generate_token() -> str:
    """Buat token acak yang aman (URL-safe), cukup panjang supaya tidak bisa ditebak."""
    return secrets.token_urlsafe(24)
