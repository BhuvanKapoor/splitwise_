(function () {
  "use strict";

  const STORAGE_KEY = "split-expenses-v1";

  // All money is stored as integer cents to avoid floating point drift.
  let state = load();

  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed.people) && Array.isArray(parsed.expenses)) return parsed;
      }
    } catch (e) {
      /* storage unavailable or corrupt; start fresh */
    }
    return { people: [], expenses: [] };
  }

  function save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
      /* ignore */
    }
  }

  function uid() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  }

  function toCents(value) {
    const n = Number(value);
    if (!isFinite(n)) return NaN;
    return Math.round(n * 100);
  }

  function fmt(cents) {
    const sign = cents < 0 ? "-" : "";
    return sign + (Math.abs(cents) / 100).toFixed(2);
  }

  function personName(id) {
    const p = state.people.find((x) => x.id === id);
    return p ? p.name : "(removed)";
  }

  // Split `total` cents equally among `ids`, giving leftover cents to the first few.
  function equalShares(total, ids) {
    const base = Math.floor(total / ids.length);
    let remainder = total - base * ids.length;
    const shares = {};
    ids.forEach((id) => {
      shares[id] = base + (remainder > 0 ? 1 : 0);
      if (remainder > 0) remainder--;
    });
    return shares;
  }

  function computeBalances() {
    const bal = {};
    state.people.forEach((p) => (bal[p.id] = 0));
    state.expenses.forEach((e) => {
      bal[e.payer] = (bal[e.payer] || 0) + e.amount;
      Object.entries(e.shares).forEach(([id, share]) => {
        bal[id] = (bal[id] || 0) - share;
      });
    });
    return bal;
  }

  // Greedy settlement: repeatedly match the largest debtor with the largest creditor.
  function computeSettlements(bal) {
    const debtors = [];
    const creditors = [];
    Object.entries(bal).forEach(([id, amt]) => {
      if (amt < 0) debtors.push({ id, amt: -amt });
      else if (amt > 0) creditors.push({ id, amt });
    });
    debtors.sort((a, b) => b.amt - a.amt);
    creditors.sort((a, b) => b.amt - a.amt);

    const result = [];
    let i = 0;
    let j = 0;
    while (i < debtors.length && j < creditors.length) {
      const pay = Math.min(debtors[i].amt, creditors[j].amt);
      result.push({ from: debtors[i].id, to: creditors[j].id, amount: pay });
      debtors[i].amt -= pay;
      creditors[j].amt -= pay;
      if (debtors[i].amt === 0) i++;
      if (creditors[j].amt === 0) j++;
    }
    return result;
  }

  // ---------- DOM ----------
  const $ = (id) => document.getElementById(id);
  const personForm = $("person-form");
  const personInput = $("person-name");
  const peopleList = $("people-list");
  const expenseForm = $("expense-form");
  const descInput = $("exp-desc");
  const amountInput = $("exp-amount");
  const payerSelect = $("exp-payer");
  const splitList = $("split-list");
  const splitSummary = $("split-summary");
  const expenseError = $("expense-error");
  const balancesList = $("balances-list");
  const settleList = $("settle-list");
  const expenseList = $("expense-list");

  function el(tag, props, children) {
    const node = document.createElement(tag);
    if (props) Object.assign(node, props);
    (children || []).forEach((c) => node.append(c));
    return node;
  }

  function emptyItem(text) {
    return el("li", { className: "empty", textContent: text });
  }

  function splitMode() {
    return expenseForm.querySelector('input[name="split-mode"]:checked').value;
  }

  function renderPeople() {
    peopleList.replaceChildren();
    if (state.people.length === 0) {
      peopleList.append(emptyItem("No one added yet."));
      return;
    }
    const involved = new Set();
    state.expenses.forEach((e) => {
      involved.add(e.payer);
      Object.keys(e.shares).forEach((id) => involved.add(id));
    });
    state.people.forEach((p) => {
      const remove = el("button", { type: "button", textContent: "×", title: "Remove" });
      remove.addEventListener("click", () => {
        if (involved.has(p.id)) {
          alert(p.name + " is part of existing expenses. Delete those expenses first.");
          return;
        }
        state.people = state.people.filter((x) => x.id !== p.id);
        save();
        renderAll();
      });
      peopleList.append(el("li", {}, [el("span", { textContent: p.name }), remove]));
    });
  }

  function renderPayerOptions() {
    const current = payerSelect.value;
    payerSelect.replaceChildren();
    state.people.forEach((p) => {
      payerSelect.append(el("option", { value: p.id, textContent: p.name }));
    });
    if (state.people.some((p) => p.id === current)) payerSelect.value = current;
  }

  function renderSplitList() {
    // Preserve existing checkbox / exact-amount state across re-renders.
    const prev = {};
    splitList.querySelectorAll("li[data-id]").forEach((li) => {
      prev[li.dataset.id] = {
        checked: li.querySelector('input[type="checkbox"]').checked,
        exact: li.querySelector('input[type="number"]')?.value || "",
      };
    });

    splitList.replaceChildren();
    if (state.people.length === 0) {
      splitList.append(emptyItem("Add people first."));
      return;
    }
    const mode = splitMode();
    state.people.forEach((p) => {
      const was = prev[p.id];
      const checkbox = el("input", { type: "checkbox", checked: was ? was.checked : true });
      const label = el("label", { className: "inline" }, [checkbox, p.name]);
      const li = el("li", {}, [label]);
      li.dataset.id = p.id;
      if (mode === "exact") {
        const input = el("input", {
          type: "number", min: "0", step: "0.01", placeholder: "0.00",
          value: was ? was.exact : "", disabled: !checkbox.checked,
        });
        input.addEventListener("input", updateSplitSummary);
        li.append(input);
      } else {
        li.append(el("span", { className: "share" }));
      }
      checkbox.addEventListener("change", () => {
        const num = li.querySelector('input[type="number"]');
        if (num) num.disabled = !checkbox.checked;
        updateSplitSummary();
      });
      splitList.append(li);
    });
    updateSplitSummary();
  }

  function selectedParticipants() {
    return Array.from(splitList.querySelectorAll("li[data-id]"))
      .filter((li) => li.querySelector('input[type="checkbox"]').checked)
      .map((li) => ({ id: li.dataset.id, li }));
  }

  function updateSplitSummary() {
    const total = toCents(amountInput.value) || 0;
    const selected = selectedParticipants();
    const mode = splitMode();

    if (mode === "equal") {
      const shares = selected.length ? equalShares(total, selected.map((s) => s.id)) : {};
      splitList.querySelectorAll("li[data-id]").forEach((li) => {
        const span = li.querySelector(".share");
        if (span) span.textContent = shares[li.dataset.id] != null ? fmt(shares[li.dataset.id]) : "—";
      });
      splitSummary.textContent = selected.length
        ? `Split equally among ${selected.length} ${selected.length === 1 ? "person" : "people"}.`
        : "Select at least one person.";
    } else {
      const sum = selected.reduce((acc, s) => {
        const v = toCents(s.li.querySelector('input[type="number"]').value);
        return acc + (isNaN(v) ? 0 : v);
      }, 0);
      const left = total - sum;
      splitSummary.textContent =
        `Assigned ${fmt(sum)} of ${fmt(total)}` +
        (left === 0 ? " ✓" : left > 0 ? ` — ${fmt(left)} left` : ` — ${fmt(-left)} over`);
    }
  }

  function renderBalances() {
    const bal = computeBalances();
    balancesList.replaceChildren();
    if (state.people.length === 0) {
      balancesList.append(emptyItem("No balances yet."));
    }
    state.people.forEach((p) => {
      const amt = bal[p.id] || 0;
      let text = "settled up";
      let cls = "amount";
      if (amt > 0) { text = "gets back " + fmt(amt); cls += " positive"; }
      else if (amt < 0) { text = "owes " + fmt(-amt); cls += " negative"; }
      balancesList.append(el("li", {}, [
        el("span", { textContent: p.name }),
        el("span", { className: cls, textContent: text }),
      ]));
    });

    settleList.replaceChildren();
    const settlements = computeSettlements(bal);
    if (settlements.length === 0) {
      settleList.append(emptyItem("Everyone is settled up."));
      return;
    }
    settlements.forEach((s) => {
      settleList.append(el("li", {}, [
        el("span", { textContent: `${personName(s.from)} → ${personName(s.to)}` }),
        el("span", { className: "amount", textContent: fmt(s.amount) }),
      ]));
    });
  }

  function renderExpenses() {
    expenseList.replaceChildren();
    if (state.expenses.length === 0) {
      expenseList.append(emptyItem("No expenses yet."));
      return;
    }
    state.expenses.slice().reverse().forEach((e) => {
      const among = Object.keys(e.shares).map(personName).join(", ");
      const del = el("button", { type: "button", className: "link danger", textContent: "Delete" });
      del.addEventListener("click", () => {
        if (!confirm(`Delete "${e.desc}"?`)) return;
        state.expenses = state.expenses.filter((x) => x.id !== e.id);
        save();
        renderAll();
      });
      expenseList.append(el("li", {}, [
        el("div", { className: "info" }, [
          el("div", { className: "title", textContent: e.desc }),
          el("div", {
            className: "meta",
            textContent: `${personName(e.payer)} paid · split ${e.mode === "exact" ? "by amount" : "equally"} among ${among}`,
          }),
        ]),
        el("div", { className: "right" }, [
          el("span", { className: "amount", textContent: fmt(e.amount) }),
          del,
        ]),
      ]));
    });
  }

  function renderAll() {
    renderPeople();
    renderPayerOptions();
    renderSplitList();
    renderBalances();
    renderExpenses();
  }

  // ---------- Events ----------
  personForm.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const name = personInput.value.trim();
    if (!name) return;
    if (state.people.some((p) => p.name.toLowerCase() === name.toLowerCase())) {
      alert(name + " is already added.");
      return;
    }
    state.people.push({ id: uid(), name });
    save();
    personInput.value = "";
    personInput.focus();
    renderAll();
  });

  amountInput.addEventListener("input", updateSplitSummary);

  expenseForm.querySelectorAll('input[name="split-mode"]').forEach((r) =>
    r.addEventListener("change", renderSplitList)
  );

  $("select-all").addEventListener("click", () => setAllChecked(true));
  $("select-none").addEventListener("click", () => setAllChecked(false));

  function setAllChecked(value) {
    splitList.querySelectorAll("li[data-id]").forEach((li) => {
      li.querySelector('input[type="checkbox"]').checked = value;
      const num = li.querySelector('input[type="number"]');
      if (num) num.disabled = !value;
    });
    updateSplitSummary();
  }

  function showError(msg) {
    expenseError.textContent = msg;
    expenseError.hidden = false;
  }

  expenseForm.addEventListener("submit", (ev) => {
    ev.preventDefault();
    expenseError.hidden = true;

    if (state.people.length === 0) return showError("Add some people first.");
    const desc = descInput.value.trim();
    const amount = toCents(amountInput.value);
    const payer = payerSelect.value;
    const mode = splitMode();
    const selected = selectedParticipants();

    if (!desc) return showError("Enter a description.");
    if (!(amount > 0)) return showError("Enter an amount greater than 0.");
    if (!payer) return showError("Choose who paid.");
    if (selected.length === 0) return showError("Choose at least one person to split with.");

    let shares;
    if (mode === "equal") {
      shares = equalShares(amount, selected.map((s) => s.id));
    } else {
      shares = {};
      let sum = 0;
      for (const s of selected) {
        const v = toCents(s.li.querySelector('input[type="number"]').value || 0);
        if (isNaN(v) || v < 0) return showError("Exact amounts must be valid, non-negative numbers.");
        if (v > 0) shares[s.id] = v;
        sum += v;
      }
      if (sum !== amount) {
        return showError(`Exact amounts add up to ${fmt(sum)}, but the total is ${fmt(amount)}.`);
      }
    }

    state.expenses.push({ id: uid(), desc, amount, payer, mode, shares, date: Date.now() });
    save();

    descInput.value = "";
    amountInput.value = "";
    splitList.querySelectorAll('input[type="number"]').forEach((i) => (i.value = ""));
    renderAll();
    descInput.focus();
  });

  $("reset-all").addEventListener("click", () => {
    if (!confirm("Remove all people and expenses?")) return;
    state = { people: [], expenses: [] };
    save();
    splitList.replaceChildren();
    renderAll();
  });

  renderAll();
})();
