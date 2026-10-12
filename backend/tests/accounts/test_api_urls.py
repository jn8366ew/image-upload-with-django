from django.urls import URLPattern, URLResolver, get_resolver


def _routes(patterns, prefix=""):
    for p in patterns:
        route = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            yield from _routes(p.url_patterns, route)
        elif isinstance(p, URLPattern):
            yield route


def test_api_urls_have_no_trailing_slash():
    api_routes = [r for r in _routes(get_resolver().url_patterns) if r.startswith("api/")]

    assert api_routes
    assert [r for r in api_routes if r.endswith("/")] == []
