from app.core.security import classify_rate_limit, rate_limit_bucket_key


def test_authentication_routes_receive_stricter_rate_limits():
    assert classify_rate_limit("POST", "/api/auth/login") == (5, 60)
    assert classify_rate_limit("POST", "/api/customer-auth/register") == (5, 60)
    assert classify_rate_limit("POST", "/api/customer-auth/identity-verification/otp/request") == (3, 300)


def test_normal_mutations_receive_shared_api_limit():
    assert classify_rate_limit("POST", "/api/orders") == (60, 60)
    assert classify_rate_limit("PATCH", "/api/inventory/stock") == (60, 60)


def test_bucket_key_is_stable_and_scoped_by_ip_and_route():
    a = rate_limit_bucket_key("203.0.113.10", "POST", "/api/auth/login")
    b = rate_limit_bucket_key("203.0.113.10", "POST", "/api/auth/login")
    c = rate_limit_bucket_key("203.0.113.11", "POST", "/api/auth/login")
    d = rate_limit_bucket_key("203.0.113.10", "POST", "/api/customer-auth/login")
    assert a == b
    assert a != c
    assert a != d
    assert len(a) == 64



def test_login_and_otp_use_separate_distributed_buckets():
    login = rate_limit_bucket_key("203.0.113.10", "POST", "/api/customer-auth/login")
    otp = rate_limit_bucket_key("203.0.113.10", "POST", "/api/customer-auth/identity-verification/otp/request")
    assert login != otp
