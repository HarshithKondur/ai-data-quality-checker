# 🧠 AI Data Quality Checker

Automatically scan any CSV file for data quality issues and get a plain-English AI-powered report — straight in your terminal.

---

## What It Does

Given any CSV file, the tool will:

| Check | What it finds |
|---|---|
| **Missing Values** | Which columns have nulls and how many |
| **Duplicates** | Exact duplicate rows |
| **Outliers** | Numeric anomalies via IQR & Z-score methods |
| **Inconsistencies** | Mixed casing, invalid emails, unparseable dates, negative values in unexpected columns |

It then sends a structured JSON summary to **Claude (claude-sonnet-4-6)** and prints back a clean, plain-English report.

---

## Requirements

- Python 3.9+
- An [Anthropic API key](https://console.anthropic.com/)

---

## Setup

### 1. Clone / enter the project

```bash
cd ai-data-quality-checker
```

### 2. Create a virtual environment (recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate      # macOS / Linux
# .venv\Scripts\activate       # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set your Anthropic API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

> **Tip:** Add this to your `.bashrc` / `.zshrc` so you don't have to set it every session.

---

## Usage

```bash
python checker.py <path-to-csv>
```

### Run on the included sample file

```bash
python checker.py sample_data.csv
```

### Optional flag: see the raw JSON summary before the AI report

```bash
python checker.py sample_data.csv --dump-summary
```

### Help

```bash
python checker.py --help
```

---

## Example Output

```
[✓] Loaded 'sample_data.csv'  —  25 rows × 9 columns

🔍 Scanning for data quality issues...
  [✓] Missing values scanned
  [✓] Duplicates scanned
  [✓] Outliers scanned
  [✓] Inconsistencies scanned

🤖 Sending findings to Claude (claude-sonnet-4-6)...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  📊  DATA QUALITY REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Overview**
The dataset contains 25 employee records across 9 columns. Several data
quality issues were found that should be addressed before using this data
for reporting or analysis.

**Missing Values**
- `age`: 3 missing values (12%)
- `salary`: 2 missing values (8%)
...

**Recommendations**
1. Remove or merge the duplicate row for Bob Smith (row 8).
2. Investigate the $920,000 salary for Karen Thomas — likely a data entry error.
...
```

---

## Project Structure

```
ai-data-quality-checker/
├── checker.py        # Main script
├── sample_data.csv   # Sample CSV with intentional issues
├── requirements.txt  # Python dependencies
└── README.md         # This file
```

---

## How It Works

```
CSV File
   │
   ▼
pandas (load + scan)
   │  ├─ missing values
   │  ├─ duplicates
   │  ├─ outliers (IQR + Z-score)
   │  └─ inconsistencies
   │
   ▼
Structured JSON summary
   │
   ▼
Claude claude-sonnet-4-6 (Anthropic API)
   │
   ▼
Plain-English report printed to terminal
```
