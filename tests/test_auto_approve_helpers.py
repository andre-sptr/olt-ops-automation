import asyncio
import csv
from pathlib import Path

import pytest

import auto_approve
from auto_approve import (
    BrowserConnectError,
    CdpEndpoint,
    build_chrome_command,
    effective_worker_count,
    ensure_cdp_browser,
    is_approve_confirmation_dialog,
    is_browser_closed_error,
    load_completed_statuses,
    parse_order_ids,
    parse_cdp_endpoint,
    pending_order_ids,
    prepare_worker_context,
    run_worker_tasks,
    select_default_context,
    validate_worker_count,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://dbaccess-ibooster.telkom.co.id/newkarina/login", True),
        ("https://dbaccess-ibooster.telkom.co.id/newkarina/verifikasi-otp", True),
        ("https://dbaccess-ibooster.telkom.co.id/newkarina", False),
        ("https://dbaccess-ibooster.telkom.co.id/newkarina/ram", False),
    ],
)
def test_is_authentication_url_covers_login_and_otp(url: str, expected: bool) -> None:
    assert auto_approve.is_authentication_url(url) is expected


def test_wait_for_authentication_completion_keeps_waiting_on_otp() -> None:
    class OtpPage:
        url = "https://dbaccess-ibooster.telkom.co.id/newkarina/verifikasi-otp"
        wait_calls = 0

        async def wait_for_url(self, predicate, *, timeout: int) -> None:
            assert timeout == 30_000
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise auto_approve.PlaywrightTimeoutError("OTP is still pending")
            self.url = "https://dbaccess-ibooster.telkom.co.id/newkarina"
            assert predicate(self.url)

    page = OtpPage()

    asyncio.run(auto_approve.wait_for_authentication_completion(page, "worker-1"))

    assert page.wait_calls == 2


def test_existing_ram_page_is_ready_when_order_search_input_is_visible() -> None:
    class SearchInput:
        async def wait_for(self, *, state: str, timeout: int) -> None:
            assert state == "visible"
            assert timeout == auto_approve.PAGE_READY_TIMEOUT_MS

    class SearchInputs:
        def nth(self, index: int) -> SearchInput:
            assert index == 0
            return SearchInput()

    class RamPage:
        url = auto_approve.DATA_URL

        def locator(self, selector: str) -> SearchInputs:
            assert selector == "thead input"
            return SearchInputs()

        def get_by_text(self, text: str):
            raise AssertionError("RAM readiness must not depend on the table heading")

    asyncio.run(auto_approve.wait_for_existing_ram_ready(RamPage(), "worker-1"))


def test_matching_order_script_scopes_rows_to_search_input_table() -> None:
    script = auto_approve.matching_order_row_indexes_js(
        "matchingOrderRowIndexes(orderId).length"
    )

    assert "searchInput.closest('.dataTables_wrapper')" in script
    assert "candidate.tBodies.length > 0" in script
    assert "table.querySelectorAll('thead tr')" in script
    assert "table.querySelectorAll('tbody tr')" in script
    assert "document.querySelectorAll('tbody tr')" not in script


def test_matching_order_script_does_not_insert_newline_after_return() -> None:
    script = auto_approve.matching_order_row_indexes_js(
        """
        (() => {
          return 0;
        })()
        """
    )

    assert "return (() => {" in script
    assert "return \n" not in script


def test_visible_data_rows_scopes_to_search_input_table() -> None:
    calls: list[tuple[str, str]] = []

    class Rows:
        def filter(self, *, has):
            raise AssertionError("tbody rows must not use a table-scoped has locator")

    class Table:
        def locator(self, selector: str):
            calls.append(("table", selector))
            assert selector == "tbody tr"
            return Rows()

    class Tables:
        @property
        def last(self):
            calls.append(("tables", "last"))
            return Table()

    class Wrapper:
        def locator(self, selector: str):
            calls.append(("wrapper", selector))
            return Tables()

    class SearchInput:
        def locator(self, selector: str):
            calls.append(("search", selector))
            return Wrapper()

    class Inputs:
        def nth(self, index: int):
            assert index == 0
            return SearchInput()

    class Page:
        def locator(self, selector: str):
            assert selector == "thead input"
            return Inputs()

    rows = auto_approve.visible_data_rows(Page())

    assert isinstance(rows, Rows)
    assert calls == [
        (
            "search",
            "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), "
            "' dataTables_wrapper ')][1]",
        ),
        ("wrapper", "table:has(tbody)"),
        ("tables", "last"),
        ("table", "tbody tr"),
    ]


