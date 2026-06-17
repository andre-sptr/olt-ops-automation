from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import re
import socket
import subprocess
import sys
import threading
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from playwright.async_api import (
    Browser,
    BrowserContext,
    Dialog,
    Error as PlaywrightError,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

DATA_URL: Final = "https://dbaccess-ibooster.telkom.co.id/newkarina/ram"
LOGIN_PATH: Final = "/newkarina/login"
OTP_PATH: Final = "/newkarina/verifikasi-otp"
AUTHENTICATION_PATHS: Final = (LOGIN_PATH, OTP_PATH)
SUCCESS_MESSAGE: Final = "Approve order berhasil"
PAGE_READY_TIMEOUT_MS: Final = 180_000
SEARCH_TIMEOUT_MS: Final = 10_000
MODAL_WAIT_MS: Final = 30_000
MODAL_RETRY_PAUSE_MS: Final = 10_000
MODAL_ATTEMPTS: Final = 5
APPROVE_DIALOG_TIMEOUT_SECONDS: Final = 60
BROWSER_LAUNCH_TIMEOUT_SECONDS: Final = 45
DEFAULT_CDP_URL: Final = "http://127.0.0.1:9222"
MATCHING_ORDER_ROW_INDEXES_HELPER_JS: Final = """
const matchingOrderRowIndexes = orderId => {
  const searchInput = document.querySelector('thead input');
  const wrapper = searchInput ? searchInput.closest('.dataTables_wrapper') : null;
  if (!wrapper) return [];
  const table = Array.from(wrapper.querySelectorAll('table')).find(candidate => {
    if (candidate.tBodies.length > 0) {
      return Array.from(candidate.querySelectorAll('thead th, thead td')).some(
        cell => cell.innerText.trim().toUpperCase() === 'ID ORDER'
      );
    }
    return false;
  });
  if (!table) return [];
  const headerRows = Array.from(table.querySelectorAll('thead tr'));
  let idIndex = -1;
  for (const headerRow of headerRows) {
    const headerCells = Array.from(headerRow.querySelectorAll('th,td'));
    idIndex = headerCells.findIndex(
      cell => cell.innerText.trim().toUpperCase() === 'ID ORDER'
    );
    if (idIndex >= 0) break;
  }
  if (idIndex < 0) return [];
  const dataRows = Array.from(table.querySelectorAll('tbody tr'))
    .filter(row => row.querySelectorAll('td').length > 0);
  return dataRows.reduce((matches, row, index) => {
    const cells = Array.from(row.querySelectorAll('td'));
    const value = cells[idIndex] ? cells[idIndex].innerText.trim() : '';
    if (value === orderId) matches.push(index);
    return matches;
  }, []);
};
"""

RESULT_FIELDNAMES: Final = [
    "order_id",
    "status",
    "message",
    "attempts",
    "worker",
    "finished_at",
]
TERMINAL_STATUSES: Final = {"APPROVED", "NOT_FOUND", "APPROVE_FAILED"}
DRY_RUN_TERMINAL_STATUSES: Final = {"APPROVED", "NOT_FOUND", "APPROVE_FAILED", "DRY_RUN_FOUND"}


class BrowserConnectError(RuntimeError):
    pass


@dataclass(frozen=True)
class CdpEndpoint:
    url: str
    host: str
    port: int


@dataclass(frozen=True)
class Result:
    order_id: str
    status: str
    message: str
    attempts: int
    worker: str
    finished_at: str


class ResultWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        if not self.path.exists():
            with self.path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDNAMES)
                writer.writeheader()

    def append(self, result: Result) -> None:
        with self.lock:
            with self.path.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDNAMES)
                writer.writerow(
                    {
                        "order_id": result.order_id,
                        "status": result.status,
                        "message": result.message,
                        "attempts": str(result.attempts),
                        "worker": result.worker,
                        "finished_at": result.finished_at,
                    }
                )


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_order_ids(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    seen: set[str] = set()
    order_ids: list[str] = []
    for token in re.split(r"[\s,]+", content):
        value = token.strip()
        if not value or not value.isdigit() or value in seen:
            continue
        seen.add(value)
        order_ids.append(value)
    return order_ids


def load_completed_statuses(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    statuses: dict[str, str] = {}
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            order_id = (row.get("order_id") or "").strip()
            status = (row.get("status") or "").strip()
            if order_id and status:
                statuses[order_id] = status
    return statuses


def pending_order_ids(
    order_ids: list[str],
    completed_statuses: dict[str, str],
    *,
    dry_run: bool,
) -> list[str]:
    terminal = DRY_RUN_TERMINAL_STATUSES if dry_run else TERMINAL_STATUSES
    return [order_id for order_id in order_ids if completed_statuses.get(order_id) not in terminal]


def validate_worker_count(requested_workers: int) -> None:
    if requested_workers < 1:
        raise ValueError("workers must be at least 1")


def effective_worker_count(*, requested_workers: int, pending_count: int) -> int:
    validate_worker_count(requested_workers)
    return min(requested_workers, pending_count)


def parse_cdp_endpoint(url: str) -> CdpEndpoint:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("--cdp-url must use HTTP on localhost or 127.0.0.1")
    if parsed.port is None:
        raise ValueError("--cdp-url must include a port")
    return CdpEndpoint(
        url=url.rstrip("/"),
        host="127.0.0.1",
        port=parsed.port,
    )


def build_chrome_command(
    *,
    chrome_path: Path,
    profile_dir: Path,
    endpoint: CdpEndpoint,
) -> list[str]:
    return [
        str(chrome_path),
        f"--remote-debugging-address={endpoint.host}",
        f"--remote-debugging-port={endpoint.port}",
        f"--user-data-dir={profile_dir.resolve()}",
        "--no-first-run",
        "--no-default-browser-check",
        DATA_URL,
    ]


def find_chrome_executable(explicit_path: Path | None = None) -> Path:
    if explicit_path is not None:
        candidate = explicit_path.expanduser().resolve()
        if candidate.is_file():
            return candidate
        raise BrowserConnectError(f"Chrome executable not found: {candidate}")

    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    checked = ", ".join(str(candidate) for candidate in candidates)
    raise BrowserConnectError(f"Chrome executable not found. Checked: {checked}")


async def is_cdp_ready(endpoint: CdpEndpoint) -> bool:
    def fetch_version() -> bool:
        try:
            with urlopen(f"{endpoint.url}/json/version", timeout=2) as response:
                payload = json.load(response)
            return bool(payload.get("webSocketDebuggerUrl"))
        except (OSError, ValueError, URLError):
            return False

    return await asyncio.to_thread(fetch_version)


def is_port_in_use(endpoint: CdpEndpoint) -> bool:
    try:
        with socket.create_connection((endpoint.host, endpoint.port), timeout=0.5):
            return True
    except OSError:
        return False


def launch_detached_chrome(command: list[str]) -> None:
    creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess,
        "CREATE_NEW_PROCESS_GROUP",
        0,
    )
    subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creationflags,
    )


