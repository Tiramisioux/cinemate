# Installing MkDocs

This project uses [MkDocs](https://www.mkdocs.org/) with the Material theme to build the documentation.

## Quick start

1. Install the Python dependencies:
   ```bash
   pip install mkdocs mkdocs-material
   ```
2. Start a local preview server from the repository root:
   ```bash
   mkdocs serve
   ```
   The site will be available at `http://127.0.0.1:8000` and reload on file changes.
3. To build the static site:
   ```bash
   mkdocs build
   ```
   The generated files will appear in the `site/` directory.
