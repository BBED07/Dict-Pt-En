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
                SELECT w.*, array_agg(t.name) as tags 
                FROM words w 
                LEFT JOIN word_tags wt ON w.id = wt.word_id 
                LEFT JOIN tags t ON wt.tag_id = t.id 
                GROUP BY w.id 
                ORDER BY w.id
            ''')
            words = cur.fetchall()
            return jsonify([{
                'id': word['id'],
                'english': word['english'],
                'portuguese': word['portuguese'],
                'example': word['example'],
                'tags': [tag for tag in word['tags'] if tag is not None]
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
        tags = data.get('tags', [])
        created_at = datetime.utcnow()
        
        with conn.cursor() as cur:
            # Insert word
            cur.execute(
                '''INSERT INTO words (english, portuguese, example, created_at) 
                   VALUES (%s, %s, %s, %s) RETURNING id''',
                (english, portuguese, example, created_at)
            )
            word_id = cur.fetchone()[0]
            
            # Handle tags
            if tags:
                # Insert new tags if they don't exist
                for tag in tags:
                    cur.execute(
                        '''INSERT INTO tags (name) VALUES (%s) 
                           ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name 
                           RETURNING id''',
                        (tag,)
                    )
                    tag_id = cur.fetchone()[0]
                    # Link tag to word
                    cur.execute(
                        '''INSERT INTO word_tags (word_id, tag_id) 
                           VALUES (%s, %s) ON CONFLICT DO NOTHING''',
                        (word_id, tag_id)
                    )
            
            conn.commit()
            return jsonify({
                "id": word_id,
                "message": "Word added successfully",
                "tags": tags
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
            
            cur.execute('''
                SELECT w.*, array_agg(t.name) as tags 
                FROM words w 
                LEFT JOIN word_tags wt ON w.id = wt.word_id 
                LEFT JOIN tags t ON wt.tag_id = t.id 
                GROUP BY w.id 
                ORDER BY RANDOM() 
                LIMIT %s
            ''', (count,))
            
            words = cur.fetchall()
            return jsonify([{
                'id': word['id'],
                'english': word['english'],
                'portuguese': word['portuguese'],
                'example': word['example'],
                'tags': [tag for tag in word['tags'] if tag is not None]
            } for word in words])
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
                    SELECT w.*, array_agg(t.name) as tags 
                    FROM words w 
                    LEFT JOIN word_tags wt ON w.id = wt.word_id 
                    LEFT JOIN tags t ON wt.tag_id = t.id 
                    WHERE w.id BETWEEN %s AND %s 
                    GROUP BY w.id 
                    ORDER BY w.id
                ''', (start_id, end_id))
            else:
                cur.execute('''
                    SELECT w.*, array_agg(t.name) as tags 
                    FROM words w 
                    LEFT JOIN word_tags wt ON w.id = wt.word_id 
                    LEFT JOIN tags t ON wt.tag_id = t.id 
                    WHERE w.id >= %s 
                    GROUP BY w.id 
                    ORDER BY w.id
                ''', (start_id,))
            
            words = cur.fetchall()
            return jsonify([{
                'id': word['id'],
                'english': word['english'],
                'portuguese': word['portuguese'],
                'example': word['example'],
                'tags': [tag for tag in word['tags'] if tag is not None]
            } for word in words])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# 导出TXT
