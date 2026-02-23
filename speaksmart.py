from flask import Flask, request, jsonify, render_template
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline

app = Flask(__name__)

# Grammar correction model
grammar_tokenizer = AutoTokenizer.from_pretrained("prithivida/grammar_error_correcter_v1")
grammar_model = AutoModelForSeq2SeqLM.from_pretrained("prithivida/grammar_error_correcter_v1")

# Emotion detection pipeline
emotion_detector = pipeline("text-classification", model="j-hartmann/emotion-english-distilroberta-base", return_all_scores=True)

def correct_sentence(sentence):
    input_text = "gec: " + sentence
    inputs = grammar_tokenizer.encode(input_text, return_tensors="pt", max_length=128, truncation=True)
    
    outputs = grammar_model.generate(
        inputs,
        max_length=128,
        num_beams=5,
        early_stopping=True
    )
    return grammar_tokenizer.decode(outputs[0], skip_special_tokens=True)

def detect_emotion(sentence):
    results = emotion_detector(sentence)[0]
    results.sort(key=lambda x: x['score'], reverse=True)
    top = results[0]
    return top['label'], round(top['score'], 3)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process_speech', methods=['POST'])
def process_speech():
    data = request.json
    text = data.get('text')

    corrected = correct_sentence(text)
    emotion, confidence = detect_emotion(corrected)

    return jsonify({
        "corrected": corrected,
        "emotion": emotion,
        "confidence": confidence
    })

if __name__ == '__main__':
    app.run(debug=True)
