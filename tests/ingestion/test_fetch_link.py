import httpx
import pytest

from app.ingestion.links import LinkFetchError, fetch_link

PUBLIC = "93.184.216.34"
OTHER_PUBLIC = "151.101.1.1"


def resolver(table: dict[str, list[str]]):
    def resolve(host: str, port: int) -> list[str]:
        return table.get(host, [])

    return resolve


def site(handler, **hosts: list[str]):
    """Keyword args can't hold dots, so hosts map 'example_com' -> 'example.com'."""
    table = {name.replace("_", "."): ips for name, ips in hosts.items()}
    return {"resolver": resolver(table), "transport": httpx.MockTransport(handler)}


def ok(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/robots.txt":
        return httpx.Response(404)
    return httpx.Response(200, content=b"<html>hi</html>", headers={"content-type": "text/html"})


def test_fetches_a_page():
    result = fetch_link("https://example.com/a?b=1", **site(ok, example_com=[PUBLIC]))

    assert result.body == b"<html>hi</html>"
    assert result.url == "https://example.com/a?b=1"
    assert result.status_code == 200
    assert result.content_type == "text/html"
    assert result.fetched_at.tzinfo is not None


def test_connects_to_the_checked_address_not_the_name():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return ok(request)

    fetch_link("https://example.com/page", **site(handler, example_com=[PUBLIC]))

    page = seen[-1]
    assert page.url.host == PUBLIC  # DNS can't change between the check and the connection
    assert page.headers["host"] == "example.com"
    assert page.extensions["sni_hostname"] == "example.com"
    assert page.headers["user-agent"].startswith("InsightHubBot")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "gopher://example.com/",
        "javascript:alert(1)",
        "//example.com/x",
        "https:///nohost",
        "https://user:pw@example.com/",
        "https://example.com:22/",
        "https://example.com:99999/",
        "",
    ],
)
def test_rejects_unsafe_urls(url):
    with pytest.raises(LinkFetchError):
        fetch_link(url, **site(ok, example_com=[PUBLIC]))


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",  # cloud metadata
        "100.64.0.1",  # carrier-grade NAT
        "0.0.0.0",
        "224.0.0.1",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",  # IPv4-mapped
        "::ffff:169.254.169.254",
        "64:ff9b::7f00:1",  # NAT64
        "2002:7f00:1::",  # 6to4
    ],
)
def test_refuses_non_public_addresses(address):
    with pytest.raises(LinkFetchError, match="private or internal"):
        fetch_link("https://example.com/", **site(ok, example_com=[address]))


def test_refuses_a_name_when_any_address_is_private():
    with pytest.raises(LinkFetchError, match="private or internal"):
        fetch_link("https://example.com/", **site(ok, example_com=[PUBLIC, "10.0.0.5"]))


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://[::1]/", "http://localhost/"])
def test_refuses_literal_and_local_hosts(url):
    table = {"localhost": ["127.0.0.1"], "127.0.0.1": ["127.0.0.1"], "::1": ["::1"]}
    with pytest.raises(LinkFetchError, match="private or internal"):
        fetch_link(url, resolver=resolver(table), transport=httpx.MockTransport(ok))


def test_error_message_does_not_leak_the_address():
    with pytest.raises(LinkFetchError) as error:
        fetch_link("https://example.com/", **site(ok, example_com=["10.9.8.7"]))
    assert "10.9.8.7" not in str(error.value)


def test_unknown_host_is_an_error():
    with pytest.raises(LinkFetchError, match="could not be found"):
        fetch_link("https://nowhere.test/", **site(ok))


def redirecting(target: str, status=302):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.headers["host"] == "example.com":
            return httpx.Response(status, headers={"location": target})
        return httpx.Response(200, content=b"final")

    return handler


def test_follows_redirects_to_public_hosts():
    result = fetch_link(
        "https://example.com/",
        **site(redirecting("https://other.com/x"), example_com=[PUBLIC], other_com=[OTHER_PUBLIC]),
    )
    assert (result.url, result.body) == ("https://other.com/x", b"final")


def test_follows_relative_redirects():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(200, content=b"new")

    result = fetch_link("https://example.com/old", **site(handler, example_com=[PUBLIC]))
    assert result.url == "https://example.com/new"


def test_redirect_to_a_private_host_is_refused():
    with pytest.raises(LinkFetchError, match="private or internal"):
        fetch_link(
            "https://example.com/",
            **site(
                redirecting("http://metadata.internal/latest"),
                example_com=[PUBLIC],
                metadata_internal=["169.254.169.254"],
            ),
        )