async def ensure_cdp_browser(
    *,
    endpoint: CdpEndpoint,
    chrome_path: Path,
    profile_dir: Path,
    timeout_seconds: float,
    probe: Callable[[CdpEndpoint], Awaitable[bool]] = is_cdp_ready,
    port_checker: Callable[[CdpEndpoint], bool] = is_port_in_use,
    launcher: Callable[[list[str]], None] = launch_detached_chrome,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> bool:
    if await probe(endpoint):
        return False
    if port_checker(endpoint):
        raise BrowserConnectError(
            f"Port {endpoint.port} is already in use, but it is not a valid Chrome CDP endpoint. "
            "Use a different loopback port with --cdp-url."
        )

    profile_dir.mkdir(parents=True, exist_ok=True)
    command = build_chrome_command(
        chrome_path=chrome_path,
        profile_dir=profile_dir,
        endpoint=endpoint,
    )
    launcher(command)

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        if await probe(endpoint):
            return True
        await sleep(0.5)
    raise BrowserConnectError(
        f"Chrome CDP endpoint {endpoint.url} did not become ready within "
        f"{timeout_seconds:g} seconds."
    )


def select_default_context(contexts: Sequence[BrowserContext]) -> BrowserContext:
    if not contexts:
        raise BrowserConnectError("Connected Chrome has no browser context")
    return contexts[0]


async def prepare_worker_context(
    contexts: Sequence[BrowserContext],
) -> tuple[BrowserContext, Page]:
    context = select_default_context(contexts)
    keepalive_page = context.pages[0] if context.pages else await context.new_page()
    return context, keepalive_page


def is_browser_closed_error(error: BaseException) -> bool:
    message = str(error).lower()
    return "target page, context or browser has been closed" in message or "browser has been closed" in message


def parse_args(argv: list[str]) -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Approve Karina RAM order IDs with Playwright.")
    parser.add_argument("--input", type=Path, default=script_dir / "order_ids.txt")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=script_dir / ".karina-playwright-profile-permanent",
    )
    parser.add_argument("--result", type=Path, default=script_dir / "auto_approve_result.csv")
    parser.add_argument("--log", type=Path, default=script_dir / "auto_approve.log")
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    parser.add_argument("--chrome-path", type=Path)
    parser.add_argument("--launch-timeout", type=float, default=BROWSER_LAUNCH_TIMEOUT_SECONDS)
    return parser.parse_args(argv)