def test_search_order_types_with_keyboard_for_datatables() -> None:
    calls: list[tuple[str, object]] = []

    class SearchInput:
        async def click(self) -> None:
            calls.append(("click", None))

        async def press(self, key: str) -> None:
            calls.append(("press", key))

        async def fill(self, value: str) -> None:
            raise AssertionError("DataTables filter requires keyboard events")

        async def press_sequentially(self, value: str, *, delay: int) -> None:
            calls.append(("type", (value, delay)))

    class Inputs:
        def nth(self, index: int) -> SearchInput:
            assert index == 0
            return SearchInput()

    class Page:
        def locator(self, selector: str) -> Inputs:
            assert selector == "thead input"
            return Inputs()

        async def wait_for_function(self, expression: str, *, arg: str, timeout: int) -> None:
            assert "matchingOrderRowIndexes" in expression
            assert arg == "205902"
            assert timeout == auto_approve.SEARCH_TIMEOUT_MS

        async def evaluate(self, expression: str, order_id: str) -> int:
            assert "matchingOrderRowIndexes" in expression
            assert order_id == "205902"
            return 1

    found = asyncio.run(auto_approve.search_order(Page(), "205902"))

    assert found is True
    assert calls == [
        ("click", None),
        ("press", "Control+A"),
        ("type", ("205902", 100)),
    ]


def test_parse_order_ids_accepts_commas_whitespace_and_newlines(tmp_path: Path) -> None:
    input_file = tmp_path / "order_ids.txt"
    input_file.write_text("205821, 205819\n205818 205821 abc 205817", encoding="utf-8")

    assert parse_order_ids(input_file) == ["205821", "205819", "205818", "205817"]


def test_load_completed_statuses_uses_latest_status_per_order(tmp_path: Path) -> None:
    result_file = tmp_path / "auto_approve_result.csv"
    with result_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["order_id", "status", "message", "attempts", "worker", "finished_at"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "order_id": "205821",
                "status": "PAGE_ERROR",
                "message": "old error",
                "attempts": "1",
                "worker": "worker-1",
                "finished_at": "2026-06-12T01:00:00+07:00",
            }
        )
        writer.writerow(
            {
                "order_id": "205821",
                "status": "APPROVED",
                "message": "ok",
                "attempts": "2",
                "worker": "worker-2",
                "finished_at": "2026-06-12T01:05:00+07:00",
            }
        )

    assert load_completed_statuses(result_file) == {"205821": "APPROVED"}


def test_pending_order_ids_skips_terminal_statuses_only() -> None:
    order_ids = ["1", "2", "3", "4", "5", "6"]
    statuses = {
        "1": "APPROVED",
        "2": "NOT_FOUND",
        "3": "APPROVE_FAILED",
        "4": "PAGE_ERROR",
        "5": "ACTION_MODAL_ERROR",
        "6": "DRY_RUN_FOUND",
    }

    assert pending_order_ids(order_ids, statuses, dry_run=False) == ["4", "5", "6"]
    assert pending_order_ids(order_ids, statuses, dry_run=True) == ["4", "5"]


def test_effective_worker_count_caps_workers_to_pending_count() -> None:
    assert effective_worker_count(requested_workers=10, pending_count=3) == 3
    assert effective_worker_count(requested_workers=10, pending_count=12) == 10


def test_effective_worker_count_rejects_invalid_worker_count() -> None:
    with pytest.raises(ValueError, match="workers must be at least 1"):
        effective_worker_count(requested_workers=0, pending_count=3)


def test_validate_worker_count_rejects_zero() -> None:
    with pytest.raises(ValueError, match="workers must be at least 1"):
        validate_worker_count(0)


def test_validate_worker_count_allows_one() -> None:
    validate_worker_count(1)


def test_is_approve_confirmation_dialog_matches_target_order() -> None:
    assert is_approve_confirmation_dialog("Approve Order 205821 ?", "205821")


def test_is_approve_confirmation_dialog_rejects_other_order() -> None:
    assert not is_approve_confirmation_dialog("Approve Order 205819 ?", "205821")


def test_parse_cdp_endpoint_accepts_loopback() -> None:
    assert parse_cdp_endpoint("http://127.0.0.1:9222") == CdpEndpoint(
        url="http://127.0.0.1:9222",
        host="127.0.0.1",
        port=9222,
    )
    assert parse_cdp_endpoint("http://localhost:9333/") == CdpEndpoint(
        url="http://localhost:9333",
        host="127.0.0.1",
        port=9333,
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:9222",
        "http://0.0.0.0:9222",
        "http://10.62.165.58:9222",
        "http://127.0.0.1",
    ],
)
def test_parse_cdp_endpoint_rejects_unsafe_or_incomplete_url(url: str) -> None:
    with pytest.raises(ValueError, match="cdp-url"):
        parse_cdp_endpoint(url)


