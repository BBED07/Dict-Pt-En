from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import psycopg2
from psycopg2.extras import DictCursor
import random
import unicodedata
from fpdf import FPDF
import tempfile
from datetime import datetime
import json
import textwrap

app = Flask(__name__)
CORS(app)

# 数据库连接
def get_db_connection():
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def normalize_text(text):
    """标准化文本"""
    return unicodedata.normalize('NFC', text) if text else ""

# 基础路由
@app.route('/')
def home():
    return 'Welcome to the Dictionary API!'

# 获取所有单词
@app.route('/words', methods=['GET'])
def get_words():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('''
                SELECT * FROM words 
                ORDER BY id
            ''')
            words = cur.fetchall()
            return jsonify([{
                'id': word['id'],
                'english': word['english'],
                'portuguese': word['portuguese'],
                'example': word['example']
            } for word in words])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# 添加新单词
@app.route('/words', methods=['POST'])
def add_word():
    data = request.get_json()
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    
    try:
        english = data['english'].strip()
        portuguese = normalize_text(data['portuguese'].strip())
        example = normalize_text(data.get('example', '').strip())
        created_at = datetime.utcnow()
        
        with conn.cursor() as cur:
            # Insert word
            cur.execute(
                '''INSERT INTO words (english, portuguese, example, created_at) 
                   VALUES (%s, %s, %s, %s) RETURNING id''',
                (english, portuguese, example, created_at)
            )
            word_id = cur.fetchone()[0]
            
        
            conn.commit()
            return jsonify({
                "id": word_id,
                "message": "Word added successfully",
            })
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# Quiz功能
@app.route('/quiz/random', methods=['GET'])
def get_random_quiz():
    try:
        count = request.args.get('count', default=10, type=int)
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
        
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('SELECT COUNT(*) FROM words')
            total_words = cur.fetchone()[0]
            
            if total_words < count:
                count = total_words
            
            # 随机选取单词
            cur.execute('''
                SELECT * FROM words 
                ORDER BY RANDOM() 
                LIMIT %s
            ''', (count,))
            
            words = cur.fetchall()
            
            # 提供问题（英语单词）和正确答案（葡萄牙语）
            quiz_data = [{
                'id': word['id'],
                'question': word['english'],  # 提供英语单词
                'correct_answer': word['portuguese'],  # 返回正确的葡萄牙语答案
                'example': word['example'],
            } for word in words]
            
            # 返回测验数据
            return jsonify(quiz_data)
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# 范围Quiz
@app.route('/quiz/range', methods=['GET'])
def get_range_quiz():
    try:
        start_id = request.args.get('start', default=1, type=int)
        end_id = request.args.get('end', type=int)
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500

        with conn.cursor(cursor_factory=DictCursor) as cur:
            if end_id:
                cur.execute('''
                    SELECT * FROM words 
                    WHERE id BETWEEN %s AND %s 
                    ORDER BY id
                ''', (start_id, end_id))

            else:
                cur.execute('''
                    SELECT * FROM words 
                    WHERE id >= %s 
                    ORDER BY id
                ''', (start_id,))
            
            # 提供问题（英语单词）和正确答案（葡萄牙语）
            quiz_data = [{
                'id': word['id'],
                'question': word['english'],  # 提供英语单词
                'correct_answer': word['portuguese'],  # 返回正确的葡萄牙语答案
                'example': word['example'],
            } for word in words]
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# 搜索功能
@app.route('/search', methods=['GET'])
def search_words():
    try:
        query = request.args.get('q', '').lower()
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
        
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('''
                SELECT * FROM words 
                WHERE LOWER(english) LIKE %s 
                OR LOWER(portuguese) LIKE %s
                ORDER BY id
            ''', (f'%{query}%', f'%{query}%'))
            
            words = cur.fetchall()
            return jsonify([{
                'id': word['id'],
                'english': word['english'],
                'portuguese': word['portuguese'],
                'example': word['example'],
            } for word in words])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# 更新单词
@app.route('/words/<int:id>', methods=['PUT'])
def update_word(id):
    data = request.get_json()
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    
    try:
        english = data['english'].strip()
        portuguese = normalize_text(data['portuguese'].strip())
        example = normalize_text(data.get('example', '').strip())
        tags = data.get('tags', [])
        updated_at = datetime.utcnow()

        with conn.cursor() as cur:
            # Update word
            cur.execute('''
                UPDATE words 
                SET english = %s, portuguese = %s, example = %s, updated_at = %s
                WHERE id = %s
                RETURNING id
            ''', (english, portuguese, example, updated_at, id))
            
            if cur.rowcount == 0:
                return jsonify({"error": "Word not found"}), 404
                
            word_id = cur.fetchone()[0]
            
            conn.commit()
            return jsonify({
                "message": "Word updated successfully",
                "id": word_id,
                "english": english,
                "portuguese": portuguese,
                "example": example,
                "tags": tags
            })
            
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# 删除单词
@app.route('/words/<int:id>', methods=['DELETE'])
def delete_word(id):
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    
    try:
        with conn.cursor() as cur:
            
            cur.execute('DELETE FROM words WHERE id = %s RETURNING id', (id,))
            
            if cur.rowcount == 0:
                return jsonify({"error": "Word not found"}), 404
            
            conn.commit()
            return jsonify({"message": "Word deleted successfully"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# ✅ 让 Flask 监听 0.0.0.0，确保 Render 可以访问
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