def setup_logging(path: Path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )


def is_authentication_url(url: str) -> bool:
    return any(path in url for path in AUTHENTICATION_PATHS)


def is_authentication_page(page: Page) -> bool:
    return is_authentication_url(page.url)


def order_search_input(page: Page) -> Locator:
    return page.locator("thead input").nth(0)


def order_table(page: Page) -> Locator:
    wrapper = order_search_input(page).locator(
        "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), "
        "' dataTables_wrapper ')][1]"
    )
    return wrapper.locator("table:has(tbody)").last


def visible_data_rows(page: Page) -> Locator:
    return order_table(page).locator("tbody tr")


def matching_order_row_indexes_js(return_expression: str) -> str:
    expression = return_expression.strip()
    return f"""
    orderId => {{
      {MATCHING_ORDER_ROW_INDEXES_HELPER_JS}
      return {expression};
    }}
    """


def is_approve_confirmation_dialog(message: str, order_id: str) -> bool:
    return bool(re.search(rf"\bApprove\s+Order\s+{re.escape(order_id)}\b", message, re.IGNORECASE))


async def wait_for_ram_ready(page: Page, worker: str) -> None:
    while True:
        await page.goto(DATA_URL, wait_until="domcontentloaded", timeout=PAGE_READY_TIMEOUT_MS)
        if is_authentication_page(page):
            await wait_for_authentication_completion(page, worker)
            continue
        await order_search_input(page).wait_for(state="visible", timeout=PAGE_READY_TIMEOUT_MS)
        return


async def wait_for_authentication_completion(page: Page, worker: str) -> None:
    logging.warning("[%s] Login/OTP required. Complete it in the browser.", worker)
    while is_authentication_page(page):
        try:
            await page.wait_for_url(
                lambda url: not is_authentication_url(str(url)),
                timeout=30_000,
            )
        except PlaywrightTimeoutError:
            logging.info("[%s] Still waiting for login/OTP completion.", worker)
    logging.info("[%s] Login/OTP completed. Opening the RAM page.", worker)


async def has_matching_order_row(page: Page, order_id: str) -> bool:
    return await matching_order_row_count(page, order_id) == 1


async def matching_order_row_count(page: Page, order_id: str) -> int:
    return int(
        await page.evaluate(
            matching_order_row_indexes_js("matchingOrderRowIndexes(orderId).length"),
            order_id,
        )
    )


