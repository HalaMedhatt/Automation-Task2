# Fakturama Image-to-Cash Automation

## 📌 Project Overview
This project is an end-to-end automation pipeline designed to process a single order image (e.g., a scanned or photographed purchase order) and transform it into a fully saved, verified Order and linked Invoice inside the **Fakturama** desktop application. 

The core philosophy of this system is an **"Order-First"** approach. It extracts structured data from the image, opens a New Order, and uses the Order's internal selectors as the primary existence check for Debtors and Products. Missing master data (Debtors, Products, VATs, Payment Methods) is only created when an exact match is unavailable, after which the system safely returns to the same open Order.

## 🏗️ Architecture & Approach
The pipeline is built using Python and is divided into three main layers:

1. **Extraction & Validation Layer (`src/extraction`, `src/models`)**:
   - **Google Gemini API**: Processes the image using a highly constrained prompt to return strictly formatted JSON. 
   - **Pydantic**: Defines the expected schema, enforcing types and ensuring no required fields are missing.
   - **Business Validation**: Uses Python's `Decimal` (never `float`) to guarantee financial precision. It calculates line totals (Qty × Unit Price × (1 - Discount)) and verifies that `Net + VAT = Gross`. If the AI misreads a number or applies a discount incorrectly, the pipeline halts immediately.
   - **AI Safeguard**: Automatically corrects common AI hallucinations (e.g., converting a discount of `0.1` back to `10.0`%).

2. **UI Automation Layer (`src/ui`)**:
   - **Microsoft UI Automation (UIA):** Discovers and interacts with accessible Fakturama controls using `pywinauto`.
   - **Native Win32 Integration:** Handles window activation,keyboard events, and focus verification.
   - **Visual Grounding:** Uses Windows GDI BitBlt to identify grid states and row boundaries.
   - **Clipboard-based Extraction:** Retrieves structured data from custom controls that do not expose accessible cells.
   - **No Hardcoded Coordinates:** Resolves controls and calculates interaction positions dynamically from the current UI.

3. **Workflow Layer (`src/workflows`)**:
   - Orchestrates the business logic. For example, the `debtor_flow` attempts an exact match (Company, Name, ZIP, City). If it fails, it triggers the creation flow, saves the new debtor, and re-selects it in the still-open Order. The exact same logic applies to Products and VATs.

## 🛠️ Tech Stack
- **Python 3.12+**: Core programming language.
- **google-genai**: For multimodal LLM extraction from images.
- **pywinauto**: For Windows Desktop UI Automation.
- **Microsoft UI Automation (UIA)**: The underlying accessibility framework used by pywinauto for control discovery.
- **pywin32:** Native Windows API integration for window management, keyboard events, and focus verification.
- **ctypes (Built-in):** Access to native Windows GDI and User32 APIs for in-memory screen capture and clipboard sequence tracking.
- **Windows Clipboard:** Deterministic extraction of structured data from custom desktop controls.
- **pydantic**: For strict data validation and schema enforcement.
- **python-dotenv**: For securely loading environment variables (e.g., API keys) from `.env` files.
- **logging** (Built-in): For tracking execution steps and capturing system errors.
- **pytest**: For unit testing calculation logic and schema validation.

## Technical Challenge: Custom Customer Grid

Fakturama exposes its customer grid as a custom SWT `Pane`
(`SWT_Window0`), preventing direct access to its rows and cells
through the tested accessibility interfaces.

### Evaluated Approaches

- **UIA / Win32:** Located the grid but could not access its internal cells.
- **OCR:** Produced unreliable column separation and recognition errors.
- **Top-to-Bottom Navigation:** Caused selection loss and Java exceptions
  during clipboard operations.
- **Bottom-to-Top Navigation:** Preserved row selection more reliably
  when reaching the first row in tested cases.
- **Keyboard-only Selection:** `Ctrl+End` did not consistently establish
  a valid row selection.
- **GetPixel:** Pixel-by-pixel inspection introduced significant delays.

### Selected Solution

A deterministic hybrid approach combining:

1. **UIA:** Dynamically locate the customer grid.
2. **Native Win32 Handle:** Improve window and keyboard focus reliability.
3. **GDI BitBlt:** Detect empty results, observe grid stability,
   and identify row boundaries efficiently.
4. **Dynamic Click:** Explicitly select the last visible row using
   dynamically calculated coordinates.
5. **Clipboard Extraction:** Retrieve original tab-separated row data
   without OCR.
6. **Reverse Navigation:** Traverse from bottom to top using `Up`
   to avoid the selection-loss issues observed in forward navigation.
7. **Exact Matching:** Evaluate all collected rows using the five
   required non-empty fields before selecting an existing customer,
   stopping for manual review, or proceeding to creation.

## Technical Challenge: Order Address Rendering

Fakturama displays the debtor's main company name instead of
the additional name stored in the delivery address.

### Evaluated Approaches

- **Direct Comparison:** Caused a false mismatch.

### Selected Solution

- Use the debtor's main company name for Order address verification.

## 📁 Project Structure
```text
fakturama-automation/
├── data/
│   ├── input/             # Source order images (git-ignored)
│   └── output/            # Extracted and validated order JSON
├── src/
│   ├── main.py                # Main entry point and pipeline orchestrator
│   ├── extraction/            # Gemini API client and strict JSON prompts
│   ├── models/                # Pydantic schemas and Business Validation logic
│   ├── ui/                    # pywinauto locators, dialogs, and form managers
│   ├── workflows/             # Order-first multi-step processes
│   └── utils/                 # Decimal math utilities, logging, and exceptions
├── tests/                     # pytest unit tests
├── .env                       # Local configuration (API keys - git-ignored)
├── .gitignore
├── requirements.txt
└── README.md
```
## ⚙️ Setup Instructions

### 1. Prerequisites
- Windows OS (Required for Fakturama and pywinauto).
- Fakturama installed locally.
- Python 3.12+ installed.
- A Google Gemini API Key.

### 2. Installation
Clone the repository and set up the virtual environment:

```bash
git clone <your-repo-url>
cd fakturama-automation
python -m venv venv
# On Windows:
venv\Scripts\activate
pip install -r requirements.txt
```
### 3. Environment Variables
Create a `.env` file in the root directory and add your Gemini API key:

```env
GEMINI_API_KEY=your_api_key_here
```
## 🚀 How to Run

1. Place the order image in the `data/input/` folder and name it `order.jpg`.
2. Ensure Fakturama is installed and can be launched.
3. Run the pipeline:

```bash
python -m src.main
```