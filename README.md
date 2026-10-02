# splitwise_

A lightweight Splitwise-style expense splitter that runs entirely in the browser (no backend, no build step).

## Features

- Add / remove people in the group
- Add an expense with a description, amount, and **who paid**
- Choose **who it's split among** (tick any subset of people)
  - **Equally** — remainder cents are distributed so shares always sum to the total
  - **Exact amounts** — enter each person's share; must add up to the total
- Live balances (who gets back / who owes)
- "Settle up" suggestions that minimise the number of payments
- Expense history with delete
- Data is saved in your browser's `localStorage`

## Run

Just open `index.html` in a browser, or serve the folder:

```sh
npx serve .
```

It can also be hosted as-is on GitHub Pages.