async def matching_order_row_index(page: Page, order_id: str) -> int | None:
    return await page.evaluate(
        matching_order_row_indexes_js(
            """
            (() => {
              const indexes = matchingOrderRowIndexes(orderId);
              return indexes.length === 1 ? indexes[0] : null;
            })()
            """
        ),
        order_id,
    )


async def search_order(page: Page, order_id: str) -> bool:
    search = order_search_input(page)
    await search.click()
    await search.press("Control+A")
    await search.press_sequentially(order_id, delay=100)
    try:
        await page.wait_for_function(
            matching_order_row_indexes_js("matchingOrderRowIndexes(orderId).length === 1"),
            arg=order_id,
            timeout=SEARCH_TIMEOUT_MS,
        )
    except PlaywrightTimeoutError:
        return False
    return await has_matching_order_row(page, order_id)


async def matching_order_row(page: Page, order_id: str) -> Locator | None:
    index = await matching_order_row_index(page, order_id)
    if index is None:
        return None
    return visible_data_rows(page).nth(index)


async def open_order_modal(page: Page, order_id: str) -> bool:
    for attempt in range(1, MODAL_ATTEMPTS + 1):
        try:
            row = await matching_order_row(page, order_id)
            if row is None:
                logging.warning("Expected exactly one row for %s on attempt %s.", order_id, attempt)
                await page.wait_for_timeout(MODAL_RETRY_PAUSE_MS)
                continue
            action_button = row.locator("button").last
            await action_button.click()
            await page.get_by_text(f"ID Order {order_id}", exact=True).wait_for(
                state="visible",
                timeout=MODAL_WAIT_MS,
            )
            return True
        except (PlaywrightTimeoutError, PlaywrightError) as error:
            logging.warning("Modal for %s did not appear on attempt %s: %s", order_id, attempt, error)
            await page.wait_for_timeout(MODAL_RETRY_PAUSE_MS)
    return False


async def close_order_modal(page: Page) -> None:
    close_button = page.locator(
        ".modal.show button.close, "
        ".modal.show button[aria-label='Close'], "
        ".modal.show [data-dismiss='modal'], "
        ".modal.show [data-bs-dismiss='modal']"
    ).first
    if await close_button.count() > 0:
        await close_button.click()
        return
    await page.keyboard.press("Escape")


async def approve_order(page: Page, order_id: str) -> tuple[bool, str]:
    dialogs: asyncio.Queue[Dialog] = asyncio.Queue()

    def handle_dialog(dialog: Dialog) -> None:
        dialogs.put_nowait(dialog)

    page.on("dialog", handle_dialog)
    try:
        await page.get_by_role("button", name="Approve", exact=True).click()

        first_dialog = await asyncio.wait_for(
            dialogs.get(),
            timeout=APPROVE_DIALOG_TIMEOUT_SECONDS,
        )
        first_message = first_dialog.message
        if not is_approve_confirmation_dialog(first_message, order_id):
            await first_dialog.dismiss()
            return False, f"Unexpected approve confirmation: {first_message}"
        await first_dialog.accept()

        second_dialog = await asyncio.wait_for(
            dialogs.get(),
            timeout=APPROVE_DIALOG_TIMEOUT_SECONDS,
        )
        second_message = second_dialog.message
        await second_dialog.accept()

        if SUCCESS_MESSAGE.lower() in second_message.lower():
            return True, SUCCESS_MESSAGE
        return False, f"{first_message} | {second_message}"
    except (TimeoutError, PlaywrightTimeoutError):
        return False, "Timed out waiting for approve dialog"
    finally:
        page.remove_listener("dialog", handle_dialog)


async def wait_for_existing_ram_ready(page: Page, worker: str) -> None:
    if DATA_URL not in page.url or is_authentication_page(page):
        await wait_for_ram_ready(page, worker)
        return
    await order_search_input(page).wait_for(state="visible", timeout=PAGE_READY_TIMEOUT_MS)


