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
   - **Microsoft UI Automation (UIA)**: Interacts with Fakturama's UI using `pywinauto`.
   - **No Hardcoded Coordinates**: The system relies on UIA properties (AutomationId, ControlType, Name) and relative relationships to locate fields, buttons, and tabs. 
   - **Robust Interactions**: Implements explicit waits, retries, and fallback strategies to handle UI rendering delays or dynamic layouts.

3. **Workflow Layer (`src/workflows`)**:
   - Orchestrates the business logic. For example, the `debtor_flow` attempts an exact match (Company, Name, ZIP, City). If it fails, it triggers the creation flow, saves the new debtor, and re-selects it in the still-open Order. The exact same logic applies to Products and VATs.

## 🛠️ Tech Stack
- **Python 3.12+**: Core programming language.
- **google-genai**: For multimodal LLM extraction from images.
- **pywinauto**: For Windows Desktop UI Automation.
- **Microsoft UI Automation (UIA)**: The underlying accessibility framework used by pywinauto for control discovery.
- **pydantic**: For strict data validation and schema enforcement.
- **python-dotenv**: For securely loading environment variables (e.g., API keys) from `.env` files.
- **logging** (Built-in): For tracking execution steps and capturing system errors.
- **pytest**: For unit testing calculation logic and schema validation.


## 📁 Project Structure
```text
fakturama-automation/
├── data/input/                # Directory for source order images (git-ignored)
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