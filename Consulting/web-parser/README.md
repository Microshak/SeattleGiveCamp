# Web Parser

This project is a simple web parser that extracts website URLs from the "Visit Website" buttons on the page [https://clutch.co/web-developers/seattle](https://clutch.co/web-developers/seattle).

## Project Structure

```
web-parser
├── src
│   ├── main.py        # Entry point of the application
│   ├── parser.py      # Contains the logic for parsing the webpage
│   └── utils.py       # Utility functions for HTTP requests and URL handling
├── requirements.txt    # Lists the project dependencies
└── README.md           # Documentation for the project
```

## Installation

To set up the project, clone the repository and install the required dependencies:

```bash
git clone <repository-url>
cd web-parser
pip install -r requirements.txt
```

## Usage

To run the web parser, execute the following command:

```bash
python src/main.py
```

This will initialize the web parser, extract the URLs from the specified webpage, and output the results to the screen.

## Dependencies

This project requires the following Python packages:

- requests
- beautifulsoup4

Make sure to install these packages using the `requirements.txt` file provided.