async def ensure_page_ready_with_recovery(
    context: BrowserContext,
    page: Page,
    worker: str,
    stop_event: asyncio.Event,
) -> Page | None:
    for attempt in range(1, 4):
        try:
            if attempt == 1:
                await wait_for_existing_ram_ready(page, worker)
            else:
                await page.reload(wait_until="domcontentloaded", timeout=PAGE_READY_TIMEOUT_MS)
                await wait_for_existing_ram_ready(page, worker)
            return page
        except (PlaywrightTimeoutError, PlaywrightError) as error:
            if is_browser_closed_error(error):
                stop_event.set()
                logging.error("[%s] Chrome was closed during page recovery.", worker)
                return None
            logging.warning("[%s] Page ready attempt %s failed: %s", worker, attempt, error)
    try:
        await page.close()
    except PlaywrightError:
        pass
    replacement = await new_worker_page(context, worker, stop_event)
    if replacement is None:
        return None
    try:
        await wait_for_ram_ready(replacement, worker)
        return replacement
    except (PlaywrightTimeoutError, PlaywrightError) as error:
        if is_browser_closed_error(error):
            stop_event.set()
        logging.error("[%s] Replacement tab failed: %s", worker, error)
        try:
            await replacement.close()
        except PlaywrightError:
            pass
        return None


async def new_worker_page(
    context: BrowserContext,
    worker: str,
    stop_event: asyncio.Event,
) -> Page | None:
    try:
        return await context.new_page()
    except (PlaywrightTimeoutError, PlaywrightError) as error:
        if is_browser_closed_error(error):
            stop_event.set()
        logging.error("[%s] Could not open worker tab: %s", worker, error)
        return None


def record_result(
    writer: ResultWriter,
    *,
    order_id: str,
    status: str,
    message: str,
    attempts: int,
    worker: str,
) -> None:
    writer.append(
        Result(
            order_id=order_id,
            status=status,
            message=message,
            attempts=attempts,
            worker=worker,
            finished_at=now_iso(),
        )
    )
    logging.info("[%s] %s %s: %s", worker, order_id, status, message)


async def process_order(
    page: Page,
    writer: ResultWriter,
    *,
    order_id: str,
    worker: str,
    dry_run: bool,
) -> None:
    if not await search_order(page, order_id):
        record_result(
            writer,
            order_id=order_id,
            status="NOT_FOUND",
            message="No matching ID ORDER row within 10 seconds",
            attempts=1,
            worker=worker,
        )
        return

    if not await open_order_modal(page, order_id):
        record_result(
            writer,
            order_id=order_id,
            status="ACTION_MODAL_ERROR",
            message="Order action modal did not open",
            attempts=MODAL_ATTEMPTS,
            worker=worker,
        )
        return

    if dry_run:
        await close_order_modal(page)
        record_result(
            writer,
            order_id=order_id,
            status="DRY_RUN_FOUND",
            message="Dry run found matching order and closed modal without approving",
            attempts=1,
            worker=worker,
        )
        return

    approved, message = await approve_order(page, order_id)
    if not approved:
        try:
            await close_order_modal(page)
        except PlaywrightError:
            pass
    record_result(
        writer,
        order_id=order_id,
        status="APPROVED" if approved else "APPROVE_FAILED",
        message=message,
        attempts=1,
        worker=worker,
    )


async def worker_loop(
    context: BrowserContext,
    queue: asyncio.Queue[str],
    writer: ResultWriter,
    stop_event: asyncio.Event,
    *,
    worker_index: int,
    dry_run: bool,
) -> None:
    worker = f"worker-{worker_index}"
    page: Page | None = None
    try:
        while True:
            if stop_event.is_set():
                break
            try:
                order_id = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            try:
                if page is None:
                    page = await new_worker_page(context, worker, stop_event)
                if page is not None:
                    page = await ensure_page_ready_with_recovery(
                        context,
                        page,
                        worker,
                        stop_event,
                    )

                if page is None:
                    page = None
                    record_result(
                        writer,
                        order_id=order_id,
                        status="PAGE_ERROR",
                        message="Page could not be made ready",
                        attempts=1,
                        worker=worker,
                    )
                    if stop_event.is_set():
                        break
                    continue

                await process_order(page, writer, order_id=order_id, worker=worker, dry_run=dry_run)
            except PlaywrightError as error:
                if is_browser_closed_error(error):
                    stop_event.set()
                record_result(
                    writer,
                    order_id=order_id,
                    status="PAGE_ERROR",
                    message=str(error),
                    attempts=1,
                    worker=worker,
                )
                if stop_event.is_set():
                    break
            finally:
                queue.task_done()
    finally:
        if page is not None:
            try:
                await page.close()
            except PlaywrightError:
                pass


