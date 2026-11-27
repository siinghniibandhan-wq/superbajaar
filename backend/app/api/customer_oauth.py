"""Google and GitHub sign-in for storefront customers (OAuth 2.0 authorization-code flow).

Flow: GET /customer-auth/oauth/{provider}/start  -> 302 to provider
      GET /customer-auth/oauth/{provider}/callback -> creates/links the customer, issues the
      normal customer session and redirects to the storefront with the token in the URL fragment.

Security notes:
- `state` is a signed, short-lived token that also carries a nonce stored in an HttpOnly cookie
  (login-CSRF protection).
- An existing account is linked by email ONLY when the provider asserts the email is verified.
- OAuth-created accounts get an unusable random password hash; the user can still use
  email/password later only via a password-reset flow (not part of this change).
"""
from datetime import datetime, timezone
import secrets
from urllib.parse import urlencode

import httpx
import psycopg
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.auth import _decode, _password_hash, _sign
from app.api.customer_auth import (
    _connect,
    _ensure_customer_identity,
    _issue_session,
    _link_verified_legacy_loyalty_account,
    _new_referral_code,
    _public_customer,
)
from app.core.config import settings
from app.services.identity import IdentityService

router = APIRouter(prefix="/customer-auth/oauth", tags=["customer social sign-in"])

STATE_COOKIE = "sb_oauth_nonce"
STATE_TTL_SECONDS = 600

PROVIDERS = {
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "scope": "openid email profile",
    },
    "github": {
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "scope": "read:user user:email",
    },
}


def _credentials(provider: str) -> tuple[str, str]:
    if provider == "google":
        return settings.google_oauth_client_id, settings.google_oauth_client_secret
    return settings.github_oauth_client_id, settings.github_oauth_client_secret


def _callback_url(provider: str) -> str:
    base = settings.public_api_base_url.rstrip("/")
    return f"{base}{settings.api_prefix.rstrip('/')}/customer-auth/oauth/{provider}/callback"


def _frontend_redirect(fragment: dict, path: str = "/customer/oauth-complete") -> RedirectResponse:
    url = settings.frontend_base_url.rstrip("/") + path + "#" + urlencode(fragment)
    response = RedirectResponse(url, status_code=302)
    response.delete_cookie(STATE_COOKIE, path="/")
    return response


def _check_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown sign-in provider")


@router.get("/providers")
def enabled_providers():
    """Lets the storefront show only the buttons that are configured."""
    return {
        "providers": [
            name for name in PROVIDERS
            if all(_credentials(name)) and settings.public_api_base_url
        ]
    }


@router.get("/{provider}/start")
def start(provider: str):
    _check_provider(provider)
    client_id, client_secret = _credentials(provider)
    if not (client_id and client_secret and settings.public_api_base_url):
        raise HTTPException(status_code=503, detail=f"{provider.title()} sign-in is not configured")
    nonce = secrets.token_urlsafe(16)
    now = int(datetime.now(timezone.utc).timestamp())
    state = _sign({"typ": "oauth_state", "p": provider, "n": nonce, "iat": now, "exp": now + STATE_TTL_SECONDS})
    params = {
        "client_id": client_id,
        "redirect_uri": _callback_url(provider),
        "response_type": "code",
        "scope": PROVIDERS[provider]["scope"],
        "state": state,
    }
    if provider == "google":
        params["prompt"] = "select_account"
    response = RedirectResponse(PROVIDERS[provider]["authorize"] + "?" + urlencode(params), status_code=302)
    response.set_cookie(
        STATE_COOKIE, nonce, max_age=STATE_TTL_SECONDS, httponly=True, path="/",
        secure=settings.public_api_base_url.startswith("https://"), samesite="lax",
    )
    return response