def test_build_chrome_command_uses_loopback_cdp_and_profile(tmp_path: Path) -> None:
    chrome_path = Path(r"C:\Chrome\chrome.exe")
    profile_dir = tmp_path / "profile"

    command = build_chrome_command(
        chrome_path=chrome_path,
        profile_dir=profile_dir,
        endpoint=parse_cdp_endpoint("http://127.0.0.1:9222"),
    )

    assert command == [
        str(chrome_path),
        "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=9222",
        f"--user-data-dir={profile_dir.resolve()}",
        "--no-first-run",
        "--no-default-browser-check",
        auto_approve.DATA_URL,
    ]


def test_ensure_cdp_browser_reuses_ready_endpoint(tmp_path: Path) -> None:
    launches: list[list[str]] = []

    async def ready(_endpoint: CdpEndpoint) -> bool:
        return True

    launched = asyncio.run(
        ensure_cdp_browser(
            endpoint=parse_cdp_endpoint("http://127.0.0.1:9222"),
            chrome_path=Path(r"C:\Chrome\chrome.exe"),
            profile_dir=tmp_path / "profile",
            timeout_seconds=1,
            probe=ready,
            port_checker=lambda _endpoint: False,
            launcher=launches.append,
        )
    )

    assert launched is False
    assert launches == []


def test_ensure_cdp_browser_launches_once_then_waits(tmp_path: Path) -> None:
    probe_results = iter([False, False, True])
    launches: list[list[str]] = []

    async def probe(_endpoint: CdpEndpoint) -> bool:
        return next(probe_results)

    launched = asyncio.run(
        ensure_cdp_browser(
            endpoint=parse_cdp_endpoint("http://127.0.0.1:9222"),
            chrome_path=Path(r"C:\Chrome\chrome.exe"),
            profile_dir=tmp_path / "profile",
            timeout_seconds=1,
            probe=probe,
            port_checker=lambda _endpoint: False,
            launcher=launches.append,
            sleep=lambda _seconds: asyncio.sleep(0),
        )
    )

    assert launched is True
    assert len(launches) == 1


def test_ensure_cdp_browser_rejects_port_owned_by_other_process(tmp_path: Path) -> None:
    async def unavailable(_endpoint: CdpEndpoint) -> bool:
        return False

    with pytest.raises(BrowserConnectError, match="already in use"):
        asyncio.run(
            ensure_cdp_browser(
                endpoint=parse_cdp_endpoint("http://127.0.0.1:9222"),
                chrome_path=Path(r"C:\Chrome\chrome.exe"),
                profile_dir=tmp_path / "profile",
                timeout_seconds=1,
                probe=unavailable,
                port_checker=lambda _endpoint: True,
                launcher=lambda _command: pytest.fail("must not launch Chrome"),
            )
        )


def test_select_default_context_requires_existing_context() -> None:
    context = object()

    assert select_default_context([context]) is context
    with pytest.raises(BrowserConnectError, match="browser context"):
        select_default_context([])


def test_prepare_worker_context_creates_keepalive_page() -> None:
    class KeepalivePage:
        close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1

    class Context:
        def __init__(self) -> None:
            self.keepalive = KeepalivePage()
            self.new_page_calls = 0
            self.pages = []

        async def new_page(self) -> KeepalivePage:
            self.new_page_calls += 1
            self.pages.append(self.keepalive)
            return self.keepalive

    context = Context()

    selected_context, keepalive = asyncio.run(prepare_worker_context([context]))

    assert selected_context is context
    assert keepalive is context.keepalive
    assert context.new_page_calls == 1
    assert keepalive.close_calls == 0


def test_prepare_worker_context_reuses_existing_page() -> None:
    existing_page = object()

    class Context:
        pages = [existing_page]

        async def new_page(self):
            raise AssertionError("must reuse an existing page")

    context = Context()

    selected_context, keepalive = asyncio.run(prepare_worker_context([context]))

    assert selected_context is context
    assert keepalive is existing_page


def test_run_worker_tasks_does_not_close_context(monkeypatch) -> None:
    class CloseGuardContext:
        close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1

    async def fake_worker_loop(*args, **kwargs) -> None:
        return None

    context = CloseGuardContext()
    monkeypatch.setattr(auto_approve, "worker_loop", fake_worker_loop)

    asyncio.run(
        run_worker_tasks(
            context,
            asyncio.Queue(),
            object(),
            worker_count=1,
            dry_run=True,
        )
    )

    assert context.close_calls == 0


def test_is_browser_closed_error_matches_target_closed() -> None:
    assert is_browser_closed_error(
        auto_approve.PlaywrightError("Target page, context or browser has been closed")
    )
    assert not is_browser_closed_error(auto_approve.PlaywrightError("Navigation timed out"))