@pytest.mark.parametrize(
    "target", ["file:///etc/passwd", "ftp://other.com/", "http://other.com:8080/"]
)
def test_redirect_to_a_disallowed_scheme_or_port_is_refused(target):
    with pytest.raises(LinkFetchError):
        fetch_link(
            "https://example.com/",
            **site(redirecting(target), example_com=[PUBLIC], other_com=[OTHER_PUBLIC]),
        )


def test_redirect_loop_stops():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"location": "/again"})

    with pytest.raises(LinkFetchError, match="too many times"):
        fetch_link("https://example.com/", max_redirects=3, **site(handler, example_com=[PUBLIC]))


def test_redirect_without_location_is_an_error():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302)

    with pytest.raises(LinkFetchError, match="nowhere"):
        fetch_link("https://example.com/", **site(handler, example_com=[PUBLIC]))


def test_rejects_declared_size_over_the_limit():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=b"x" * 100, headers={"content-length": "100"})

    with pytest.raises(LinkFetchError, match="too large"):
        fetch_link("https://example.com/", max_bytes=50, **site(handler, example_com=[PUBLIC]))


def test_stops_streaming_past_the_limit_even_without_content_length():
    def chunks():
        for _ in range(100):
            yield b"x" * 10

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=chunks())

    with pytest.raises(LinkFetchError, match="too large"):
        fetch_link("https://example.com/", max_bytes=50, **site(handler, example_com=[PUBLIC]))


def test_total_time_limit():
    with pytest.raises(LinkFetchError, match="too long"):
        fetch_link("https://example.com/", timeout_seconds=0, **site(ok, example_com=[PUBLIC]))


def test_network_timeout_and_errors_become_link_errors():
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    def broken(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LinkFetchError, match="too long to respond"):
        fetch_link("https://example.com/", respect_robots=False, **site(slow, example_com=[PUBLIC]))
    with pytest.raises(LinkFetchError, match="could not be reached"):
        fetch_link(
            "https://example.com/", respect_robots=False, **site(broken, example_com=[PUBLIC])
        )


def test_http_errors_become_link_errors():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(403)

    with pytest.raises(LinkFetchError, match="HTTP 403"):
        fetch_link("https://example.com/", **site(handler, example_com=[PUBLIC]))


def with_robots(robots: httpx.Response):
    def handler(request):
        if request.url.path == "/robots.txt":
            return robots
        return httpx.Response(200, content=b"page")

    return handler


def test_robots_disallow_blocks_the_fetch():
    robots = httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
    handler = with_robots(robots)
    with pytest.raises(LinkFetchError, match="robots.txt does not allow"):
        fetch_link("https://example.com/private/x", **site(handler, example_com=[PUBLIC]))
    assert fetch_link("https://example.com/public", **site(handler, example_com=[PUBLIC])).body


def test_robots_rule_naming_our_bot_applies():
    robots = httpx.Response(200, text="User-agent: InsightHubBot\nDisallow: /\n")
    with pytest.raises(LinkFetchError, match="robots.txt does not allow"):
        fetch_link("https://example.com/", **site(with_robots(robots), example_com=[PUBLIC]))


def test_missing_robots_allows_everything():
    assert fetch_link(
        "https://example.com/", **site(with_robots(httpx.Response(404)), example_com=[PUBLIC])
    ).body


def test_unreachable_robots_blocks_the_fetch():
    with pytest.raises(LinkFetchError, match="robots.txt could not be checked"):
        fetch_link(
            "https://example.com/",
            **site(with_robots(httpx.Response(503)), example_com=[PUBLIC]),
        )


def test_robots_can_be_skipped():
    robots = httpx.Response(200, text="User-agent: *\nDisallow: /\n")
    result = fetch_link(
        "https://example.com/",
        respect_robots=False,
        **site(with_robots(robots), example_com=[PUBLIC]),
    )
    assert result.body == b"page"


def test_robots_is_checked_again_after_a_redirect_to_another_host():
    def handler(request):
        host = request.headers["host"]
        if request.url.path == "/robots.txt":
            if host == "other.com":
                return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
            return httpx.Response(404)
        if host == "example.com":
            return httpx.Response(302, headers={"location": "https://other.com/x"})
        return httpx.Response(200, content=b"final")

    with pytest.raises(LinkFetchError, match="robots.txt does not allow"):
        fetch_link(
            "https://example.com/", **site(handler, example_com=[PUBLIC], other_com=[OTHER_PUBLIC])
        )
