import psycopg2
import os
from flask import Flask, request, jsonify

app = Flask(__name__)

# ✅ 通过环境变量获取 Render 提供的数据库 URL
DATABASE_URL = os.getenv("DATABASE_URL")

# ✅ 连接数据库
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

# ✅ 创建数据库表（只执行一次）
def create_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS words (
            id SERIAL PRIMARY KEY,
            english TEXT NOT NULL,
            portuguese TEXT NOT NULL
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

# ✅ 主页路由，测试 API 是否在线
@app.route("/")
def home():
    return "✅ API is running!"

# ✅ 添加单词
@app.route("/add_word", methods=["POST"])
def add_word():
    data = request.json
    english = data.get("english")
    portuguese = data.get("portuguese")

    if not english or not portuguese:
        return jsonify({"error": "缺少参数"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO words (english, portuguese) VALUES (%s, %s)", (english, portuguese))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "单词已添加！"}), 201

# ✅ 获取所有单词
@app.route("/get_words", methods=["GET"])
def get_words():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT english, portuguese FROM words")
    words = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify(words)

# ✅ 确保数据库表存在
create_table()

# ✅ 让 Flask 监听 0.0.0.0，确保 Render 可以访问
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