def _fetch_profile(provider: str, code: str) -> dict:
    """Exchange the code and return {id, email, email_verified, name}. Raises ValueError on failure."""
    client_id, client_secret = _credentials(provider)
    with httpx.Client(timeout=10) as http:
        token_response = http.post(
            PROVIDERS[provider]["token"],
            data={
                "client_id": client_id, "client_secret": client_secret, "code": code,
                "redirect_uri": _callback_url(provider), "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        token = token_response.json().get("access_token") if token_response.status_code == 200 else None
        if not token:
            raise ValueError("Provider did not return an access token")
        auth = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        if provider == "google":
            info = http.get("https://openidconnect.googleapis.com/v1/userinfo", headers=auth)
            if info.status_code != 200:
                raise ValueError("Could not read Google profile")
            data = info.json()
            return {
                "id": str(data.get("sub") or ""),
                "email": (data.get("email") or "").strip().lower(),
                "email_verified": data.get("email_verified") is True,
                "name": data.get("name") or "",
            }

        user = http.get("https://api.github.com/user", headers=auth)
        emails = http.get("https://api.github.com/user/emails", headers=auth)
        if user.status_code != 200:
            raise ValueError("Could not read GitHub profile")
        data = user.json()
        email, verified = "", False
        if emails.status_code == 200:
            primary = next((e for e in emails.json() if e.get("primary") and e.get("verified")), None)
            if primary:
                email, verified = primary["email"].strip().lower(), True
        return {
            "id": str(data.get("id") or ""),
            "email": email,
            "email_verified": verified,
            "name": data.get("name") or data.get("login") or "",
        }


def _resolve_customer(conn, provider: str, profile: dict):
    """Return the customer row for this social identity, creating/linking as needed."""
    existing = conn.execute(
        "SELECT ca.id,ca.email,ca.full_name,ca.phone,ca.referral_code,ca.is_active "
        "FROM customer_oauth_identities oi JOIN customer_accounts ca ON ca.id=oi.customer_id "
        "WHERE oi.provider=%s AND oi.provider_user_id=%s FOR UPDATE OF ca",
        (provider, profile["id"]),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE customer_oauth_identities SET last_login_at=now() WHERE provider=%s AND provider_user_id=%s",
            (provider, profile["id"]),
        )
        return existing

    email = profile["email"]
    if not email or not profile["email_verified"]:
        raise HTTPException(status_code=422, detail=f"{provider.title()} did not share a verified email address")

    customer = conn.execute(
        "SELECT id,email,full_name,phone,referral_code,is_active FROM customer_accounts "
        "WHERE lower(email)=lower(%s) FOR UPDATE",
        (email,),
    ).fetchone()
    if customer is None:
        full_name = " ".join((profile["name"] or email.split("@")[0]).split())
        if len(full_name) < 2:
            full_name = email.split("@")[0]
        customer = conn.execute(
            "INSERT INTO customer_accounts (email,full_name,phone,password_hash,referral_code) "
            "VALUES (%s,%s,NULL,%s,%s) RETURNING id,email,full_name,phone,referral_code,is_active",
            (email, full_name, _password_hash(secrets.token_urlsafe(48)), _new_referral_code(conn)),
        ).fetchone()
        identity = IdentityService(conn)
        party = identity.create_party(
            party_type="individual", display_name=full_name,
            reason=f"Customer {provider} sign-in registration",
        )
        identity.link_profile(
            party_id=party["id"], profile_type="customer_account",
            source_id=customer["id"], link_method="authenticated_claim",
        )
        identity.link_auth_account(
            party_id=party["id"], account_type="customer",
            source_id=customer["id"], link_method="authenticated_claim",
        )
        identity.add_contact(party_id=party["id"], contact_type="email", value=email, source=f"{provider}_oauth")
        card = "SB-" + secrets.token_hex(5).upper()
        loyalty = conn.execute(
            "INSERT INTO loyalty_accounts (customer_email,card_number) VALUES (%s,%s) "
            "ON CONFLICT (customer_email) DO NOTHING RETURNING id",
            (email, card),
        ).fetchone()
        if loyalty:
            conn.execute(
                "INSERT INTO identity_loyalty_accounts(party_id,loyalty_account_id,link_method) "
                "VALUES(%s,%s,'verified_customer_account')",
                (party["id"], loyalty["id"]),
            )
    conn.execute(
        "INSERT INTO customer_oauth_identities (customer_id,provider,provider_user_id,provider_email,last_login_at) "
        "VALUES (%s,%s,%s,%s,now()) ON CONFLICT DO NOTHING",
        (customer["id"], provider, profile["id"], email),
    )
    return customer


@router.get("/{provider}/callback")
def callback(provider: str, request: Request, code: str = "", state: str = "", error: str = ""):
    _check_provider(provider)
    login_failed = lambda msg: _frontend_redirect({"error": msg}, "/customer/login")
    if error or not code or not state:
        return login_failed("Sign-in was cancelled or failed. Please try again.")
    try:
        claims = _decode(state)
    except HTTPException:
        return login_failed("Sign-in link expired. Please try again.")
    cookie_nonce = request.cookies.get(STATE_COOKIE, "")
    if (
        claims.get("typ") != "oauth_state" or claims.get("p") != provider
        or not cookie_nonce or not secrets.compare_digest(str(claims.get("n", "")), cookie_nonce)
    ):
        return login_failed("Sign-in could not be verified. Please try again.")
    try:
        profile = _fetch_profile(provider, code)
        if not profile["id"]:
            raise ValueError("missing id")
    except (ValueError, httpx.HTTPError):
        return login_failed(f"Could not complete {provider.title()} sign-in. Please try again.")

    try:
        with _connect() as conn:
            with conn.transaction():
                customer = _resolve_customer(conn, provider, profile)
                if not customer["is_active"]:
                    raise HTTPException(status_code=403, detail="This account is inactive")
                sbid = _ensure_customer_identity(conn, customer["id"], customer["full_name"])
                _link_verified_legacy_loyalty_account(
                    conn, customer_id=int(customer["id"]), customer_email=customer["email"]
                )
                customer = {**customer, "sbid": sbid}
                session = _issue_session(conn, customer)
    except HTTPException as exc:
        return login_failed(str(exc.detail))
    except psycopg.Error:
        return login_failed("Sign-in is temporarily unavailable. Please try again.")
    return _frontend_redirect({"token": session["access_token"]})
