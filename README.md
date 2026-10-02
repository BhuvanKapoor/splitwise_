# splitwise_

Two ways to split expenses with friends:

1. **Streamlit app** (`streamlit_app.py`): organise expenses by **trip**, saved to a SQLite database so you can come back to any trip later.
2. **Static web app** (`index.html`): a single-page splitter that saves to your browser.

## Streamlit app (trips)

```sh
pip install -r requirements.txt
streamlit run streamlit_app.py
```

- Create as many trips as you like (each with its own currency) and switch between them from the sidebar
- Each trip has its own people and expenses
- For every expense, pick **who paid**, the date, and **who it's split among**, either equally or by exact amounts
- Balances table (paid / share of costs / owes or gets back) and settle-up suggestions for each trip
- Search and delete expenses, and download a trip as CSV
- Rename a trip, change its currency, or delete it

Data is stored in `splitwise.db` next to the app. Set the `SPLITWISE_DB` environment variable to use a different path.
On hosts with temporary storage, such as Streamlit Community Cloud, the database is wiped whenever the app restarts, so run it locally or on a server with a persistent disk to keep your trips.

## Static web app

A lightweight splitter that runs entirely in the browser (no backend, no build step).

- Add / remove people in the group
- Add an expense with a description, amount, and **who paid**
- Choose **who it's split among** (tick any subset of people)
  - **Equally**: leftover cents are distributed so shares always add up to the total
  - **Exact amounts**: enter each person's share; they must add up to the total
- Live balances (who gets back / who owes)
- "Settle up" suggestions that minimise the number of payments
- Expense history with delete
- Data is saved in your browser's `localStorage`

Just open `index.html` in a browser, or serve the folder:

```sh
npx serve .
```

It can also be hosted as-is on GitHub Pages.