async def run_worker_tasks(
    context: BrowserContext,
    queue: asyncio.Queue[str],
    writer: ResultWriter,
    *,
    worker_count: int,
    dry_run: bool,
) -> None:
    stop_event = asyncio.Event()
    tasks = [
        asyncio.create_task(
            worker_loop(
                context,
                queue,
                writer,
                stop_event,
                worker_index=index,
                dry_run=dry_run,
            )
        )
        for index in range(1, worker_count + 1)
    ]
    await asyncio.gather(*tasks)


async def connect_to_cdp_browser(
    playwright_chromium,
    endpoint: CdpEndpoint,
    *,
    timeout_seconds: float,
) -> Browser:
    try:
        return await playwright_chromium.connect_over_cdp(
            endpoint.url,
            timeout=timeout_seconds * 1000,
        )
    except PlaywrightError as error:
        raise BrowserConnectError(
            f"Could not connect Playwright to Chrome at {endpoint.url}: {error}"
        ) from error


async def run_async(args: argparse.Namespace) -> int:
    setup_logging(args.log)
    validate_worker_count(args.workers)
    try:
        endpoint = parse_cdp_endpoint(args.cdp_url)
        chrome_path = find_chrome_executable(args.chrome_path)
    except (ValueError, BrowserConnectError) as error:
        logging.error("BROWSER_CONNECT_ERROR: %s", error)
        return 2

    order_ids = parse_order_ids(args.input)
    statuses = load_completed_statuses(args.result)
    pending = pending_order_ids(order_ids, statuses, dry_run=args.dry_run)
    worker_count = (
        effective_worker_count(requested_workers=args.workers, pending_count=len(pending))
        if pending
        else 0
    )
    if worker_count == 0:
        logging.info("No pending order IDs to process.")
        return 0

    logging.info("Processing %s pending order IDs with %s workers.", len(pending), worker_count)
    writer = ResultWriter(args.result)
    queue: asyncio.Queue[str] = asyncio.Queue()
    for order_id in pending:
        queue.put_nowait(order_id)

    try:
        launched = await ensure_cdp_browser(
            endpoint=endpoint,
            chrome_path=chrome_path,
            profile_dir=args.profile_dir,
            timeout_seconds=args.launch_timeout,
        )
    except BrowserConnectError as error:
        logging.error("BROWSER_CONNECT_ERROR: %s", error)
        return 2

    if launched:
        logging.info("Permanent Chrome opened with profile: %s", args.profile_dir)
    else:
        logging.info("Reusing permanent Chrome at %s", endpoint.url)

    logging.info("Starting Playwright browser driver.")
    async with async_playwright() as playwright:
        logging.info("Playwright driver started.")
        try:
            browser = await connect_to_cdp_browser(
                playwright.chromium,
                endpoint,
                timeout_seconds=args.launch_timeout,
            )
            context, keepalive_page = await prepare_worker_context(browser.contexts)
        except BrowserConnectError as error:
            logging.error("BROWSER_CONNECT_ERROR: %s", error)
            return 2
        logging.info("Connected to permanent Chrome.")
        logging.info("Keepalive tab ready; Chrome will remain open after workers finish.")
        await run_worker_tasks(
            context,
            queue,
            writer,
            worker_count=worker_count,
            dry_run=args.dry_run,
        )
        _ = keepalive_page
    return 0


def run(args: argparse.Namespace) -> int:
    return asyncio.run(run_async(args))


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
