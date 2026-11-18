import os

from wsgi import app


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("\n=======================================================")
    print("  SMART ROSTER MANAGEMENT SYSTEM")
    print(f"  Running locally on http://127.0.0.1:{port}")
    print("=======================================================\n")
    app.run(
        host='127.0.0.1',
        port=port,
        debug=app.config['DEBUG'],
        use_reloader=False
    )