@app.route('/export/txt', methods=['GET'])
def export_txt():
    try:
        include_examples = request.args.get('include_examples', 'true').lower() == 'true'
        include_tags = request.args.get('include_tags', 'true').lower() == 'true'
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
        
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('''
                SELECT w.*, array_agg(t.name) as tags 
                FROM words w 
                LEFT JOIN word_tags wt ON w.id = wt.word_id 
                LEFT JOIN tags t ON wt.tag_id = t.id 
                GROUP BY w.id 
                ORDER BY w.id
            ''')
            words = cur.fetchall()
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as temp_file:
                for word in words:
                    line = f"{word['english']} -> {word['portuguese']}"
                    if include_examples and word['example']:
                        line += f" | Example: {word['example']}"
                    if include_tags:
                        tags = [tag for tag in word['tags'] if tag is not None]
                        if tags:
                            line += f" | Tags: {', '.join(tags)}"
                    temp_file.write(line + "\n")
                temp_path = temp_file.name
                
        return send_file(temp_path, as_attachment=True, download_name='vocabulary.txt')
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# 导出PDF
@app.route('/export/pdf', methods=['GET'])
def export_pdf():
    try:
        include_examples = request.args.get('include_examples', 'true').lower() == 'true'
        include_tags = request.args.get('include_tags', 'true').lower() == 'true'
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
        
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('''
                SELECT w.*, array_agg(t.name) as tags 
                FROM words w 
                LEFT JOIN word_tags wt ON w.id = wt.word_id 
                LEFT JOIN tags t ON wt.tag_id = t.id 
                GROUP BY w.id 
                ORDER BY w.id
            ''')
            words = cur.fetchall()
            
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=11)
            
            # 设置列宽
            col_widths = []
            headers = ["No.", "English", "Portuguese"]
            if include_examples:
                headers.append("Example")
            if include_tags:
                headers.append("Tags")
                
            # 计算列宽
            page_width = pdf.w - 20
            if len(headers) == 3:
                col_widths = [20, (page_width-20)/2, (page_width-20)/2]
            elif len(headers) == 4:
                col_widths = [20, (page_width-20)/3, (page_width-20)/3, (page_width-20)/3]
            elif len(headers) == 5:
                col_widths = [20, (page_width-20)/4, (page_width-20)/4, (page_width-20)/4, (page_width-20)/4]
            
            # 添加表头
            pdf.set_fill_color(200, 200, 200)
            for i, header in enumerate(headers):
                pdf.cell(col_widths[i], 10, header, 1, 0, 'C', True)
            pdf.ln()
            
            # 添加数据
            for word in words:
                # 计算所需的最大行数
                lines = 1
                if include_examples:
                    example_lines = len(textwrap.wrap(word['example'], width=30))
                    lines = max(lines, example_lines)
                if include_tags:
                    tags = [tag for tag in word['tags'] if tag is not None]
                    tag_lines = len(textwrap.wrap(', '.join(tags), width=30))
                    lines = max(lines, tag_lines)
                
                height = 7 * lines
                
                # 写入数据
                pdf.cell(col_widths[0], height, str(word['id']), 1, 0, 'C')
                pdf.cell(col_widths[1], height, word['english'], 1, 0)
                pdf.cell(col_widths[2], height, word['portuguese'], 1, 0)
                
                if include_examples:
                    pdf.cell(col_widths[3], height, word['example'], 1, 0)
                if include_tags:
                    tags = [tag for tag in word['tags'] if tag is not None]
                    pdf.cell(col_widths[-1], height, ', '.join(tags), 1, 0)
                
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
                SELECT w.*, array_agg(t.name) as tags 
                FROM words w 
                LEFT JOIN word_tags wt ON w.id = wt.word_id 
                LEFT JOIN tags t ON wt.tag_id = t.id 
                WHERE LOWER(w.english) LIKE %s 
                OR LOWER(w.portuguese) LIKE %s
                GROUP BY w.id 
                ORDER BY w.id
            ''', (f'%{query}%', f'%{query}%'))
            
            words = cur.fetchall()
            return jsonify([{
                'id': word['id'],
                'english': word['english'],
                'portuguese': word['portuguese'],
                'example': word['example'],
                'tags': [tag for tag in word['tags'] if tag is not None]
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
            
            # Remove old tag associations
            cur.execute('DELETE FROM word_tags WHERE word_id = %s', (word_id,))
            
            # Add new tags
            if tags:
                for tag in tags:
                    # Insert or get tag
                    cur.execute(
                        '''INSERT INTO tags (name) VALUES (%s) 
                           ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name 
                           RETURNING id''',
                        (tag,)
                    )
                    tag_id = cur.fetchone()[0]
                    
                    # Link tag to word
                    cur.execute(
                        '''INSERT INTO word_tags (word_id, tag_id) 
                           VALUES (%s, %s) ON CONFLICT DO NOTHING''',
                        (word_id, tag_id)
                    )
            
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

# 获取单个单词
@app.route('/words/<int:id>', methods=['GET'])
def get_word(id):
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('''
                SELECT w.*, array_agg(t.name) as tags 
                FROM words w 
                LEFT JOIN word_tags wt ON w.id = wt.word_id 
                LEFT JOIN tags t ON wt.tag_id = t.id 
                WHERE w.id = %s
                GROUP BY w.id
            ''', (id,))
            
            word = cur.fetchone()
            if not word:
                return jsonify({"error": "Word not found"}), 404
                
            return jsonify({
                'id': word['id'],
                'english': word['english'],
                'portuguese': word['portuguese'],
                'example': word['example'],
                'tags': [tag for tag in word['tags'] if tag is not None],
                'created_at': word['created_at'],
                'updated_at': word['updated_at']
            })
    except Exception as e:
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
            # First delete tag associations
            cur.execute('DELETE FROM word_tags WHERE word_id = %s', (id,))
            
            # Then delete the word
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

# 获取所有标签
@app.route('/tags', methods=['GET'])
def get_tags():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('''
                SELECT t.*, COUNT(wt.word_id) as word_count 
                FROM tags t 
                LEFT JOIN word_tags wt ON t.id = wt.tag_id 
                GROUP BY t.id 
                ORDER BY t.name
            ''')
            tags = cur.fetchall()
            return jsonify([{
                'id': tag['id'],
                'name': tag['name'],
                'word_count': tag['word_count']
            } for tag in tags])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# ✅ 让 Flask 监听 0.0.0.0，确保 Render 可以访问
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
