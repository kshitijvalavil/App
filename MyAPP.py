from flask import Flask, jsonify, render_template_string

from token_dashboard import bp as tokens_bp

app = Flask(__name__)
app.register_blueprint(tokens_bp)

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My Flask App</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f0f4f8;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .card {
            background: white;
            border-radius: 16px;
            padding: 48px 56px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.08);
            text-align: center;
            max-width: 480px;
            width: 90%;
        }
        .badge {
            display: inline-block;
            background: #e8f5e9;
            color: #2e7d32;
            font-size: 13px;
            font-weight: 600;
            padding: 4px 12px;
            border-radius: 999px;
            margin-bottom: 24px;
        }
        h1 { font-size: 2rem; color: #1a202c; margin-bottom: 12px; }
        p  { color: #718096; line-height: 1.6; margin-bottom: 32px; }
        .btn {
            background: #4f46e5;
            color: white;
            border: none;
            padding: 12px 28px;
            border-radius: 8px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        .btn:hover { background: #4338ca; }
        #msg { margin-top: 20px; color: #4f46e5; font-weight: 500; min-height: 24px; }
    </style>
</head>
<body>
    <div class="card">
        <span class="badge">🚀 Live on Render</span>
        <h1>Hello, World!</h1>
        <p>Your Flask app is up and running. Edit <code>app.py</code> to start building.</p>
        <button class="btn" onclick="ping()">Ping the API</button>
        <div id="msg"></div>
        <p style="margin:24px 0 0"><a href="/tokens">Token usage dashboard &rarr;</a></p>
    </div>
    <script>
        async function ping() {
            const res = await fetch('/api/ping');
            const data = await res.json();
            document.getElementById('msg').textContent = '✅ ' + data.message;
        }
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/ping")
def ping():
    return jsonify({"message": "pong! Your API is working."})

if __name__ == "__main__":
    app.run(debug=True)
