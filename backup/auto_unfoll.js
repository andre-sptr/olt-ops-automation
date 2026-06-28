(async () => {
  const CONFIG = {
    keepUsernames: ["princess_ulel"],
    dryRun: false,
    clickDelayMs: 1200,
    clickJitterMs: 700,
    confirmDelayMs: 300,
    scrollDelayMs: 850,
    scrollJitterMs: 500,
    maxActions: 1000,
    pauseEveryActions: 25,
    pauseMs: 15000,
    networkWaitMs: 3000,
    stopOnConsecutiveServerProblems: 2,
    stopOnNetworkMisses: 3,
    stableRoundsToStop: 4
  };

  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const jitter = max => Math.floor(Math.random() * Math.max(0, max || 0));
  const pacedSleep = (base, random = 0) => sleep(base + jitter(random));
  const norm = value => String(value || "")
    .trim()
    .replace(/^@+/, "")
    .toLowerCase();
  const cleanText = el => String(el?.innerText || el?.textContent || "")
    .replace(/\s+/g, " ")
    .trim();
  const keep = new Set(CONFIG.keepUsernames.map(norm));

  const state = {
    stopped: false,
    seen: new Set(),
    actions: 0,
    ok: 0,
    skip: 0,
    err: 0,
    dry: 0,
    netOk: 0,
    netWarn: 0,
    netErr: 0,
    netMiss: 0,
    consecutiveServerProblems: 0,
    rounds: 0,
    started: new Date()
  };

  const panel = document.createElement("div");
  panel.style = [
    "position:fixed",
    "z-index:2147483647",
    "right:10px",
    "bottom:10px",
    "width:560px",
    "max-width:calc(100vw - 20px)",
    "background:#101820",
    "color:#f4f7fb",
    "font:12px Consolas,monospace",
    "border:2px solid #18a999",
    "border-radius:6px",
    "box-shadow:0 8px 30px rgba(0,0,0,.35)"
  ].join(";");

  const toolbar = document.createElement("div");
  toolbar.style = "display:flex;gap:8px;align-items:center;padding:8px;border-bottom:1px solid #28434d;";

  const title = document.createElement("strong");
  title.textContent = CONFIG.dryRun ? "TikTok unfollow DRY RUN" : "TikTok unfollow LIVE";
  title.style = "flex:1;color:#fff;";

  const stopButton = document.createElement("button");
  stopButton.textContent = "Stop";
  stopButton.style = "padding:6px 10px;background:#d64045;color:#fff;border:0;border-radius:4px;cursor:pointer;";
  stopButton.onclick = () => {
    state.stopped = true;
    update("STOP\tALL\tStop requested");
  };

  const downloadButton = document.createElement("button");
  downloadButton.textContent = "Download Log";
  downloadButton.style = "padding:6px 10px;background:#18a999;color:#fff;border:0;border-radius:4px;cursor:pointer;";

  const box = document.createElement("textarea");
  box.readOnly = true;
  box.style = [
    "display:block",
    "width:100%",
    "height:300px",
    "box-sizing:border-box",
    "background:#101820",
    "color:#f4f7fb",
    "font:12px Consolas,monospace",
    "border:0",
    "padding:8px",
    "resize:vertical",
    "outline:none"
  ].join(";");

  toolbar.append(title, stopButton, downloadButton);
  panel.append(toolbar, box);
  document.body.appendChild(panel);

  const log = [
    `TikTok unfollow started: ${state.started.toISOString()}`,
    `URL: ${location.href}`,
    `Mode: ${CONFIG.dryRun ? "DRY_RUN (no clicks)" : "LIVE (will click unfollow)"}`,
    `Keep: ${[...keep].map(x => `@${x}`).join(", ")}`,
    `Safety: maxActions=${CONFIG.maxActions}, clickDelay=${CONFIG.clickDelayMs}-${CONFIG.clickDelayMs + CONFIG.clickJitterMs}ms, pauseEvery=${CONFIG.pauseEveryActions}, pauseMs=${CONFIG.pauseMs}`,
    "",
    "status\tusername\tdetail"
  ];

  downloadButton.onclick = () => {
    const blob = new Blob([box.value], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `tiktok_unfollow_log_${new Date().toISOString().replace(/[:.]/g, "-")}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  function update(line) {
    if (line) log.push(line);
    box.value = log.join("\n");
    box.scrollTop = box.scrollHeight;
    document.title = `TT_UNFOLLOW A${state.actions} OK${state.ok} SK${state.skip} ER${state.err}`;
  }

  function isVisible(el) {
    if (!el || !el.getBoundingClientRect) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return rect.width > 0
      && rect.height > 0
      && style.display !== "none"
      && style.visibility !== "hidden";
  }

  function getPopup() {
    const byE2E = document.querySelector('[data-e2e="follow-info-popup"]');
    if (byE2E && isVisible(byE2E)) return byE2E;

    const dialogs = [...document.querySelectorAll('[role="dialog"]')].filter(isVisible);
    return dialogs.find(dialog => /mengikuti|following/i.test(cleanText(dialog))) || document.body;
  }

  function getList(root) {
    const candidates = [...root.querySelectorAll("*")]
      .filter(isVisible)
      .filter(el => {
        const style = getComputedStyle(el);
        return el.scrollHeight > el.clientHeight + 40
          && (style.overflowY === "auto" || style.overflowY === "scroll");
      })
      .sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight));

    return candidates[0] || root;
  }

  function usernameFromHref(href) {
    const match = String(href || "").match(/\/@([^/?#]+)/);
    return match ? norm(decodeURIComponent(match[1])) : "";
  }

  function closestUserRow(link, root) {
    let node = link;
    for (let i = 0; i < 8 && node && node !== root; i++) {
      const rect = node.getBoundingClientRect();
      const hasButton = node.querySelector('button[data-e2e="follow-button"], button');
      if (hasButton && rect.height >= 35 && rect.height <= 180) return node;
      node = node.parentElement;
    }

    return link.closest("li") || link.parentElement;
  }

  function buttonLooksFollowing(button) {
    if (!button || button.disabled) return false;

    const text = cleanText(button).toLowerCase();
    const aria = String(button.getAttribute("aria-label") || "").trim().toLowerCase();
    const exactFollowing = ["mengikuti", "following", "teman", "friends"];

    return exactFollowing.includes(text)
      || aria.startsWith("mengikuti ")
      || aria.startsWith("following ")
      || aria.startsWith("teman ")
      || aria.startsWith("friends ");
  }

  function getRows(root) {
    const links = [...root.querySelectorAll('a[href^="/@"], a[href*="tiktok.com/@"]')]
      .filter(isVisible);
    const rows = [];
    const used = new Set();

    for (const link of links) {
      const username = usernameFromHref(link.getAttribute("href"));
      if (!username || used.has(username)) continue;

      const row = closestUserRow(link, root);
      const button = row && [...row.querySelectorAll('button[data-e2e="follow-button"], button')]
        .filter(isVisible)
        .find(buttonLooksFollowing);

      rows.push({
        username,
        href: link.getAttribute("href"),
        label: cleanText(link),
        row,
        button,
        buttonText: cleanText(button)
      });
      used.add(username);
    }

    return rows;
  }

  function findConfirmButton() {
    const cancelWords = /cancel|batal|tidak|no/i;

    return [...document.querySelectorAll('button, [role="button"]')]
      .filter(isVisible)
      .find(button => {
        const text = cleanText(button).toLowerCase();
        if (!text || cancelWords.test(text)) return false;
        return text === "berhenti mengikuti"
          || text === "unfollow"
          || text === "hapus"
          || text === "remove"
          || text === "ya"
          || text === "yes"
          || text === "confirm";
      });
  }

  function installNetworkMonitor() {
    if (window.__TT_UNFOLLOW_NET && window.__TT_UNFOLLOW_NET.version === 1) {
      return window.__TT_UNFOLLOW_NET;
    }

    const monitor = {
      version: 1,
      results: [],
      waiters: [],
      record(result) {
        this.results.push(result);
        if (this.results.length > 120) this.results.shift();
        this.waiters.slice().forEach(waiter => waiter());
      },
      waitForResult(afterIndex, timeoutMs) {
        return new Promise(resolve => {
          let done = false;

          const finish = result => {
            if (done) return;
            done = true;
            clearTimeout(timer);
            this.waiters = this.waiters.filter(waiter => waiter !== check);
            resolve(result || null);
          };

          const choose = final => {
            const candidates = this.results.slice(afterIndex)
              .filter(item => item && item.path === "/api/commit/follow/user/");
            const definitive = candidates.find(item =>
              item.error
              || item.httpStatus >= 400
              || item.statusCode !== null
              || item.statusMsg
            );

            if (definitive) finish(definitive);
            if (final && candidates.length) finish(candidates[candidates.length - 1]);
            if (final) finish(null);
          };

          const check = () => choose(false);
          const timer = setTimeout(() => choose(true), timeoutMs);
          this.waiters.push(check);
          check();
        });
      }
    };

    function safeText(value, limit = 500) {
      return String(value || "").slice(0, limit);
    }

    function parseUrl(rawUrl) {
      try {
        const url = new URL(String(rawUrl), location.href);
        return {
          path: url.pathname,
          type: url.searchParams.get("type"),
          actionType: url.searchParams.get("action_type"),
          userId: url.searchParams.get("user_id")
        };
      } catch {
        return { path: String(rawUrl || ""), type: null, actionType: null, userId: null };
      }
    }

    function parseJson(text) {
      if (!text) return {};
      try {
        const json = JSON.parse(text);
        return {
          statusCode: json.status_code ?? json.statusCode ?? null,
          followStatus: json.follow_status ?? json.followStatus ?? null,
          statusMsg: json.status_msg || json.statusMsg || ""
        };
      } catch {
        return {};
      }
    }

    function shouldRecord(urlInfo) {
      return urlInfo.path === "/api/commit/follow/user/";
    }

    const nativeFetch = window.fetch;
    window.fetch = async function(input, init) {
      const rawUrl = typeof input === "string" ? input : input && input.url;
      const method = String((init && init.method) || (input && input.method) || "GET").toUpperCase();
      const urlInfo = parseUrl(rawUrl);

      try {
        const response = await nativeFetch.apply(this, arguments);
        if (shouldRecord(urlInfo)) {
          const result = {
            source: "fetch",
            method,
            httpStatus: response.status,
            error: "",
            responseText: "",
            statusCode: null,
            followStatus: null,
            statusMsg: "",
            ...urlInfo
          };

          response.clone().text()
            .then(text => monitor.record({ ...result, responseText: safeText(text), ...parseJson(text) }))
            .catch(error => monitor.record({ ...result, error: safeText(error) }));
        }
        return response;
      } catch (error) {
        if (shouldRecord(urlInfo)) {
          monitor.record({
            source: "fetch",
            method,
            httpStatus: 0,
            error: safeText(error),
            responseText: "",
            statusCode: null,
            followStatus: null,
            statusMsg: "",
            ...urlInfo
          });
        }
        throw error;
      }
    };

    const NativeXHR = window.XMLHttpRequest;
    function WrappedXHR() {
      const xhr = new NativeXHR();
      const result = {
        source: "xhr",
        method: "GET",
        httpStatus: 0,
        error: "",
        responseText: "",
        statusCode: null,
        followStatus: null,
        statusMsg: "",
        path: "",
        type: null,
        actionType: null,
        userId: null
      };

      const nativeOpen = xhr.open;
      xhr.open = function(method, url) {
        Object.assign(result, parseUrl(url), { method: String(method || "GET").toUpperCase() });
        return nativeOpen.apply(xhr, arguments);
      };

      const nativeSend = xhr.send;
      xhr.send = function() {
        xhr.addEventListener("loadend", () => {
          if (!shouldRecord(result)) return;
          let text = "";
          try {
            text = safeText(xhr.responseText || "");
          } catch {}
          monitor.record({
            ...result,
            httpStatus: xhr.status,
            responseText: text,
            ...parseJson(text)
          });
        });
        return nativeSend.apply(xhr, arguments);
      };

      return xhr;
    }

    WrappedXHR.prototype = NativeXHR.prototype;
    Object.setPrototypeOf(WrappedXHR, NativeXHR);
    window.XMLHttpRequest = WrappedXHR;
    window.__TT_UNFOLLOW_NET = monitor;
    return monitor;
  }

  const networkMonitor = CONFIG.dryRun ? null : installNetworkMonitor();

  function applyNetworkSafety(result, username) {
    if (!result) {
      state.netMiss++;
      state.netWarn++;
      update(`WARN\t@${username}\tno commit/follow response captured (${state.netMiss}/${CONFIG.stopOnNetworkMisses})`);

      if (state.netMiss >= CONFIG.stopOnNetworkMisses) {
        state.stopped = true;
        update("STOP\tALL\tnetwork response missing repeatedly; verify manually before continuing");
      }
      return true;
    }

    state.netMiss = 0;

    if (result.error || result.httpStatus < 200 || result.httpStatus >= 300) {
      state.err++;
      state.netErr++;
      state.consecutiveServerProblems++;
      update(`ERROR\t@${username}\tHTTP ${result.httpStatus || "failed"} ${result.error || ""}`.trim());
      return false;
    }

    if (result.statusCode !== null && result.statusCode !== 0) {
      state.err++;
      state.netErr++;
      state.consecutiveServerProblems++;
      update(`ERROR\t@${username}\tserver status_code=${result.statusCode} ${result.statusMsg || ""}`.trim());
      return false;
    }

    state.netOk++;
    state.consecutiveServerProblems = 0;
    update(`NET\t@${username}\taccepted HTTP ${result.httpStatus}${result.statusCode === 0 ? " status_code=0" : ""}`);
    return true;
  }

  async function unfollow(row) {
    if (!row.button || !buttonLooksFollowing(row.button)) {
      state.skip++;
      update(`SKIP\t@${row.username}\tfollowing button not found`);
      return false;
    }

    const netStart = networkMonitor ? networkMonitor.results.length : 0;
    row.button.scrollIntoView({ block: "center", inline: "nearest" });
    await sleep(150);
    row.button.click();
    state.actions++;
    await sleep(CONFIG.confirmDelayMs);

    const confirmButton = findConfirmButton();
    if (confirmButton) {
      const confirmText = cleanText(confirmButton);
      confirmButton.click();
      const netResult = networkMonitor && await networkMonitor.waitForResult(netStart, CONFIG.networkWaitMs);
      const accepted = applyNetworkSafety(netResult, row.username);
      if (accepted) {
        state.ok++;
        update(`OK\t@${row.username}\tconfirmed: ${confirmText}`);
      }
      await pacedSleep(CONFIG.clickDelayMs, CONFIG.clickJitterMs);
      return accepted;
    }

    const netResult = networkMonitor && await networkMonitor.waitForResult(netStart, CONFIG.networkWaitMs);
    const accepted = applyNetworkSafety(netResult, row.username);
    if (accepted) {
      state.ok++;
      update(`OK\t@${row.username}\tclicked; no confirm dialog detected`);
    }
    await pacedSleep(CONFIG.clickDelayMs, CONFIG.clickJitterMs);
    return accepted;
  }

  update();
  window.stopTikTokUnfollowExcept = () => {
    state.stopped = true;
    update("STOP\tALL\tStop requested from console");
  };

  let stableRounds = 0;

  while (!state.stopped) {
    const popup = getPopup();
    const list = getList(popup);
    const rows = getRows(list);
    let newTargetsThisRound = 0;

    if (!rows.length) {
      state.rounds++;
      update(`WAIT\tALL\tNo rows found in modal round ${state.rounds}`);
      await sleep(CONFIG.scrollDelayMs);
    }

    for (const row of rows) {
      if (state.stopped) break;
      if (state.seen.has(row.username)) continue;
      state.seen.add(row.username);

      if (keep.has(row.username)) {
        state.skip++;
        update(`KEEP\t@${row.username}\tprotected account`);
        continue;
      }

      if (!row.button) {
        state.skip++;
        update(`SKIP\t@${row.username}\tbutton not in following state`);
        continue;
      }

      newTargetsThisRound++;

      if (CONFIG.dryRun) {
        state.dry++;
        update(`DRY\t@${row.username}\twould unfollow (${row.buttonText || "button"})`);
      } else {
        await unfollow(row);

        if (state.consecutiveServerProblems >= CONFIG.stopOnConsecutiveServerProblems) {
          state.stopped = true;
          update(`STOP\tALL\tserver rejected ${state.consecutiveServerProblems} actions in a row`);
        }

        if (state.actions >= CONFIG.maxActions) {
          state.stopped = true;
          update(`STOP\tALL\tmaxActions reached: ${CONFIG.maxActions}`);
        }

        if (!state.stopped && CONFIG.pauseEveryActions > 0 && state.actions % CONFIG.pauseEveryActions === 0) {
          update(`PAUSE\tALL\tcooldown after ${state.actions} actions`);
          await pacedSleep(CONFIG.pauseMs, CONFIG.scrollJitterMs);
        }
      }
    }

    const atBottom = list.scrollTop + list.clientHeight >= list.scrollHeight - 8;
    if (newTargetsThisRound === 0 && atBottom) {
      stableRounds++;
    } else {
      stableRounds = 0;
    }

    if (stableRounds >= CONFIG.stableRoundsToStop) break;

    const before = list.scrollTop;
    list.scrollTop = Math.min(
      list.scrollTop + Math.max(260, Math.floor(list.clientHeight * 0.85)),
      list.scrollHeight
    );
    list.dispatchEvent(new Event("scroll", { bubbles: true }));
    await pacedSleep(CONFIG.scrollDelayMs, CONFIG.scrollJitterMs);

    if (list.scrollTop === before && atBottom) stableRounds++;
  }

  log.push("");
  log.push(`Finished: ${new Date().toISOString()}`);
  log.push(`Summary: ACTIONS=${state.actions} OK=${state.ok} DRY=${state.dry} SKIP=${state.skip} ERROR=${state.err} NET_OK=${state.netOk} NET_WARN=${state.netWarn} NET_ERR=${state.netErr}`);
  if (CONFIG.dryRun) {
    log.push("Dry-run only. Change CONFIG.dryRun to false for live unfollow.");
  }
  box.value = log.join("\n");
  document.title = `TT_UNFOLLOW_DONE OK${state.ok} DRY${state.dry} SK${state.skip} ER${state.err}`;
})();
