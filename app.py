# 使用 Flask 创建 RESTful API
from flask import Flask, request, jsonify
from flask_cors import CORS
import json

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 词汇数据的文件路径
VOCAB_FILE = "vocabulary.json"

# 读取词汇数据
def load_vocabulary():
    try:
        with open(VOCAB_FILE, "r", encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

# 保存词汇数据
def save_vocabulary(vocabulary):
    with open(VOCAB_FILE, "w", encoding='utf-8') as file:
        json.dump(vocabulary, file, ensure_ascii=False, indent=4)

# API 路由
@app.route('/api/words', methods=['GET'])
def get_words():
    vocabulary = load_vocabulary()
    return jsonify(vocabulary)

@app.route('/api/words', methods=['POST'])
def add_word():
    data = request.json
    vocabulary = load_vocabulary()
    vocabulary[data['english']] = {
        'portuguese': data['portuguese'],
        'example': data['example']
    }
    save_vocabulary(vocabulary)
    return jsonify({"message": "Word added successfully"})

@app.route('/api/words/<english>', methods=['PUT'])
def update_word(english):
    data = request.json
    vocabulary = load_vocabulary()
    if english in vocabulary:
        vocabulary[english] = {
            'portuguese': data['portuguese'],
            'example': data['example']
        }
        save_vocabulary(vocabulary)
        return jsonify({"message": "Word updated successfully"})
    return jsonify({"error": "Word not found"}), 404

@app.route('/api/words/<english>', methods=['DELETE'])
def delete_word(english):
    vocabulary = load_vocabulary()
    if english in vocabulary:
        del vocabulary[english]
        save_vocabulary(vocabulary)
        return jsonify({"message": "Word deleted successfully"})
    return jsonify({"error": "Word not found"}), 404

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=10000)
