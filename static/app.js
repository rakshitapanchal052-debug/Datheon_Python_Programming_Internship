const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});
const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 });
const elements = {
  value: document.querySelector("#portfolio-value"),
  invested: document.querySelector("#invested-value"),
  gain: document.querySelector("#gain-value"),
  return: document.querySelector("#total-return"),
  updated: document.querySelector("#updated-at"),
  count: document.querySelector("#holding-count"),
  footerCount: document.querySelector("#footer-count"),
  tbody: document.querySelector("#holdings-body"),
  empty: document.querySelector("#empty-state"),
  refresh: document.querySelector("#refresh-button"),
  dialog: document.querySelector("#holding-dialog"),
  form: document.querySelector("#holding-form"),
  ticker: document.querySelector("#ticker"),
  error: document.querySelector("#form-error"),
  save: document.querySelector("#save-button"),
  toast: document.querySelector("#toast"),
  snapshot: document.querySelector("#snapshot-status"),
};
let toastTimeout;

function showToast(message, isError = false) {
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", isError);
  elements.toast.classList.add("visible");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => elements.toast.classList.remove("visible"), 3500);
}

function setGainClass(node, value) {
  node.classList.toggle("negative", Number(value) < 0);
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "The request could not be completed.");
  return payload;
}

function renderPortfolio(data) {
  const { holdings, totals } = data;
  elements.value.textContent = currency.format(Number(totals.market_value));
  elements.invested.textContent = currency.format(Number(totals.invested));
  elements.gain.textContent = currency.format(Number(totals.gain_loss));
  elements.return.textContent = `${Number(totals.gain_loss_percent) >= 0 ? "+" : ""}${Number(totals.gain_loss_percent).toFixed(2)}%`;
  setGainClass(elements.return, totals.gain_loss_percent);
  elements.gain.style.color = Number(totals.gain_loss) < 0 ? "#ce555b" : "#253b31";
  elements.updated.textContent = `Updated ${new Date(data.updated_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
  elements.count.textContent = holdings.length;
  elements.footerCount.textContent = `${holdings.length} ${holdings.length === 1 ? "holding" : "holdings"}`;
  elements.empty.hidden = holdings.length > 0;
  elements.tbody.replaceChildren(...holdings.map(createHoldingRow));
  elements.snapshot.textContent = holdings.length
    ? "Performance snapshot saved to portfolio_summary.csv."
    : "Your performance snapshots are saved to CSV.";
}

function createHoldingRow(holding) {
  const row = document.createElement("tr");
  const asset = document.createElement("td");
  const assetCell = document.createElement("div");
  assetCell.className = "asset-cell";
  const icon = document.createElement("span");
  icon.className = "asset-icon";
  icon.textContent = holding.ticker.slice(0, 2);
  const copy = document.createElement("span");
  copy.className = "asset-copy";
  const ticker = document.createElement("span");
  ticker.className = "asset-ticker";
  ticker.textContent = holding.ticker;
  const name = document.createElement("span");
  name.className = "asset-name";
  name.textContent = holding.company || "Stock";
  copy.append(ticker, name);
  assetCell.append(icon, copy);
  asset.append(assetCell);
  row.append(asset);

  for (const text of [
    number.format(Number(holding.shares)),
    currency.format(Number(holding.buy_price)),
    currency.format(Number(holding.current_price)),
    currency.format(Number(holding.market_value)),
  ]) {
    const cell = document.createElement("td");
    cell.textContent = text;
    row.append(cell);
  }

  const returnCell = document.createElement("td");
  const returnPill = document.createElement("span");
  returnPill.className = "return-value";
  setGainClass(returnPill, holding.gain_loss);
  returnPill.textContent = `${Number(holding.gain_loss) >= 0 ? "+" : ""}${currency.format(Number(holding.gain_loss))} (${Number(holding.gain_loss_percent).toFixed(2)}%)`;
  returnCell.append(returnPill);
  row.append(returnCell);

  const actionCell = document.createElement("td");
  const remove = document.createElement("button");
  remove.className = "delete-button";
  remove.type = "button";
  remove.setAttribute("aria-label", `Remove ${holding.ticker}`);
  remove.title = `Remove ${holding.ticker}`;
  remove.textContent = "×";
  remove.addEventListener("click", () => removeHolding(holding.ticker, remove));
  actionCell.append(remove);
  row.append(actionCell);
  return row;
}

async function refreshPortfolio() {
  elements.refresh.disabled = true;
  elements.refresh.querySelector("svg").classList.add("spinning");
  try {
    renderPortfolio(await requestJson("/api/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    }));
  } catch (error) {
    elements.snapshot.textContent = error.message;
    showToast(error.message, true);
  } finally {
    elements.refresh.disabled = false;
    elements.refresh.querySelector("svg").classList.remove("spinning");
  }
}

async function removeHolding(ticker, button) {
  button.disabled = true;
  try {
    await requestJson(`/api/positions/${encodeURIComponent(ticker)}`, { method: "DELETE" });
    showToast(`${ticker} removed from your portfolio.`);
    await refreshPortfolio();
  } catch (error) {
    showToast(error.message, true);
    button.disabled = false;
  }
}

function openDialog() {
  elements.error.textContent = "";
  elements.form.reset();
  elements.dialog.showModal();
  elements.ticker.focus();
}

document.querySelector("#add-button").addEventListener("click", openDialog);
document.querySelector("#empty-add-button").addEventListener("click", openDialog);
document.querySelector("#close-dialog").addEventListener("click", () => elements.dialog.close());
document.querySelector("#cancel-dialog").addEventListener("click", () => elements.dialog.close());
elements.refresh.addEventListener("click", refreshPortfolio);
elements.dialog.addEventListener("click", (event) => {
  if (event.target === elements.dialog) elements.dialog.close();
});
elements.ticker.addEventListener("input", () => {
  elements.ticker.value = elements.ticker.value.toUpperCase().replace(/\s/g, "");
});
elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.error.textContent = "";
  elements.save.disabled = true;
  elements.save.textContent = "Saving…";
  try {
    await requestJson("/api/positions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker: elements.ticker.value,
        shares: elements.form.elements.shares.value,
        buy_price: elements.form.elements.buy_price.value,
      }),
    });
    elements.dialog.close();
    showToast(`${elements.ticker.value} saved to your portfolio.`);
    await refreshPortfolio();
  } catch (error) {
    elements.error.textContent = error.message;
  } finally {
    elements.save.disabled = false;
    elements.save.textContent = "Save holding";
  }
});

refreshPortfolio();
