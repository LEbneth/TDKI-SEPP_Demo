# TDKI-SEPP Demo

## Project Structure

```text
AI Demo/
├── main.py
├── config.py
├── context.txt
├── requirements.txt
├── prompts/
│   ├── 1_tool_selection.txt
│   ├── 2_progress.txt
│   └── 3_analysis.txt
├── scripts/
│   ├── scan_device.py
│   ├── check_credentials.py
│   ├── analyze_network.py
│   └── generate_report.py
└── templates/
    └── index.html
```

## Installation

### 1. Install Ollama

Download and install Ollama:

https://ollama.com

### 2. Pull the Required Model

```bash
ollama pull qwen3:4b
```

### 3. Test the Installation

Run the model from the terminal to ensure it is working correctly:

```bash
ollama run qwen3:4b
```

Enter a test prompt to verify that the model is working, then exit with:

```bash
/bye
```

### 4. Install Python Dependencies

Create and activate a virtual environment:

```bash
python -m venv venv
venv\Scripts\activate # For Windows
source venv/bin/activate  # For Linux/Mac
```

Install the required dependencies:

```bash
pip install -r requirements.txt
```

### 5. Run the Application

Make sure Ollama is running by starting it manually or running the following command in a separate terminal widow:

```bash
ollama serve
```

Run the application:

```bash
python main.py
```

Go to the given URL in your browser to access the application. (Should be: http://127.0.0.1:8000)