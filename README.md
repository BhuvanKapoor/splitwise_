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

### Where data is saved

The sidebar shows which storage the app is using.

- **Google Sheets** (recommended, especially on Streamlit Community Cloud): used when Google credentials are configured (see below).
- **Local SQLite** (default): used when they aren't. Data goes in `splitwise.db` next to the app (set `SPLITWISE_DB` to change the path). On hosts with temporary storage, such as Streamlit Community Cloud, this file is wiped whenever the app restarts.

### Saving to Google Sheets

1. In the [Google Cloud console](https://console.cloud.google.com/), create (or pick) a project and enable the **Google Sheets API**.
2. Go to **IAM & Admin → Service accounts**, create a service account, then under **Keys → Add key → JSON** download its key file.
3. Create an empty Google Sheet and **share it with the service account's email** (`...@...iam.gserviceaccount.com`) as an **Editor**.
4. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`, put the sheet's URL under `[google_sheets]`, and copy the fields from the JSON key into `[gcp_service_account]`.
   On Streamlit Community Cloud, paste the same content into **App settings → Secrets** instead.
5. Restart the app. The sidebar should say **Saving to Google Sheets**.

The app creates four tabs in the sheet the first time it runs:

| Tab | Columns |
| --- | --- |
| `trips` | id, name, currency, created_at |
| `people` | id, trip_id, name |
| `expenses` | id, trip_id, spent_on, description, amount, payer_id, paid_by, split_mode, split_among, created_at |
| `shares` | expense_id, person_id, person, share |

Amounts are stored in normal currency units (e.g. `33.34`). `paid_by`, `split_among` and `person` are readable copies of names for browsing the sheet; the app uses the id columns. Avoid editing the sheet by hand while the app is open, and don't reorder its columns.

`secrets.toml` holds a private key: it's listed in `.gitignore`, so never commit it.

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
