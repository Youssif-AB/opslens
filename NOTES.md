# OpsLens – Learning Notes

## Flask App Structure
- Using a package-based Flask app instead of single-file app.py
- app/ is a Python package because it has __init__.py

## __init__.py
- Runs when the app package is imported
- Creates the Flask app object
- Imports routes so decorators execute

## routes.py
- Contains route functions (URL → response)
- Uses the Flask app created in __init__.py
- Routes attach to the app via decorators

## Templates vs Static
- templates/: HTML rendered by Flask
- static/: CSS and other files served as-is
