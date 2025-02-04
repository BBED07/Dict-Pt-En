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

app = Flask(__name__)
CORS(app)

# PostgreSQL 数据库连接
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

# 现有的基础路由
@app.route('/')
def home():
    return 'Welcome to the Dictionary API!'

@app.route('/words', methods=['GET'])
def get_words():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('SELECT * FROM words ORDER BY id')
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
        
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO words (english, portuguese, example) VALUES (%s, %s, %s) RETURNING id',
                (english, portuguese, example)
            )
            new_id = cur.fetchone()[0]
            conn.commit()
            return jsonify({"id": new_id, "message": "Word added successfully"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# 新增的Quiz功能路由
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
            
            cur.execute('''
                SELECT * FROM words 
                ORDER BY RANDOM() 
                LIMIT %s
            ''', (count,))
            
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
                cur.execute('SELECT * FROM words WHERE id BETWEEN %s AND %s ORDER BY id', 
                          (start_id, end_id))
            else:
                cur.execute('SELECT * FROM words WHERE id >= %s ORDER BY id', (start_id,))
            
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

# 导出功能路由
@app.route('/export/txt', methods=['GET'])
def export_txt():
    try:
        include_examples = request.args.get('include_examples', 'true').lower() == 'true'
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
        
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('SELECT * FROM words ORDER BY id')
            words = cur.fetchall()
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as temp_file:
                for word in words:
                    if include_examples:
                        temp_file.write(f"{word['english']} -> {word['portuguese']} | Example: {word['example']}\n")
                    else:
                        temp_file.write(f"{word['english']} -> {word['portuguese']}\n")
                temp_path = temp_file.name
                
        return send_file(temp_path, as_attachment=True, download_name='vocabulary.txt')
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/export/pdf', methods=['GET'])
def export_pdf():
    try:
        include_examples = request.args.get('include_examples', 'true').lower() == 'true'
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
        
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('SELECT * FROM words ORDER BY id')
            words = cur.fetchall()
            
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=11)
            
            # 设置列宽
            if include_examples:
                col_widths = [10, 40, 40, 100]
            else:
                col_widths = [10, 90, 90]
            line_height = 8
            
            # 添加表头
            pdf.cell(col_widths[0], line_height, "No.", 1)
            pdf.cell(col_widths[1], line_height, "English", 1)
            pdf.cell(col_widths[2], line_height, "Portuguese", 1)
            if include_examples:
                pdf.cell(col_widths[3], line_height, "Example", 1)
            pdf.ln()
            
            # 添加数据
            for word in words:
                pdf.cell(col_widths[0], line_height, str(word['id']), 1)
                pdf.cell(col_widths[1], line_height, word['english'], 1)
                pdf.cell(col_widths[2], line_height, word['portuguese'], 1)
                if include_examples:
                    pdf.cell(col_widths[3], line_height, word['example'], 1)
                pdf.ln()
            
            # 保存到临时文件
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                temp_path = temp_file.name
                pdf.output(temp_path)
                
            return send_file(temp_path, as_attachment=True, download_name='vocabulary.pdf')
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
                'example': word['example']
            } for word in words])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# 修改单词
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
        
        with conn.cursor() as cur:
            cur.execute('''
                UPDATE words 
                SET english = %s, portuguese = %s, example = %s 
                WHERE id = %s
                RETURNING id
            ''', (english, portuguese, example, id))
            
            if cur.rowcount == 0:
                return jsonify({"error": "Word not found"}), 404
                
            conn.commit()
            return jsonify({"message": "Word updated successfully"})
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
