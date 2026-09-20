from app.services.research_run import get_research_service


def test_get_research_service_reuses_the_stateless_instance() -> None:
    clear = getattr(get_research_service, "cache_clear", None)
    if clear is not None:
        clear()
    try:
        first = get_research_service()
        second = get_research_service()
        assert second is first
    finally:
        clear = getattr(get_research_service, "cache_clear", None)
        if clear is not None:
            clear()
